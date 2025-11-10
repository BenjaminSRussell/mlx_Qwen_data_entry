"""Pytest configuration and fixtures."""

import os
import sys
import tempfile
import pytest
from pathlib import Path

# Add src directory to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_log_file(temp_dir):
    """Create a sample PostgreSQL log file."""
    log_file = temp_dir / "postgres.log"
    log_content = """2025-01-09 10:30:45.123 UTC [12345] LOG:  duration: 234.567 ms  statement: SELECT * FROM users WHERE email = 'user@example.com'
2025-01-09 10:30:46.456 UTC [12346] LOG:  duration: 45.123 ms  statement: SELECT id, name FROM products WHERE category = 'electronics'
2025-01-09 10:30:47.789 UTC [12347] LOG:  duration: 567.890 ms  statement: SELECT * FROM orders WHERE user_id = 123 AND status = 'pending'
2025-01-09 10:30:48.012 UTC [12348] LOG:  duration: 12.345 ms  statement: INSERT INTO logs (timestamp, message) VALUES ('2025-01-09 10:30:48', 'User login')
2025-01-09 10:30:49.234 UTC [12349] LOG:  duration: 890.123 ms  statement: UPDATE users SET last_login = NOW() WHERE id = 123
2025-01-09 10:30:50.234 UTC [12350] LOG:  duration: 234.567 ms  statement: SELECT * FROM users WHERE email = 'user2@example.com'
2025-01-09 10:30:51.234 UTC [12351] LOG:  duration: 234.567 ms  statement: SELECT * FROM users WHERE email = 'user3@example.com'
2025-01-09 10:30:52.234 UTC [12352] LOG:  duration: 234.567 ms  statement: SELECT * FROM users WHERE email = 'user4@example.com'
2025-01-09 10:30:53.234 UTC [12353] LOG:  duration: 234.567 ms  statement: SELECT * FROM users WHERE email = 'user5@example.com'
2025-01-09 10:30:54.234 UTC [12354] LOG:  duration: 234.567 ms  statement: SELECT * FROM users WHERE email = 'user6@example.com'
"""
    log_file.write_text(log_content)
    return log_file


@pytest.fixture
def sample_rag_dataset(temp_dir):
    """Create a sample RAG evaluation dataset."""
    import json

    dataset_file = temp_dir / "rag_golden_set.json"
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

    with open(dataset_file, 'w') as f:
        json.dump(dataset, f)

    return dataset_file
