"""Main evaluation harness orchestration."""

from datetime import datetime
from typing import Dict, Any, List, Optional

from ..common.config import get_config
from ..common.database import get_metrics_db
from ..common.logger import logger
from ..common.models import EvalResult
from .evaluators import RAGAccuracyEvaluator, SLOEvaluator, BusinessMetricsEvaluator


class EvalHarness:
    """Main evaluation harness that orchestrates all evaluations."""

    def __init__(self):
        """Initialize evaluation harness with configuration."""
        self.config = get_config()
        self.db = get_metrics_db()

    def run_rag_evaluation(self) -> Optional[EvalResult]:
        """Run RAG accuracy evaluation."""
        datasets = self.config.eval_harness.datasets

        if 'rag_accuracy' not in datasets:
            logger.info("RAG accuracy evaluation not configured")
            return None

        rag_config = datasets['rag_accuracy']
        dataset_path = rag_config.get('path')
        metric = rag_config.get('metric', 'mrr')

        if not dataset_path:
            logger.warning("RAG dataset path not configured")
            return None

        evaluator = RAGAccuracyEvaluator(dataset_path, metric)
        metrics = evaluator.evaluate()

        result = EvalResult(
            eval_timestamp=datetime.utcnow(),
            eval_type='rag_accuracy',
            metrics=metrics,
            rag_mrr=metrics.get('mrr'),
            rag_precision_at_k=metrics.get('precision_at_10'),
            rag_recall_at_k=metrics.get('recall_at_10'),
            test_count=metrics.get('test_count'),
            overall_score=metrics.get('mrr')  # Use MRR as overall score
        )

        return result

    def run_slo_evaluation(self) -> EvalResult:
        """Run SLO compliance evaluation."""
        slos = self.config.eval_harness.slos

        evaluator = SLOEvaluator(
            p95_threshold_ms=slos.get('p95_latency_ms', 500),
            p99_threshold_ms=slos.get('p99_latency_ms', 1000),
            error_rate_threshold=slos.get('error_rate_percent', 0.1) / 100
        )

        metrics = evaluator.evaluate()

        result = EvalResult(
            eval_timestamp=datetime.utcnow(),
            eval_type='slo_check',
            metrics=metrics,
            p95_latency_ms=metrics.get('p95_latency_ms'),
            p99_latency_ms=metrics.get('p99_latency_ms'),
            error_rate=metrics.get('error_rate'),
            slo_passed=metrics.get('slo_passed', False),
            slo_violations=metrics.get('violations', {})
        )

        return result

    def run_business_metrics_evaluation(self) -> Optional[EvalResult]:
        """Run business metrics evaluation."""
        datasets = self.config.eval_harness.datasets

        if 'business_metrics' not in datasets:
            logger.info("Business metrics evaluation not configured")
            return None

        biz_config = datasets['business_metrics']
        if not biz_config.get('enabled', False):
            return None

        metric_name = biz_config.get('metric', 'search_relevance')

        evaluator = BusinessMetricsEvaluator(metric_name)
        metrics = evaluator.evaluate()

        result = EvalResult(
            eval_timestamp=datetime.utcnow(),
            eval_type='business_metrics',
            metrics=metrics,
            overall_score=metrics.get('score')
        )

        return result

    def save_result(self, result: EvalResult) -> bool:
        """
        Save evaluation result to database.

        Args:
            result: EvalResult object

        Returns:
            True if saved successfully
        """
        try:
            sql = """
                INSERT INTO qwen_dba.eval_results (
                    eval_timestamp,
                    eval_type,
                    environment,
                    config_version,
                    metrics,
                    overall_score,
                    p95_latency_ms,
                    p99_latency_ms,
                    error_rate,
                    rag_mrr,
                    rag_precision_at_k,
                    rag_recall_at_k,
                    slo_passed,
                    slo_violations,
                    test_count,
                    passed_count,
                    failed_count,
                    notes
                ) VALUES (
                    :eval_timestamp,
                    :eval_type,
                    :environment,
                    :config_version,
                    :metrics,
                    :overall_score,
                    :p95_latency_ms,
                    :p99_latency_ms,
                    :error_rate,
                    :rag_mrr,
                    :rag_precision_at_k,
                    :rag_recall_at_k,
                    :slo_passed,
                    :slo_violations,
                    :test_count,
                    :passed_count,
                    :failed_count,
                    :notes
                )
            """

            import json

            params = {
                'eval_timestamp': result.eval_timestamp,
                'eval_type': result.eval_type,
                'environment': result.environment,
                'config_version': result.config_version,
                'metrics': json.dumps(result.metrics),
                'overall_score': result.overall_score,
                'p95_latency_ms': result.p95_latency_ms,
                'p99_latency_ms': result.p99_latency_ms,
                'error_rate': result.error_rate,
                'rag_mrr': result.rag_mrr,
                'rag_precision_at_k': result.rag_precision_at_k,
                'rag_recall_at_k': result.rag_recall_at_k,
                'slo_passed': result.slo_passed,
                'slo_violations': json.dumps(result.slo_violations),
                'test_count': result.test_count,
                'passed_count': result.passed_count,
                'failed_count': result.failed_count,
                'notes': result.notes
            }

            self.db.execute_raw(sql, params)
            logger.info(f"Saved {result.eval_type} evaluation result")
            return True

        except Exception as e:
            logger.error(f"Error saving evaluation result: {e}")
            return False

    def run_all(self) -> List[EvalResult]:
        """
        Run all configured evaluations.

        Returns:
            List of EvalResult objects
        """
        logger.info("Starting evaluation harness")

        results = []

        # Run RAG evaluation
        rag_result = self.run_rag_evaluation()
        if rag_result:
            results.append(rag_result)
            self.save_result(rag_result)

        # Run SLO evaluation
        slo_result = self.run_slo_evaluation()
        results.append(slo_result)
        self.save_result(slo_result)

        # Run business metrics evaluation
        biz_result = self.run_business_metrics_evaluation()
        if biz_result:
            results.append(biz_result)
            self.save_result(biz_result)

        logger.info(f"Evaluation harness completed: {len(results)} evaluations run")

        return results

    def get_latest_results(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get latest evaluation results from database.

        Args:
            limit: Number of results to retrieve

        Returns:
            List of evaluation result dictionaries
        """
        sql = """
            SELECT
                eval_timestamp,
                eval_type,
                overall_score,
                p95_latency_ms,
                p99_latency_ms,
                error_rate,
                rag_mrr,
                slo_passed
            FROM qwen_dba.eval_results
            ORDER BY eval_timestamp DESC
            LIMIT :limit
        """

        rows = self.db.execute_raw(sql, {'limit': limit})

        results = []
        for row in rows:
            results.append({
                'eval_timestamp': row[0],
                'eval_type': row[1],
                'overall_score': float(row[2]) if row[2] else None,
                'p95_latency_ms': float(row[3]) if row[3] else None,
                'p99_latency_ms': float(row[4]) if row[4] else None,
                'error_rate': float(row[5]) if row[5] else None,
                'rag_mrr': float(row[6]) if row[6] else None,
                'slo_passed': row[7]
            })

        return results
