"""Conversation memory for the orchestrators.

The frontend sends the last few turns with each message; the orchestrators
fold them into their extraction/classification prompts so follow-ups work
("actually make it 80 squares", "and what about Naples?"). The memory is
only ever an INPUT to the LLM's extraction/classification step -- every
business decision downstream is still plain Python against live API data,
exactly as before. Nothing is stored server-side.
"""

from typing import Any, Optional

MAX_TURNS = 8
MAX_CHARS_PER_TURN = 500


def format_history(history: Optional[list[dict[str, Any]]]) -> str:
    """Renders prior turns as a compact transcript block, or "" if none."""
    if not history:
        return ""
    turns = [t for t in history if t.get("text")][-MAX_TURNS:]
    if not turns:
        return ""
    lines = []
    for turn in turns:
        speaker = "Assistant" if turn.get("role") == "assistant" else "Customer"
        text = str(turn["text"]).strip().replace("\n", " ")
        if len(text) > MAX_CHARS_PER_TURN:
            text = text[: MAX_CHARS_PER_TURN - 1] + "…"
        lines.append(f"{speaker}: {text}")
    return "Earlier in this conversation (oldest first):\n" + "\n".join(lines)
