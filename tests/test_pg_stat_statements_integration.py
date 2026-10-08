"""pg_stat_statements source + stat_snapshots history against a real Postgres (#3, #7).

History tests need only QWEN_DBA_TEST_DATABASE_URL. The live-extension test also
needs pg_stat_statements in shared_preload_libraries; it is skipped otherwise,
unless QWEN_DBA_REQUIRE_PGSS=1 (CI's pg-stat-statements job), where it must run.
"""
import csv
import os
from datetime import datetime, timedelta

import pytest

from tests.test_postgres_integration import DB_URL, ci_config, run_cli  # noqa: F401  (fixture)

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not DB_URL, reason="QWEN_DBA_TEST_DATABASE_URL not set"),
]


@pytest.fixture
def history(ci_config):  # noqa: F811
    run_cli(ci_config, "init-db")
    from qwen_dba.common.database import get_metrics_db
    from qwen_dba.profiler.pg_stat_statements import StatSnapshotStore

    db = get_metrics_db()
    db.execute_raw("TRUNCATE qwen_dba.stat_snapshots, qwen_dba.workload_snapshots RESTART IDENTITY")
    return ci_config, StatSnapshotStore(db)


def _rows(calls):
    from qwen_dba.profiler.pg_stat_statements import StatementRow

    return [
        StatementRow(query="SELECT * FROM users WHERE id = $1", calls=calls, total_exec_time_ms=calls * 2.0,
                     mean_exec_time_ms=2.0, queryid=11, dbid=1, userid=10),
        StatementRow(query="UPDATE users SET x = $1 WHERE id = $2", calls=calls // 2, total_exec_time_ms=calls * 5.0,
                     mean_exec_time_ms=10.0, queryid=12, dbid=1, userid=10),
    ]


def test_two_snapshots_coexist_and_feed_deltas(history):
    _, store = history
    t1, t2 = datetime(2026, 10, 1, 12), datetime(2026, 10, 1, 13)
    assert store.save(_rows(10), t1) == 2
    assert store.save(_rows(30), t2) == 2
    caps = store.captures()
    assert [c[0] for c in caps] == [t2, t1] and caps[0][1] == 2
    assert store.latest_capture(before=t2) == t1
    from qwen_dba.profiler.pg_stat_statements import delta_rows

    prev = store.load_capture(t1)
    d = {r.queryid: r for r in delta_rows(_rows(30), prev)}
    assert d[11].calls == 20 and d[12].calls == 10


def test_retention_prunes_old_captures_and_csv_export(history, tmp_path):
    ci_config, store = history
    now = datetime(2026, 10, 7, 12)
    store.save(_rows(10), now - timedelta(days=45))
    store.save(_rows(20), now - timedelta(days=10))
    store.save(_rows(30), now)
    assert store.prune(retention_days=30, now=now) == 2
    assert [c[0] for c in store.captures()] == [now, now - timedelta(days=10)]

    out = tmp_path / "stats.csv"
    assert store.export_csv(out, since=now - timedelta(days=1)) == 2
    with open(out) as f:
        rows = list(csv.DictReader(f))
    assert {r["queryid"] for r in rows} == {"11", "12"}
    assert rows[0]["query_fingerprint"].startswith("SELECT * FROM USERS WHERE ID = ?")

    # CLI wrappers
    out2 = tmp_path / "all.csv"
    assert "Wrote 4 rows" in run_cli(ci_config, "stats", "export", "--csv", str(out2))
    # remaining captures are all in the past relative to the wall clock
    assert "Pruned 4 rows" in run_cli(ci_config, "stats", "prune", "--days", "0.0001")
    assert store.captures() == []


def _pgss_usable():
    from qwen_dba.common.database import Database

    db = Database(DB_URL)
    try:
        db.execute_raw("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
        db.execute_raw("SELECT 1 FROM pg_stat_statements LIMIT 1")
        return db, None
    except Exception as exc:  # not preloaded / not installed
        return None, str(exc).splitlines()[0]


@pytest.mark.pgss
def test_profile_from_live_pg_stat_statements(history):
    ci_config, store = history
    db, why = _pgss_usable()
    if db is None:
        if os.environ.get("QWEN_DBA_REQUIRE_PGSS") == "1":
            pytest.fail(f"pg_stat_statements required but unavailable: {why}")
        pytest.skip(f"pg_stat_statements unavailable: {why}")

    db.execute_raw("CREATE TABLE IF NOT EXISTS public.pgss_probe (id int primary key, email text)")
    db.execute_raw("TRUNCATE public.pgss_probe")
    db.execute_raw("INSERT INTO public.pgss_probe SELECT g, 'u' || g || '@x' FROM generate_series(1, 50) g")

    def workload(n):
        for i in range(n):
            db.execute_raw("SELECT * FROM public.pgss_probe WHERE email = :e", {"e": f"u{i}@x"})

    workload(12)
    out = run_cli(ci_config, "profile", "--source", "pg_stat_statements")
    assert "Snapshots saved to database" in out
    workload(8)
    run_cli(ci_config, "profile", "--source", "pg_stat_statements")

    from qwen_dba.profiler.fingerprint import QueryFingerprinter

    fp = QueryFingerprinter().fingerprint("SELECT * FROM public.pgss_probe WHERE email = 'u1@x'")
    counts = [r[0] for r in db.execute_raw(
        "SELECT execution_count FROM qwen_dba.workload_snapshots WHERE query_fingerprint = :fp "
        "ORDER BY snapshot_timestamp", {"fp": fp})]
    assert len(counts) == 2, counts
    assert counts[0] >= 12 and counts[1] == 8  # second run is the delta since the first capture
    assert len(store.captures()) == 2  # both captures kept in history
