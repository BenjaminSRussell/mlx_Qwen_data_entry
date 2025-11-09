# Getting Started with Qwen-DBA

## Quick Start Guide

This guide will walk you through setting up and running Qwen-DBA Phase 1 for the first time.

## Prerequisites Checklist

Before starting, ensure you have:

- [ ] Apple Silicon Mac (M1/M2/M3)
- [ ] Python 3.9 or higher
- [ ] PostgreSQL 12 or higher
- [ ] At least 16GB RAM
- [ ] 10GB free disk space (for model cache)
- [ ] Database credentials with appropriate permissions

## Step-by-Step Setup

### 1. Install Python Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Qwen-DBA
pip install -r requirements.txt
pip install -e .

# Verify MLX installation
python -c "import mlx.core as mx; print(f'MLX version: {mx.__version__}')"
```

### 2. Configure Database

Create two databases:
- Primary database (your production DB to monitor)
- Metrics database (stores Qwen-DBA metadata)

```sql
-- As PostgreSQL superuser
CREATE DATABASE qwen_dba_metrics;
GRANT ALL PRIVILEGES ON DATABASE qwen_dba_metrics TO your_user;
```

### 3. Set Up Environment Variables

```bash
# Copy example env file
cp .env.example .env

# Edit with your credentials
nano .env
```

Add:
```
DB_PASSWORD=your_primary_db_password
METRICS_DB_PASSWORD=your_metrics_db_password
```

### 4. Configure Qwen-DBA

Edit `config.yaml`:

```yaml
databases:
  primary:
    host: "localhost"
    port: 5432
    database: "your_production_db"
    username: "your_user"
    password_env: "DB_PASSWORD"

  metrics:
    host: "localhost"
    port: 5432
    database: "qwen_dba_metrics"
    username: "your_user"
    password_env: "METRICS_DB_PASSWORD"

profiler:
  sources:
    postgres_logs:
      enabled: true
      log_path: "/path/to/postgresql.log"
```

### 5. Initialize Database Schema

```bash
qwen-dba init-db
```

Expected output:
```
✓ Configuration loaded from config.yaml
Initializing database schema...
✓ Database schema initialized successfully
```

### 6. Enable PostgreSQL Logging

Edit your PostgreSQL configuration (`postgresql.conf`):

```
# Required settings
logging_collector = on
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d.log'
log_rotation_age = 1d
log_rotation_size = 100MB

# Log all queries with duration
log_min_duration_statement = 0  # Log all queries
log_line_prefix = '%t [%p] '
log_duration = on
```

Restart PostgreSQL:
```bash
# macOS with Homebrew
brew services restart postgresql

# Linux
sudo systemctl restart postgresql
```

### 7. Run First Profiling

```bash
qwen-dba profile
```

If you see "No query logs to aggregate", your log path may be incorrect. Check:
```bash
# Find PostgreSQL log directory
psql -c "SHOW log_directory;"
psql -c "SHOW data_directory;"
```

### 8. Run Evaluation

```bash
qwen-dba eval
```

Note: RAG evaluation requires a dataset. Create a simple one:

```bash
mkdir -p eval_data
cat > eval_data/rag_golden_set.json << 'EOF'
[
  {
    "query": "test query 1",
    "retrieved": ["doc1", "doc2", "doc3"],
    "relevant": ["doc1"]
  }
]
EOF
```

Update `config.yaml`:
```yaml
eval_harness:
  datasets:
    rag_accuracy:
      path: "eval_data/rag_golden_set.json"
```

### 9. Generate First Recommendation

```bash
qwen-dba recommend
```

This will:
1. Download the Qwen model (~4GB, one-time)
2. Load it into memory
3. Analyze your workload
4. Generate a recommendation

**First run takes 5-10 minutes for model download.**

### 10. Check System Status

```bash
qwen-dba status
```

Expected output:
```
Qwen-DBA System Status

  Workload Snapshots: 15
  Evaluation Results: 2
  Recommendations: 1
  Pending Recommendations: 1
```

## Common Issues and Solutions

### Issue: "Model download failed"

**Solution**: Check internet connection and disk space.
```bash
# Clear cache and retry
rm -rf ~/.cache/huggingface/
qwen-dba recommend
```

### Issue: "No query logs found"

**Solution**: Verify PostgreSQL logging is enabled and log path is correct.
```bash
# Check current log file
ls -lh /path/to/postgresql/log/

# Verify logging is working
psql -c "SELECT 1;" && tail -f /path/to/postgresql/log/postgresql-*.log
```

### Issue: "Database connection refused"

**Solution**: Check PostgreSQL is running and credentials are correct.
```bash
# Test connection
psql -h localhost -U your_user -d qwen_dba_metrics -c "SELECT 1;"

# Check environment variables are loaded
source .env
echo $METRICS_DB_PASSWORD
```

### Issue: "Out of memory during recommendation"

**Solution**: Use smaller model or increase swap space.

Edit `config.yaml`:
```yaml
architect:
  model:
    name: "Qwen/Qwen2.5-3B-Instruct"  # Smaller model
```

## Running on a Schedule

### Using Cron (Linux/macOS)

```bash
# Edit crontab
crontab -e

# Add entries (adjust paths)
0 2 * * * cd /path/to/mlx_Qwen_data_entry && /path/to/venv/bin/qwen-dba run-all
```

### Using systemd Timer (Linux)

Create `/etc/systemd/system/qwen-dba.service`:
```ini
[Unit]
Description=Qwen-DBA Daily Analysis
After=postgresql.service

[Service]
Type=oneshot
User=your_user
WorkingDirectory=/path/to/mlx_Qwen_data_entry
Environment=PATH=/path/to/venv/bin:/usr/bin
ExecStart=/path/to/venv/bin/qwen-dba run-all
```

Create `/etc/systemd/system/qwen-dba.timer`:
```ini
[Unit]
Description=Run Qwen-DBA daily at 2 AM

[Timer]
OnCalendar=daily
OnCalendar=02:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable qwen-dba.timer
sudo systemctl start qwen-dba.timer
```

## Next Steps

1. **Fine-tune Configuration**:
   - Adjust SLO thresholds based on your needs
   - Configure focus areas for recommendations
   - Set up Slack notifications (optional)

2. **Create RAG Evaluation Dataset**:
   - Build golden set of query-result pairs
   - Include edge cases and common queries

3. **Review First Recommendation**:
   - Validate the analysis
   - Test in staging if available
   - Implement and monitor

4. **Iterate on Prompts**:
   - Adjust `architect.prompt` settings
   - Refine focus areas
   - Experiment with temperature

5. **Plan for Phase 2**:
   - Design shadow environment
   - Plan workload replay strategy
   - Prepare for automated testing

## Getting Help

- Check the main README for detailed documentation
- Review `docs/PHASE_1_OVERVIEW.md` for architecture details
- Open an issue on GitHub for bugs or questions

## Success Checklist

After setup, you should be able to:

- [ ] Run `qwen-dba profile` and see workload snapshots
- [ ] Run `qwen-dba eval` and see evaluation results
- [ ] Run `qwen-dba recommend` and get an AI recommendation
- [ ] View recommendations with `qwen-dba list-recommendations`
- [ ] Check system status with `qwen-dba status`
- [ ] Run complete workflow with `qwen-dba run-all`

Congratulations! You now have a working AI-powered database advisor.
