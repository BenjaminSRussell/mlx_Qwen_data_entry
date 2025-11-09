"""Query fingerprinting for workload analysis."""

import re
import hashlib
from typing import Optional


class QueryFingerprinter:
    """Fingerprints SQL queries by normalizing them."""

    def __init__(
        self,
        normalize_literals: bool = True,
        normalize_whitespace: bool = True,
        case_insensitive: bool = True
    ):
        """Initialize fingerprinter with normalization options."""
        self.normalize_literals = normalize_literals
        self.normalize_whitespace = normalize_whitespace
        self.case_insensitive = case_insensitive

    def fingerprint(self, query: str) -> str:
        """Generate normalized query fingerprint.

        Args:
            query: SQL query to fingerprint

        Returns:
            Normalized query fingerprint
        """
        normalized = query

        if self.case_insensitive:
            normalized = normalized.upper()

        if self.normalize_literals:
            normalized = re.sub(r"'[^']*'", "?", normalized)
            normalized = re.sub(r'"[^"]*"', "?", normalized)
            normalized = re.sub(r'\b\d+\b', '?', normalized)
            normalized = re.sub(r'\b\d+\.\d+\b', '?', normalized)
            normalized = re.sub(r'\([^)]*\)', '(?)', normalized)

        if self.normalize_whitespace:
            normalized = re.sub(r'\s+', ' ', normalized)
            normalized = normalized.strip()

        return normalized

    def get_query_hash(self, query: str) -> str:
        """Get SHA-256 hash of query fingerprint."""
        fingerprint = self.fingerprint(query)
        return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]

    def extract_query_type(self, query: str) -> Optional[str]:
        """Extract query type (SELECT, INSERT, UPDATE, etc.)."""
        query_upper = query.strip().upper()

        query_types = [
            "SELECT", "INSERT", "UPDATE", "DELETE",
            "CREATE", "ALTER", "DROP", "TRUNCATE",
            "BEGIN", "COMMIT", "ROLLBACK", "WITH"
        ]

        for qtype in query_types:
            if query_upper.startswith(qtype):
                return qtype

        return "OTHER"

    def extract_tables(self, query: str) -> list[str]:
        """Extract table names from query using simple heuristics."""
        tables = []
        from_matches = re.finditer(
            r'\bFROM\s+(\w+(?:\.\w+)?)',
            query,
            re.IGNORECASE
        )
        for match in from_matches:
            tables.append(match.group(1))

        join_matches = re.finditer(r'\bJOIN\s+(\w+(?:\.\w+)?)', query, re.IGNORECASE)
        for match in join_matches:
            tables.append(match.group(1))

        update_matches = re.finditer(r'\b(?:UPDATE|DELETE FROM)\s+(\w+(?:\.\w+)?)', query, re.IGNORECASE)
        for match in update_matches:
            tables.append(match.group(1))

        insert_matches = re.finditer(r'\bINSERT INTO\s+(\w+(?:\.\w+)?)', query, re.IGNORECASE)
        for match in insert_matches:
            tables.append(match.group(1))

        return list(set(tables))
