"""Parse, classify and diff proposed SQL with the real PostgreSQL parser (pglast / libpg_query)."""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import List, Optional

try:  # pglast wraps libpg_query: the parser PostgreSQL itself uses
    from pglast import parse_sql, prettify
    from pglast.parser import ParseError
except ImportError:  # pragma: no cover - requirements pin pglast
    parse_sql = prettify = None

    class ParseError(Exception):
        pass


@dataclass
class SqlCheck:
    """Result of checking a proposal's SQL."""

    ok: bool
    error: Optional[str] = None
    statement_types: List[str] = field(default_factory=list)
    destructive: List[str] = field(default_factory=list)  # human-readable reasons
    normalized: Optional[str] = None  # prettified SQL used for diffs

    @property
    def is_destructive(self) -> bool:
        return bool(self.destructive)


_ALTER_DROP_SUBTYPES = {"AT_DropColumn", "AT_DropConstraint", "AT_DropNotNull", "AT_AlterColumnType"}


def _enum_name(enum_cls_name: str, value) -> str:
    """pglast stores enums as ints in some versions and as enum members in others."""
    if hasattr(value, "name"):
        return value.name
    try:
        from pglast import enums
        return getattr(enums, enum_cls_name)(value).name
    except Exception:
        return str(value)


def _destructive_reasons(stmt) -> List[str]:
    name = type(stmt).__name__
    if name == "DropStmt":
        kind = _enum_name("ObjectType", getattr(stmt, "removeType", "")).replace("OBJECT_", "")
        return [f"DROP {kind}".strip()]
    if name == "TruncateStmt":
        return ["TRUNCATE"]
    if name == "DeleteStmt" and getattr(stmt, "whereClause", None) is None:
        return ["DELETE without WHERE (deletes every row)"]
    if name == "UpdateStmt" and getattr(stmt, "whereClause", None) is None:
        return ["UPDATE without WHERE (rewrites every row)"]
    if name == "AlterTableStmt":
        out = []
        for cmd in getattr(stmt, "cmds", None) or ():
            sub = _enum_name("AlterTableType", getattr(cmd, "subtype", ""))
            if sub in _ALTER_DROP_SUBTYPES:
                out.append(f"ALTER TABLE {sub.replace('AT_', '')}")
        return out
    return []


def check_sql(sql: Optional[str]) -> SqlCheck:
    """Parse ``sql``. Unparseable or empty SQL is ``ok=False``, which blocks apply.

    Destructive statements (DROP, TRUNCATE, DELETE/UPDATE without WHERE, ALTER ... DROP
    or column type changes) are listed so reviewers can't miss them.
    """
    if sql is None or not sql.strip():
        return SqlCheck(ok=False, error="empty SQL")
    if parse_sql is None:  # pragma: no cover
        return SqlCheck(ok=False, error="pglast is not installed; cannot validate SQL")
    try:
        stmts = parse_sql(sql)
    except ParseError as exc:
        return SqlCheck(ok=False, error=f"parse error: {exc}")
    if not stmts:
        return SqlCheck(ok=False, error="no SQL statements (only comments?)")
    types = [type(s.stmt).__name__ for s in stmts]
    destructive: List[str] = []
    for s in stmts:
        destructive.extend(_destructive_reasons(s.stmt))
    try:
        normalized = prettify(sql)
    except Exception:  # prettify can't render every node; fall back to the raw text
        normalized = sql.strip()
    return SqlCheck(ok=True, statement_types=types, destructive=destructive, normalized=normalized)


def _diff_text(sql: Optional[str]) -> List[str]:
    if not sql or not sql.strip():
        return []
    chk = check_sql(sql)
    text = chk.normalized if chk.ok and chk.normalized else sql.strip()
    return [line.rstrip() for line in text.splitlines()]


def render_diff(current_sql: Optional[str], proposed_sql: str, context: int = 3) -> str:
    """Unified diff of current -> proposed SQL, both prettified so layout noise disappears.

    With no current SQL (e.g. a brand-new index) every line shows as an addition.
    """
    before, after = _diff_text(current_sql), _diff_text(proposed_sql)
    lines = list(difflib.unified_diff(
        before, after, fromfile="current" if before else "current (none)", tofile="proposed",
        lineterm="", n=context,
    ))
    return "\n".join(lines) if lines else "(no changes)"
