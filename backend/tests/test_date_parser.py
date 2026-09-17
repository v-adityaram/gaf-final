"""date_parser.resolve_delivery_date -- deterministic calendar arithmetic
against a fixed, known "today" (never the real system clock, so these are
stable regardless of what day they run)."""

from datetime import date

from app.services import date_parser

WEDNESDAY = date(2026, 9, 16)
FRIDAY = date(2026, 9, 18)
assert WEDNESDAY.weekday() == 2 and FRIDAY.weekday() == 4


def test_recognised_phrases_resolve_to_the_nearest_matching_date():
    cases = [
        ("today", WEDNESDAY, "2026-09-16"),
        ("tomorrow", WEDNESDAY, "2026-09-17"),
        ("Friday", WEDNESDAY, "2026-09-18"),          # nearest upcoming occurrence
        ("next Friday", WEDNESDAY, "2026-09-18"),     # same thing on a different day
        ("this Friday", WEDNESDAY, "2026-09-18"),
        ("next Friday", FRIDAY, "2026-09-25"),        # said ON that weekday -> following week
        ("Friday", FRIDAY, "2026-09-18"),             # bare weekday on that day -> today
        ("  NEXT tuesday  ", WEDNESDAY, "2026-09-22"),
        ("2026-10-03", WEDNESDAY, "2026-10-03"),      # ISO passes through
    ]
    for phrase, today, expected in cases:
        assert date_parser.resolve_delivery_date(phrase, today=today) == expected, phrase


def test_unrecognised_phrases_resolve_to_none_never_a_guess():
    for phrase in ["2026-13-40", "sometime next month", "ASAP", "next week", "Oct 1", "", "   ", None]:
        assert date_parser.resolve_delivery_date(phrase, today=WEDNESDAY) is None, phrase


def test_uses_the_real_today_when_not_overridden():
    assert date_parser.resolve_delivery_date("today") == date.today().isoformat()
