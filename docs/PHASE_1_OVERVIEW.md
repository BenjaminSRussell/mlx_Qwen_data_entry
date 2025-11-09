# Phase 1: The Profiler & Advisor - Detailed Overview

## Goal

Build the core data-gathering and analysis loop. The system observes the production workload and uses Qwen-MLX to recommend changes. A human engineer validates and implements these changes.

## Components

### 1. Workload Profiler (v1)

**Focus**: Simple, read-only aggregation of production workload.

**Tasks**:
- Ingest query logs from multiple sources:
  - PostgreSQL logs (standard format, JSON, CSV)
  - Vector database query logs
  - Application-level query logs
- Aggregate queries into workload snapshots with:
  - Query fingerprint (normalized pattern)
  - Execution statistics (p50, p95, p99 latency)
  - Frequency metrics
  - Error rates
  - Resource usage (rows scanned, buffer hits/misses)
  - Impact score (frequency × latency)

**Implementation Details**:

The profiler uses a three-stage pipeline:

1. **Log Parsing**:
   - Pluggable parsers for different log formats
   - Support for PostgreSQL standard logs, JSON logs, and vector DB logs
   - Robust error handling for malformed log entries

2. **Query Fingerprinting**:
   - Normalizes queries by replacing literals with placeholders
   - Case-insensitive comparison
   - Whitespace normalization
   - Groups similar queries together for pattern analysis

3. **Aggregation**:
   - Configurable time windows (default: 1 hour)
   - Calculates percentile latencies (p50, p95, p99)
   - Computes impact scores to prioritize optimization efforts
   - Filters out low-frequency queries (configurable threshold)

**Output**: Workload snapshots stored in `qwen_dba.workload_snapshots` table.

### 2. Eval Harness (v1)

**Focus**: Establish a "golden set" of performance and quality metrics.

**Tasks**:
- Run evaluations against production environment
- Track multiple metric types:
  - RAG accuracy (Mean Reciprocal Rank, Precision@K, Recall@K)
  - Business metrics (search relevance, user satisfaction)
  - System-level SLOs (p95/p99 latency, error rates)
- Store evaluation results with timestamps for trend analysis
- Alert on SLO violations

**Implementation Details**:

The eval harness supports three evaluator types:

1. **RAG Accuracy Evaluator**:
   - Uses a golden dataset of query-relevance pairs
   - Computes MRR (Mean Reciprocal Rank) as primary metric
   - Calculates Precision@K and Recall@K for retrieval quality
   - Configurable K value (default: 10)

2. **SLO Evaluator**:
   - Monitors recent workload snapshots
   - Checks compliance against configured thresholds:
     - P95 latency threshold (default: 500ms)
     - P99 latency threshold (default: 1000ms)
     - Error rate threshold (default: 0.1%)
   - Reports violations with actual vs. expected values

3. **Business Metrics Evaluator**:
   - Extensible framework for custom metrics
   - Example: search result relevance scoring
   - Integration points for your specific KPIs

**Output**: Evaluation results stored in `qwen_dba.eval_results` table.

### 3. Qwen-MLX "Architect" (v1)

**Focus**: AI-powered recommendation engine.

**Flow**:

1. **Data Collection**:
   - Cron job or manual trigger activates the Architect
   - Pulls latest workload snapshots (top N by impact score)
   - Retrieves recent evaluation results
   - Optionally includes database schema and current config

2. **Prompt Construction**:
   - Builds comprehensive context for Qwen
   - Includes:
     - Workload summary with top slow queries
     - Evaluation metrics and SLO status
     - Database schema (tables, columns, indexes)
     - Current configuration settings
     - Focus areas (indexes, query optimization, etc.)
   - Formats as structured markdown for clarity

3. **AI Analysis**:
   - Uses Qwen-MLX model (default: Qwen2.5-7B-Instruct)
   - 4-bit quantization for memory efficiency (~4GB VRAM)
   - Temperature: 0.7 for balanced creativity/consistency
   - Generates structured JSON recommendation

4. **Recommendation Output**:
   - Structured format includes:
     - Recommendation type (index, query rewrite, schema change, etc.)
     - Priority level (critical, high, medium, low)
     - Detailed rationale
     - Configuration patch
     - Expected effects (latency improvement %, cost reduction %)
     - Risk assessment
     - Migration SQL (to apply the change)
     - Rollback SQL (to undo if needed)
     - Confidence score
   - Saved to database and optionally posted to Slack

**Output**: Recommendations stored in `qwen_dba.recommendations` table.

### 4. Human Executor

**Focus**: Human review and implementation workflow.

**Process**:

1. **Review Recommendations**:
   ```bash
   qwen-dba list-recommendations --limit 10
   ```
   - Examine the rationale and expected impact
   - Validate against domain knowledge
   - Check for edge cases the AI might have missed

2. **Validate in Staging** (if available):
   - Test migration SQL in non-production environment
   - Monitor for unexpected side effects
   - Verify expected performance improvements

3. **Create Pull Request**:
   - Include recommendation details in PR description
   - Add migration and rollback SQL
   - Reference recommendation ID for traceability

4. **Deploy and Monitor**:
   - Apply changes during low-traffic window
   - Monitor key metrics post-deployment
   - Update recommendation status in database
   - Record actual effects for learning

## Timeline & Key Difficulties

### Estimated Time: 4-8 weeks

**Week 1-2: Infrastructure Setup**
- Set up database schema
- Configure log collection
- Implement basic profiler

**Week 3-4: Core Functionality**
- Complete profiler with all log sources
- Implement eval harness
- Set up Qwen-MLX integration

**Week 5-6: AI Integration**
- Implement Architect with prompt engineering
- Test and refine recommendation quality
- Build CLI and automation

**Week 7-8: Testing and Refinement**
- End-to-end testing
- Prompt engineering iterations
- Documentation and examples

### Key Difficulties

1. **Instrumentation (Hardest Part)**:
   - Getting clean, reliable query logs from all systems
   - PostgreSQL logging configuration varies by version
   - Vector DB logs may not include all necessary metrics
   - Application logs need standardization
   - **Solution**: Start simple with one source, iterate

2. **Prompt Engineering**:
   - Balancing context size vs. detail
   - Ensuring Qwen outputs valid, parseable JSON
   - Handling edge cases (no clear optimization, conflicting goals)
   - Calibrating confidence scores
   - **Solution**: Start with simple prompts, iterate based on outputs

3. **Query Fingerprinting Accuracy**:
   - Normalizing queries while preserving semantics
   - Handling complex queries (CTEs, subqueries)
   - Different SQL dialects
   - **Solution**: Use simple heuristics first, refine over time

4. **SLO Definition**:
   - Determining appropriate thresholds
   - Balancing sensitivity vs. alert fatigue
   - Different SLOs for different query types
   - **Solution**: Start conservative, adjust based on data

## Value Proposition

At the end of Phase 1, you have:

- **Automated Workload Analysis**: No more manual log diving
- **AI-Powered Insights**: Qwen finds patterns humans might miss
- **Actionable Recommendations**: Specific SQL to improve performance
- **Risk Assessment**: Understand impact before making changes
- **Knowledge Base**: Historical data for trend analysis
- **Foundation for Automation**: Ready for Phase 2 (shadow testing)

## Success Metrics

Phase 1 is successful when:

- Workload profiler runs daily and captures >90% of production queries
- Eval harness detects SLO violations within 1 hour
- Qwen generates at least 1 valid, useful recommendation per week
- 50%+ of recommendations are approved by engineers
- Implemented recommendations achieve >20% of predicted improvements
- System runs unattended for 1+ week without manual intervention

## Next Steps: Phase 2

Once Phase 1 is stable:
- Build shadow environment infrastructure
- Implement workload replay capability
- Add automated testing and validation
- Generate Pull Requests automatically with benchmark data
