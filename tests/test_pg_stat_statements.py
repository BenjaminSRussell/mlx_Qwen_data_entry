"""pg_stat_statements source (#3): mapping, fingerprint alignment, deltas (mocked rows)."""
from datetime import datetime, timedelta

import pytest

from qwen_dba.profiler.fingerprint import QueryFingerprinter
from qwen_dba.profiler.parsers import get_parser
from qwen_dba.profiler.pg_stat_statements import (
    PgStatStatementsSource,
    PgStatStatementsUnavailable,
    StatementRow,
    Z_P95,
    delta_rows,
    rows_to_snapshots,
)

FP = QueryFingerprinter()
T0 = datetime(2026, 10, 7, 12, 0, 0)


def row(query, calls, total, sd=0.0, mx=None, queryid=None, **kw):
    mean = total / calls if calls else 0.0
    return StatementRow(query=query, calls=calls, total_exec_time_ms=total, mean_exec_time_ms=mean,
                        stddev_exec_time_ms=sd, min_exec_time_ms=kw.pop("mn", mean),
                        max_exec_time_ms=mx if mx is not None else mean, queryid=queryid, dbid=1, userid=10, **kw)


def test_fingerprints_align_with_log_path(sample_log_file):
    """The same statements seen in a log file and in pg_stat_statements share fingerprints."""
    log_fps = {FP.fingerprint(q.query) for q in get_parser("postgres_logs", "standard").parse_file(str(sample_log_file))}
    pgss_texts = [
        "SELECT * FROM users WHERE email = $1",
        "SELECT id, name FROM products WHERE category = $1",
        "SELECT * FROM orders WHERE user_id = $1 AND status = $2",
        "INSERT INTO logs (timestamp, message) VALUES ($1, $2)",
        "UPDATE users SET last_login = NOW() WHERE id = $1",
    ]
    assert {FP.fingerprint(q) for q in pgss_texts} == log_fps
    # IN-lists: expanded params and PG 18 list squashing collapse like literal lists
    lit = FP.fingerprint("SELECT * FROM t WHERE id IN (1, 2, 3)")
    assert FP.fingerprint("select * from t where id in ($1, $2, $3)") == lit
    assert FP.fingerprint("SELECT * FROM t WHERE id IN ($1 /*, ... */)") == lit


def test_rows_map_to_workload_snapshots():
    rows = [
        row("SELECT * FROM users WHERE email = $1", 100, 2_000.0, sd=5.0, mx=40.0, queryid=1,
            rows=100, shared_blks_hit=900, shared_blks_read=100),
        row("UPDATE users SET last_login = NOW() WHERE id = $1", 3, 30.0, queryid=2),
    ]
    snaps = rows_to_snapshots(rows, FP, T0, T0 - timedelta(hours=1), T0, min_calls=5)
    assert len(snaps) == 1  # UPDATE below min_calls
    s = snaps[0]
    assert s.query_fingerprint == FP.fingerprint("SELECT * FROM users WHERE email = 'a@b.c'")
    assert (s.query_type, s.query_source, s.execution_count) == ("SELECT", "postgres", 100)
    assert s.avg_execution_time_ms == pytest.approx(20.0)
    assert s.p95_latency_ms == pytest.approx(20.0 + Z_P95 * 5.0)
    assert s.p99_latency_ms <= s.max_latency_ms == 40.0  # estimate capped at max
    assert (s.avg_rows_returned, s.avg_buffer_hits, s.avg_buffer_misses) == (1.0, 9.0, 1.0)
    assert s.impact_score == pytest.approx(2_000.0)


def test_rows_with_same_fingerprint_are_merged_with_pooled_stats():
    a = row("SELECT * FROM t WHERE id = $1", 10, 100.0, sd=0.0, mx=10.0, queryid=1)        # mean 10
    b = row("select *  from t where id = $1", 30, 900.0, sd=0.0, mx=30.0, queryid=2, mn=30.0)  # mean 30, other user/text
    (s,) = rows_to_snapshots([a, b], FP, T0, T0, T0)
    assert s.execution_count == 40 and s.total_execution_time_ms == 1000.0
    assert s.avg_execution_time_ms == pytest.approx(25.0)
    # pooled sd of {10 x10, 30 x30} = sqrt(E[x^2] - mean^2) = sqrt(700 - 625)
    assert s.p95_latency_ms == pytest.approx(min(25.0 + Z_P95 * 75 ** 0.5, 30.0))
    assert (s.min_latency_ms, s.max_latency_ms) == (10.0, 30.0)


def test_deltas_between_captures_and_counter_reset():
    prev = {r.key: r for r in [row("SELECT 1", 10, 100.0, sd=0.0, queryid=1),
                               row("SELECT 2", 5, 50.0, queryid=2),
                               row("SELECT 3", 7, 70.0, queryid=3)]}
    cur = [
        row("SELECT 1", 30, 500.0, sd=0.0, queryid=1),  # +20 calls, +400 ms
        row("SELECT 2", 2, 40.0, queryid=2),            # counters went down -> reset, take as-is
        row("SELECT 3", 7, 70.0, queryid=3),            # no new calls -> dropped
        row("SELECT 4", 4, 8.0, queryid=4),             # new statement
    ]
    d = {r.queryid: r for r in delta_rows(cur, prev)}
    assert set(d) == {1, 2, 4}
    assert (d[1].calls, d[1].total_exec_time_ms, d[1].mean_exec_time_ms) == (20, 400.0, 20.0)
    assert d[2].calls == 2 and d[4].calls == 4
    assert delta_rows(cur, None) == cur  # first capture: cumulative


def test_delta_variance_of_new_calls_only():
    prev = row("q", 2, 20.0, sd=0.0, queryid=9)                 # {10, 10}
    cur = StatementRow(query="q", calls=4, total_exec_time_ms=80.0, mean_exec_time_ms=20.0,
                       stddev_exec_time_ms=10.0, queryid=9, dbid=1, userid=10)  # {10,10,30,30}
    (d,) = delta_rows([cur], {prev.key: prev})
    assert (d.calls, d.mean_exec_time_ms) == (2, 30.0)
    assert d.stddev_exec_time_ms == pytest.approx(0.0, abs=1e-9)  # new calls were {30, 30}


class FakeResult(list):
    pass


class FakeRow:
    def __init__(self, **m):
        self._mapping = m

    def __getitem__(self, i):
        return list(self._mapping.values())[i]


class FakeDB:
    def __init__(self, columns, rows=(), fail=None):
        self.columns, self.rows, self.fail, self.sql = columns, list(rows), fail, []

    def execute_raw(self, sql, params=None):
        self.sql.append(sql)
        if "information_schema.columns" in sql:
            return [(c,) for c in self.columns]
        if self.fail:
            raise self.fail
        if "pg_stat_statements_reset" in sql:
            return []
        return self.rows


def test_source_uses_pg13_or_legacy_column_names_and_maps_rows():
    r = FakeRow(queryid=7, dbid=1, userid=10, query="SELECT $1", calls=3, total_exec_time_ms=9.0,
                mean_exec_time_ms=3.0, stddev_exec_time_ms=0.5, min_exec_time_ms=2.0, max_exec_time_ms=4.0,
                rows=3, shared_blks_hit=6, shared_blks_read=0)
    new = FakeDB(["total_exec_time"], [r])
    (got,) = PgStatStatementsSource(new).fetch()
    assert (got.queryid, got.calls, got.mean_exec_time_ms) == (7, 3, 3.0)
    assert "s.total_exec_time  AS" in new.sql[-1]
    old = FakeDB(["total_time"], [r])
    PgStatStatementsSource(old).fetch()
    assert "s.total_time  AS" in old.sql[-1]


def test_missing_extension_raises_actionable_error():
    with pytest.raises(PgStatStatementsUnavailable, match="shared_preload_libraries"):
        PgStatStatementsSource(FakeDB([])).fetch()
    with pytest.raises(PgStatStatementsUnavailable, match="must be loaded"):
        PgStatStatementsSource(FakeDB(["total_exec_time"], fail=RuntimeError("must be loaded via shared_preload_libraries"))).fetch()


def test_config_flag_selects_source(tmp_path, monkeypatch):
    import yaml
    from pathlib import Path
    from qwen_dba.common import config as config_mod
    from qwen_dba.profiler import profiler as profiler_mod

    cfg = yaml.safe_load((Path(__file__).resolve().parent.parent / "config.yaml").read_text())
    assert cfg["profiler"]["source"] == "logs"  # log parser stays the default
    cfg["profiler"]["source"] = "pg_stat_statements"
    path = tmp_path / "c.yaml"
    path.write_text(yaml.safe_dump(cfg))
    config_mod.reload_config(str(path))
    monkeypatch.setattr(profiler_mod, "get_metrics_db", lambda: None)
    try:
        p = profiler_mod.WorkloadProfiler()
        assert p.source == "pg_stat_statements" and p.pgss_settings["retention_days"] == 30
        called = {}
        monkeypatch.setattr(p, "_snapshots_from_pg_stat_statements", lambda: called.setdefault("pgss", []))
        monkeypatch.setattr(p, "collect_logs", lambda: called.setdefault("logs", []))
        p.create_snapshots()
        assert "pgss" in called and "logs" not in called
        assert profiler_mod.WorkloadProfiler(source="logs").source == "logs"
        with pytest.raises(ValueError):
            profiler_mod.WorkloadProfiler(source="nope")
    finally:
        config_mod._config = None
