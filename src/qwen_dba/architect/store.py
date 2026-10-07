"""Persistence for architect inputs/outputs (no MLX import, usable by the stub)."""

import json
from typing import List

from ..common.logger import logger
from ..common.models import WorkloadSnapshot, Recommendation


def _num(value):
    """NUMERIC -> float, keeping NULL as None (and 0 as 0.0, not None)."""
    return None if value is None else float(value)


def load_recent_workload_snapshots(db, limit: int = 50) -> List[WorkloadSnapshot]:
    """Get recent workload snapshots from database."""
    sql = """
        SELECT
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
        FROM qwen_dba.workload_snapshots
        ORDER BY impact_score DESC
        LIMIT :limit
    """

    rows = db.execute_raw(sql, {'limit': limit})

    snapshots = []
    for row in rows:
        snapshot = WorkloadSnapshot(
            snapshot_timestamp=row[0],
            window_start=row[1],
            window_end=row[2],
            query_fingerprint=row[3],
            query_type=row[4],
            query_source=row[5],
            example_query=row[6],
            execution_count=row[7],
            total_execution_time_ms=_num(row[8]),
            avg_execution_time_ms=_num(row[9]),
            p50_latency_ms=_num(row[10]),
            p95_latency_ms=_num(row[11]),
            p99_latency_ms=_num(row[12]),
            max_latency_ms=_num(row[13]),
            min_latency_ms=_num(row[14]),
            avg_rows_returned=_num(row[15]),
            avg_rows_scanned=_num(row[16]),
            avg_buffer_hits=_num(row[17]),
            avg_buffer_misses=_num(row[18]),
            error_count=row[19],
            error_rate=_num(row[20]),
            impact_score=_num(row[21])
        )
        snapshots.append(snapshot)

    return snapshots


def save_recommendation(db, recommendation: Recommendation) -> bool:
    """Save recommendation to database."""
    try:
        sql = """
            INSERT INTO qwen_dba.recommendations (
                recommendation_id,
                recommendation_timestamp,
                status,
                priority,
                recommendation_type,
                title,
                rationale,
                config_patch,
                expected_effects,
                expected_latency_improvement_percent,
                expected_cost_reduction_percent,
                risk_level,
                risk_notes,
                migration_sql,
                rollback_sql,
                model_name,
                model_version,
                confidence_score
            ) VALUES (
                :recommendation_id,
                :recommendation_timestamp,
                :status,
                :priority,
                :recommendation_type,
                :title,
                :rationale,
                :config_patch,
                :expected_effects,
                :expected_latency_improvement_percent,
                :expected_cost_reduction_percent,
                :risk_level,
                :risk_notes,
                :migration_sql,
                :rollback_sql,
                :model_name,
                :model_version,
                :confidence_score
            )
        """

        params = {
            'recommendation_id': recommendation.recommendation_id,
            'recommendation_timestamp': recommendation.recommendation_timestamp,
            'status': recommendation.status.value,
            'priority': recommendation.priority,
            'recommendation_type': recommendation.recommendation_type.value,
            'title': recommendation.title,
            'rationale': recommendation.rationale,
            'config_patch': json.dumps(recommendation.config_patch),
            'expected_effects': json.dumps(recommendation.expected_effects),
            'expected_latency_improvement_percent': recommendation.expected_latency_improvement_percent,
            'expected_cost_reduction_percent': recommendation.expected_cost_reduction_percent,
            'risk_level': recommendation.risk_level.value,
            'risk_notes': recommendation.risk_notes,
            'migration_sql': recommendation.migration_sql,
            'rollback_sql': recommendation.rollback_sql,
            'model_name': recommendation.model_name,
            'model_version': recommendation.model_version,
            'confidence_score': recommendation.confidence_score
        }

        db.execute_raw(sql, params)
        logger.info(f"Saved recommendation: {recommendation.recommendation_id}")
        return True

    except Exception as e:
        logger.error(f"Error saving recommendation: {e}")
        return False
