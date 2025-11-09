"""Command-line interface for Qwen-DBA."""

import click
from rich.console import Console
from rich.table import Table
from pathlib import Path

from .common.config import get_config, reload_config
from .common.database import get_metrics_db
from .profiler.profiler import WorkloadProfiler
from .eval_harness.harness import EvalHarness
from .architect.architect import QwenArchitect

console = Console()


@click.group()
@click.option('--config', default='config.yaml', help='Path to configuration file')
@click.pass_context
def cli(ctx, config):
    """Qwen-DBA: AI-Powered Database Administrator using Qwen-MLX"""
    ctx.ensure_object(dict)
    ctx.obj['config_path'] = config

    try:
        get_config(config)
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

        architect = QwenArchitect()
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


def main():
    """Main entry point."""
    cli(obj={})


if __name__ == '__main__':
    main()
