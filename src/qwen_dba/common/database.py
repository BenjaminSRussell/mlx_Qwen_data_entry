"""Database connection utilities."""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from .config import get_config


class Database:
    """Database connection manager."""

    def __init__(self, connection_string: str):
        """Initialize database connection."""
        self.engine = create_engine(
            connection_string,
            poolclass=NullPool,  # Use NullPool for simplicity in Phase 1
            echo=False
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get database session context manager."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def execute_raw(self, sql: str, params: dict = None) -> list:
        """Execute raw SQL query."""
        with self.get_session() as session:
            result = session.execute(text(sql), params or {})
            if result.returns_rows:
                return result.fetchall()
            return []

    def execute_script(self, sql_file_path: str):
        """Execute SQL script file."""
        with open(sql_file_path, 'r') as f:
            sql = f.read()

        with self.get_session() as session:
            # Split by semicolons and execute each statement
            statements = [s.strip() for s in sql.split(';') if s.strip()]
            for statement in statements:
                session.execute(text(statement))

    def schema_exists(self, schema_name: str) -> bool:
        """Check if a schema exists."""
        sql = "SELECT 1 FROM information_schema.schemata WHERE schema_name = :schema_name"
        result = self.execute_raw(sql, {'schema_name': schema_name})
        return bool(result)


# Global database instances
_primary_db = None
_metrics_db = None


def get_primary_db() -> Database:
    """Get primary database connection."""
    global _primary_db
    if _primary_db is None:
        config = get_config()
        _primary_db = Database(config.get_primary_db_connection_string())
    return _primary_db


def get_metrics_db() -> Database:
    """Get metrics database connection."""
    global _metrics_db
    if _metrics_db is None:
        config = get_config()
        _metrics_db = Database(config.get_metrics_db_connection_string())
    return _metrics_db
