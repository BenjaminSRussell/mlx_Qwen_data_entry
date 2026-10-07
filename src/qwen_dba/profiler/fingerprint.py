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
            # String literals (single quotes); keep double-quoted identifiers
            normalized = re.sub(r"'([^']|'')*'", "?", normalized)
            # Numeric literals: replace full number tokens including decimals first
            normalized = re.sub(r'\b\d+\.\d+\b', '?', normalized)
            normalized = re.sub(r'\b\d+\b', '?', normalized)
            # Collapse IN-lists / value tuples but NOT SELECT column lists:
            # only replace parenthetical groups that look like value lists (all ?/,/space)
            def _collapse_value_lists(match: re.Match) -> str:
                inner = match.group(1)
                if re.fullmatch(r'[\s?,]*', inner):
                    return '(?)'
                return match.group(0)
            normalized = re.sub(r'\(([^()]*)\)', _collapse_value_lists, normalized)

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
        # Strip EXTRACT(...) / CAST(...) style function calls so their
        # keywords are not mistaken for tables.
        scrubbed = re.sub(
            r'\bEXTRACT\s*\([^)]*\)',
            ' ',
            query,
            flags=re.IGNORECASE,
        )
        tables = []
        patterns = [
            r'\bFROM\s+("?[\w]+"?\.?\w*)',
            r'\bJOIN\s+("?[\w]+"?\.?\w*)',
            r'\bUPDATE\s+("?[\w]+"?\.?\w*)',
            r'\bDELETE\s+FROM\s+("?[\w]+"?\.?\w*)',
            r'\bINSERT\s+INTO\s+("?[\w]+"?\.?\w*)',
        ]
        for pat in patterns:
            for match in re.finditer(pat, scrubbed, re.IGNORECASE):
                name = match.group(1).strip()
                # Ignore obvious non-tables
                if name.upper() in {'SELECT', 'WHERE', 'SET', 'VALUES', 'LATERAL'}:
                    continue
                tables.append(name.strip('"'))
        return list(dict.fromkeys(tables))
