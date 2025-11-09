"""Tests for the evaluation harness."""

import pytest
from datetime import datetime

from qwen_dba.eval_harness.evaluators import RAGAccuracyEvaluator


class TestRAGAccuracyEvaluator:
    """Test RAG accuracy evaluator."""

    def test_calculate_mrr(self, sample_rag_dataset):
        """Test Mean Reciprocal Rank calculation."""
        evaluator = RAGAccuracyEvaluator(str(sample_rag_dataset), metric="mrr")

        results = evaluator.load_dataset()
        mrr = evaluator.calculate_mrr(results)

        # MRR should be between 0 and 1
        assert 0 <= mrr <= 1
        # With our sample data, MRR should be > 0
        assert mrr > 0

    def test_calculate_precision_at_k(self, sample_rag_dataset):
        """Test Precision@K calculation."""
        evaluator = RAGAccuracyEvaluator(str(sample_rag_dataset), metric="mrr")

        results = evaluator.load_dataset()
        precision = evaluator.calculate_precision_at_k(results, k=3)

        # Precision should be between 0 and 1
        assert 0 <= precision <= 1

    def test_calculate_recall_at_k(self, sample_rag_dataset):
        """Test Recall@K calculation."""
        evaluator = RAGAccuracyEvaluator(str(sample_rag_dataset), metric="mrr")

        results = evaluator.load_dataset()
        recall = evaluator.calculate_recall_at_k(results, k=3)

        # Recall should be between 0 and 1
        assert 0 <= recall <= 1

    def test_evaluate(self, sample_rag_dataset):
        """Test full evaluation."""
        evaluator = RAGAccuracyEvaluator(str(sample_rag_dataset), metric="mrr")

        metrics = evaluator.evaluate()

        assert "mrr" in metrics
        assert "precision_at_10" in metrics
        assert "recall_at_10" in metrics
        assert "test_count" in metrics
        assert metrics["test_count"] == 3  # Sample dataset has 3 entries


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
