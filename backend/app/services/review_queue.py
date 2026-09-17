"""Human-in-the-loop queue for warranty answers below the auto-answer
confidence threshold. Append-only JSONL under data/review_queue/; a
resolution appends a second record with the same review_id, so the file
is its own audit trail.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import DATA_DIR

REVIEW_DIR = DATA_DIR / "review_queue"
REVIEW_FILE = REVIEW_DIR / "warranty_reviews.jsonl"

AUTO_ANSWER_THRESHOLD = 95


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read() -> list[dict[str, Any]]:
    if not REVIEW_FILE.exists():
        return []
    out = []
    for line in REVIEW_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _append(record: dict[str, Any]) -> None:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with REVIEW_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=True) + "\n")


def enqueue(*, question: str, draft_answer: Optional[str], confidence: float, reasons: list[str],
            sources: list[dict[str, Any]], location: Optional[str], route: str = "warranty") -> dict[str, Any]:
    record = {
        "review_id": f"RV-{uuid.uuid4().hex[:8].upper()}",
        "created_at": _now(),
        "status": "pending",
        "route": route,
        "question": question,
        "draft_answer": draft_answer,
        "confidence": confidence,
        "reasons": reasons,
        "sources": sources,
        "location": location,
    }
    _append(record)
    return record


def resolve(review_id: str, decision: str, final_answer: Optional[str], reviewer: Optional[str]) -> Optional[dict[str, Any]]:
    items = {r["review_id"]: r for r in _read()}
    current = items.get(review_id)
    if current is None:
        return None
    record = {**current, "status": "resolved", "decision": decision, "final_answer": final_answer or current.get("draft_answer"),
              "reviewer": reviewer, "resolved_at": _now()}
    _append(record)
    return record


def list_reviews(status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for r in _read():
        latest[r["review_id"]] = r  # later lines win
    rows = sorted(latest.values(), key=lambda r: r["created_at"], reverse=True)
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return rows[: max(1, min(limit, 500))]


def reset_all() -> None:
    if REVIEW_FILE.exists():
        REVIEW_FILE.unlink()
