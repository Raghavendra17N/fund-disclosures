#!/usr/bin/env python3
"""Shared helpers for the holdings ingestion plan and run report.

Pure functions (no GCS, no pandas at import time) so they can be unit tested offline.
Only scheme names, AMFI codes, AMC slugs and counts are handled here: never holdings values.
"""
from __future__ import annotations

import html
import io
import re
from typing import Dict, Iterable, List, Optional, Set

NORMALIZED_PREFIX = "fund_holdings/normalized/"
_CODE_RE = re.compile(r"as_of=([^/]+)/([^/]+)\.parquet$")
_SECRET_RE = re.compile(r"(?i)(token|secret|key|password|passwd|authorization|bearer)[=:\s]+\S+")
_PATH_RE = re.compile(r"(/[\w.\-]+){3,}")
_URL_QUERY_RE = re.compile(r"(https?://[^\s?)\]|]+)\?\S*")


def prev_period(period: str) -> str:
    """YYYY-MM -> previous calendar month YYYY-MM."""
    y, m = int(period[:4]), int(period[5:7])
    m -= 1
    if m == 0:
        y, m = y - 1, 12
    return f"{y:04d}-{m:02d}"


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MATURITY_RE = re.compile(r"(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-]*(20\d\d)\b")


def clean_name(text: Optional[str]) -> str:
    """Decode HTML entities (&amp; -> &, &#39; -> ') left in scheme/AMC names; collapses repeated escapes."""
    s = str(text or "")
    for _ in range(3):
        u = html.unescape(s)
        if u == s:
            break
        s = u
    return re.sub(r"\s+", " ", s).strip()


def maturity_hint(name: str, period: str) -> str:
    """'Sep 2026' when the fund name carries a month-year on or before the period end (likely matured), else ''."""
    py, pm = int(period[:4]), int(period[5:7])
    for mon, yr in _MATURITY_RE.findall(name or ""):
        if (int(yr), _MONTHS[mon.lower()]) <= (py, pm):
            return f"{mon.title()} {yr}"
    return ""


def sanitize_reason(text: Optional[str], limit: int = 160) -> str:
    """One short line, safe to print: no secrets, query strings, file paths or tracebacks."""
    if not text:
        return ""
    s = str(text)
    # Prefer the last exception line of a traceback, e.g. "HTTPError: HTTP Error 403: Forbidden".
    m = re.search(r"((?:[A-Za-z_.]+(?:Error|Exception)):[^|\n]*)\)?\s*$", s)
    if m:
        s = m.group(1)
    s = _SECRET_RE.sub("[redacted]", s)
    s = _URL_QUERY_RE.sub(r"\1", s)
    s = _PATH_RE.sub("…", s)
    s = re.sub(r"\s+", " ", s).strip(" |)")
    return s[: limit - 1] + "…" if len(s) > limit else s


def code_from_blob(name: str) -> Optional[tuple]:
    """'fund_holdings/normalized/as_of=2026-10-31/151067.parquet' -> ('2026-10-31', '151067')."""
    m = _CODE_RE.search(name)
    return (m.group(1), m.group(2)) if m else None


def list_state(bucket, period: str, resolve_missing_amc: bool = True) -> Dict[str, Dict[str, str]]:
    """{amfi_code: {"amc_id": ..., "as_of": ...}} for parquet blobs of one period.

    The exporter stamps amc_id in blob metadata. Blobs uploaded by hand have none, so the amc_id
    column is read from the (small) parquet itself. A manual upload therefore counts as done.
    """
    state: Dict[str, Dict[str, str]] = {}
    for blob in bucket.list_blobs(prefix=f"{NORMALIZED_PREFIX}as_of={period}"):
        hit = code_from_blob(blob.name)
        if not hit:
            continue
        as_of, code = hit
        amc_id = (blob.metadata or {}).get("amc_id") or ""
        if not amc_id and resolve_missing_amc:
            amc_id = read_parquet_field(blob, "amc_id")
        state[code] = {"amc_id": amc_id, "as_of": as_of}
    return state


def read_parquet_field(blob, column: str) -> str:
    """First value of a column from a parquet blob ('' on any failure)."""
    try:
        import pandas as pd  # lazy: keeps pure helpers importable without pandas

        df = pd.read_parquet(io.BytesIO(blob.download_as_bytes()), columns=[column])
        return str(df[column].iloc[0]) if len(df) else ""
    except Exception:
        return ""


def fund_name(bucket, period: str, as_of: str, code: str) -> str:
    """Scheme (main fund) name from a parquet, for funds listed in the report."""
    blob = bucket.get_blob(f"{NORMALIZED_PREFIX}as_of={as_of}/{code}.parquet")
    return clean_name(read_parquet_field(blob, "amfi_name") if blob else "") or f"AMFI {code}"


def codes_by_amc(state: Dict[str, Dict[str, str]]) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {}
    for code, info in state.items():
        out.setdefault(info.get("amc_id") or "", set()).add(code)
    return out


def plan_amcs(
    amc_ids: Iterable[str],
    current: Dict[str, Dict[str, str]],
    previous: Dict[str, Dict[str, str]],
    force: bool = False,
) -> List[Dict[str, object]]:
    """Decide per AMC: run or skip.

    A fund is done when its parquet for this period is in GCS (written by an earlier run or by hand).
    Expected funds are the ones the AMC had last month, so an AMC is skipped only when none of those is
    missing. An AMC with no history is skipped when it already has any output this period.
    """
    cur, prev = codes_by_amc(current), codes_by_amc(previous)
    plan = []
    for amc in amc_ids:
        have, expected = cur.get(amc, set()), prev.get(amc, set())
        missing = expected - have
        if force:
            action, why = "run", "force re-run requested"
        elif not have:
            action, why = "run", "no output in GCS for this period yet"
        elif missing:
            action, why = "run", f"{len(missing)} of {len(expected)} funds from last month still missing"
        else:
            action, why = "skip", f"already complete in GCS ({len(have)} funds)"
        plan.append({"amc_id": amc, "action": action, "reason": why, "have": len(have), "expected": len(expected)})
    return plan
