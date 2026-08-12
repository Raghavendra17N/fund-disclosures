#!/usr/bin/env python3
"""
Quantum Mutual Fund — download **monthly combined** portfolio `.xlsx` for given YYYY-MM.

Source (server-rendered HTML):
  https://www.quantumamc.com/portfolio/combined/-1/1/0/0

Each row’s `<a>` uses an `onclick` like:
  GTMcodeforxml('<xlsx url>', '...', 'February 2026 - All Funds', 'All Funds Portfolio');

We match labels of the form `<Month> <YYYY> - All Funds` and download the corresponding file.

Note: Quantum is a small AMC; this page lists **one combined workbook per month** (all funds),
not separate files per scheme.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE = "https://www.quantumamc.com"
LISTING_URL = f"{BASE}/portfolio/combined/-1/1/0/0"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
}

MONTH_NAMES_EN = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

# onclick="GTMcodeforxml('https://...uuid.xlsx', '...', 'January 2026 - All Funds', 'All Funds Portfolio');"
GTM_RE = re.compile(
    r"GTMcodeforxml\(\s*'(https://www\.quantumamc\.com/FileCDN/FactSheet/[a-f0-9\-]+\.xlsx)'\s*,"
    r"\s*'[^']*'\s*,\s*'([^']+)'\s*,\s*'All Funds Portfolio'\s*\)",
    re.I,
)

LABEL_MONTH_RE = re.compile(
    r"^([A-Za-z]+)\s+(\d{4})\s*-\s*All\s+Funds\s*$",
    re.I,
)


def _ssl_context(insecure: bool) -> ssl.SSLContext:
    if insecure:
        return ssl._create_unverified_context()
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def month_key_to_parts(month_key: str) -> tuple[int, int]:
    parts = month_key.strip().split("-")
    if len(parts) != 2:
        raise ValueError(f"Expected YYYY-MM, got {month_key!r}")
    y, m = int(parts[0]), int(parts[1].zfill(2))
    if not (1 <= m <= 12):
        raise ValueError(f"Bad month in {month_key!r}")
    return y, m


def label_to_year_month(label: str) -> tuple[int, int] | None:
    m = LABEL_MONTH_RE.match(label.strip())
    if not m:
        return None
    mon_name, y_s = m.group(1).title(), m.group(2)
    if mon_name not in MONTH_NAMES_EN:
        return None
    mi = MONTH_NAMES_EN.index(mon_name) + 1
    return int(y_s), mi


def fetch_listing_html(*, ctx: ssl.SSLContext) -> str:
    req = urllib.request.Request(LISTING_URL, headers=HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_all_funds_rows(html: str) -> dict[tuple[int, int], tuple[str, str]]:
    """Map (year, month) -> (url, label)."""
    out: dict[tuple[int, int], tuple[str, str]] = {}
    for url, label in GTM_RE.findall(html):
        ym = label_to_year_month(label)
        if ym is None:
            continue
        out[ym] = (url, label.strip())
    return out


def safe_filename(url: str) -> str:
    path = urlparse(url).path
    base = unquote(path.rsplit("/", 1)[-1].split("?")[0])
    if base.lower().endswith(".xlsx"):
        return re.sub(r"[^\w.\-]+", "_", base).strip("._")[:120] or "quantum_portfolio.xlsx"
    return "quantum_portfolio.xlsx"


def download(url: str, *, ctx: ssl.SSLContext) -> bytes:
    req = urllib.request.Request(
        url,
        headers={**HEADERS, "Accept": "*/*", "Referer": LISTING_URL},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
        return resp.read()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Quantum MF combined monthly portfolio xlsx",
    )
    parser.add_argument("--months", nargs="+", default=["2026-01", "2026-02"], help="YYYY-MM")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
    )
    parser.add_argument(
        "--insecure-ssl",
        action="store_true",
        help="Disable TLS verification if your Python lacks CA certs",
    )
    parser.add_argument("--fortnightly", action="store_true", help="Fetch fortnightly debt portfolios when supported")
    args = parser.parse_args()

    ctx = _ssl_context(args.insecure_ssl)
    amc_dir = args.root / "amcs" / "quantum-mutual-fund"

    print(f"GET {LISTING_URL} …", flush=True)
    try:
        html = fetch_listing_html(ctx=ctx)
    except urllib.error.URLError as e:
        if not args.insecure_ssl and "CERTIFICATE_VERIFY_FAILED" in str(e).upper():
            raise SystemExit(
                f"{e}\n\nRetry with:  python3 scripts/fetch_quantum.py ... --insecure-ssl"
            ) from e
        raise
    index = parse_all_funds_rows(html)
    print(f"  Parsed {len(index)} month row(s) (All Funds)", flush=True)

    want_keys = [month_key_to_parts(m) for m in args.months]

    for mk in args.months:
        y, mon = month_key_to_parts(mk)
        out_dir = amc_dir / mk
        out_dir.mkdir(parents=True, exist_ok=True)
        row = index.get((y, mon))
        manifest: list[dict] = []
        print(f"\n{mk}:", flush=True)
        if not row:
            print(f"  No 'All Funds' row for this month (check live site).", flush=True)
            (out_dir / "manifest.json").write_text("[]\n", encoding="utf-8")
            continue
        url, label = row
        fn = safe_filename(url)
        rec = {
            "month": mk,
            "label": label,
            "kind": "combined_all_funds",
            "download_url": url,
            "saved_as": fn,
        }
        try:
            body = download(url, ctx=ctx)
            h = hashlib.sha256(body).hexdigest()
            (out_dir / fn).write_bytes(body)
            manifest.append({**rec, "sha256": h})
            print(f"  OK {fn} ({len(body)} bytes)", flush=True)
        except Exception as e:
            manifest.append({**rec, "sha256": "", "error": str(e)})
            print(f"  ERR {fn}: {e}", flush=True)

        (out_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )
        print(f"  Wrote {out_dir / 'manifest.json'}", flush=True)


if __name__ == "__main__":
    main()
