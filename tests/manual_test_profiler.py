"""Manual tests for profiler without pytest."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from qwen_dba.profiler.fingerprint import QueryFingerprinter
from qwen_dba.profiler.parsers import PostgresLogParser
from qwen_dba.profiler.aggregator import WorkloadAggregator


def test_fingerprinter():
    """Test query fingerprinting."""
    print("Testing QueryFingerprinter...")

    fingerprinter = QueryFingerprinter()

    query1 = "SELECT * FROM users WHERE email = 'user@example.com'"
    query2 = "SELECT * FROM users WHERE email = 'other@example.com'"

    fp1 = fingerprinter.fingerprint(query1)
    fp2 = fingerprinter.fingerprint(query2)

    print(f"  Query 1: {query1}")
    print(f"  Fingerprint 1: {fp1}")
    print(f"  Query 2: {query2}")
    print(f"  Fingerprint 2: {fp2}")
    print(f"  Fingerprints match: {fp1 == fp2}")

    assert fp1 == fp2, "Fingerprints should match for queries with same structure"
    assert "?" in fp1, "Literals should be replaced with ?"

    # Test query type extraction
    query_type = fingerprinter.extract_query_type(query1)
    print(f"  Query type: {query_type}")
    assert query_type == "SELECT", f"Expected SELECT, got {query_type}"

    # Test table extraction
    tables = fingerprinter.extract_tables(query1)
    print(f"  Tables found: {tables}")
    assert "users" in tables, "Should find 'users' table"

    print("PASS: QueryFingerprinter tests\n")


def test_log_parser():
    """Test PostgreSQL log parser."""
    print("Testing PostgresLogParser...")

    # Create a sample log file
    log_content = """2025-01-09 10:30:45.123 UTC [12345] LOG:  duration: 234.567 ms  statement: SELECT * FROM users WHERE email = 'user@example.com'
2025-01-09 10:30:46.456 UTC [12346] LOG:  duration: 45.123 ms  statement: SELECT id, name FROM products WHERE category = 'electronics'
2025-01-09 10:30:47.789 UTC [12347] LOG:  duration: 567.890 ms  statement: SELECT * FROM orders WHERE user_id = 123 AND status = 'pending'
"""

    # Write to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
        f.write(log_content)
        log_file = f.name

    try:
        parser = PostgresLogParser()
        logs = list(parser.parse_file(log_file))

        print(f"  Parsed {len(logs)} log entries")

        assert len(logs) == 3, f"Expected 3 logs, got {len(logs)}"

        first_log = logs[0]
        print(f"  First log: {first_log.query[:50]}...")
        print(f"  Execution time: {first_log.execution_time_ms}ms")

        assert first_log.execution_time_ms > 0, "Execution time should be > 0"
        assert first_log.success is True, "Log should be marked as successful"

        print("PASS: PostgresLogParser tests\n")

    finally:
        import os
        os.unlink(log_file)


def test_aggregator():
    """Test workload aggregator."""
    print("Testing WorkloadAggregator...")

    from qwen_dba.common.models import QueryLog
    from datetime import datetime, timedelta

    # Create sample query logs
    base_time = datetime(2025, 1, 9, 10, 30, 0)
    logs = []

    # Same query executed multiple times
    for i in range(10):
        logs.append(QueryLog(
            timestamp=base_time + timedelta(seconds=i),
            query=f"SELECT * FROM users WHERE email = 'user{i}@example.com'",
            execution_time_ms=100 + i * 10,
            success=True,
            source="postgres"
        ))

    # Different query executed a few times
    for i in range(3):
        logs.append(QueryLog(
            timestamp=base_time + timedelta(seconds=i),
            query=f"INSERT INTO logs VALUES ({i}, 'test')",
            execution_time_ms=50 + i * 5,
            success=True,
            source="postgres"
        ))

    aggregator = WorkloadAggregator(window_minutes=60, min_query_count=3)
    snapshots = aggregator.aggregate(logs)

    print(f"  Created {len(snapshots)} workload snapshots")

    assert len(snapshots) >= 1, "Should create at least one snapshot"

    snapshot = snapshots[0]
    print(f"  Top snapshot query type: {snapshot.query_type}")
    print(f"  Execution count: {snapshot.execution_count}")
    print(f"  P95 latency: {snapshot.p95_latency_ms}ms")
    print(f"  Impact score: {snapshot.impact_score}")

    assert snapshot.execution_count >= 3, "Execution count should be >= min_query_count"
    assert snapshot.p95_latency_ms is not None, "P95 latency should be calculated"
    assert snapshot.impact_score > 0, "Impact score should be > 0"

    print("PASS: WorkloadAggregator tests\n")


if __name__ == "__main__":
    try:
        test_fingerprinter()
        test_log_parser()
        test_aggregator()
        print("\nAll manual tests passed")
    except AssertionError as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
