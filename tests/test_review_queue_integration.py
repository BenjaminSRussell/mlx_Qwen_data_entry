"""Review queue against a real Postgres (#5, #6): approval gate, rejects, confirm, audit."""
import pytest

from tests.test_postgres_integration import DB_URL, ci_config, run_cli  # noqa: F401  (fixture)

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not DB_URL, reason="QWEN_DBA_TEST_DATABASE_URL not set"),
]


@pytest.fixture
def queue(ci_config, monkeypatch):  # noqa: F811
    monkeypatch.delenv("REVIEW_MODE", raising=False)
    run_cli(ci_config, "init-db")
    from qwen_dba.common.database import get_metrics_db
    from qwen_dba.review import ReviewQueue

    db = get_metrics_db()
    db.execute_raw("TRUNCATE qwen_dba.proposed_writes, qwen_dba.review_audit RESTART IDENTITY")
    db.execute_raw("DROP TABLE IF EXISTS public.review_target")
    db.execute_raw("CREATE TABLE public.review_target (id int primary key, v text)")
    yield ReviewQueue(db, target_db_factory=lambda name: db, review_mode=True), db
    db.execute_raw("DROP TABLE IF EXISTS public.review_target")


def rows(db):
    return db.execute_raw("SELECT id, v FROM public.review_target ORDER BY id")


def actions(q, pid):
    return [e["action"] for e in reversed(q.audit_log(pid))]


def test_never_applies_without_approval_in_review_mode(queue):
    from qwen_dba.review import ReviewError

    q, db = queue
    p = q.propose("INSERT INTO public.review_target VALUES (1, 'a')", "seed row", confidence=0.9)
    assert p.status == "pending" and p.parse_ok
    with pytest.raises(ReviewError, match="not approved"):
        q.apply(p.proposal_id, "ben", confirm=True)
    assert rows(db) == []  # nothing written
    q.approve(p.proposal_id, "ben")
    with pytest.raises(ReviewError, match="explicit confirmation"):
        q.apply(p.proposal_id, "ben", confirm=False)
    assert rows(db) == []
    applied = q.apply(p.proposal_id, "ben", confirm=True)
    assert applied.status == "applied" and applied.applied_by == "ben"
    assert [tuple(r) for r in rows(db)] == [(1, "a")]
    assert actions(q, p.proposal_id) == ["propose", "apply_blocked", "approve", "apply_blocked", "apply"]
    with pytest.raises(ReviewError):  # can't re-apply
        q.apply(p.proposal_id, "ben", confirm=True)


def test_reject_needs_and_keeps_reason(queue):
    from qwen_dba.review import ReviewError

    q, db = queue
    p = q.propose("DELETE FROM public.review_target", "wipe table")
    assert p.destructive == ["DELETE without WHERE (deletes every row)"]
    with pytest.raises(ReviewError, match="reason"):
        q.reject(p.proposal_id, "ben", "  ")
    r = q.reject(p.proposal_id, "ben", "no WHERE clause")
    assert (r.status, r.reason, r.reviewed_by) == ("rejected", "no WHERE clause", "ben")
    assert q.list(status="rejected")[0].proposal_id == p.proposal_id  # row stays, with reason
    with pytest.raises(ReviewError):
        q.approve(p.proposal_id, "ben")
    with pytest.raises(ReviewError):
        q.apply(p.proposal_id, "ben", confirm=True)
    audit = q.audit_log(p.proposal_id)
    assert audit[1]["action"] == "reject" and audit[1]["reason"] == "no WHERE clause"


def test_parse_failure_blocks_approve_and_apply_even_without_review_mode(queue):
    from qwen_dba.review import ReviewError, ReviewQueue

    q, db = queue
    p = q.propose("INSRT INTO public.review_target VALUES (2, 'b')", "typo")
    assert not p.parse_ok and "syntax error" in p.parse_error
    with pytest.raises(ReviewError, match="does not parse"):
        q.approve(p.proposal_id, "ben")
    loose = ReviewQueue(db, target_db_factory=lambda n: db, review_mode=False)
    with pytest.raises(ReviewError, match="does not parse"):
        loose.apply(p.proposal_id, "ben", confirm=True)
    assert rows(db) == []


def test_failed_apply_is_rolled_back_and_audited(queue):
    from qwen_dba.review import ReviewError

    q, db = queue
    p = q.propose("INSERT INTO public.review_target VALUES (5, 'x'); INSERT INTO public.review_target VALUES (5, 'dup')",
                  "duplicate key")
    q.approve(p.proposal_id, "ben")
    with pytest.raises(ReviewError, match="rolled back"):
        q.apply(p.proposal_id, "ben", confirm=True)
    assert rows(db) == []  # first insert rolled back too
    f = q.get(p.proposal_id)
    assert f.status == "failed" and "duplicate key" in f.apply_error
    assert actions(q, p.proposal_id)[-1] == "apply_failed"


def test_review_mode_off_still_needs_confirm(queue, monkeypatch):
    from qwen_dba.review import ReviewQueue

    q, db = queue
    monkeypatch.setenv("REVIEW_MODE", "0")
    loose = ReviewQueue(db, target_db_factory=lambda n: db, review_mode=True)  # env wins
    assert loose.review_mode is False
    p = loose.propose("INSERT INTO public.review_target VALUES (3, 'c')", "direct")
    assert loose.apply(p.proposal_id, "ben", confirm=True).status == "applied"


def test_cli_flow_with_diff_and_recommend_enqueue(ci_config, queue, tmp_path):  # noqa: F811
    from pathlib import Path

    q, db = queue
    db.execute_raw("CREATE TABLE IF NOT EXISTS public.orders "
                   "(id int, total numeric, created_at timestamp, user_id int, status text)")
    examples = Path(__file__).resolve().parent.parent / "examples" / "review"
    out = run_cli(ci_config, "review", "propose", "--file", str(examples / "proposed_query.sql"),
                  "--current-file", str(examples / "current_query.sql"), "--title", "narrow orders query",
                  "--confidence", "0.8", "--by", "architect")
    assert "-SELECT *" in out and "+LIMIT 50" in out  # diff shown for the fixture proposal
    pid = q.list()[0].proposal_id
    assert "pending" in run_cli(ci_config, "review", "list")
    run_cli(ci_config, "review", "approve", pid, "--by", "ben")
    from click.testing import CliRunner
    from qwen_dba.cli import cli

    # without --confirm the CLI asks; answering "n" applies nothing
    res = CliRunner().invoke(cli, ["--config", ci_config, "review", "apply", pid, "--by", "ben"], input="n\n", obj={})
    assert res.exit_code == 2 and "explicit confirmation" in res.output
    res = CliRunner().invoke(cli, ["--config", ci_config, "review", "apply", pid, "--by", "ben"], input="y\n", obj={})
    assert res.exit_code == 0 and "applied" in res.output, res.output
    audit = run_cli(ci_config, "review", "audit", pid)
    assert "apply_blocked" in audit and "approve" in audit

    # recommend queues the architect's migration_sql for review
    db.execute_raw("TRUNCATE qwen_dba.workload_snapshots, qwen_dba.recommendations RESTART IDENTITY")
    run_cli(ci_config, "profile")
    out = run_cli(ci_config, "recommend")
    assert "Queued for review as pw-" in out
    latest = q.list()[0]
    assert latest.source == "architect" and latest.recommendation_id and latest.status == "pending"
    db.execute_raw("DROP TABLE IF EXISTS public.orders")
