"""Filter disclosure filenames/URLs to a calendar as-of date (YYYY-MM-DD)."""
from __future__ import annotations

import re

DATE_TAIL_RE = re.compile(
    r"-(\d{1,2})-(\d{1,2})-(\d{4})(\.(?:xlsx|xls|xlsb|pdf|zip))?$",
    re.I,
)


def parse_as_of(as_of: str) -> tuple[int, int, int] | None:
    parts = as_of.strip().split("-")
    if len(parts) != 3:
        return None
    try:
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None
    if m < 1 or m > 12 or d < 1 or d > 31:
        return None
    return y, m, d


def as_of_tail(as_of: str) -> str | None:
    parsed = parse_as_of(as_of)
    if not parsed:
        return None
    y, m, d = parsed
    return f"-{d:02d}-{m:02d}-{y}"


def filename_matches_as_of(url_or_name: str, as_of: str) -> bool:
    tail = as_of_tail(as_of)
    if not tail:
        return True
    return tail.lower() in url_or_name.lower()


def default_as_of_for_month(month_key: str, *, fortnightly: bool) -> str | None:
    """Mid-month fortnightly default when --as-of omitted."""
    parts = month_key.strip().split("-")
    if len(parts) != 2:
        return None
    y, m = parts[0], parts[1].zfill(2)
    if fortnightly:
        return f"{y}-{m}-15"
    return None
