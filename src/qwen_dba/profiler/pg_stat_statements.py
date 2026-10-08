"""Live workload metrics from ``pg_stat_statements`` (#3) and their history (#7).

The log parser stays the default for offline use. Set ``profiler.source:
pg_stat_statements`` (or ``qwen-dba profile --source pg_stat_statements``) to read
the extension instead:

* :class:`PgStatStatementsSource` reads the view (PG 13+ column names, with a
  fallback for 9.4-12) and can reset it behind ``reset_after_read``.
* :func:`rows_to_snapshots` maps rows onto the same :class:`WorkloadSnapshot`
  model and the same :class:`QueryFingerprinter` as the log path. Both
  ``$1`` placeholders and literals normalize to ``?``, so fingerprints line up.
* :class:`StatSnapshotStore` keeps every capture in ``qwen_dba.stat_snapshots``.
  Consecutive captures turn the cumulative counters into per-window deltas. The
  store also handles retention pruning and CSV export for notebooks (#7).

``pg_stat_statements`` has no percentiles. p95/p99 are estimated as
``mean + z * stddev`` (z = 1.645 / 2.326), capped at ``max_exec_time``, and p50
uses the mean. They are labelled as estimates in the docs.
"""
from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

from ..common.models import QuerySource, WorkloadSnapshot
from .fingerprint import QueryFingerprinter

Z_P95 = 1.645
Z_P99 = 2.326

SETUP_HINT = (
    "pg_stat_statements is not available. Add it to shared_preload_libraries "
    "(e.g. `postgres -c shared_preload_libraries=pg_stat_statements`, then restart), "
    "run `CREATE EXTENSION pg_stat_statements;` in the target database, and give the "
    "profiler role `pg_read_all_stats` to see every user's statements. See README "
    "'Live metrics from pg_stat_statements'."
)


class PgStatStatementsUnavailable(RuntimeError):
    """The extension is not installed/loaded or not readable by this role."""


@dataclass
class StatementRow:
    """One ``pg_stat_statements`` row (cumulative since the last reset)."""

    query: str
    calls: int
    total_exec_time_ms: float
    mean_exec_time_ms: float = 0.0
    stddev_exec_time_ms: float = 0.0
    min_exec_time_ms: float = 0.0
    max_exec_time_ms: float = 0.0
    rows: int = 0
    shared_blks_hit: int = 0
    shared_blks_read: int = 0
    queryid: Optional[int] = None
    dbid: Optional[int] = None
    userid: Optional[int] = None

    @property
    def key(self) -> Tuple:
        """Identity across captures: (queryid, dbid, userid), or the query text if no queryid."""
        if self.queryid is not None:
            return (self.queryid, self.dbid, self.userid)
        return ("q", self.query, self.dbid, self.userid)

    @classmethod
    def from_mapping(cls, m) -> "StatementRow":
        names = {f.name for f in fields(cls)}
        data = {k: m[k] for k in m.keys() if k in names} if hasattr(m, "keys") else dict(m)
        for k in ("calls", "rows", "shared_blks_hit", "shared_blks_read"):
            data[k] = int(data.get(k) or 0)
        for k in ("total_exec_time_ms", "mean_exec_time_ms", "stddev_exec_time_ms",
                  "min_exec_time_ms", "max_exec_time_ms"):
            data[k] = float(data.get(k) or 0.0)
        for k in ("queryid", "dbid", "userid"):
            if data.get(k) is not None:
                data[k] = int(data[k])
        return cls(**data)


# --------------------------------------------------------------------------- source

_COLUMNS_13 = """
    s.queryid, s.dbid, s.userid, s.query, s.calls,
    s.total_exec_time  AS total_exec_time_ms,
    s.mean_exec_time   AS mean_exec_time_ms,
    s.stddev_exec_time AS stddev_exec_time_ms,
    s.min_exec_time    AS min_exec_time_ms,
    s.max_exec_time    AS max_exec_time_ms,
    s.rows, s.shared_blks_hit, s.shared_blks_read
"""
_COLUMNS_LEGACY = """
    s.queryid, s.dbid, s.userid, s.query, s.calls,
    s.total_time  AS total_exec_time_ms,
    s.mean_time   AS mean_exec_time_ms,
    s.stddev_time AS stddev_exec_time_ms,
    s.min_time    AS min_exec_time_ms,
    s.max_time    AS max_exec_time_ms,
    s.rows, s.shared_blks_hit, s.shared_blks_read
"""


class PgStatStatementsSource:
    """Reads ``pg_stat_statements`` through a :class:`~qwen_dba.common.database.Database`."""

    def __init__(self, db, min_calls: int = 1, current_database_only: bool = True,
                 limit: int = 5000, include_utility: bool = False):
        self.db = db
        self.min_calls = max(int(min_calls), 1)
        self.current_database_only = current_database_only
        self.limit = int(limit)
        self.include_utility = include_utility
        self._legacy: Optional[bool] = None

    def _is_legacy(self) -> bool:
        if self._legacy is None:
            try:
                rows = self.db.execute_raw(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'pg_stat_statements' AND column_name IN ('total_exec_time', 'total_time')"
                )
            except Exception as exc:  # pragma: no cover - surfaced via fetch()
                raise PgStatStatementsUnavailable(f"{SETUP_HINT} ({exc})") from exc
            cols = {r[0] for r in rows}
            if not cols:
                raise PgStatStatementsUnavailable(SETUP_HINT + " (view pg_stat_statements not found)")
            self._legacy = "total_exec_time" not in cols
        return self._legacy

    def fetch(self) -> List[StatementRow]:
        """Current cumulative rows (calls >= ``min_calls``), most expensive first."""
        cols = _COLUMNS_LEGACY if self._is_legacy() else _COLUMNS_13
        where = ["s.calls >= :min_calls", "s.query IS NOT NULL", "s.query <> '<insufficient privilege>'"]
        if self.current_database_only:
            where.append("s.dbid = (SELECT oid FROM pg_database WHERE datname = current_database())")
        if not self.include_utility:
            # Ignore our own probes and transaction control noise.
            where.append("s.query !~* '^\\s*(BEGIN|COMMIT|ROLLBACK|SET|SHOW|RESET|DISCARD)\\b'")
            where.append("s.query NOT ILIKE '%pg_stat_statements%'")
        sql = (f"SELECT {cols} FROM pg_stat_statements s WHERE " + " AND ".join(where)
               + " ORDER BY 7 DESC NULLS LAST LIMIT :limit")
        try:
            result = self.db.execute_raw(sql, {"min_calls": self.min_calls, "limit": self.limit})
        except Exception as exc:
            raise PgStatStatementsUnavailable(f"{SETUP_HINT} ({exc})") from exc
        return [StatementRow.from_mapping(r._mapping if hasattr(r, "_mapping") else r) for r in result]

    def stats_reset_at(self) -> Optional[datetime]:
        """When the counters were last reset (PG 14+ ``pg_stat_statements_info``), else None."""
        try:
            rows = self.db.execute_raw("SELECT stats_reset FROM pg_stat_statements_info")
        except Exception:
            return None
        if not rows or rows[0][0] is None:
            return None
        ts = rows[0][0]
        return ts.replace(tzinfo=None) if getattr(ts, "tzinfo", None) else ts

    def reset(self) -> None:
        """Reset the counters (needs superuser or EXECUTE on pg_stat_statements_reset)."""
        self.db.execute_raw("SELECT pg_stat_statements_reset()")


# ------------------------------------------------------------------ mapping / deltas

def delta_rows(current: Sequence[StatementRow],
               previous: Optional[Dict[Tuple, StatementRow]]) -> List[StatementRow]:
    """Turn cumulative rows into per-window rows by subtracting the previous capture.

    A row whose counters went backwards (the view was reset, or the entry was
    evicted and re-added) is taken as-is. Rows with no new calls are dropped.
    min/max are cumulative in the view, so they are kept, not subtracted.
    """
    if not previous:
        return [r for r in current if r.calls > 0]
    out: List[StatementRow] = []
    for r in current:
        p = previous.get(r.key)
        if p is None or r.calls < p.calls or r.total_exec_time_ms < p.total_exec_time_ms:
            if r.calls > 0:
                out.append(r)
            continue
        calls = r.calls - p.calls
        if calls <= 0:
            continue
        total = r.total_exec_time_ms - p.total_exec_time_ms
        mean = total / calls
        # Variance of the new calls only, from the two cumulative (n, mean, sd) triples.
        sum_sq_now = r.calls * (r.stddev_exec_time_ms ** 2 + r.mean_exec_time_ms ** 2)
        sum_sq_prev = p.calls * (p.stddev_exec_time_ms ** 2 + p.mean_exec_time_ms ** 2)
        var = max((sum_sq_now - sum_sq_prev) / calls - mean ** 2, 0.0)
        out.append(StatementRow(
            query=r.query, calls=calls, total_exec_time_ms=total, mean_exec_time_ms=mean,
            stddev_exec_time_ms=math.sqrt(var), min_exec_time_ms=r.min_exec_time_ms,
            max_exec_time_ms=r.max_exec_time_ms, rows=max(r.rows - p.rows, 0),
            shared_blks_hit=max(r.shared_blks_hit - p.shared_blks_hit, 0),
            shared_blks_read=max(r.shared_blks_read - p.shared_blks_read, 0),
            queryid=r.queryid, dbid=r.dbid, userid=r.userid,
        ))
    return out


def rows_to_snapshots(rows: Iterable[StatementRow], fingerprinter: QueryFingerprinter,
                      snapshot_timestamp: datetime, window_start: datetime, window_end: datetime,
                      min_calls: int = 1) -> List[WorkloadSnapshot]:
    """Group rows by fingerprint (several queryids can normalize to one pattern) into snapshots."""
    groups: Dict[str, List[StatementRow]] = {}
    for r in rows:
        if r.calls <= 0:
            continue
        groups.setdefault(fingerprinter.fingerprint(r.query), []).append(r)

    snapshots: List[WorkloadSnapshot] = []
    for fp, rs in groups.items():
        calls = sum(r.calls for r in rs)
        if calls < max(min_calls, 1):
            continue
        total = sum(r.total_exec_time_ms for r in rs)
        mean = total / calls
        # Pooled standard deviation across the merged rows.
        sum_sq = sum(r.calls * (r.stddev_exec_time_ms ** 2 + r.mean_exec_time_ms ** 2) for r in rs)
        sd = math.sqrt(max(sum_sq / calls - mean ** 2, 0.0))
        mx = max(r.max_exec_time_ms for r in rs)
        mn = min(r.min_exec_time_ms for r in rs)
        cap = mx if mx > 0 else float("inf")
        example = max(rs, key=lambda r: r.calls).query
        snap = WorkloadSnapshot(
            snapshot_timestamp=snapshot_timestamp, window_start=window_start, window_end=window_end,
            query_fingerprint=fp, query_type=fingerprinter.extract_query_type(example),
            query_source=QuerySource.POSTGRES, example_query=example,
            execution_count=calls, total_execution_time_ms=total, avg_execution_time_ms=mean,
            p50_latency_ms=min(mean, cap), p95_latency_ms=min(mean + Z_P95 * sd, cap),
            p99_latency_ms=min(mean + Z_P99 * sd, cap), max_latency_ms=mx, min_latency_ms=mn,
            avg_rows_returned=sum(r.rows for r in rs) / calls,
            avg_buffer_hits=sum(r.shared_blks_hit for r in rs) / calls,
            avg_buffer_misses=sum(r.shared_blks_read for r in rs) / calls,
        )
        snap.calculate_impact_score()
        snapshots.append(snap)
    snapshots.sort(key=lambda s: s.impact_score, reverse=True)
    return snapshots


# ------------------------------------------------------------------- history (#7)

STAT_COLUMNS = ["captured_at", "queryid", "dbid", "userid", "query_fingerprint", "query_type",
                "query", "calls", "total_exec_time_ms", "mean_exec_time_ms", "stddev_exec_time_ms",
                "min_exec_time_ms", "max_exec_time_ms", "rows", "shared_blks_hit", "shared_blks_read"]


class StatSnapshotStore:
    """``qwen_dba.stat_snapshots``: every pg_stat_statements capture, for trends and deltas."""

    def __init__(self, db, fingerprinter: Optional[QueryFingerprinter] = None):
        self.db = db
        self.fingerprinter = fingerprinter or QueryFingerprinter()

    def save(self, rows: Sequence[StatementRow], captured_at: datetime) -> int:
        sql = (
            "INSERT INTO qwen_dba.stat_snapshots (" + ", ".join(STAT_COLUMNS) + ") VALUES ("
            + ", ".join(":" + c for c in STAT_COLUMNS) + ")"
        )
        n = 0
        with self.db.get_session() as session:
            from sqlalchemy import text
            stmt = text(sql)
            for r in rows:
                d = asdict(r)
                d.update(captured_at=captured_at,
                         query_fingerprint=self.fingerprinter.fingerprint(r.query),
                         query_type=self.fingerprinter.extract_query_type(r.query))
                session.execute(stmt, {c: d.get(c) for c in STAT_COLUMNS})
                n += 1
        return n

    def captures(self, limit: int = 50) -> List[Tuple[datetime, int, int]]:
        """(captured_at, statements, total calls), newest first."""
        rows = self.db.execute_raw(
            "SELECT captured_at, COUNT(*), COALESCE(SUM(calls), 0) FROM qwen_dba.stat_snapshots "
            "GROUP BY captured_at ORDER BY captured_at DESC LIMIT :limit", {"limit": limit})
        return [(r[0], int(r[1]), int(r[2])) for r in rows]

    def latest_capture(self, before: Optional[datetime] = None) -> Optional[datetime]:
        sql = "SELECT MAX(captured_at) FROM qwen_dba.stat_snapshots"
        params = {}
        if before is not None:
            sql += " WHERE captured_at < :before"
            params["before"] = before
        rows = self.db.execute_raw(sql, params)
        return rows[0][0] if rows and rows[0][0] is not None else None

    def load_capture(self, captured_at: datetime) -> Dict[Tuple, StatementRow]:
        rows = self.db.execute_raw(
            "SELECT queryid, dbid, userid, query, calls, total_exec_time_ms, mean_exec_time_ms, "
            "stddev_exec_time_ms, min_exec_time_ms, max_exec_time_ms, rows, shared_blks_hit, "
            "shared_blks_read FROM qwen_dba.stat_snapshots WHERE captured_at = :ts", {"ts": captured_at})
        out = {}
        for r in rows:
            row = StatementRow.from_mapping(r._mapping)
            out[row.key] = row
        return out

    def prune(self, retention_days: Optional[float] = None, before: Optional[datetime] = None,
              now: Optional[datetime] = None) -> int:
        """Delete captures older than ``retention_days`` (or before ``before``). Returns rows deleted."""
        if before is None:
            if retention_days is None or retention_days <= 0:
                return 0
            before = (now or datetime.utcnow()) - timedelta(days=retention_days)
        rows = self.db.execute_raw(
            "WITH d AS (DELETE FROM qwen_dba.stat_snapshots WHERE captured_at < :before RETURNING 1) "
            "SELECT COUNT(*) FROM d", {"before": before})
        return int(rows[0][0]) if rows else 0

    def export_csv(self, path: Union[str, Path], since: Optional[datetime] = None,
                   until: Optional[datetime] = None) -> int:
        """Write captures (oldest first) to CSV with a header row. Returns data rows written."""
        where, params = [], {}
        if since is not None:
            where.append("captured_at >= :since")
            params["since"] = since
        if until is not None:
            where.append("captured_at <= :until")
            params["until"] = until
        sql = "SELECT " + ", ".join(STAT_COLUMNS) + " FROM qwen_dba.stat_snapshots"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY captured_at, queryid NULLS LAST, query_fingerprint"
        rows = self.db.execute_raw(sql, params)
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(STAT_COLUMNS)
            for r in rows:
                w.writerow([v.isoformat() if isinstance(v, datetime) else v for v in r])
        return len(rows)
