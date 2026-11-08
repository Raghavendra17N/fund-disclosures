#!/usr/bin/env python3
"""
Month names as AMC sites write them: full names (SEPTEMBER), three-letter abbreviations (SEP) and the common SEPT spelling, in any letter case.

Some AMCs switch between styles from one month to the next (Bank of India published 31-AUGUST-2026 and then 30-SEP-2026). A fetcher that only
knows full names silently skips the abbreviated month, so every fetcher that reads a month from a document name should use ``month_number``,
``month_key`` and ``MONTH_WORD_PATTERN`` instead of its own table.
"""
from __future__ import annotations

_FULL = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]

MONTH_NUMBERS: dict[str, int] = {}
for _i, _name in enumerate(_FULL, start=1):
    MONTH_NUMBERS[_name] = _i
    MONTH_NUMBERS[_name[:3]] = _i
MONTH_NUMBERS["sept"] = 9

# Regex alternation, longest words first so "september" wins over "sept" and "sep".
MONTH_WORD_PATTERN = "|".join(sorted(MONTH_NUMBERS, key=lambda w: (-len(w), w)))


def month_number(word: str | None) -> int | None:
    """1-12 for a month word in any case (full, 3-letter or SEPT); None for anything else (never guesses)."""
    if not word:
        return None
    return MONTH_NUMBERS.get(str(word).strip().strip(".").lower())


def month_key(word: str | None, year: str | int | None) -> str | None:
    """'YYYY-MM' from a month word and a four-digit year, or None."""
    n = month_number(word)
    try:
        y = int(str(year).strip())
    except (TypeError, ValueError):
        return None
    if n is None or not (1900 <= y <= 2200):
        return None
    return f"{y:04d}-{n:02d}"
