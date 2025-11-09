"""Manual tests for eval harness without pytest."""

import sys
import json
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from qwen_dba.eval_harness.evaluators import RAGAccuracyEvaluator


def test_rag_evaluator():
    """Test RAG accuracy evaluator."""
    print("Testing RAGAccuracyEvaluator...")

    # Create a sample dataset
    dataset = [
        {
            "query": "What is the capital of France?",
            "retrieved": ["doc_123", "doc_456", "doc_789"],
            "relevant": ["doc_123"]
        },
        {
            "query": "How do I reset my password?",
            "retrieved": ["doc_234", "doc_345", "doc_456"],
            "relevant": ["doc_234", "doc_345"]
        },
        {
            "query": "What are the shipping options?",
            "retrieved": ["doc_567", "doc_678", "doc_789"],
            "relevant": ["doc_567"]
        }
    ]

    # Write to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(dataset, f)
        dataset_file = f.name

    try:
        evaluator = RAGAccuracyEvaluator(dataset_file, metric="mrr")

        # Test MRR calculation
        mrr = evaluator.calculate_mrr(dataset)
        print(f"  MRR: {mrr:.4f}")
        assert 0 <= mrr <= 1, f"MRR should be between 0 and 1, got {mrr}"
        assert mrr > 0, "MRR should be > 0 for our test dataset"

        # Test Precision@K
        precision = evaluator.calculate_precision_at_k(dataset, k=3)
        print(f"  Precision@3: {precision:.4f}")
        assert 0 <= precision <= 1, f"Precision should be between 0 and 1, got {precision}"

        # Test Recall@K
        recall = evaluator.calculate_recall_at_k(dataset, k=3)
        print(f"  Recall@3: {recall:.4f}")
        assert 0 <= recall <= 1, f"Recall should be between 0 and 1, got {recall}"

        # Test full evaluation
        metrics = evaluator.evaluate()
        print(f"  Full evaluation metrics: {list(metrics.keys())}")

        assert "mrr" in metrics, "Should have MRR metric"
        assert "precision_at_10" in metrics, "Should have precision metric"
        assert "recall_at_10" in metrics, "Should have recall metric"
        assert "test_count" in metrics, "Should have test count"
        assert metrics["test_count"] == 3, f"Expected 3 test cases, got {metrics['test_count']}"

        print("PASS: RAGAccuracyEvaluator tests\n")

    finally:
        import os
        os.unlink(dataset_file)


def test_mrr_edge_cases():
    """Test MRR with edge cases."""
    print("Testing MRR edge cases...")

    evaluator = RAGAccuracyEvaluator("dummy.json", metric="mrr")

    # Case 1: Perfect ranking (relevant doc is first)
    perfect = [
        {
            "retrieved": ["doc_1", "doc_2", "doc_3"],
            "relevant": ["doc_1"]
        }
    ]
    mrr = evaluator.calculate_mrr(perfect)
    print(f"  Perfect ranking MRR: {mrr:.4f}")
    assert mrr == 1.0, f"Perfect ranking should have MRR=1.0, got {mrr}"

    # Case 2: Relevant doc is second
    second_place = [
        {
            "retrieved": ["doc_1", "doc_2", "doc_3"],
            "relevant": ["doc_2"]
        }
    ]
    mrr = evaluator.calculate_mrr(second_place)
    print(f"  Second place MRR: {mrr:.4f}")
    assert mrr == 0.5, f"Second place should have MRR=0.5, got {mrr}"

    # Case 3: No relevant docs retrieved
    no_relevant = [
        {
            "retrieved": ["doc_1", "doc_2", "doc_3"],
            "relevant": ["doc_999"]
        }
    ]
    mrr = evaluator.calculate_mrr(no_relevant)
    print(f"  No relevant docs MRR: {mrr:.4f}")
    assert mrr == 0.0, f"No relevant docs should have MRR=0.0, got {mrr}"

    print("PASS: MRR edge cases tests\n")


if __name__ == "__main__":
    try:
        test_rag_evaluator()
        test_mrr_edge_cases()
        print("\nAll eval harness tests passed")
    except AssertionError as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
