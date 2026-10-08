"""SQL parse gate, destructive detection and diffs for the review queue (#5, #6). No DB needed."""
from pathlib import Path

import pytest

from qwen_dba.review import check_sql, render_diff, review_mode_enabled

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "review"


@pytest.mark.parametrize("sql,flag", [
    ("DROP TABLE users", "DROP TABLE"),
    ("DROP INDEX idx_a", "DROP INDEX"),
    ("TRUNCATE orders", "TRUNCATE"),
    ("DELETE FROM users", "DELETE without WHERE"),
    ("UPDATE users SET active = false", "UPDATE without WHERE"),
    ("ALTER TABLE t DROP COLUMN c", "DropColumn"),
    ("ALTER TABLE t ALTER COLUMN c TYPE text", "AlterColumnType"),
    ("CREATE INDEX i ON t (a); DROP TABLE old_t", "DROP TABLE"),  # hidden in a batch
])
def test_destructive_statements_are_flagged(sql, flag):
    chk = check_sql(sql)
    assert chk.ok and chk.is_destructive
    assert any(flag in d for d in chk.destructive), chk.destructive


@pytest.mark.parametrize("sql", [
    "CREATE INDEX CONCURRENTLY idx_orders_user ON orders (user_id)",
    "DELETE FROM sessions WHERE expires_at < now()",
    "UPDATE users SET active = false WHERE id = 7",
    "ALTER TABLE t ADD COLUMN c int",
    "INSERT INTO t (a) VALUES (1)",
])
def test_safe_statements_parse_without_flags(sql):
    chk = check_sql(sql)
    assert chk.ok and not chk.destructive and chk.statement_types


@pytest.mark.parametrize("sql,msg", [
    ("SELEC * FRM users", "syntax error"),
    ("CREATE INDEX ON", "syntax error"),
    ("", "empty"),
    ("-- just a comment", "no SQL statements"),
])
def test_unparseable_sql_is_not_ok(sql, msg):
    chk = check_sql(sql)
    assert not chk.ok and msg in chk.error


def test_diff_shown_for_fixture_proposal():
    current = (EXAMPLES / "current_query.sql").read_text()
    proposed = (EXAMPLES / "proposed_query.sql").read_text()
    diff = render_diff(current, proposed)
    lines = diff.splitlines()
    assert lines[0] == "--- current" and lines[1] == "+++ proposed"
    assert "-SELECT *" in lines
    assert any(l.startswith("+SELECT id") for l in lines)
    assert "+LIMIT 50" in lines
    assert " FROM orders" in lines  # unchanged context survives prettifying
    # comments and layout differences alone are not changes
    assert render_diff("select 1", "SELECT   1 -- same") == "(no changes)"


def test_diff_for_new_object_has_no_current():
    diff = render_diff(None, "CREATE INDEX i ON t (a)")
    assert diff.splitlines()[0] == "--- current (none)"
    assert all(l.startswith(("+", "-", "@")) for l in diff.splitlines())


def test_review_mode_defaults_on_and_env_overrides(monkeypatch):
    monkeypatch.delenv("REVIEW_MODE", raising=False)
    assert review_mode_enabled() is True
    assert review_mode_enabled(False) is False
    monkeypatch.setenv("REVIEW_MODE", "1")
    assert review_mode_enabled(False) is True
    monkeypatch.setenv("REVIEW_MODE", "0")
    assert review_mode_enabled(True) is False
