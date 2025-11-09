# Qwen-DBA Testing Guide

## Test Results Summary

### ✅ Completed Tests

#### Phase 1.1: Environment Setup ✅
- **Python Version**: 3.11.14
- **Platform**: Linux x86_64
- **Core Dependencies Installed**:
  - pydantic 2.12.4
  - pyyaml
  - python-dotenv 1.2.1
  - sqlalchemy 2.0.44

#### Phase 2.1: Profiler Tests ✅

**Query Fingerprinting**:
- ✅ Basic fingerprinting works correctly
- ✅ Queries with same structure but different literals produce identical fingerprints
- ✅ Literals are correctly replaced with `?` placeholders
- ✅ Case-insensitive normalization works
- ✅ Whitespace normalization works
- ✅ Query type extraction works (SELECT, INSERT, UPDATE, DELETE)
- ✅ Table name extraction works for simple queries

**Log Parsing**:
- ✅ PostgreSQL standard log format parsing works
- ✅ Execution times are correctly extracted
- ✅ Timestamps are parsed correctly
- ✅ Malformed log entries are skipped without crashing

**Workload Aggregation**:
- ✅ Query logs are correctly aggregated by fingerprint
- ✅ P95 latency is calculated correctly
- ✅ Impact scores are calculated (frequency × latency)
- ✅ Min query count filtering works
- ✅ Snapshots are sorted by impact score

#### Phase 2.2: Eval Harness Tests ✅

**RAG Accuracy Evaluation**:
- ✅ Mean Reciprocal Rank (MRR) calculation works
- ✅ Precision@K calculation works
- ✅ Recall@K calculation works
- ✅ Dataset loading from JSON works
- ✅ Full evaluation pipeline works

**MRR Edge Cases**:
- ✅ Perfect ranking (relevant doc first) = MRR 1.0
- ✅ Second place ranking = MRR 0.5
- ✅ No relevant docs retrieved = MRR 0.0

## Bug Fixes Applied

### 1. Database Connection Initialization (Fixed)

**Problem**: Evaluators were initializing database connections even when not needed for basic metric calculation. This made testing difficult and violated separation of concerns.

**Fix**: Added `use_db` parameter to evaluators:
```python
# Before
evaluator = RAGAccuracyEvaluator(dataset_path)  # Always tries to connect to DB

# After
evaluator = RAGAccuracyEvaluator(dataset_path, use_db=False)  # No DB needed
```

**Files Changed**:
- `src/qwen_dba/eval_harness/evaluators.py`

**Impact**:
- Improved testability
- Reduced coupling
- Allows standalone use of metric calculation functions

## Test Files Created

### Unit Tests
1. **tests/conftest.py**: Pytest configuration and fixtures
2. **tests/test_profiler.py**: Pytest tests for profiler
3. **tests/test_eval_harness.py**: Pytest tests for eval harness

### Manual Tests
1. **tests/manual_test_profiler.py**: Standalone profiler tests
2. **tests/manual_test_eval.py**: Standalone eval harness tests

## Environment Limitations

### MLX Not Available
- **Issue**: MLX requires Apple Silicon (M1/M2/M3)
- **Current Environment**: Linux x86_64
- **Impact**: Cannot test Qwen-MLX Architect in this environment
- **Workaround**: Architect tests require macOS with Apple Silicon

### PostgreSQL Database
- **Issue**: Docker not available in test environment
- **Current Setup**: Tests use mocked database or no database
- **Impact**: Cannot test full database integration
- **Workaround**: Use manual testing on a machine with PostgreSQL

## Running Tests

### Quickstart (Manual Tests)

```bash
# Test profiler components
python3 tests/manual_test_profiler.py

# Test eval harness components
python3 tests/manual_test_eval.py
```

### With Pytest (Requires Installation)

```bash
# Install test dependencies
pip install pytest

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_profiler.py -v

# Run specific test
pytest tests/test_profiler.py::TestQueryFingerprinter::test_basic_fingerprint -v
```

## Test Coverage

### ✅ Fully Tested
- Query fingerprinting
- PostgreSQL log parsing
- Workload aggregation
- RAG accuracy metrics (MRR, Precision@K, Recall@K)

### ⚠️ Partially Tested
- SLO evaluator (logic tested, DB integration not tested)
- Business metrics evaluator (logic tested, DB integration not tested)

### ❌ Not Tested (Requires Specific Environment)
- Qwen-MLX model loading (requires Apple Silicon)
- Qwen-MLX inference (requires Apple Silicon)
- Database schema initialization (requires PostgreSQL)
- Full CLI commands (requires PostgreSQL)
- End-to-end workflow (requires PostgreSQL + MLX)

## Next Steps for Complete Testing

### Phase 1.2-1.5: Database Setup

**Requirements**:
- PostgreSQL database (Docker or native)
- Database credentials configured in .env
- MLX-compatible machine (Apple Silicon)

**Steps**:
1. Set up test PostgreSQL:
   ```bash
   docker run --name test-postgres \
     -e POSTGRES_PASSWORD=mysecretpassword \
     -p 5432:5432 -d postgres
   ```

2. Configure .env:
   ```bash
   cp .env.example .env
   # Edit .env with connection strings
   ```

3. Initialize schema:
   ```bash
   qwen-dba init-db
   ```

4. Verify tables exist:
   ```bash
   psql -h localhost -U postgres -c "\dt qwen_dba.*"
   ```

### Phase 2.3: Architect Testing

**Requirements**:
- Apple Silicon Mac
- Qwen model downloaded
- ~16GB RAM available

**Steps**:
1. Download model:
   ```bash
   # Model will auto-download on first run
   # Or pre-download:
   python3 -c "from mlx_lm import load; load('Qwen/Qwen2.5-7B-Instruct')"
   ```

2. Test recommendation generation:
   ```bash
   qwen-dba recommend
   ```

3. Verify output:
   ```bash
   qwen-dba list-recommendations
   ```

### Phase 3: End-to-End Testing

**Workflow**:
1. Create sample workload:
   ```bash
   # Use examples/sample_postgres_log.txt
   qwen-dba profile
   ```

2. Run evaluation:
   ```bash
   # Use examples/sample_rag_dataset.json
   qwen-dba eval
   ```

3. Generate recommendation:
   ```bash
   qwen-dba recommend
   ```

4. Human validation:
   - Review recommendation
   - Check migration SQL syntax
   - Verify risk assessment

### Phase 4: Stress Testing

**Large Log Files**:
```bash
# Generate or obtain 10GB+ log file
# Test profiler performance and memory usage
qwen-dba profile --log-file /path/to/large.log
```

**Prompt Engineering Loop**:
- Run `qwen-dba recommend` on 20+ different workloads
- Track recommendation quality in spreadsheet
- Iterate on `prompt_builder.py` to improve accuracy

## Known Issues

### 1. pg_stat_statements Integration (TODO)

**Issue**: Profiler currently only reads from log files, not live PostgreSQL stats.

**Impact**: Cannot monitor live production databases efficiently.

**Planned Fix**: Add `pg_stat_statements` adapter in profiler.

### 2. Model Download Size (WARNING)

**Issue**: Qwen2.5-7B-Instruct is ~4GB download.

**Impact**: First run takes 5-10 minutes.

**Mitigation**: Document clearly in getting started guide.

## Test Metrics

### Code Coverage (Estimated)

- **Profiler**: ~80% (core logic fully tested, DB integration not tested)
- **Eval Harness**: ~70% (metric calculation tested, DB integration not tested)
- **Architect**: ~0% (requires MLX environment)
- **CLI**: ~0% (requires full environment)
- **Overall**: ~40%

### Test Execution Time

- Manual profiler tests: ~0.5 seconds
- Manual eval tests: ~0.3 seconds
- Total: <1 second (excluding DB/MLX tests)

## Continuous Integration Recommendations

### GitHub Actions Workflow

```yaml
name: Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.11
      - name: Install dependencies
        run: |
          pip install pydantic pyyaml python-dotenv sqlalchemy pytest
      - name: Run unit tests
        run: |
          pytest tests/ -v -k "not mlx and not db_integration"

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v2
      - name: Run integration tests
        run: |
          # Tests that require PostgreSQL
          pytest tests/ -v -k "db_integration"
```

## Conclusion

**Phase 1.1 ✅**: Environment setup complete
**Phase 2.1 ✅**: Profiler core logic validated
**Phase 2.2 ✅**: Eval harness core logic validated

**Ready for**: Manual end-to-end testing on macOS with Apple Silicon + PostgreSQL

**Improvements Made**:
- Made evaluators more testable by making DB connections optional
- Added comprehensive test suite
- Validated core business logic
- Documented testing approach

**Confidence Level**: High for profiler and eval harness logic. Requires full environment for Architect and E2E testing.
