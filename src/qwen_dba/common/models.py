"""Data models for Qwen-DBA."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum

from pydantic import BaseModel, Field


class QueryType(str, Enum):
    """Types of database queries."""
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    CREATE = "CREATE"
    ALTER = "ALTER"
    DROP = "DROP"
    VECTOR_SEARCH = "VECTOR_SEARCH"
    OTHER = "OTHER"


class QuerySource(str, Enum):
    """Source of the query."""
    POSTGRES = "postgres"
    VECTOR_DB = "vector_db"
    CACHE = "cache"
    APPLICATION = "application"
    OTHER = "other"


class WorkloadSnapshot(BaseModel):
    """Aggregated workload data for a query pattern."""

    # Identification
    snapshot_timestamp: datetime
    window_start: datetime
    window_end: datetime
    query_fingerprint: str
    query_type: Optional[str] = None
    query_source: str = QuerySource.POSTGRES
    example_query: Optional[str] = None

    # Statistics
    execution_count: int = 0
    total_execution_time_ms: float = 0.0
    avg_execution_time_ms: float = 0.0
    p50_latency_ms: Optional[float] = None
    p95_latency_ms: Optional[float] = None
    p99_latency_ms: Optional[float] = None
    max_latency_ms: Optional[float] = None
    min_latency_ms: Optional[float] = None

    # Resource usage
    avg_rows_returned: Optional[float] = None
    avg_rows_scanned: Optional[float] = None
    avg_buffer_hits: Optional[float] = None
    avg_buffer_misses: Optional[float] = None

    # Errors
    error_count: int = 0
    error_rate: float = 0.0

    # Impact
    impact_score: float = 0.0

    def calculate_impact_score(self) -> float:
        """Calculate impact score (frequency * avg latency)."""
        self.impact_score = self.execution_count * self.avg_execution_time_ms
        return self.impact_score


class EvalResult(BaseModel):
    """Evaluation harness result."""

    eval_timestamp: datetime
    eval_type: str
    environment: str = "production"
    config_version: Optional[str] = None

    # Metrics
    metrics: Dict[str, Any] = Field(default_factory=dict)
    overall_score: Optional[float] = None
    p95_latency_ms: Optional[float] = None
    p99_latency_ms: Optional[float] = None
    error_rate: Optional[float] = None

    # RAG metrics
    rag_mrr: Optional[float] = None
    rag_precision_at_k: Optional[float] = None
    rag_recall_at_k: Optional[float] = None

    # SLO
    slo_passed: bool = False
    slo_violations: Dict[str, Any] = Field(default_factory=dict)

    # Test details
    test_count: Optional[int] = None
    passed_count: Optional[int] = None
    failed_count: Optional[int] = None

    notes: Optional[str] = None


class RecommendationStatus(str, Enum):
    """Status of a recommendation."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"
    ROLLED_BACK = "rolled_back"


class RecommendationType(str, Enum):
    """Type of recommendation."""
    INDEX = "index"
    QUERY_REWRITE = "query_rewrite"
    SCHEMA_CHANGE = "schema_change"
    CONFIG_TUNING = "config_tuning"
    VECTOR_PARAMS = "vector_params"


class RiskLevel(str, Enum):
    """Risk level of a recommendation."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Recommendation(BaseModel):
    """A recommendation from the Qwen-MLX Architect."""

    # Metadata
    recommendation_id: str
    recommendation_timestamp: datetime
    status: RecommendationStatus = RecommendationStatus.PENDING
    priority: str = "medium"

    # Context
    workload_snapshot_ids: List[int] = Field(default_factory=list)
    eval_result_ids: List[int] = Field(default_factory=list)

    # Content
    recommendation_type: RecommendationType
    title: str
    rationale: str
    config_patch: Dict[str, Any]

    # Expected effects
    expected_effects: Dict[str, Any] = Field(default_factory=dict)
    expected_latency_improvement_percent: Optional[float] = None
    expected_cost_reduction_percent: Optional[float] = None

    # Risk
    risk_level: RiskLevel = RiskLevel.MEDIUM
    risk_notes: Optional[str] = None

    # Migration
    migration_sql: Optional[str] = None
    rollback_sql: Optional[str] = None

    # Implementation tracking
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    implemented_by: Optional[str] = None
    implemented_at: Optional[datetime] = None

    # Results
    actual_effects: Dict[str, Any] = Field(default_factory=dict)
    implementation_notes: Optional[str] = None

    # Model info
    model_name: Optional[str] = None
    model_version: Optional[str] = None
    confidence_score: Optional[float] = None


class QueryLog(BaseModel):
    """A single query log entry."""

    timestamp: datetime
    query: str
    query_fingerprint: Optional[str] = None
    query_type: Optional[str] = None

    # Performance
    execution_time_ms: float
    rows_returned: Optional[int] = None
    rows_scanned: Optional[int] = None

    # Resources
    buffer_hits: Optional[int] = None
    buffer_misses: Optional[int] = None

    # Status
    success: bool = True
    error_message: Optional[str] = None

    # Source
    source: str = QuerySource.POSTGRES
    database: Optional[str] = None
    user: Optional[str] = None
