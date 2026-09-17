#!/usr/bin/env python
"""Clears the runtime state the app accumulates between demos -- request/
order metrics, the confirmed-orders ledger, the warranty review queue and
feedback -- without touching the synthetic dataset itself.

Run: python scripts/reset_demo_state.py   (stop the backend first, or call
POST /api/session/reset afterwards to drop in-memory order sessions)
"""

from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
TARGETS = [
    DATA / "metrics" / "request_history.jsonl",
    DATA / "metrics" / "order_history.jsonl",
    DATA / "orders" / "confirmed_orders.json",
    DATA / "review_queue" / "warranty_reviews.jsonl",
    DATA / "feedback.jsonl",
    Path(__file__).resolve().parent.parent / "backend" / "data" / "feedback.jsonl",
]

for path in TARGETS:
    if path.exists():
        path.unlink()
        print(f"removed {path.relative_to(DATA.parent)}")
print("Demo state cleared. The synthetic dataset (products, customers, orders, documents...) is untouched.")
