from pathlib import Path
from qwen_dba.profiler.parsers import PostgresLogParser
from qwen_dba.profiler.fingerprint import QueryFingerprinter


def test_multiline_and_execute_and_tz(tmp_path: Path):
    log = tmp_path / "pg.log"
    log.write_text(
        "2025-01-09 12:34:56.789 EST [12345] LOG:  duration: 12.3 ms  statement: SELECT id\n"
        "FROM users\n"
        "WHERE active = true\n"
        "2025-01-09 12:35:00.000 UTC [12346] LOG:  duration: 1.0 ms  execute <unnamed>: SELECT 1\n"
    )
    rows = list(PostgresLogParser().parse_file(str(log)))
    assert len(rows) == 2
    assert "FROM users" in rows[0].query
    assert "pg_log_tz=EST" in rows[0].query
    assert rows[1].query.startswith("SELECT 1")


def test_fingerprint_keeps_identifiers_and_decimals():
    fp = QueryFingerprinter()
    out = fp.fingerprint('SELECT "Users".id, 1.5 FROM "Users" WHERE name = \'x\'')
    assert "?.?" not in out
    assert "1.5" not in out
    # Double-quoted identifier should not become ?
    assert "?" in out  # string literal became ?


def test_extract_tables_skips_extract_fn():
    fp = QueryFingerprinter()
    tables = fp.extract_tables("SELECT EXTRACT(YEAR FROM created_at) FROM events")
    assert "events" in tables
    assert "created_at" not in tables
    assert not any(t.upper() == "YEAR" for t in tables)
