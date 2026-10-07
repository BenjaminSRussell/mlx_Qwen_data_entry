"""CPU StubArchitect for Linux CI / non-Mac demos (no MLX)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol

from ..common.logger import logger
from ..common.models import (
    Recommendation,
    RecommendationStatus,
    RecommendationType,
    RiskLevel,
    WorkloadSnapshot,
    EvalResult,
)


class ArchitectBackend(Protocol):
    def generate_recommendation(
        self,
        workload_snapshots: Optional[List[WorkloadSnapshot]] = None,
        eval_results: Optional[List[EvalResult]] = None,
        schema_info: Optional[Dict[str, Any]] = None,
        current_config: Optional[Dict[str, Any]] = None,
    ) -> Optional[Recommendation]: ...

    def run(self) -> Optional[Recommendation]: ...


class StubArchitect:
    """Heuristic architect that proposes safe, reviewable SQL without MLX."""

    def __init__(self, db=None):
        """``db``: a ``Database``; defaults to the configured metrics DB on run()."""
        self._db = db
        logger.info("StubArchitect enabled (no MLX)")

    def _database(self):
        if self._db is not None:
            return self._db
        try:
            from ..common.database import get_metrics_db
            return get_metrics_db()
        except Exception as e:  # no config / no DB: still usable offline
            logger.warning(f"StubArchitect: metrics DB unavailable ({e}); running without persistence")
            return None

    def generate_recommendation(
        self,
        workload_snapshots: Optional[List[WorkloadSnapshot]] = None,
        eval_results: Optional[List[EvalResult]] = None,
        schema_info: Optional[Dict[str, Any]] = None,
        current_config: Optional[Dict[str, Any]] = None,
    ) -> Optional[Recommendation]:
        snapshots = workload_snapshots or []
        top = max(snapshots, key=lambda s: getattr(s, "impact_score", 0) or 0) if snapshots else None

        if top is not None and getattr(top, "example_query", None):
            example = (top.example_query or "").strip().rstrip(";")
            # EXPLAIN ANALYZE *executes* the statement, so only use it for reads;
            # for INSERT/UPDATE/DELETE emit a plan-only EXPLAIN.
            if (getattr(top, "query_type", "") or "").upper() == "SELECT":
                sql = f"EXPLAIN (ANALYZE, BUFFERS) {example};"
            else:
                sql = f"EXPLAIN {example};"
            title = f"Explain high-impact query ({getattr(top, 'query_type', 'unknown')})"
            rationale = (
                "Stub heuristic: highest impact_score query should be EXPLAINed before index changes."
            )
            rtype = RecommendationType.QUERY_REWRITE
        else:
            sql = "SELECT version();"
            title = "Stub health check"
            rationale = "No workload snapshots available; emit a no-op health SQL for CI loop."
            rtype = RecommendationType.CONFIG_TUNING

        return Recommendation(
            recommendation_id=str(uuid.uuid4()),
            recommendation_timestamp=datetime.utcnow(),
            status=RecommendationStatus.PENDING,
            recommendation_type=rtype,
            title=title,
            rationale=rationale,
            config_patch={"backend": "stub", "mlx": False},
            risk_level=RiskLevel.LOW,
            migration_sql=sql,
            rollback_sql="-- stub: no-op",
            model_name="stub-architect",
            model_version="0.1.0",
            confidence_score=0.4,
        )

    def run(self, save: bool = True) -> Optional[Recommendation]:
        """Same loop as QwenArchitect.run: read snapshots, propose, persist."""
        from . import store

        db = self._database()
        snapshots: List[WorkloadSnapshot] = []
        if db is not None:
            try:
                snapshots = store.load_recent_workload_snapshots(db)
            except Exception as e:
                logger.warning(f"StubArchitect: could not load workload snapshots: {e}")
        recommendation = self.generate_recommendation(workload_snapshots=snapshots)
        if recommendation and save and db is not None:
            store.save_recommendation(db, recommendation)
        return recommendation
