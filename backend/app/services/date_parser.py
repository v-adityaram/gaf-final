"""Deterministic parsing of the verbatim delivery-date phrase the order
extraction call returns (e.g. "next Friday", "tomorrow", "next Tuesday")
into a real calendar date.

This is arithmetic against the actual system date (date.today()), never a
guess and never an LLM call -- an unrecognized phrase (e.g. "sometime next
month") resolves to None, shown as "N/A"/left blank for the customer to
pick themselves, rather than ever fabricating a date.
"""

import re
from datetime import date, timedelta
from typing import Optional

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WEEKDAY_PHRASE = re.compile(r"^(?:(next|this|coming)\s+)?(" + "|".join(_WEEKDAYS) + r")$", re.IGNORECASE)


def resolve_delivery_date(phrase: Optional[str], *, today: Optional[date] = None) -> Optional[str]:
    """Returns an ISO ("YYYY-MM-DD") date string for a recognized phrase,
    or None when the phrase doesn't match a known pattern.

    Recognized: "today", "tomorrow", an exact weekday name optionally
    prefixed with "next"/"this"/"coming" (e.g. "Friday", "this Friday",
    "next Tuesday"), and an already-ISO date passed straight through.

    Weekday resolution always lands on the *nearest* upcoming occurrence
    of that weekday -- "Friday" said on a Wednesday means this coming
    Friday, and so does "next Friday" said on that same Wednesday. The one
    exception: "next <weekday>" said ON that weekday means the following
    week's occurrence, not today (saying "next Friday" on a Friday doesn't
    mean today) -- every other combination resolves to the closest match.
    """
    if not phrase:
        return None
    text = phrase.strip().lower()
    today = today or date.today()

    if _ISO_DATE.match(text):
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            return None

    if text == "today":
        return today.isoformat()
    if text == "tomorrow":
        return (today + timedelta(days=1)).isoformat()

    match = _WEEKDAY_PHRASE.match(text)
    if match:
        qualifier, weekday_name = match.groups()
        target_weekday = _WEEKDAYS[weekday_name.lower()]
        days_ahead = (target_weekday - today.weekday()) % 7
        if days_ahead == 0 and qualifier and qualifier.lower() == "next":
            days_ahead = 7
        return (today + timedelta(days=days_ahead)).isoformat()

    return None
