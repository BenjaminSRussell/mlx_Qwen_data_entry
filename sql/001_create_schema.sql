-- Qwen-DBA Phase 1 Database Schema
-- This schema stores workload snapshots, evaluation results, and recommendations

-- Create schema for Qwen-DBA metadata
CREATE SCHEMA IF NOT EXISTS qwen_dba;

-- ============================================================================
-- Workload Snapshots
-- ============================================================================

-- Stores aggregated query workload data
CREATE TABLE IF NOT EXISTS qwen_dba.workload_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,

    -- Query identification
    query_fingerprint TEXT NOT NULL,  -- Normalized query pattern
    query_type VARCHAR(50),           -- SELECT, INSERT, UPDATE, DELETE, etc.
    query_source VARCHAR(100),        -- postgres, vector_db, cache, etc.

    -- Query examples (for reference)
    example_query TEXT,

    -- Workload statistics
    execution_count INTEGER NOT NULL DEFAULT 0,
    total_execution_time_ms NUMERIC(15, 3),
    avg_execution_time_ms NUMERIC(15, 3),
    p50_latency_ms NUMERIC(15, 3),
    p95_latency_ms NUMERIC(15, 3),
    p99_latency_ms NUMERIC(15, 3),
    max_latency_ms NUMERIC(15, 3),
    min_latency_ms NUMERIC(15, 3),

    -- Resource usage
    avg_rows_returned NUMERIC(15, 2),
    avg_rows_scanned NUMERIC(15, 2),
    avg_buffer_hits NUMERIC(15, 2),
    avg_buffer_misses NUMERIC(15, 2),

    -- Error tracking
    error_count INTEGER DEFAULT 0,
    error_rate NUMERIC(5, 4),

    -- Impact score (calculated: frequency * avg_latency)
    impact_score NUMERIC(20, 3),

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CONSTRAINT unique_snapshot_fingerprint UNIQUE (snapshot_timestamp, query_fingerprint, query_source)
);

-- Indexes for efficient querying
CREATE INDEX idx_workload_snapshots_timestamp ON qwen_dba.workload_snapshots(snapshot_timestamp DESC);
CREATE INDEX idx_workload_snapshots_impact ON qwen_dba.workload_snapshots(impact_score DESC);
CREATE INDEX idx_workload_snapshots_fingerprint ON qwen_dba.workload_snapshots(query_fingerprint);

-- ============================================================================
-- Evaluation Results
-- ============================================================================

-- Stores evaluation harness results
CREATE TABLE IF NOT EXISTS qwen_dba.eval_results (
    id SERIAL PRIMARY KEY,
    eval_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    eval_type VARCHAR(50) NOT NULL,  -- rag_accuracy, business_metric, slo_check, etc.

    -- Environment info
    environment VARCHAR(50) DEFAULT 'production',
    config_version VARCHAR(100),

    -- Metrics (stored as JSONB for flexibility)
    metrics JSONB NOT NULL,

    -- Specific metric fields for easy querying
    overall_score NUMERIC(10, 6),
    p95_latency_ms NUMERIC(15, 3),
    p99_latency_ms NUMERIC(15, 3),
    error_rate NUMERIC(5, 4),

    -- RAG-specific metrics
    rag_mrr NUMERIC(10, 6),          -- Mean Reciprocal Rank
    rag_precision_at_k NUMERIC(10, 6),
    rag_recall_at_k NUMERIC(10, 6),

    -- SLO compliance
    slo_passed BOOLEAN,
    slo_violations JSONB,

    -- Test details
    test_count INTEGER,
    passed_count INTEGER,
    failed_count INTEGER,

    -- Metadata
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for evaluation results
CREATE INDEX idx_eval_results_timestamp ON qwen_dba.eval_results(eval_timestamp DESC);
CREATE INDEX idx_eval_results_type ON qwen_dba.eval_results(eval_type);
CREATE INDEX idx_eval_results_environment ON qwen_dba.eval_results(environment);

-- ============================================================================
-- Recommendations
-- ============================================================================

-- Stores Qwen-MLX Architect recommendations
CREATE TABLE IF NOT EXISTS qwen_dba.recommendations (
    id SERIAL PRIMARY KEY,
    recommendation_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Recommendation metadata
    recommendation_id VARCHAR(100) UNIQUE NOT NULL,  -- UUID or hash
    status VARCHAR(50) NOT NULL DEFAULT 'pending',   -- pending, approved, rejected, implemented, rolled_back
    priority VARCHAR(20),                             -- critical, high, medium, low

    -- Analysis context
    workload_snapshot_ids INTEGER[],                  -- References to workload_snapshots
    eval_result_ids INTEGER[],                        -- References to eval_results

    -- Recommendation content
    recommendation_type VARCHAR(50),                  -- index, query_rewrite, schema_change, config_tuning
    title TEXT NOT NULL,
    rationale TEXT NOT NULL,

    -- Configuration patch (the actual change to apply)
    config_patch JSONB NOT NULL,

    -- Expected effects
    expected_effects JSONB,                           -- predicted improvements
    expected_latency_improvement_percent NUMERIC(10, 2),
    expected_cost_reduction_percent NUMERIC(10, 2),

    -- Risk assessment
    risk_level VARCHAR(20),                           -- low, medium, high
    risk_notes TEXT,

    -- Migration SQL (if applicable)
    migration_sql TEXT,
    rollback_sql TEXT,

    -- Implementation tracking
    approved_by VARCHAR(100),
    approved_at TIMESTAMP,
    implemented_by VARCHAR(100),
    implemented_at TIMESTAMP,

    -- Results after implementation
    actual_effects JSONB,
    implementation_notes TEXT,

    -- Model info
    model_name VARCHAR(200),
    model_version VARCHAR(100),
    confidence_score NUMERIC(5, 4),

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for recommendations
CREATE INDEX idx_recommendations_timestamp ON qwen_dba.recommendations(recommendation_timestamp DESC);
CREATE INDEX idx_recommendations_status ON qwen_dba.recommendations(status);
CREATE INDEX idx_recommendations_priority ON qwen_dba.recommendations(priority);
CREATE INDEX idx_recommendations_type ON qwen_dba.recommendations(recommendation_type);

-- ============================================================================
-- System Configuration History
-- ============================================================================

-- Tracks configuration changes over time
CREATE TABLE IF NOT EXISTS qwen_dba.config_history (
    id SERIAL PRIMARY KEY,
    change_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),

    -- What changed
    config_key VARCHAR(200) NOT NULL,
    old_value JSONB,
    new_value JSONB,

    -- Why it changed
    change_reason TEXT,
    recommendation_id VARCHAR(100),  -- Reference to recommendations table

    -- Who/what changed it
    changed_by VARCHAR(100),         -- human, qwen-dba-automated, etc.

    -- Metadata
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_config_history_timestamp ON qwen_dba.config_history(change_timestamp DESC);
CREATE INDEX idx_config_history_key ON qwen_dba.config_history(config_key);

-- ============================================================================
-- Views for Analysis
-- ============================================================================

-- View: Top impact queries from latest snapshot
CREATE OR REPLACE VIEW qwen_dba.v_top_impact_queries AS
WITH latest_snapshot AS (
    SELECT DISTINCT snapshot_timestamp
    FROM qwen_dba.workload_snapshots
    ORDER BY snapshot_timestamp DESC
    LIMIT 1
)
SELECT
    ws.query_fingerprint,
    ws.query_type,
    ws.query_source,
    ws.execution_count,
    ws.p95_latency_ms,
    ws.impact_score,
    ws.example_query
FROM qwen_dba.workload_snapshots ws
INNER JOIN latest_snapshot ls ON ws.snapshot_timestamp = ls.snapshot_timestamp
ORDER BY ws.impact_score DESC
LIMIT 50;

-- View: Recent recommendation summary
CREATE OR REPLACE VIEW qwen_dba.v_recent_recommendations AS
SELECT
    r.recommendation_id,
    r.recommendation_timestamp,
    r.status,
    r.priority,
    r.recommendation_type,
    r.title,
    r.expected_latency_improvement_percent,
    r.risk_level,
    r.confidence_score
FROM qwen_dba.recommendations r
WHERE r.recommendation_timestamp >= NOW() - INTERVAL '30 days'
ORDER BY r.recommendation_timestamp DESC;

-- View: SLO compliance over time
CREATE OR REPLACE VIEW qwen_dba.v_slo_compliance AS
SELECT
    DATE_TRUNC('day', eval_timestamp) as eval_date,
    eval_type,
    AVG(CASE WHEN slo_passed THEN 1.0 ELSE 0.0 END) as pass_rate,
    AVG(p95_latency_ms) as avg_p95_latency,
    AVG(error_rate) as avg_error_rate
FROM qwen_dba.eval_results
WHERE eval_timestamp >= NOW() - INTERVAL '90 days'
GROUP BY DATE_TRUNC('day', eval_timestamp), eval_type
ORDER BY eval_date DESC;
