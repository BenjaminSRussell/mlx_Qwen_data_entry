"""Main Qwen-MLX Architect orchestration."""

import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from ..common.config import get_config
from ..common.database import get_metrics_db
from ..common.logger import logger
from ..common.models import WorkloadSnapshot, EvalResult, Recommendation, RecommendationType, RiskLevel, RecommendationStatus
from .model import QwenModel
from .prompt_builder import PromptBuilder


class QwenArchitect:
    """Main Qwen-MLX Architect that generates optimization recommendations."""

    def __init__(self):
        """Initialize the Architect with configuration."""
        self.config = get_config()
        self.db = get_metrics_db()

        # Initialize model
        model_config = self.config.architect.model
        self.model = QwenModel(
            model_name=model_config.name,
            quantization=model_config.quantization,
            max_tokens=model_config.max_tokens,
            temperature=model_config.temperature
        )

        # Initialize prompt builder
        prompt_config = self.config.architect.prompt
        self.prompt_builder = PromptBuilder(
            include_schema=prompt_config.get('include_schema', True),
            include_workload_stats=prompt_config.get('include_workload_stats', True),
            include_current_config=prompt_config.get('include_current_config', True),
            max_workload_entries=prompt_config.get('max_workload_entries', 50)
        )

    def get_recent_workload_snapshots(self, limit: int = 50) -> List[WorkloadSnapshot]:
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

        rows = self.db.execute_raw(sql, {'limit': limit})

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
                total_execution_time_ms=float(row[8]),
                avg_execution_time_ms=float(row[9]),
                p50_latency_ms=float(row[10]) if row[10] else None,
                p95_latency_ms=float(row[11]) if row[11] else None,
                p99_latency_ms=float(row[12]) if row[12] else None,
                max_latency_ms=float(row[13]) if row[13] else None,
                min_latency_ms=float(row[14]) if row[14] else None,
                avg_rows_returned=float(row[15]) if row[15] else None,
                avg_rows_scanned=float(row[16]) if row[16] else None,
                avg_buffer_hits=float(row[17]) if row[17] else None,
                avg_buffer_misses=float(row[18]) if row[18] else None,
                error_count=row[19],
                error_rate=float(row[20]),
                impact_score=float(row[21])
            )
            snapshots.append(snapshot)

        return snapshots

    def get_recent_eval_results(self, limit: int = 5) -> List[EvalResult]:
        """Get recent evaluation results from database."""
        sql = """
            SELECT
                eval_timestamp,
                eval_type,
                environment,
                config_version,
                overall_score,
                p95_latency_ms,
                p99_latency_ms,
                error_rate,
                rag_mrr,
                rag_precision_at_k,
                rag_recall_at_k,
                slo_passed,
                test_count,
                passed_count,
                failed_count,
                notes
            FROM qwen_dba.eval_results
            ORDER BY eval_timestamp DESC
            LIMIT :limit
        """

        rows = self.db.execute_raw(sql, {'limit': limit})

        results = []
        for row in rows:
            result = EvalResult(
                eval_timestamp=row[0],
                eval_type=row[1],
                environment=row[2],
                config_version=row[3],
                overall_score=float(row[4]) if row[4] else None,
                p95_latency_ms=float(row[5]) if row[5] else None,
                p99_latency_ms=float(row[6]) if row[6] else None,
                error_rate=float(row[7]) if row[7] else None,
                rag_mrr=float(row[8]) if row[8] else None,
                rag_precision_at_k=float(row[9]) if row[9] else None,
                rag_recall_at_k=float(row[10]) if row[10] else None,
                slo_passed=row[11],
                test_count=row[12],
                passed_count=row[13],
                failed_count=row[14],
                notes=row[15]
            )
            results.append(result)

        return results

    def generate_recommendation(
        self,
        workload_snapshots: Optional[List[WorkloadSnapshot]] = None,
        eval_results: Optional[List[EvalResult]] = None,
        schema_info: Optional[Dict[str, Any]] = None,
        current_config: Optional[Dict[str, Any]] = None
    ) -> Optional[Recommendation]:
        """
        Generate a recommendation using Qwen-MLX.

        Args:
            workload_snapshots: Workload snapshots to analyze
            eval_results: Evaluation results to consider
            schema_info: Database schema information
            current_config: Current system configuration

        Returns:
            Recommendation object or None
        """
        # Get data if not provided
        if workload_snapshots is None:
            workload_snapshots = self.get_recent_workload_snapshots()

        if eval_results is None:
            eval_results = self.get_recent_eval_results()

        if not workload_snapshots:
            logger.warning("No workload data available for analysis")
            return None

        # Get focus areas from config
        focus_areas = self.config.architect.analysis.get('focus_areas', [])

        # Build prompt
        logger.info("Building analysis prompt")
        prompt = self.prompt_builder.build_analysis_prompt(
            workload_snapshots=workload_snapshots,
            eval_results=eval_results,
            schema_info=schema_info,
            current_config=current_config,
            focus_areas=focus_areas
        )

        # Generate recommendation using Qwen
        logger.info("Generating recommendation with Qwen-MLX")
        try:
            response = self.model.generate(prompt)
            logger.info(f"Qwen response: {response[:200]}...")

            # Parse JSON response
            recommendation_data = self._parse_response(response)

            if not recommendation_data:
                logger.error("Failed to parse recommendation from Qwen response")
                return None

            # Create Recommendation object
            recommendation = self._create_recommendation(recommendation_data)

            return recommendation

        except Exception as e:
            logger.error(f"Error generating recommendation: {e}")
            return None

    def _parse_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse JSON response from Qwen."""
        try:
            # Try to extract JSON from response
            # Sometimes the model includes additional text
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1

            if start_idx == -1 or end_idx == 0:
                return None

            json_str = response[start_idx:end_idx]
            return json.loads(json_str)

        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
            return None

    def _create_recommendation(self, data: Dict[str, Any]) -> Recommendation:
        """Create Recommendation object from parsed data."""
        recommendation_id = data.get('recommendation_id', str(uuid.uuid4()))

        # Map recommendation type
        rec_type_str = data.get('recommendation_type', 'config_tuning')
        rec_type_map = {
            'index': RecommendationType.INDEX,
            'query_rewrite': RecommendationType.QUERY_REWRITE,
            'schema_change': RecommendationType.SCHEMA_CHANGE,
            'config_tuning': RecommendationType.CONFIG_TUNING,
            'vector_params': RecommendationType.VECTOR_PARAMS
        }
        rec_type = rec_type_map.get(rec_type_str, RecommendationType.CONFIG_TUNING)

        # Map risk level
        risk_str = data.get('risk_level', 'medium')
        risk_map = {
            'low': RiskLevel.LOW,
            'medium': RiskLevel.MEDIUM,
            'high': RiskLevel.HIGH
        }
        risk_level = risk_map.get(risk_str, RiskLevel.MEDIUM)

        recommendation = Recommendation(
            recommendation_id=recommendation_id,
            recommendation_timestamp=datetime.utcnow(),
            status=RecommendationStatus.PENDING,
            priority=data.get('priority', 'medium'),
            recommendation_type=rec_type,
            title=data.get('title', 'Optimization Recommendation'),
            rationale=data.get('rationale', ''),
            config_patch=data.get('config_patch', {}),
            expected_effects=data.get('expected_effects', {}),
            expected_latency_improvement_percent=data.get('expected_effects', {}).get('latency_improvement_percent'),
            expected_cost_reduction_percent=data.get('expected_effects', {}).get('cost_reduction_percent'),
            risk_level=risk_level,
            risk_notes=data.get('risk_notes'),
            migration_sql=data.get('migration_sql'),
            rollback_sql=data.get('rollback_sql'),
            model_name=self.model.model_name,
            model_version=self.config.architect.model.quantization,
            confidence_score=data.get('confidence_score')
        )

        return recommendation

    def save_recommendation(self, recommendation: Recommendation) -> bool:
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

            self.db.execute_raw(sql, params)
            logger.info(f"Saved recommendation: {recommendation.recommendation_id}")
            return True

        except Exception as e:
            logger.error(f"Error saving recommendation: {e}")
            return False

    def run(self) -> Optional[Recommendation]:
        """
        Run the Architect: analyze workload and generate recommendation.

        Returns:
            Recommendation object or None
        """
        logger.info("Starting Qwen Architect")

        # Generate recommendation
        recommendation = self.generate_recommendation()

        if recommendation:
            # Save to database
            self.save_recommendation(recommendation)

            # Output to configured destination
            self._output_recommendation(recommendation)

        logger.info("Qwen Architect completed")
        return recommendation

    def _output_recommendation(self, recommendation: Recommendation):
        """Output recommendation to configured destination."""
        output_config = self.config.architect.output
        destination = output_config.get('destination', 'database')

        # Already saved to database
        if destination == 'database':
            return

        # Output to file
        if destination == 'file':
            import os
            os.makedirs('recommendations', exist_ok=True)
            filename = f"recommendations/recommendation_{recommendation.recommendation_id}.json"
            with open(filename, 'w') as f:
                json.dump(recommendation.dict(), f, indent=2, default=str)
            logger.info(f"Recommendation saved to file: {filename}")

        # Output to Slack (placeholder)
        if destination == 'slack':
            logger.info("Slack output not implemented yet")
            # TODO: Implement Slack webhook
