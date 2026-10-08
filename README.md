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
- `stat_snapshots`: Every `pg_stat_statements` capture, kept for trends and deltas (#7)
- `proposed_writes`: Review queue of proposed SQL writes (#5)
- `review_audit`: Every review action, including blocked apply attempts (#5, #6)

## Live metrics from pg_stat_statements (#3, #7)

The profiler reads PostgreSQL log files by default, which works offline. To profile live workloads without shipping logs, read the `pg_stat_statements` extension instead:

```yaml
# config.yaml
profiler:
  source: "pg_stat_statements"      # default: "logs"
  pg_stat_statements:
    database: "primary"             # databases entry to read the view from
    min_calls: 1
    use_deltas: true                # per-window numbers = this capture minus the previous one
    store_history: true             # keep each capture in qwen_dba.stat_snapshots
    retention_days: 30              # prune older captures on save (0 = keep everything)
    reset_after_read: false         # pg_stat_statements_reset() after a saved capture
```

Or pick the source per run:

```bash
qwen-dba profile --source pg_stat_statements
```

Rows from the view map onto the same `workload_snapshots` model and the same fingerprinter as the log path. `$1` parameters and log literals both normalize to `?`, so fingerprints line up across the two sources. Several `queryid`s that normalize to one pattern (for example, different users) are merged.

`pg_stat_statements` doesn't record percentiles. **p50, p95 and p99 are estimates**: the mean, then `mean + 1.645·stddev` and `mean + 2.326·stddev`, capped at `max_exec_time`.

**Enable the extension.** Changing `shared_preload_libraries` needs a server restart.

```bash
# postgresql.conf, or a server flag
shared_preload_libraries = 'pg_stat_statements'
# then, in the database you profile:
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
```

With docker compose, add a command to the postgres service:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    command: ["postgres", "-c", "shared_preload_libraries=pg_stat_statements"]
```

**Privileges.**

| Action | Needs |
|---|---|
| Read the view | `CONNECT` on the database. Without `pg_read_all_stats`, other users' query text shows as `<insufficient privilege>` and is skipped. Use `GRANT pg_read_all_stats TO qwen_dba;`. |
| `reset_after_read: true` | Superuser, or `GRANT EXECUTE ON FUNCTION pg_stat_statements_reset TO qwen_dba;` (the full signature differs by version). |
| Store history | `INSERT`/`DELETE` on `qwen_dba.stat_snapshots` in the metrics database (created by `qwen-dba init-db`). |

If the extension is missing or not preloaded, the profiler stops with an error that explains how to fix it. The log parser keeps working.

**Capture history (#7).** Each saved profile run, and each `qwen-dba stats snapshot`, stores the raw cumulative rows in `qwen_dba.stat_snapshots`. Columns: `captured_at`, `queryid`, `dbid`, `userid`, `query_fingerprint`, `query_type`, `query`, `calls`, `total/mean/stddev/min/max_exec_time_ms`, `rows`, `shared_blks_hit` and `shared_blks_read`. Consecutive captures coexist, and the next run uses the previous capture to compute per-window deltas. A counter reset is detected, and the current values are used as-is.

```bash
qwen-dba stats snapshot                       # capture only (e.g. from cron every 5 min)
qwen-dba stats list                           # captures, newest first
qwen-dba stats prune --days 30                # retention (also runs automatically on save)
qwen-dba stats export --csv stats.csv --since 2026-10-01   # for notebooks: pandas.read_csv("stats.csv")
```

## Human review queue for proposed writes (#5, #6)

Proposed SQL is never applied until it passes review. With **review mode on**, nothing can be applied until a reviewer approves it. Review mode is the default; turn it off with `review.mode` or `REVIEW_MODE=1/0`. The rules are enforced in `qwen_dba/review/queue.py`, so every interface gets them:

| Rule | Behaviour |
|---|---|
| Approval gate | With `REVIEW_MODE=1`, `apply` is refused unless the proposal is `approved`. |
| Explicit confirm | `apply` always needs confirmation. The CLI shows the diff and asks `[y/N]`; scripts pass `--confirm`. |
| Parse gate | SQL is parsed with the real PostgreSQL parser ([pglast](https://github.com/lelit/pglast), libpg_query). If it doesn't parse, it can't be approved or applied. |
| Destructive flags | DROP, TRUNCATE, DELETE/UPDATE without WHERE, and ALTER ... DROP or column type changes are flagged in `list`, `show` and the apply prompt. |
| Rejects keep a reason | `reject` needs `--reason`. The row stays in the queue as `rejected` with the reason; a DB `CHECK` enforces it. |
| Audit | `propose`, `approve`, `reject`, `apply`, `apply_blocked` and `apply_failed` are written to `qwen_dba.review_audit` with actor, reason and details. |
| Atomic apply | The SQL runs in one transaction on its target database. On error, everything rolls back and the proposal becomes `failed`. |

`qwen-dba recommend` queues each recommendation's `migration_sql` automatically (`review.enqueue_recommendations`).

**Linux / stub path:** no Apple Silicon or MLX needed.

```bash
docker compose up -d postgres
export QWEN_DBA_DATABASE_URL=postgresql+psycopg2://qwen:qwen@localhost:5432/qwen_dba_test
export QWEN_ARCHITECT=stub REVIEW_MODE=1 PYTHONPATH=src
python -m qwen_dba.cli init-db
python -m qwen_dba.cli profile && python -m qwen_dba.cli recommend   # -> "Queued for review as pw-..."

python -m qwen_dba.cli review list --status pending
python -m qwen_dba.cli review show pw-...                  # unified diff current -> proposed, flags
python -m qwen_dba.cli review approve pw-... --by ben
python -m qwen_dba.cli review apply pw-... --by ben        # shows the diff again, asks to confirm
python -m qwen_dba.cli review reject pw-... --by ben --reason "no WHERE clause"
python -m qwen_dba.cli review audit pw-...

# Manual proposals, with the current definition to diff against (fixture in examples/review/):
python -m qwen_dba.cli review propose --file examples/review/proposed_query.sql \
    --current-file examples/review/current_query.sql --title "narrow orders query"
```

The diff is a unified diff of the **prettified** current and proposed SQL, so formatting and comments don't show up as changes. A proposal with no current SQL, such as a new index, shows as all additions.

## Future Phases

Phase 2 will add automated shadow testing and workload replay. Phase 3 will implement closed-loop autonomous optimization with guardrails.

## License

MIT License


## Architect backends

| Environment | Backend | How |
|-------------|---------|-----|
| Linux CI / Docker | `StubArchitect` | `QWEN_ARCHITECT=stub` (default when MLX import fails) |
| Apple Silicon | `QwenArchitect` (MLX) | `QWEN_ARCHITECT=mlx` or auto when `mlx` importable |

CI runs the propose path with Stub only — no Apple Silicon required.


## Tests

```bash
pip install -r requirements-test.txt
PYTHONPATH=src pytest -q          # unit tests; Postgres tests skip without a DB

# Postgres integration (init-db, profile/eval/recommend writes)
docker compose up -d postgres
export QWEN_DBA_TEST_DATABASE_URL=postgresql+psycopg2://qwen:qwen@localhost:5432/qwen_dba_test
PYTHONPATH=src pytest -q -m postgres

# Live pg_stat_statements test: needs the extension preloaded (see above), e.g.
#   docker run -d -p 5433:5432 -e POSTGRES_USER=qwen -e POSTGRES_PASSWORD=qwen -e POSTGRES_DB=qwen_dba_test \
#     postgres:16-alpine -c shared_preload_libraries=pg_stat_statements
QWEN_DBA_REQUIRE_PGSS=1 PYTHONPATH=src pytest -q -m pgss
```

`QWEN_DBA_DATABASE_URL` overrides the connection strings in `config.yaml`. `QWEN_DBA_CONFIG` (or `--config`) selects the config file.
