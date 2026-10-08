"""``qwen_dba.proposed_writes`` review queue with an audit log (#5, #6).

Lifecycle::

    propose -> pending --approve--> approved --apply(confirm)--> applied | failed
                       \\--reject(reason)--> rejected

Rules enforced here, not in the UI:

* With review mode on (``REVIEW_MODE=1``, the default), a proposal can only be applied
  after it has been **approved**.
* ``apply`` always needs ``confirm=True``. The CLI asks for it after showing the diff.
* SQL that does not parse with the PostgreSQL parser can never be applied. It also
  can't be approved.
* Rejecting needs a reason, and the row stays in the queue with it.
* Every action, including blocked apply attempts, is written to ``qwen_dba.review_audit``.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import text

from .sqlcheck import check_sql, render_diff

STATUSES = ("pending", "approved", "rejected", "applied", "failed")


class ReviewError(RuntimeError):
    """A review action was refused (wrong state, missing confirm/reason, bad SQL)."""


def review_mode_enabled(config_value: Optional[bool] = None) -> bool:
    """``REVIEW_MODE`` env (1/0, true/false) wins over config; default **on**."""
    env = os.getenv("REVIEW_MODE")
    if env is not None and env.strip() != "":
        return env.strip().lower() not in ("0", "false", "no", "off")
    return True if config_value is None else bool(config_value)


@dataclass
class Proposal:
    proposal_id: str
    status: str
    title: str
    sql: str
    current_sql: Optional[str]
    confidence: Optional[float]
    source: str
    recommendation_id: Optional[str]
    target_db: str
    parse_ok: bool
    parse_error: Optional[str]
    destructive: List[str]
    created_at: datetime
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reason: Optional[str] = None
    applied_by: Optional[str] = None
    applied_at: Optional[datetime] = None
    apply_error: Optional[str] = None

    @property
    def diff(self) -> str:
        return render_diff(self.current_sql, self.sql)


_COLS = ("proposal_id, status, title, sql, current_sql, confidence, source, recommendation_id, target_db, "
         "parse_ok, parse_error, destructive, created_at, reviewed_by, reviewed_at, reason, applied_by, "
         "applied_at, apply_error")


def _to_proposal(row) -> Proposal:
    m = dict(row._mapping)
    d = m.get("destructive")
    m["destructive"] = d if isinstance(d, list) else json.loads(d or "[]")
    m["confidence"] = None if m.get("confidence") is None else float(m["confidence"])
    return Proposal(**m)


class ReviewQueue:
    """Queue backed by the metrics DB; ``apply`` runs SQL on ``target_db_factory(name)``."""

    def __init__(self, db, target_db_factory: Optional[Callable[[str], Any]] = None,
                 review_mode: Optional[bool] = None):
        self.db = db
        self.target_db_factory = target_db_factory
        self.review_mode = review_mode_enabled(review_mode)

    # ---------------------------------------------------------------- audit
    def _audit(self, session, proposal_id: str, action: str, actor: Optional[str],
               reason: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> None:
        session.execute(text(
            "INSERT INTO qwen_dba.review_audit (proposal_id, action, actor, reason, details) "
            "VALUES (:p, :a, :actor, :r, CAST(:d AS JSONB))"),
            {"p": proposal_id, "a": action, "actor": actor, "r": reason, "d": json.dumps(details or {})})

    def audit_log(self, proposal_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        sql = "SELECT ts, proposal_id, action, actor, reason, details FROM qwen_dba.review_audit"
        params: Dict[str, Any] = {"limit": limit}
        if proposal_id:
            sql += " WHERE proposal_id = :p"
            params["p"] = proposal_id
        sql += " ORDER BY id DESC LIMIT :limit"
        return [dict(r._mapping) for r in self.db.execute_raw(sql, params)]

    # ------------------------------------------------------------- queries
    def get(self, proposal_id: str) -> Proposal:
        rows = self.db.execute_raw(f"SELECT {_COLS} FROM qwen_dba.proposed_writes WHERE proposal_id = :p",
                                   {"p": proposal_id})
        if not rows:
            raise ReviewError(f"no proposal {proposal_id!r}")
        return _to_proposal(rows[0])

    def list(self, status: Optional[str] = None, limit: int = 50) -> List[Proposal]:
        sql = f"SELECT {_COLS} FROM qwen_dba.proposed_writes"
        params: Dict[str, Any] = {"limit": limit}
        if status:
            sql += " WHERE status = :s"
            params["s"] = status
        sql += " ORDER BY created_at DESC, id DESC LIMIT :limit"
        return [_to_proposal(r) for r in self.db.execute_raw(sql, params)]

    # ------------------------------------------------------------- actions
    def propose(self, sql: str, title: str, confidence: Optional[float] = None,
                current_sql: Optional[str] = None, source: str = "manual",
                recommendation_id: Optional[str] = None, target_db: str = "primary",
                actor: Optional[str] = None) -> Proposal:
        """Queue a write. Unparseable SQL is queued too (so it is visible) but can't be applied."""
        chk = check_sql(sql)
        pid = "pw-" + uuid.uuid4().hex[:12]
        with self.db.get_session() as s:
            s.execute(text(
                "INSERT INTO qwen_dba.proposed_writes (proposal_id, status, title, sql, current_sql, confidence, "
                "source, recommendation_id, target_db, parse_ok, parse_error, destructive) VALUES "
                "(:p, 'pending', :title, :sql, :cur, :conf, :src, :rec, :tdb, :ok, :err, CAST(:destr AS JSONB))"),
                {"p": pid, "title": title, "sql": sql, "cur": current_sql, "conf": confidence, "src": source,
                 "rec": recommendation_id, "tdb": target_db, "ok": chk.ok, "err": chk.error,
                 "destr": json.dumps(chk.destructive)})
            self._audit(s, pid, "propose", actor or source,
                        details={"parse_ok": chk.ok, "parse_error": chk.error, "destructive": chk.destructive,
                                 "statement_types": chk.statement_types, "confidence": confidence})
        return self.get(pid)

    def _transition(self, proposal_id: str, allowed_from: tuple, new_status: str, actor: str,
                    reason: Optional[str], action: str) -> Proposal:
        p = self.get(proposal_id)
        if p.status not in allowed_from:
            raise ReviewError(f"{proposal_id} is {p.status}; can only {action} from {', '.join(allowed_from)}")
        with self.db.get_session() as s:
            n = s.execute(text(
                "UPDATE qwen_dba.proposed_writes SET status = :new, reviewed_by = :actor, reviewed_at = NOW(), "
                "reason = :reason, updated_at = NOW() WHERE proposal_id = :p AND status = :old"),
                {"new": new_status, "actor": actor, "reason": reason, "p": proposal_id, "old": p.status}).rowcount
            if n != 1:  # raced with another reviewer
                raise ReviewError(f"{proposal_id} changed concurrently; reload and retry")
            self._audit(s, proposal_id, action, actor, reason, {"from": p.status, "to": new_status})
        return self.get(proposal_id)

    def approve(self, proposal_id: str, actor: str, reason: Optional[str] = None) -> Proposal:
        if not actor:
            raise ReviewError("approve needs a reviewer name")
        p = self.get(proposal_id)
        if not p.parse_ok:
            raise ReviewError(f"{proposal_id} does not parse ({p.parse_error}); reject it instead")
        return self._transition(proposal_id, ("pending",), "approved", actor, reason, "approve")

    def reject(self, proposal_id: str, actor: str, reason: str) -> Proposal:
        if not actor:
            raise ReviewError("reject needs a reviewer name")
        if not reason or not reason.strip():
            raise ReviewError("reject needs a reason")
        return self._transition(proposal_id, ("pending", "approved"), "rejected", actor, reason.strip(), "reject")

    def apply(self, proposal_id: str, actor: str, confirm: bool = False) -> Proposal:
        """Run the proposal's SQL on its target DB in one transaction."""
        p = self.get(proposal_id)
        problem = None
        if not confirm:
            problem = "apply requires explicit confirmation"
        elif not p.parse_ok:
            problem = f"SQL does not parse: {p.parse_error}"
        elif not check_sql(p.sql).ok:  # re-check: never trust the stored flag alone
            problem = "SQL does not parse"
        elif self.review_mode and p.status != "approved":
            problem = f"review mode is on and {proposal_id} is {p.status}, not approved"
        elif not self.review_mode and p.status not in ("pending", "approved"):
            problem = f"{proposal_id} is {p.status}"
        if problem:
            with self.db.get_session() as s:
                self._audit(s, proposal_id, "apply_blocked", actor, problem,
                            {"status": p.status, "review_mode": self.review_mode, "confirm": confirm})
            raise ReviewError(problem)
        if self.target_db_factory is None:
            raise ReviewError("no target database configured for apply")

        target = self.target_db_factory(p.target_db)
        error = None
        try:
            with target.get_session() as ts:
                ts.execute(text(p.sql))
        except Exception as exc:  # the target transaction was rolled back by get_session()
            error = str(exc).splitlines()[0][:500]
        status = "failed" if error else "applied"
        with self.db.get_session() as s:
            s.execute(text(
                "UPDATE qwen_dba.proposed_writes SET status = :st, applied_by = :actor, applied_at = NOW(), "
                "apply_error = :err, updated_at = NOW() WHERE proposal_id = :p"),
                {"st": status, "actor": actor, "err": error, "p": proposal_id})
            self._audit(s, proposal_id, "apply_failed" if error else "apply", actor, error,
                        {"from": p.status, "review_mode": self.review_mode, "destructive": p.destructive})
        result = self.get(proposal_id)
        if error:
            raise ReviewError(f"apply failed (rolled back): {error}")
        return result
