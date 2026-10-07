"""End-to-end DB write paths against a real Postgres (#2).

Skipped unless QWEN_DBA_TEST_DATABASE_URL is set (CI sets it via a postgres
service container; locally use docker-compose.yml). The schema is created in
a throwaway database state: every table is truncated before each test.
"""
import os
import shutil
from pathlib import Path

import pytest
import yaml

DB_URL = os.environ.get("QWEN_DBA_TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(not DB_URL, reason="QWEN_DBA_TEST_DATABASE_URL not set"),
]

ROOT = Path(__file__).resolve().parent.parent
TABLES = ["workload_snapshots", "eval_results", "recommendations", "config_history"]


@pytest.fixture
def ci_config(tmp_path, monkeypatch):
    """config.yaml pointed at the sample log + dataset, all DBs -> test URL."""
    config = yaml.safe_load((ROOT / "config.yaml").read_text())
    config["profiler"]["sources"]["postgres_logs"]["log_path"] = str(ROOT / "examples" / "sample_postgres_log.txt")
    config["profiler"]["aggregation"]["min_query_count"] = 1
    # The sample log is from 2025; aggregate over a window wide enough to include it.
    config["profiler"]["aggregation"]["window_minutes"] = 60 * 24 * 365 * 20
    rag = tmp_path / "rag.json"
    shutil.copy(ROOT / "examples" / "sample_rag_dataset.json", rag)
    config["eval_harness"]["datasets"]["rag_accuracy"]["path"] = str(rag)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config))
    monkeypatch.setenv("QWEN_DBA_DATABASE_URL", DB_URL)
    monkeypatch.setenv("QWEN_ARCHITECT", "stub")
    return str(path)


def run_cli(config_path, *args):
    from click.testing import CliRunner
    from qwen_dba.cli import cli

    result = CliRunner().invoke(cli, ["--config", config_path, *args], obj={}, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    return result.output


def count(table):
    from qwen_dba.common.database import get_metrics_db

    return get_metrics_db().execute_raw(f"SELECT COUNT(*) FROM qwen_dba.{table}")[0][0]


@pytest.fixture
def fresh_schema(ci_config):
    run_cli(ci_config, "init-db")
    from qwen_dba.common.database import get_metrics_db

    db = get_metrics_db()
    db.execute_raw("TRUNCATE " + ", ".join(f"qwen_dba.{t}" for t in TABLES) + " RESTART IDENTITY")
    return ci_config


def test_init_db_creates_schema_and_is_idempotent(ci_config):
    run_cli(ci_config, "init-db")
    run_cli(ci_config, "init-db")  # second run must not fail on existing indexes
    from qwen_dba.common.database import get_metrics_db

    rows = get_metrics_db().execute_raw(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'qwen_dba'"
    )
    names = {r[0] for r in rows}
    assert set(TABLES) <= names
    assert {"v_top_impact_queries", "v_recent_recommendations", "v_slo_compliance"} <= names


def test_profile_writes_workload_snapshots(fresh_schema):
    out = run_cli(fresh_schema, "profile")
    assert "Snapshots saved to database" in out
    assert count("workload_snapshots") >= 1
    from qwen_dba.common.database import get_metrics_db

    row = get_metrics_db().execute_raw(
        "SELECT query_fingerprint, execution_count, impact_score FROM qwen_dba.workload_snapshots "
        "ORDER BY impact_score DESC LIMIT 1"
    )[0]
    assert row[0] and row[1] >= 1 and float(row[2]) > 0


def test_eval_writes_eval_results(fresh_schema):
    run_cli(fresh_schema, "eval")
    assert count("eval_results") >= 1
    from qwen_dba.common.database import get_metrics_db

    types = {r[0] for r in get_metrics_db().execute_raw("SELECT eval_type FROM qwen_dba.eval_results")}
    assert "rag_accuracy" in types


def test_recommend_reads_snapshots_and_persists(fresh_schema):
    run_cli(fresh_schema, "profile")
    run_cli(fresh_schema, "recommend")
    from qwen_dba.common.database import get_metrics_db

    rows = get_metrics_db().execute_raw(
        "SELECT status, model_name, migration_sql FROM qwen_dba.recommendations"
    )
    assert len(rows) == 1
    status, model, sql = rows[0]
    assert status == "pending" and model == "stub-architect"
    # Built from the stored snapshots, not the empty-workload health check.
    assert sql.startswith("EXPLAIN")


def test_status_reports_counts(fresh_schema):
    run_cli(fresh_schema, "profile")
    out = run_cli(fresh_schema, "status")
    assert "Workload Snapshots:" in out
