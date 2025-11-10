"""Custom exceptions for Qwen-DBA."""


class QwenDbaError(Exception):
    """Base exception for Qwen-DBA application errors."""
    pass


class ConfigError(QwenDbaError):
    """Custom exception for configuration errors."""
    pass


class DatabaseError(QwenDbaError):
    """Custom exception for database errors."""
    pass


class ProfilerError(QwenDbaError):
    """Custom exception for profiler errors."""
    pass


class EvalHarnessError(QwenDbaError):
    """Custom exception for evaluation harness errors."""
    pass


class ArchitectError(QwenDbaError):
    """Custom exception for Qwen Architect errors."""
    pass
