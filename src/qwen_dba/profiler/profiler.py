"""Main workload profiler orchestration."""

from datetime import datetime
from typing import List, Optional
from pathlib import Path

from ..common.config import get_config
from ..common.database import get_metrics_db
from ..common.logger import logger
from ..common.models import QueryLog, WorkloadSnapshot
from .parsers import get_parser
from .fingerprint import QueryFingerprinter
from .aggregator import WorkloadAggregator


class WorkloadProfiler:
    """Main workload profiler that orchestrates log collection and aggregation."""

    def __init__(self):
        """Initialize profiler with configuration."""
        self.config = get_config()
        self.db = get_metrics_db()

        # Initialize components
        fingerprint_config = self.config.profiler.fingerprint
        self.fingerprinter = QueryFingerprinter(
            normalize_literals=fingerprint_config.get('normalize_literals', True),
            normalize_whitespace=fingerprint_config.get('normalize_whitespace', True),
            case_insensitive=fingerprint_config.get('case_insensitive', True)
        )

        aggregation_config = self.config.profiler.aggregation
        self.aggregator = WorkloadAggregator(
            window_minutes=aggregation_config.get('window_minutes', 60),
            min_query_count=aggregation_config.get('min_query_count', 5),
            fingerprinter=self.fingerprinter
        )

    def collect_logs(self) -> List[QueryLog]:
        """
        Collect query logs from all configured sources.

        Returns:
            List of QueryLog objects
        """
        all_logs = []

        sources = self.config.profiler.sources

        for source_name, source_config in sources.items():
            if not source_config.get('enabled', False):
                continue

            try:
                logger.info(f"Collecting logs from {source_name}")

                log_path = source_config.get('log_path')
                if not log_path:
                    logger.warning(f"No log_path configured for {source_name}")
                    continue

                if not Path(log_path).exists():
                    logger.warning(f"Log file not found: {log_path}")
                    continue

                log_format = source_config.get('log_format', 'standard')
                parser = get_parser(source_name, log_format)

                logs = list(parser.parse_file(log_path))
                logger.info(f"Collected {len(logs)} logs from {source_name}")

                all_logs.extend(logs)

            except Exception as e:
                logger.error(f"Error collecting logs from {source_name}: {e}")
                continue

        return all_logs

    def create_snapshots(
        self,
        query_logs: Optional[List[QueryLog]] = None
    ) -> List[WorkloadSnapshot]:
        """
        Create workload snapshots from query logs.

        Args:
            query_logs: Query logs to aggregate (if None, collects from sources)

        Returns:
            List of WorkloadSnapshot objects
        """
        if query_logs is None:
            query_logs = self.collect_logs()

        if not query_logs:
            logger.warning("No query logs to aggregate")
            return []

        logger.info(f"Aggregating {len(query_logs)} query logs")

        snapshots = self.aggregator.aggregate(query_logs)

        logger.info(f"Created {len(snapshots)} workload snapshots")

        return snapshots

    def save_snapshots(self, snapshots: List[WorkloadSnapshot]) -> int:
        """
        Save workload snapshots to database.

        Args:
            snapshots: List of WorkloadSnapshot objects

        Returns:
            Number of snapshots saved
        """
        if not snapshots:
            return 0

        saved_count = 0

        for snapshot in snapshots:
            try:
                sql = """
                    INSERT INTO qwen_dba.workload_snapshots (
                        snapshot_timestamp,
                        window_start,
                        window_end,
                        query_fingerprint,
                        query_type,
                        query_source,
                        example_query,
                        execution_count,
                        total_execution_time_ms,
                        avg_execution_time_ms,
                        p50_latency_ms,
                        p95_latency_ms,
                        p99_latency_ms,
                        max_latency_ms,
                        min_latency_ms,
                        avg_rows_returned,
                        avg_rows_scanned,
                        avg_buffer_hits,
                        avg_buffer_misses,
                        error_count,
                        error_rate,
                        impact_score
                    ) VALUES (
                        :snapshot_timestamp,
                        :window_start,
                        :window_end,
                        :query_fingerprint,
                        :query_type,
                        :query_source,
                        :example_query,
                        :execution_count,
                        :total_execution_time_ms,
                        :avg_execution_time_ms,
                        :p50_latency_ms,
                        :p95_latency_ms,
                        :p99_latency_ms,
                        :max_latency_ms,
                        :min_latency_ms,
                        :avg_rows_returned,
                        :avg_rows_scanned,
                        :avg_buffer_hits,
                        :avg_buffer_misses,
                        :error_count,
                        :error_rate,
                        :impact_score
                    )
                    ON CONFLICT (snapshot_timestamp, query_fingerprint, query_source)
                    DO UPDATE SET
                        execution_count = EXCLUDED.execution_count,
                        avg_execution_time_ms = EXCLUDED.avg_execution_time_ms,
                        p95_latency_ms = EXCLUDED.p95_latency_ms,
                        impact_score = EXCLUDED.impact_score
                """

                params = {
                    'snapshot_timestamp': snapshot.snapshot_timestamp,
                    'window_start': snapshot.window_start,
                    'window_end': snapshot.window_end,
                    'query_fingerprint': snapshot.query_fingerprint,
                    'query_type': snapshot.query_type,
                    'query_source': snapshot.query_source,
                    'example_query': snapshot.example_query,
                    'execution_count': snapshot.execution_count,
                    'total_execution_time_ms': snapshot.total_execution_time_ms,
                    'avg_execution_time_ms': snapshot.avg_execution_time_ms,
                    'p50_latency_ms': snapshot.p50_latency_ms,
                    'p95_latency_ms': snapshot.p95_latency_ms,
                    'p99_latency_ms': snapshot.p99_latency_ms,
                    'max_latency_ms': snapshot.max_latency_ms,
                    'min_latency_ms': snapshot.min_latency_ms,
                    'avg_rows_returned': snapshot.avg_rows_returned,
                    'avg_rows_scanned': snapshot.avg_rows_scanned,
                    'avg_buffer_hits': snapshot.avg_buffer_hits,
                    'avg_buffer_misses': snapshot.avg_buffer_misses,
                    'error_count': snapshot.error_count,
                    'error_rate': snapshot.error_rate,
                    'impact_score': snapshot.impact_score
                }

                self.db.execute_raw(sql, params)
                saved_count += 1

            except Exception as e:
                logger.error(f"Error saving snapshot: {e}")
                continue

        logger.info(f"Saved {saved_count} workload snapshots")
        return saved_count

    def run(self) -> int:
        """
        Run the profiler: collect logs, create snapshots, and save to database.

        Returns:
            Number of snapshots created
        """
        logger.info("Starting workload profiler")

        # Collect and aggregate
        snapshots = self.create_snapshots()

        # Save to database
        if snapshots:
            self.save_snapshots(snapshots)

        logger.info("Workload profiler completed")
        return len(snapshots)
