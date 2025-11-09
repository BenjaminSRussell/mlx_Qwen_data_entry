"""Workload aggregation for creating snapshots."""

import statistics
from datetime import datetime, timedelta
from typing import List, Dict
from collections import defaultdict

from ..common.models import QueryLog, WorkloadSnapshot
from .fingerprint import QueryFingerprinter


class WorkloadAggregator:
    """Aggregates query logs into workload snapshots."""

    def __init__(
        self,
        window_minutes: int = 60,
        min_query_count: int = 5,
        fingerprinter: QueryFingerprinter = None
    ):
        """
        Initialize aggregator.

        Args:
            window_minutes: Time window for aggregation
            min_query_count: Minimum executions to track a query pattern
            fingerprinter: Query fingerprinter (creates default if None)
        """
        self.window_minutes = window_minutes
        self.min_query_count = min_query_count
        self.fingerprinter = fingerprinter or QueryFingerprinter()

    def aggregate(
        self,
        query_logs: List[QueryLog],
        snapshot_timestamp: datetime = None
    ) -> List[WorkloadSnapshot]:
        """
        Aggregate query logs into workload snapshots.

        Args:
            query_logs: List of query logs to aggregate
            snapshot_timestamp: Timestamp for the snapshot (default: now)

        Returns:
            List of WorkloadSnapshot objects
        """
        if not query_logs:
            return []

        snapshot_timestamp = snapshot_timestamp or datetime.utcnow()

        # Determine time window
        window_end = max(log.timestamp for log in query_logs)
        window_start = window_end - timedelta(minutes=self.window_minutes)

        # Filter logs to window
        windowed_logs = [
            log for log in query_logs
            if window_start <= log.timestamp <= window_end
        ]

        # Group logs by fingerprint
        fingerprint_groups: Dict[str, List[QueryLog]] = defaultdict(list)

        for log in windowed_logs:
            fingerprint = self.fingerprinter.fingerprint(log.query)
            log.query_fingerprint = fingerprint

            # Extract query type if not set
            if not log.query_type:
                log.query_type = self.fingerprinter.extract_query_type(log.query)

            fingerprint_groups[fingerprint].append(log)

        # Create snapshots
        snapshots = []

        for fingerprint, logs in fingerprint_groups.items():
            # Skip if below minimum count
            if len(logs) < self.min_query_count:
                continue

            snapshot = self._create_snapshot(
                fingerprint,
                logs,
                snapshot_timestamp,
                window_start,
                window_end
            )
            snapshots.append(snapshot)

        # Sort by impact score (descending)
        snapshots.sort(key=lambda s: s.impact_score, reverse=True)

        return snapshots

    def _create_snapshot(
        self,
        fingerprint: str,
        logs: List[QueryLog],
        snapshot_timestamp: datetime,
        window_start: datetime,
        window_end: datetime
    ) -> WorkloadSnapshot:
        """Create a single workload snapshot from grouped logs."""

        # Basic stats
        execution_count = len(logs)
        execution_times = [log.execution_time_ms for log in logs]

        # Calculate latency percentiles
        execution_times_sorted = sorted(execution_times)
        p50_idx = int(len(execution_times_sorted) * 0.50)
        p95_idx = int(len(execution_times_sorted) * 0.95)
        p99_idx = int(len(execution_times_sorted) * 0.99)

        p50_latency = execution_times_sorted[p50_idx] if execution_times_sorted else 0
        p95_latency = execution_times_sorted[p95_idx] if execution_times_sorted else 0
        p99_latency = execution_times_sorted[p99_idx] if execution_times_sorted else 0

        # Calculate resource usage (if available)
        rows_returned_values = [log.rows_returned for log in logs if log.rows_returned is not None]
        rows_scanned_values = [log.rows_scanned for log in logs if log.rows_scanned is not None]
        buffer_hits_values = [log.buffer_hits for log in logs if log.buffer_hits is not None]
        buffer_misses_values = [log.buffer_misses for log in logs if log.buffer_misses is not None]

        avg_rows_returned = statistics.mean(rows_returned_values) if rows_returned_values else None
        avg_rows_scanned = statistics.mean(rows_scanned_values) if rows_scanned_values else None
        avg_buffer_hits = statistics.mean(buffer_hits_values) if buffer_hits_values else None
        avg_buffer_misses = statistics.mean(buffer_misses_values) if buffer_misses_values else None

        # Error tracking
        error_count = sum(1 for log in logs if not log.success)
        error_rate = error_count / execution_count if execution_count > 0 else 0

        # Get query type and source from first log
        query_type = logs[0].query_type
        query_source = logs[0].source
        example_query = logs[0].query

        # Calculate totals and averages
        total_execution_time_ms = sum(execution_times)
        avg_execution_time_ms = statistics.mean(execution_times)

        # Create snapshot
        snapshot = WorkloadSnapshot(
            snapshot_timestamp=snapshot_timestamp,
            window_start=window_start,
            window_end=window_end,
            query_fingerprint=fingerprint,
            query_type=query_type,
            query_source=query_source,
            example_query=example_query,
            execution_count=execution_count,
            total_execution_time_ms=total_execution_time_ms,
            avg_execution_time_ms=avg_execution_time_ms,
            p50_latency_ms=p50_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            max_latency_ms=max(execution_times),
            min_latency_ms=min(execution_times),
            avg_rows_returned=avg_rows_returned,
            avg_rows_scanned=avg_rows_scanned,
            avg_buffer_hits=avg_buffer_hits,
            avg_buffer_misses=avg_buffer_misses,
            error_count=error_count,
            error_rate=error_rate
        )

        # Calculate impact score
        snapshot.calculate_impact_score()

        return snapshot
