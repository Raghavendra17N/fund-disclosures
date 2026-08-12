#!/usr/bin/env python3
"""
Tata Mutual Fund - download monthly portfolio files for YYYY-MM.

Public page:
  https://www.tatamutualfund.com/schemes-related/portfolio

Source used:
  The page embeds JSON as "initialData" for the default "Monthly" tab.
  Each row contains:
    - field_document_title (e.g. "Portfolio as on 31st January, 2026")
    - field_media_document (download URL)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import urllib.error
import urllib.request
import warnings
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, urlunparse

PAGE_URL = "https://www.tatamutualfund.com/schemes-related/portfolio"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TITLE_RE = re.compile(
    r"portfolio\s+as\s+on\s+\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r",?\s+([12]\d{3})",
    re.I,
)
MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


def _ssl_context(insecure: bool) -> ssl.SSLContext:
    if insecure:
        return ssl._create_unverified_context()
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def month_key_to_ym(month_key: str) -> tuple[int, int]:
    parts = month_key.strip().split("-")
    if len(parts) != 2:
        raise ValueError(f"Expected YYYY-MM, got {month_key!r}")
    y, m = int(parts[0]), int(parts[1].zfill(2))
    if not (1 <= m <= 12):
        raise ValueError(f"Bad month in {month_key!r}")
    return y, m


def parse_month_from_title(title: str) -> tuple[int, int] | None:
    m = TITLE_RE.search(title or "")
    if not m:
        return None
    month = MONTHS.get(m.group(1).lower())
    if not month:
        return None
    return int(m.group(2)), month


def safe_filename(name: str) -> str:
    s = (name or "").strip() or "tata_monthly_portfolio.xlsx"
    s = re.sub(r"[^\w.\-() ]+", "_", s).strip("._ ")
    return s[:220] or "tata_monthly_portfolio.xlsx"


def path_to_download_url(url: str) -> str:
    p = urlparse(url)
    safe_path = "/".join(quote(seg, safe="%") for seg in p.path.split("/"))
    host = p.netloc
    if host.lower() == "betacms.tatamutualfund.com":
        host = "www.tatamutualfund.com"
    return urlunparse((p.scheme, host, safe_path, p.params, p.query, p.fragment))


def fetch_text(url: str, *, ctx: ssl.SSLContext) -> str:
    req = urllib.request.Request(url, headers=HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def extract_initial_data_array(html_text: str) -> list[dict]:
    # The page contains escaped script payload; decode escapes first.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        decoded = html_text.encode("utf-8").decode("unicode_escape", errors="ignore")
    needle = '"initialData":['
    idx = decoded.find(needle)
    if idx < 0:
        return []

    start = decoded.find("[", idx)
    if start < 0:
        return []

    depth = 0
    end = -1
    for i, ch in enumerate(decoded[start:], start=start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return []

    arr_txt = decoded[start : end + 1]
    arr = json.loads(arr_txt)
    if not isinstance(arr, list):
        return []
    return [r for r in arr if isinstance(r, dict)]


def fetch_rows(*, ctx: ssl.SSLContext) -> list[dict]:
    html_text = fetch_text(PAGE_URL, ctx=ctx)
    rows = extract_initial_data_array(html_text)
    # Guard: keep only rows that look like Monthly tab entries
    return [r for r in rows if "portfolio as on" in str(r.get("field_document_title") or "").lower()]


def download(url: str, *, ctx: ssl.SSLContext) -> bytes:
    req = urllib.request.Request(
        url,
        headers={**HEADERS, "Accept": "*/*", "Referer": PAGE_URL},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
        return resp.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Tata monthly portfolio files")
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
    amc_dir = args.root / "amcs" / "tata-mutual-fund"
    targets = {month_key_to_ym(mk): mk for mk in args.months}

    print(f"GET {PAGE_URL}", flush=True)
    try:
        rows = fetch_rows(ctx=ctx)
    except urllib.error.URLError as e:
        if not args.insecure_ssl and "CERTIFICATE_VERIFY_FAILED" in str(e).upper():
            raise SystemExit(
                f"{e}\n\nRetry with:  python3 scripts/fetch_tata.py ... --insecure-ssl"
            ) from e
        raise
    print(f"  Indexed {len(rows)} row(s) from embedded Monthly tab data", flush=True)

    by_month: dict[tuple[int, int], list[dict]] = {}
    seen: set[str] = set()
    for row in rows:
        title = str(row.get("field_document_title") or "").strip()
        ym = parse_month_from_title(title)
        if ym is None or ym not in targets:
            continue
        raw_url = str(row.get("field_media_document") or row.get("field_icon_link") or "").strip()
        if not raw_url:
            continue
        key = f"{ym}:{raw_url}"
        if key in seen:
            continue
        seen.add(key)
        by_month.setdefault(ym, []).append(row)

    for ym, mk in targets.items():
        out_dir = amc_dir / mk
        out_dir.mkdir(parents=True, exist_ok=True)
        for p in out_dir.iterdir():
            if p.is_file():
                p.unlink()

        selected = by_month.get(ym, [])
        manifest: list[dict] = []
        print(f"\n{mk}: {len(selected)} file(s)", flush=True)
        if not selected:
            print("  No monthly portfolio row found for this month.", flush=True)
            (out_dir / "manifest.json").write_text("[]\n", encoding="utf-8")
            continue

        for row in selected:
            title = str(row.get("field_document_title") or "").strip()
            raw_url = str(row.get("field_media_document") or row.get("field_icon_link") or "").strip()
            url = path_to_download_url(raw_url)
            raw_name = unquote(urlparse(url).path.rsplit("/", 1)[-1])
            fn = safe_filename(raw_name or f"tata_monthly_portfolio_{mk}.xlsx")
            rec = {
                "month": mk,
                "title": title,
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

        (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"  Wrote {out_dir / 'manifest.json'}", flush=True)


if __name__ == "__main__":
    main()
