"""Command-line interface for Qwen-DBA."""

import click
from rich.console import Console
from rich.table import Table
from pathlib import Path

from .common.config import get_config, reload_config
from .common.database import get_metrics_db
from .profiler.profiler import WorkloadProfiler
from .eval_harness.harness import EvalHarness
from .architect.factory import create_architect
from .review import ReviewError, ReviewQueue, check_sql

console = Console()


@click.group()
@click.option('--config', default=None, envvar='QWEN_DBA_CONFIG', help='Path to configuration file (default: $QWEN_DBA_CONFIG or config.yaml)')
@click.pass_context
def cli(ctx, config):
    """Qwen-DBA: AI-Powered Database Administrator using Qwen-MLX"""
    ctx.ensure_object(dict)
    ctx.obj['config_path'] = config

    try:
        # reload (not get): modules imported above may already have cached the
        # default config.yaml, which silently ignored --config.
        reload_config(config)
        from .common import database, logger as logger_module
        database.reset_connections()
        logger_module.setup_logger()
        console.print(f"[green]OK[/green] Configuration loaded from {config}")
    except Exception as e:
        console.print(f"[red]ERROR[/red] Loading configuration: {e}")
        ctx.exit(1)


@cli.command()
@click.pass_context
def init_db(ctx):
    """Initialize database schema."""
    config_path = ctx.obj['config_path']

    try:
        console.print("[cyan]Initializing database schema...[/cyan]")

        db = get_metrics_db()
        schema_file = Path(__file__).parent.parent.parent / 'sql' / '001_create_schema.sql'

        if not schema_file.exists():
            console.print(f"[red]ERROR[/red] Schema file not found: {schema_file}")
            return

        db.execute_script(str(schema_file))
        console.print("[green]OK[/green] Database schema initialized")

    except Exception as e:
        console.print(f"[red]ERROR[/red] Initializing database: {e}")
        raise


@cli.command()
@click.option('--save/--no-save', default=True, help='Save snapshots to database')
@click.pass_context
def profile(ctx, save):
    """Run workload profiler to collect and aggregate query logs."""
    try:
        console.print("[cyan]Starting workload profiler...[/cyan]")

        profiler = WorkloadProfiler()
        snapshots = profiler.create_snapshots()

        if snapshots:
            console.print(f"[green]OK[/green] Created {len(snapshots)} workload snapshots")
            table = Table(title="Top Workload Snapshots by Impact")
            table.add_column("Query Type", style="cyan")
            table.add_column("Executions", justify="right", style="magenta")
            table.add_column("P95 Latency", justify="right", style="yellow")
            table.add_column("Impact Score", justify="right", style="green")

            for snapshot in snapshots[:5]:
                table.add_row(
                    snapshot.query_type or "N/A",
                    f"{snapshot.execution_count:,}",
                    f"{snapshot.p95_latency_ms:.2f}ms",
                    f"{snapshot.impact_score:,.0f}"
                )

            console.print(table)

            if save:
                profiler.save_snapshots(snapshots)
                console.print("[green]OK[/green] Snapshots saved to database")
        else:
            console.print("[yellow]WARN[/yellow] No snapshots created")

    except Exception as e:
        console.print(f"[red]ERROR[/red] Running profiler: {e}")
        raise


@cli.command()
@click.pass_context
def eval(ctx):
    """Run evaluation harness to check metrics and SLOs."""
    try:
        console.print("[cyan]Starting evaluation harness...[/cyan]")

        harness = EvalHarness()
        results = harness.run_all()

        console.print(f"[green]OK[/green] Completed {len(results)} evaluations")
        table = Table(title="Evaluation Results")
        table.add_column("Type", style="cyan")
        table.add_column("Score", justify="right", style="magenta")
        table.add_column("P95 Latency", justify="right", style="yellow")
        table.add_column("SLO Status", style="green")

        for result in results:
            slo_status = "PASSED" if result.slo_passed else "FAILED" if result.slo_passed is False else "N/A"
            slo_color = "green" if result.slo_passed else "red" if result.slo_passed is False else "white"

            table.add_row(
                result.eval_type,
                f"{result.overall_score:.4f}" if result.overall_score else "N/A",
                f"{result.p95_latency_ms:.2f}ms" if result.p95_latency_ms else "N/A",
                f"[{slo_color}]{slo_status}[/{slo_color}]"
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]ERROR[/red] Running evaluations: {e}")
        raise


@cli.command()
@click.pass_context
def recommend(ctx):
    """Run Qwen-MLX Architect to generate optimization recommendations."""
    try:
        console.print("[cyan]Starting Qwen-MLX Architect...[/cyan]")

        architect = create_architect()
        recommendation = architect.run()

        if recommendation:
            console.print(f"[green]OK[/green] Generated recommendation: {recommendation.recommendation_id}")
            console.print("\n[bold]Recommendation Details:[/bold]")
            console.print(f"  [cyan]Type:[/cyan] {recommendation.recommendation_type.value}")
            console.print(f"  [cyan]Priority:[/cyan] {recommendation.priority}")
            console.print(f"  [cyan]Title:[/cyan] {recommendation.title}")
            console.print(f"  [cyan]Risk Level:[/cyan] {recommendation.risk_level.value}")

            if recommendation.expected_latency_improvement_percent:
                console.print(f"  [cyan]Expected Improvement:[/cyan] {recommendation.expected_latency_improvement_percent:.1f}%")

            console.print(f"\n[bold]Rationale:[/bold]\n{recommendation.rationale}")

            if recommendation.migration_sql:
                console.print(f"\n[bold]Migration SQL:[/bold]\n{recommendation.migration_sql}")
                if get_config().review.enqueue_recommendations:
                    try:
                        patch = recommendation.config_patch or {}
                        proposal = _review_queue().propose(
                            sql=recommendation.migration_sql,
                            title=recommendation.title,
                            confidence=recommendation.confidence_score,
                            current_sql=patch.get("current_sql") if isinstance(patch, dict) else None,
                            source="architect",
                            recommendation_id=recommendation.recommendation_id,
                        )
                        console.print(f"[green]OK[/green] Queued for review as {proposal.proposal_id} "
                                      f"(qwen-dba review show {proposal.proposal_id})")
                    except Exception as e:  # e.g. init-db not re-run after upgrading
                        console.print(f"[yellow]WARN[/yellow] Could not queue for review: {e}")

        else:
            console.print("[yellow]WARN[/yellow] No recommendation generated")

    except Exception as e:
        console.print(f"[red]ERROR[/red] Running Architect: {e}")
        raise


@cli.command()
@click.option('--limit', default=10, help='Number of recommendations to show')
@click.pass_context
def list_recommendations(ctx, limit):
    """List recent recommendations."""
    try:
        db = get_metrics_db()

        sql = """
            SELECT
                recommendation_id,
                recommendation_timestamp,
                status,
                priority,
                recommendation_type,
                title,
                expected_latency_improvement_percent,
                risk_level
            FROM qwen_dba.recommendations
            ORDER BY recommendation_timestamp DESC
            LIMIT :limit
        """

        rows = db.execute_raw(sql, {'limit': limit})

        if not rows:
            console.print("[yellow]No recommendations found[/yellow]")
            return

        table = Table(title=f"Recent Recommendations (showing {len(rows)})")
        table.add_column("ID", style="cyan")
        table.add_column("Timestamp", style="white")
        table.add_column("Status", style="magenta")
        table.add_column("Type", style="yellow")
        table.add_column("Title", style="green")
        table.add_column("Improvement", justify="right", style="blue")

        for row in rows:
            table.add_row(
                row[0][:16],  # Truncate ID
                str(row[1]),
                row[2],
                row[4],
                row[5][:50],  # Truncate title
                f"{row[6]:.1f}%" if row[6] else "N/A"
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]ERROR[/red] Listing recommendations: {e}")
        raise


@cli.command()
@click.pass_context
def run_all(ctx):
    """Run complete workflow: profile -> eval -> recommend."""
    try:
        console.print("[bold cyan]Running complete Qwen-DBA workflow[/bold cyan]\n")

        console.print("[cyan]Step 1/3: Profiling workload...[/cyan]")
        ctx.invoke(profile, save=True)
        console.print()

        console.print("[cyan]Step 2/3: Running evaluations...[/cyan]")
        ctx.invoke(eval)
        console.print()

        console.print("[cyan]Step 3/3: Generating recommendations...[/cyan]")
        ctx.invoke(recommend)
        console.print()

        console.print("[bold green]OK - Workflow completed[/bold green]")

    except Exception as e:
        console.print(f"[red]ERROR[/red] Workflow failed: {e}")
        raise


@cli.command()
@click.pass_context
def status(ctx):
    """Show current system status."""
    try:
        db = get_metrics_db()

        console.print("[bold]Qwen-DBA System Status[/bold]\n")

        # Get workload snapshot count
        result = db.execute_raw("SELECT COUNT(*) FROM qwen_dba.workload_snapshots")
        snapshot_count = result[0][0] if result else 0
        console.print(f"  [cyan]Workload Snapshots:[/cyan] {snapshot_count:,}")

        # Get eval result count
        result = db.execute_raw("SELECT COUNT(*) FROM qwen_dba.eval_results")
        eval_count = result[0][0] if result else 0
        console.print(f"  [cyan]Evaluation Results:[/cyan] {eval_count:,}")

        # Get recommendation count
        result = db.execute_raw("SELECT COUNT(*) FROM qwen_dba.recommendations")
        rec_count = result[0][0] if result else 0
        console.print(f"  [cyan]Recommendations:[/cyan] {rec_count:,}")

        # Get pending recommendations
        result = db.execute_raw("SELECT COUNT(*) FROM qwen_dba.recommendations WHERE status = 'pending'")
        pending_count = result[0][0] if result else 0
        console.print(f"  [cyan]Pending Recommendations:[/cyan] {pending_count:,}")

    except Exception as e:
        console.print(f"[red]ERROR[/red] Getting status: {e}")
        raise


# ---------------------------------------------------------------------------
# Human review queue (#5, #6)
# ---------------------------------------------------------------------------

def _review_queue() -> ReviewQueue:
    from .common.database import Database, get_primary_db

    config = get_config()

    def target(name):
        if name == "primary":
            return get_primary_db()
        if name == "metrics":
            return get_metrics_db()
        return Database(config.databases[name].get_connection_string())

    return ReviewQueue(get_metrics_db(), target_db_factory=target, review_mode=config.review.mode)


def _print_proposal(p, show_diff: bool = True):
    color = {"pending": "yellow", "approved": "cyan", "applied": "green", "rejected": "red", "failed": "red"}
    console.print(f"[bold]{p.proposal_id}[/bold]  [{color.get(p.status, 'white')}]{p.status}[/]  {p.title}")
    console.print(f"  source={p.source}  target={p.target_db}  confidence="
                  f"{'n/a' if p.confidence is None else f'{p.confidence:.2f}'}  created={p.created_at}")
    if not p.parse_ok:
        console.print(f"  [red]PARSE FAILED[/red]: {p.parse_error}  (apply is blocked)")
    if p.destructive:
        console.print(f"  [bold red]DESTRUCTIVE[/bold red]: {', '.join(p.destructive)}")
    if p.reviewed_by:
        console.print(f"  reviewed by {p.reviewed_by} at {p.reviewed_at}" + (f": {p.reason}" if p.reason else ""))
    if p.applied_at:
        console.print(f"  {p.status} by {p.applied_by} at {p.applied_at}" + (f": {p.apply_error}" if p.apply_error else ""))
    if show_diff:
        console.print("\n[bold]Diff (current -> proposed):[/bold]")
        for line in p.diff.splitlines():
            style = "green" if line.startswith("+") and not line.startswith("+++") else \
                    "red" if line.startswith("-") and not line.startswith("---") else \
                    "cyan" if line.startswith("@@") else None
            console.print(line, style=style, markup=False, highlight=False)


@cli.group()
def review():
    """Review proposed SQL writes before they are applied (REVIEW_MODE)."""


@review.command("propose")
@click.option("--sql", "sql_text", default=None, help="Proposed SQL")
@click.option("--file", "sql_file", type=click.Path(exists=True, dir_okay=False), default=None, help="Read proposed SQL from a file")
@click.option("--current-file", type=click.Path(exists=True, dir_okay=False), default=None, help="Current definition/statement to diff against")
@click.option("--title", required=True)
@click.option("--confidence", type=float, default=None)
@click.option("--target", default="primary", help="databases entry the SQL will run on")
@click.option("--by", "actor", default=None, help="Who is proposing")
def review_propose(sql_text, sql_file, current_file, title, confidence, target, actor):
    """Queue a proposed write (it is never applied by this command)."""
    if bool(sql_text) == bool(sql_file):
        raise click.UsageError("give exactly one of --sql or --file")
    sql = sql_text or Path(sql_file).read_text()
    current = Path(current_file).read_text() if current_file else None
    p = _review_queue().propose(sql, title, confidence=confidence, current_sql=current,
                                target_db=target, actor=actor)
    _print_proposal(p)


@review.command("list")
@click.option("--status", type=click.Choice(["pending", "approved", "rejected", "applied", "failed"]), default=None)
@click.option("--limit", default=20)
def review_list(status, limit):
    """List proposals, newest first."""
    q = _review_queue()
    table = Table(title=f"Proposed writes (review mode {'ON' if q.review_mode else 'OFF'})")
    for col in ("ID", "Status", "Title", "Conf.", "Flags", "Created"):
        table.add_column(col)
    for p in q.list(status=status, limit=limit):
        flags = ", ".join(([] if p.parse_ok else ["PARSE FAILED"]) + p.destructive)
        table.add_row(p.proposal_id, p.status, p.title[:60],
                      "" if p.confidence is None else f"{p.confidence:.2f}", flags, str(p.created_at)[:19])
    console.print(table)


@review.command("show")
@click.argument("proposal_id")
def review_show(proposal_id):
    """Show a proposal with its unified diff, parse status and destructive flags."""
    _print_proposal(_review_queue().get(proposal_id))


def _run_review(action):
    try:
        return action()
    except ReviewError as e:
        console.print(f"[red]REFUSED[/red] {e}")
        raise SystemExit(2)


@review.command("approve")
@click.argument("proposal_id")
@click.option("--by", "actor", required=True, help="Reviewer name")
@click.option("--reason", default=None)
def review_approve(proposal_id, actor, reason):
    """Approve a pending proposal (does not apply it)."""
    p = _run_review(lambda: _review_queue().approve(proposal_id, actor, reason))
    _print_proposal(p, show_diff=False)


@review.command("reject")
@click.argument("proposal_id")
@click.option("--by", "actor", required=True, help="Reviewer name")
@click.option("--reason", required=True, help="Why (kept on the row)")
def review_reject(proposal_id, actor, reason):
    """Reject a proposal; it stays in the queue with the reason."""
    p = _run_review(lambda: _review_queue().reject(proposal_id, actor, reason))
    _print_proposal(p, show_diff=False)


@review.command("apply")
@click.argument("proposal_id")
@click.option("--by", "actor", required=True, help="Who is applying")
@click.option("--confirm", "confirmed", is_flag=True, help="Skip the interactive prompt (scripts)")
def review_apply(proposal_id, actor, confirmed):
    """Apply an approved proposal after showing its diff and asking for confirmation."""
    q = _review_queue()
    p = _run_review(lambda: q.get(proposal_id))
    _print_proposal(p)
    if not confirmed:
        prompt = "Apply this SQL to '%s'%s?" % (p.target_db, " (DESTRUCTIVE)" if p.destructive else "")
        confirmed = click.confirm(prompt, default=False)
    p = _run_review(lambda: q.apply(proposal_id, actor, confirm=confirmed))
    console.print(f"[green]OK[/green] {p.proposal_id} applied to {p.target_db}")


@review.command("audit")
@click.argument("proposal_id", required=False)
@click.option("--limit", default=50)
def review_audit(proposal_id, limit):
    """Show the review audit log (all actions, including blocked applies)."""
    table = Table(title="Review audit log")
    for col in ("When", "Proposal", "Action", "Actor", "Reason"):
        table.add_column(col)
    for e in _review_queue().audit_log(proposal_id, limit):
        table.add_row(str(e["ts"])[:19], e["proposal_id"], e["action"], e["actor"] or "", e["reason"] or "")
    console.print(table)


def main():
    """Main entry point."""
    cli(obj={})


if __name__ == '__main__':
    main()
