"""Log parsers for different data sources."""

import re
import json
from datetime import datetime
from typing import Iterator, Optional, Dict, Any
from pathlib import Path

from ..common.models import QueryLog, QuerySource


class LogParser:
    """Base class for log parsers."""

    def parse_file(self, file_path: str) -> Iterator[QueryLog]:
        """Parse a log file and yield QueryLog entries."""
        raise NotImplementedError


class PostgresLogParser(LogParser):
    """Parser for PostgreSQL log files."""

    # Pattern for standard PostgreSQL log format
    # Example: 2025-01-09 12:34:56.789 UTC [12345] LOG:  duration: 123.456 ms  statement: SELECT * FROM users WHERE id = 1
    LOG_PATTERN = re.compile(
        r'(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} \w+) '
        r'\[(?P<pid>\d+)\] '
        r'(?P<level>\w+):\s+'
        r'duration: (?P<duration>[\d.]+) ms\s+'
        r'statement: (?P<statement>.*?)$',
        re.MULTILINE
    )

    def __init__(self, source: str = QuerySource.POSTGRES):
        """Initialize parser."""
        self.source = source

    def parse_file(self, file_path: str) -> Iterator[QueryLog]:
        """Parse PostgreSQL log file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Log file not found: {file_path}")

        with open(path, 'r') as f:
            content = f.read()

        for match in self.LOG_PATTERN.finditer(content):
            try:
                # Parse timestamp
                timestamp_str = match.group('timestamp')
                timestamp = datetime.strptime(
                    timestamp_str.rsplit(' ', 1)[0],  # Remove timezone
                    '%Y-%m-%d %H:%M:%S.%f'
                )

                # Parse duration
                duration_ms = float(match.group('duration'))

                # Get query
                query = match.group('statement').strip()

                # Skip empty queries
                if not query:
                    continue

                yield QueryLog(
                    timestamp=timestamp,
                    query=query,
                    execution_time_ms=duration_ms,
                    success=True,
                    source=self.source
                )

            except Exception as e:
                # Log parsing error and continue
                print(f"Error parsing log entry: {e}")
                continue


class JSONLogParser(LogParser):
    """Parser for JSON-formatted log files."""

    def __init__(self, source: str = QuerySource.APPLICATION):
        """Initialize parser."""
        self.source = source

    def parse_file(self, file_path: str) -> Iterator[QueryLog]:
        """Parse JSON log file (one JSON object per line)."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Log file not found: {file_path}")

        with open(path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                    yield self._parse_entry(entry)
                except json.JSONDecodeError as e:
                    print(f"Error parsing JSON at line {line_num}: {e}")
                    continue
                except Exception as e:
                    print(f"Error processing entry at line {line_num}: {e}")
                    continue

    def _parse_entry(self, entry: Dict[str, Any]) -> QueryLog:
        """Parse a single JSON log entry."""
        # Flexible field mapping - adjust based on your log format
        timestamp_str = entry.get('timestamp') or entry.get('time') or entry.get('ts')
        if isinstance(timestamp_str, str):
            # Try multiple timestamp formats
            for fmt in ['%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
                try:
                    timestamp = datetime.strptime(timestamp_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                timestamp = datetime.utcnow()
        else:
            timestamp = datetime.utcnow()

        return QueryLog(
            timestamp=timestamp,
            query=entry.get('query', ''),
            execution_time_ms=float(entry.get('duration_ms', 0) or entry.get('latency_ms', 0)),
            rows_returned=entry.get('rows_returned'),
            rows_scanned=entry.get('rows_scanned'),
            success=entry.get('success', True),
            error_message=entry.get('error'),
            source=self.source,
            database=entry.get('database'),
            user=entry.get('user')
        )


class VectorDBLogParser(LogParser):
    """Parser for vector database query logs."""

    def __init__(self):
        """Initialize parser."""
        self.source = QuerySource.VECTOR_DB

    def parse_file(self, file_path: str) -> Iterator[QueryLog]:
        """Parse vector DB log file (JSON format)."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Log file not found: {file_path}")

        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)

                    # Extract timestamp
                    timestamp_str = entry.get('timestamp')
                    if timestamp_str:
                        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    else:
                        timestamp = datetime.utcnow()

                    # Vector search queries are represented as JSON
                    query = json.dumps({
                        'collection': entry.get('collection'),
                        'query_vector': '[...]',  # Truncate actual vector
                        'top_k': entry.get('top_k'),
                        'filter': entry.get('filter')
                    })

                    yield QueryLog(
                        timestamp=timestamp,
                        query=query,
                        query_type="VECTOR_SEARCH",
                        execution_time_ms=float(entry.get('latency_ms', 0)),
                        rows_returned=entry.get('results_count'),
                        success=entry.get('status') == 'success',
                        error_message=entry.get('error'),
                        source=self.source
                    )

                except Exception as e:
                    print(f"Error parsing vector DB log entry: {e}")
                    continue


def get_parser(source_type: str, log_format: str = "standard") -> LogParser:
    """
    Get appropriate parser based on source type and format.

    Args:
        source_type: Type of log source (postgres, vector, application)
        log_format: Format of the logs (standard, json, csv)

    Returns:
        Appropriate LogParser instance
    """
    if source_type == "postgres_logs":
        if log_format == "json":
            return JSONLogParser(source=QuerySource.POSTGRES)
        return PostgresLogParser()
    elif source_type == "vector_logs":
        return VectorDBLogParser()
    elif source_type == "application_logs":
        return JSONLogParser(source=QuerySource.APPLICATION)
    else:
        raise ValueError(f"Unknown source type: {source_type}")
