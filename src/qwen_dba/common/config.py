"""Configuration management for Qwen-DBA."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv


# Load environment variables
load_dotenv()


class DatabaseConfig(BaseModel):
    """Database connection configuration."""
    type: str = "postgresql"
    host: str = "localhost"
    port: int = 5432
    database: str
    username: str
    password_env: str

    def get_connection_string(self) -> str:
        """Get SQLAlchemy connection string."""
        password = os.getenv(self.password_env, "")
        return f"{self.type}://{self.username}:{password}@{self.host}:{self.port}/{self.database}"


class VectorDBConfig(BaseModel):
    """Vector database configuration."""
    enabled: bool = False
    type: str = "chroma"
    host: str = "localhost"
    port: int = 8000
    collection: str = "embeddings"


class ProfilerConfig(BaseModel):
    """Workload profiler configuration."""
    enabled: bool = True
    sources: Dict[str, Any] = Field(default_factory=dict)
    aggregation: Dict[str, Any] = Field(default_factory=dict)
    fingerprint: Dict[str, Any] = Field(default_factory=dict)


class EvalHarnessConfig(BaseModel):
    """Evaluation harness configuration."""
    enabled: bool = True
    datasets: Dict[str, Any] = Field(default_factory=dict)
    slos: Dict[str, Any] = Field(default_factory=dict)
    schedule: Dict[str, str] = Field(default_factory=dict)


class ModelConfig(BaseModel):
    """Qwen-MLX model configuration."""
    name: str = "Qwen/Qwen2.5-7B-Instruct"
    quantization: str = "4bit"
    max_tokens: int = 4096
    temperature: float = 0.7


class ArchitectConfig(BaseModel):
    """Qwen-MLX Architect configuration."""
    enabled: bool = True
    model: ModelConfig = Field(default_factory=ModelConfig)
    prompt: Dict[str, Any] = Field(default_factory=dict)
    analysis: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)
    schedule: Dict[str, str] = Field(default_factory=dict)


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = "INFO"
    format: str = "json"
    output: str = "stdout"
    file_path: Optional[str] = None


class MetricsConfig(BaseModel):
    """Prometheus metrics configuration."""
    enabled: bool = True
    port: int = 9090
    path: str = "/metrics"


class Config(BaseModel):
    """Main configuration for Qwen-DBA."""
    databases: Dict[str, DatabaseConfig]
    vector_db: VectorDBConfig = Field(default_factory=VectorDBConfig)
    profiler: ProfilerConfig = Field(default_factory=ProfilerConfig)
    eval_harness: EvalHarnessConfig = Field(default_factory=EvalHarnessConfig)
    architect: ArchitectConfig = Field(default_factory=ArchitectConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)

    @classmethod
    def load_from_file(cls, config_path: str = "config.yaml") -> "Config":
        """Load configuration from YAML file."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(path, "r") as f:
            config_dict = yaml.safe_load(f)

        return cls(**config_dict)

    def get_primary_db_connection_string(self) -> str:
        """Get primary database connection string."""
        return self.databases["primary"].get_connection_string()

    def get_metrics_db_connection_string(self) -> str:
        """Get metrics database connection string."""
        return self.databases["metrics"].get_connection_string()


# Global configuration instance
_config: Optional[Config] = None


def get_config(config_path: str = "config.yaml") -> Config:
    """Get global configuration instance."""
    global _config
    if _config is None:
        _config = Config.load_from_file(config_path)
    return _config


def reload_config(config_path: str = "config.yaml") -> Config:
    """Reload configuration from file."""
    global _config
    _config = Config.load_from_file(config_path)
    return _config
