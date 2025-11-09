# Qwen-DBA: AI-Powered Database Administrator using Qwen-MLX

**Phase 1: The Profiler & Advisor (Human-in-the-Loop)**

An AI-powered database optimization system that uses Qwen language models running on Apple MLX to analyze production workloads and recommend performance improvements.

## Overview

Qwen-DBA is a three-phase system designed to automate database administration tasks. This repository implements **Phase 1**, which focuses on data gathering, analysis, and human-validated recommendations.

### Phase 1 Components

1. **Workload Profiler (v1)**: Ingests and aggregates query logs from various sources (PostgreSQL, vector databases, application logs)
2. **Eval Harness (v1)**: Tracks performance metrics, RAG accuracy, and SLO compliance
3. **Qwen-MLX Architect (v1)**: Uses Qwen models to analyze workload data and generate optimization recommendations
4. **Human Executor**: Engineers review and implement recommendations manually

## Features

- 📊 **Workload Analysis**: Automatic query log collection and aggregation
- 🎯 **Query Fingerprinting**: Groups similar queries for pattern detection
- 📈 **Performance Metrics**: Tracks p50/p95/p99 latencies, error rates, and impact scores
- 🔍 **RAG Evaluation**: Measures retrieval-augmented generation quality
- ⚡ **SLO Monitoring**: Automatic SLO compliance checking
- 🤖 **AI Recommendations**: Qwen-MLX generates actionable optimization suggestions
- 💾 **PostgreSQL Schema**: Complete schema for tracking all metrics and recommendations

## Architecture

```
┌─────────────────┐
│  Query Logs     │
│  (Postgres,     │
│   Vector DB,    │
│   App Logs)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────────┐
│   Workload      │─────▶│  Workload        │
│   Profiler      │      │  Snapshots DB    │
└─────────────────┘      └──────────┬───────┘
                                    │
         ┌──────────────────────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────────┐
│  Eval Harness   │─────▶│  Eval Results    │
│  (Metrics/SLO)  │      │  DB              │
└─────────────────┘      └──────────┬───────┘
                                    │
         ┌──────────────────────────┘
         │
         ▼
┌─────────────────┐      ┌──────────────────┐
│  Qwen-MLX       │─────▶│ Recommendations  │
│  Architect      │      │ DB               │
└─────────────────┘      └──────────┬───────┘
                                    │
                                    ▼
                          ┌──────────────────┐
                          │ Human Review     │
                          │ & Implementation │
                          └──────────────────┘
```

## Installation

### Prerequisites

- Python 3.9+
- Apple Silicon Mac (for MLX support)
- PostgreSQL 12+
- At least 16GB RAM (for running Qwen models)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/mlx_Qwen_data_entry.git
cd mlx_Qwen_data_entry
```

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
pip install -e .
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your database credentials
```

5. Configure the system:
```bash
# Edit config.yaml with your database connections and preferences
vi config.yaml
```

6. Initialize the database schema:
```bash
qwen-dba init-db
```

## Configuration

Edit `config.yaml` to configure:

- **Database connections** (primary DB, metrics DB)
- **Workload profiler settings** (log sources, aggregation windows)
- **Evaluation harness settings** (SLO thresholds, evaluation datasets)
- **Qwen-MLX model settings** (model size, quantization, temperature)

Example configuration:

```yaml
databases:
  primary:
    type: "postgresql"
    host: "localhost"
    port: 5432
    database: "production_db"
    username: "postgres"
    password_env: "DB_PASSWORD"

  metrics:
    type: "postgresql"
    host: "localhost"
    port: 5432
    database: "qwen_dba_metrics"
    username: "postgres"
    password_env: "METRICS_DB_PASSWORD"

architect:
  model:
    name: "Qwen/Qwen2.5-7B-Instruct"
    quantization: "4bit"
    max_tokens: 4096
    temperature: 0.7
```

## Usage

### Command Line Interface

```bash
# Initialize database schema
qwen-dba init-db

# Run workload profiler
qwen-dba profile

# Run evaluation harness
qwen-dba eval

# Generate recommendations with Qwen-MLX
qwen-dba recommend

# Run complete workflow (profile -> eval -> recommend)
qwen-dba run-all

# List recent recommendations
qwen-dba list-recommendations --limit 10

# Check system status
qwen-dba status
```

### Programmatic Usage

```python
from qwen_dba.profiler.profiler import WorkloadProfiler
from qwen_dba.eval_harness.harness import EvalHarness
from qwen_dba.architect.architect import QwenArchitect

# Profile workload
profiler = WorkloadProfiler()
snapshots = profiler.create_snapshots()
profiler.save_snapshots(snapshots)

# Run evaluations
harness = EvalHarness()
results = harness.run_all()

# Generate recommendations
architect = QwenArchitect()
recommendation = architect.run()

if recommendation:
    print(f"Recommendation: {recommendation.title}")
    print(f"Expected improvement: {recommendation.expected_latency_improvement_percent}%")
    print(f"Migration SQL: {recommendation.migration_sql}")
```

## Workflow

### 1. Workload Profiling

The profiler:
1. Reads query logs from configured sources
2. Normalizes queries into fingerprints
3. Aggregates statistics (execution count, latencies, errors)
4. Calculates impact scores (frequency × latency)
5. Stores workload snapshots in the database

### 2. Evaluation

The eval harness:
1. Runs RAG accuracy tests (MRR, precision@k, recall@k)
2. Checks SLO compliance (latency thresholds, error rates)
3. Evaluates business-specific metrics
4. Stores results for trend analysis

### 3. AI Recommendations

The Qwen-MLX Architect:
1. Loads recent workload snapshots and eval results
2. Builds a comprehensive prompt with context
3. Uses Qwen to analyze and generate recommendations
4. Outputs structured recommendations with migration SQL

### 4. Human Review

Engineers review recommendations and:
1. Validate the analysis
2. Check for edge cases
3. Test in staging (if available)
4. Create a PR with the changes
5. Deploy to production
6. Monitor results

## Database Schema

The system creates the following tables in the `qwen_dba` schema:

- `workload_snapshots`: Aggregated query statistics
- `eval_results`: Evaluation and SLO compliance results
- `recommendations`: AI-generated optimization recommendations
- `config_history`: Configuration change tracking

## Project Structure

```
mlx_Qwen_data_entry/
├── config.yaml                 # Main configuration
├── requirements.txt            # Python dependencies
├── setup.py                    # Package setup
├── sql/
│   └── 001_create_schema.sql  # Database schema
├── src/qwen_dba/
│   ├── common/                # Shared utilities
│   ├── profiler/              # Workload profiler
│   ├── eval_harness/          # Evaluation harness
│   ├── architect/             # Qwen-MLX Architect
│   └── cli.py                 # Command-line interface
├── docs/                      # Documentation
└── examples/                  # Example files
```

## Future Phases

### Phase 2: The Shadow Tester (Semi-Autonomous)
- Automatic shadow environment setup
- Workload replay and A/B testing
- Automated PR generation with benchmark results

### Phase 3: The Autonomous Autotuner (Closed-Loop)
- Multi-objective optimization
- Automatic deployment with guardrails
- Continuous learning and adaptation

## License

MIT License - see LICENSE file for details

## Acknowledgments

- Built with [MLX](https://github.com/ml-explore/mlx) for Apple Silicon
- Uses [Qwen models](https://huggingface.co/Qwen) from Alibaba Cloud

---

**Note**: This is Phase 1 of a three-phase system. Current functionality focuses on analysis and human-validated recommendations.
