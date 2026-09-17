"""Thumbs up/down on assistant answers. Kept in memory for the summary
endpoint and appended to a JSONL file so nothing is lost across restarts --
the same "no database for a demo" stance as order_service.py."""

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FEEDBACK_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "feedback.jsonl"

_lock = threading.Lock()
_entries: list[dict[str, Any]] = []


def _load() -> None:
    if _entries or not FEEDBACK_FILE.exists():
        return
    with FEEDBACK_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    _entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue


def record(entry: dict[str, Any]) -> str:
    feedback_id = str(uuid.uuid4())
    stored = {"feedback_id": feedback_id, "at": datetime.now(timezone.utc).isoformat(), **entry}
    with _lock:
        _load()
        _entries.append(stored)
        try:
            FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)
            with FEEDBACK_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(stored) + "\n")
        except OSError:
            pass  # in-memory copy still holds it; a read-only disk shouldn't break the UI
    return feedback_id


def summary(limit: int = 10) -> dict[str, Any]:
    with _lock:
        _load()
        up = sum(1 for e in _entries if e.get("rating") == "up")
        down = sum(1 for e in _entries if e.get("rating") == "down")
        recent = list(reversed(_entries[-limit:]))
    return {"up": up, "down": down, "total": up + down, "recent": recent}


def reset_all() -> None:
    with _lock:
        _entries.clear()
