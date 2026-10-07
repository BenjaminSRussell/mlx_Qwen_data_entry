from qwen_dba.architect.stub import StubArchitect
from qwen_dba.architect.factory import create_architect
import os


def test_stub_generates_recommendation_without_mlx():
    arch = StubArchitect()
    rec = arch.generate_recommendation(workload_snapshots=[])
    assert rec is not None
    assert rec.model_name == "stub-architect"
    assert rec.migration_sql
    assert rec.config_patch.get("backend") == "stub"


def test_factory_respects_stub_env(monkeypatch):
    monkeypatch.setenv("QWEN_ARCHITECT", "stub")
    arch = create_architect()
    assert type(arch).__name__ == "StubArchitect"
