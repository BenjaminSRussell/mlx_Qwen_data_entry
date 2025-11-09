# Qwen-DBA: AI-Powered Database Administrator

AI-powered database optimization system using Qwen language models on Apple MLX to analyze production workloads and recommend performance improvements.

## Overview

Qwen-DBA analyzes database query logs and uses AI to generate optimization recommendations. This is Phase 1 (human-in-the-loop): the system profiles workloads, evaluates performance, and generates recommendations that engineers review and implement manually.

## Components

1. **Workload Profiler**: Ingests and aggregates query logs from PostgreSQL, vector databases, and application logs
2. **Eval Harness**: Tracks performance metrics, RAG accuracy, and SLO compliance
3. **Qwen-MLX Architect**: Uses Qwen models to analyze workload data and generate recommendations
4. **CLI**: Command-line interface for running profiling, evaluation, and recommendations

## Installation

### Prerequisites

- Python 3.9+
- Apple Silicon Mac (for MLX support)
- PostgreSQL 12+
- 16GB+ RAM

### Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -e .

# Configure environment
cp .env.example .env
# Edit .env with database credentials

# Configure system
# Edit config.yaml with your settings

# Initialize database
qwen-dba init-db
```

## Usage

```bash
# Run workload profiler
qwen-dba profile

# Run evaluation harness
qwen-dba eval

# Generate AI recommendations
qwen-dba recommend

# Run complete workflow
qwen-dba run-all

# List recommendations
qwen-dba list-recommendations

# Check system status
qwen-dba status
```

## Project Structure

```
mlx_Qwen_data_entry/
├── config.yaml              # Main configuration
├── requirements.txt         # Dependencies
├── sql/
│   └── 001_create_schema.sql
├── src/qwen_dba/
│   ├── common/             # Config, models, database
│   ├── profiler/           # Query log profiling
│   ├── eval_harness/       # Metrics evaluation
│   ├── architect/          # AI recommendation engine
│   └── cli.py
├── tests/                  # Test suite
└── examples/               # Sample files
```

## Configuration

Edit `config.yaml` to configure:

- Database connections (primary and metrics databases)
- Workload profiler settings (log sources, aggregation windows)
- Evaluation harness settings (SLO thresholds, datasets)
- Qwen-MLX model settings (model size, quantization, temperature)

## Database Schema

The system creates these tables in the `qwen_dba` schema:

- `workload_snapshots`: Aggregated query statistics
- `eval_results`: Evaluation and SLO compliance results
- `recommendations`: AI-generated optimization recommendations
- `config_history`: Configuration change tracking

## Future Phases

Phase 2 will add automated shadow testing and workload replay. Phase 3 will implement closed-loop autonomous optimization with guardrails.

## License

MIT License
