"""Config / connection-string behaviour (no database needed)."""
from qwen_dba.common.config import DatabaseConfig


def make(**kw):
    base = dict(host="db.local", port=5433, database="metrics", username="svc", password_env="TEST_PW")
    base.update(kw)
    return DatabaseConfig(**base)


def test_postgres_pins_psycopg2_driver(monkeypatch):
    monkeypatch.delenv("QWEN_DBA_DATABASE_URL", raising=False)
    monkeypatch.setenv("TEST_PW", "pw")
    assert make().get_connection_string() == "postgresql+psycopg2://svc:pw@db.local:5433/metrics"


def test_password_special_characters_are_escaped(monkeypatch):
    monkeypatch.delenv("QWEN_DBA_DATABASE_URL", raising=False)
    monkeypatch.setenv("TEST_PW", "p@ss:w/rd")
    url = make().get_connection_string()
    assert "p%40ss%3Aw%2Frd@db.local" in url


def test_explicit_driver_is_kept(monkeypatch):
    monkeypatch.delenv("QWEN_DBA_DATABASE_URL", raising=False)
    monkeypatch.setenv("TEST_PW", "x")
    assert make(type="postgresql+psycopg").get_connection_string().startswith("postgresql+psycopg://")


def test_env_override(monkeypatch):
    monkeypatch.setenv("QWEN_DBA_DATABASE_URL", "postgresql+psycopg2://a:b@h/d")
    assert make().get_connection_string() == "postgresql+psycopg2://a:b@h/d"


def test_stub_never_explain_analyzes_writes():
    from qwen_dba.architect.stub import StubArchitect
    from qwen_dba.common.models import WorkloadSnapshot

    fields = WorkloadSnapshot.model_fields
    assert "example_query" in fields
    from types import SimpleNamespace

    write = SimpleNamespace(impact_score=10, example_query="UPDATE t SET x = 1 WHERE id = 1", query_type="UPDATE")
    read = SimpleNamespace(impact_score=5, example_query="SELECT * FROM t", query_type="SELECT")
    arch = StubArchitect(db=object())
    assert arch.generate_recommendation(workload_snapshots=[write, read]).migration_sql == "EXPLAIN UPDATE t SET x = 1 WHERE id = 1;"
    assert "ANALYZE" in arch.generate_recommendation(workload_snapshots=[read]).migration_sql
