"""Tests for the workload profiler."""

import pytest
from datetime import datetime

from qwen_dba.profiler.fingerprint import QueryFingerprinter
from qwen_dba.profiler.parsers import PostgresLogParser
from qwen_dba.profiler.aggregator import WorkloadAggregator
from qwen_dba.common.models import QueryLog


class TestQueryFingerprinter:
    """Test query fingerprinting functionality."""

    def test_basic_fingerprint(self):
        """Test basic query fingerprinting."""
        fingerprinter = QueryFingerprinter()

        query1 = "SELECT * FROM users WHERE email = 'user@example.com'"
        query2 = "SELECT * FROM users WHERE email = 'other@example.com'"

        fp1 = fingerprinter.fingerprint(query1)
        fp2 = fingerprinter.fingerprint(query2)

        # Same structure, different literals should have same fingerprint
        assert fp1 == fp2
        assert "?" in fp1  # Literals should be replaced

    def test_case_insensitive(self):
        """Test case-insensitive fingerprinting."""
        fingerprinter = QueryFingerprinter(case_insensitive=True)

        query1 = "SELECT * FROM users"
        query2 = "select * from users"

        fp1 = fingerprinter.fingerprint(query1)
        fp2 = fingerprinter.fingerprint(query2)

        assert fp1 == fp2

    def test_whitespace_normalization(self):
        """Test whitespace normalization."""
        fingerprinter = QueryFingerprinter(normalize_whitespace=True)

        query1 = "SELECT   *   FROM   users"
        query2 = "SELECT * FROM users"

        fp1 = fingerprinter.fingerprint(query1)
        fp2 = fingerprinter.fingerprint(query2)

        assert fp1 == fp2

    def test_extract_query_type(self):
        """Test query type extraction."""
        fingerprinter = QueryFingerprinter()

        assert fingerprinter.extract_query_type("SELECT * FROM users") == "SELECT"
        assert fingerprinter.extract_query_type("INSERT INTO users VALUES (1, 'test')") == "INSERT"
        assert fingerprinter.extract_query_type("UPDATE users SET name = 'test'") == "UPDATE"
        assert fingerprinter.extract_query_type("DELETE FROM users WHERE id = 1") == "DELETE"

    def test_extract_tables(self):
        """Test table name extraction."""
        fingerprinter = QueryFingerprinter()

        query = "SELECT * FROM users WHERE id = 1"
        tables = fingerprinter.extract_tables(query)
        assert "users" in tables

        query = "SELECT u.*, o.* FROM users u JOIN orders o ON u.id = o.user_id"
        tables = fingerprinter.extract_tables(query)
        assert "users" in tables
        assert "orders" in tables


class TestPostgresLogParser:
    """Test PostgreSQL log parser."""

    def test_parse_log_file(self, sample_log_file):
        """Test parsing a PostgreSQL log file."""
        parser = PostgresLogParser()
        logs = list(parser.parse_file(str(sample_log_file)))

        assert len(logs) > 0

        # Check first log entry
        first_log = logs[0]
        assert isinstance(first_log, QueryLog)
        assert first_log.execution_time_ms > 0
        assert "users" in first_log.query.lower()
        assert first_log.success is True

    def test_parse_log_with_errors(self, temp_dir):
        """Test parsing logs with malformed entries."""
        log_file = temp_dir / "error_log.log"
        log_file.write_text("""
2025-01-09 10:30:45.123 UTC [12345] LOG:  duration: 234.567 ms  statement: SELECT * FROM users
MALFORMED LINE
2025-01-09 10:30:46.456 UTC [12346] LOG:  duration: 45.123 ms  statement: SELECT * FROM products
""")

        parser = PostgresLogParser()
        logs = list(parser.parse_file(str(log_file)))

        # Should skip malformed line and parse valid ones
        assert len(logs) == 2


class TestWorkloadAggregator:
    """Test workload aggregation."""

    def test_aggregate_logs(self, sample_log_file):
        """Test aggregating query logs."""
        # Parse logs
        parser = PostgresLogParser()
        logs = list(parser.parse_file(str(sample_log_file)))

        # Aggregate
        aggregator = WorkloadAggregator(window_minutes=60, min_query_count=2)
        snapshots = aggregator.aggregate(logs)

        assert len(snapshots) > 0

        # Check snapshot properties
        snapshot = snapshots[0]
        assert snapshot.execution_count >= 2
        assert snapshot.avg_execution_time_ms > 0
        assert snapshot.p95_latency_ms is not None
        assert snapshot.impact_score > 0

    def test_min_query_count_filter(self, sample_log_file):
        """Test that queries below min count are filtered."""
        parser = PostgresLogParser()
        logs = list(parser.parse_file(str(sample_log_file)))

        # High threshold - should filter most queries
        aggregator = WorkloadAggregator(window_minutes=60, min_query_count=100)
        snapshots = aggregator.aggregate(logs)

        assert len(snapshots) == 0  # Not enough repetitions

    def test_impact_score_calculation(self, sample_log_file):
        """Test impact score calculation."""
        parser = PostgresLogParser()
        logs = list(parser.parse_file(str(sample_log_file)))

        aggregator = WorkloadAggregator(window_minutes=60, min_query_count=2)
        snapshots = aggregator.aggregate(logs)

        # Snapshots should be sorted by impact score
        if len(snapshots) > 1:
            assert snapshots[0].impact_score >= snapshots[1].impact_score


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
