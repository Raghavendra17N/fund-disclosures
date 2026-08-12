#!/usr/bin/env python3
"""
PGIM India Mutual Fund — download monthly portfolio files for given YYYY-MM.

Public page:
  https://www.pgimindia.com/mutual-funds/disclosures

API (disclosure module):
  GET  https://www.pgimindia.com/api/v1/brochure/disclosure/section
  POST https://www.pgimindia.com/api/v1/brochure/published/disclosure

The monthly portfolio section is identified dynamically from disclosure sections:
  Header path "Portfolios" -> section "Monthly Portfolio"
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
from urllib.parse import quote, unquote, urlparse, urlunparse

BASE = "https://www.pgimindia.com"
PAGE_URL = f"{BASE}/mutual-funds/disclosures"
SECTIONS_URL = f"{BASE}/api/v1/brochure/disclosure/section"
DISCLOSURE_URL = f"{BASE}/api/v1/brochure/published/disclosure"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

POST_HEADERS = {
    **HEADERS,
    "Content-Type": "application/json",
    "Origin": BASE,
    "Referer": PAGE_URL,
}

DATE_MONTH_YEAR_RE = re.compile(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})")
MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
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


def safe_filename(name: str) -> str:
    s = (name or "").strip() or "pgim_monthly_portfolio.xlsx"
    s = re.sub(r"[^\w.\-() ]+", "_", s).strip("._ ")
    return s[:220] or "pgim_monthly_portfolio.xlsx"


def path_to_download_url(url: str) -> str:
    p = urlparse(url)
    safe_path = "/".join(quote(seg, safe="") for seg in p.path.split("/"))
    return urlunparse((p.scheme, p.netloc, safe_path, p.params, p.query, p.fragment))


def parse_date_month_year(s: str) -> tuple[int, int] | None:
    m = DATE_MONTH_YEAR_RE.search((s or "").strip())
    if not m:
        return None
    month = MONTHS.get(m.group(2).lower())
    if not month:
        return None
    return int(m.group(3)), month


def fetch_json(url: str, *, ctx: ssl.SSLContext) -> dict:
    req = urllib.request.Request(url, headers=HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def post_json(url: str, payload: dict, *, ctx: ssl.SSLContext) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=POST_HEADERS,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def get_monthly_portfolio_section_id(*, ctx: ssl.SSLContext) -> str:
    obj = fetch_json(SECTIONS_URL, ctx=ctx)
    for header in obj.get("data") or []:
        if str(header.get("path", "")).strip().lower() != "portfolios":
            continue
        for section in header.get("Sections") or []:
            if str(section.get("path", "")).strip().lower() == "monthly portfolio":
                sid = str(section.get("SectionId") or "").strip()
                if sid:
                    return sid
    raise RuntimeError("Could not locate Monthly Portfolio section id")


def fetch_monthly_portfolio_rows(section_id: str, *, ctx: ssl.SSLContext) -> list[dict]:
    payload = {
        "sectionId": section_id,
        "source": "W",
        "branchCode": None,
    }
    obj = post_json(DISCLOSURE_URL, payload, ctx=ctx)
    rows: list[dict] = []
    for tab in obj.get("data") or []:
        tab_name = str(tab.get("tabName") or "").strip()
        for item in tab.get("content") or []:
            if isinstance(item, dict):
                rows.append({**item, "_tabName": tab_name})
    return rows


def download(url: str, *, ctx: ssl.SSLContext) -> bytes:
    req = urllib.request.Request(
        url,
        headers={**HEADERS, "Accept": "*/*", "Referer": PAGE_URL},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
        return resp.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch PGIM India monthly portfolio files")
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
    args = parser.parse_args()

    ctx = _ssl_context(args.insecure_ssl)
    amc_dir = args.root / "amcs" / "pgim-india-mutual-fund"
    targets = {month_key_to_ym(mk): mk for mk in args.months}

    print(f"GET {SECTIONS_URL} …", flush=True)
    try:
        section_id = get_monthly_portfolio_section_id(ctx=ctx)
        rows = fetch_monthly_portfolio_rows(section_id, ctx=ctx)
    except urllib.error.URLError as e:
        if not args.insecure_ssl and "CERTIFICATE_VERIFY_FAILED" in str(e).upper():
            raise SystemExit(
                f"{e}\n\nRetry with:  python3 scripts/fetch_pgim.py ... --insecure-ssl"
            ) from e
        raise

    print(f"  Section: {section_id}", flush=True)
    print(f"  Indexed {len(rows)} disclosure row(s)", flush=True)

    by_month: dict[tuple[int, int], list[dict]] = {}
    seen: set[str] = set()
    for row in rows:
        ym = parse_date_month_year(str(row.get("dateMonthYear") or ""))
        if ym is None or ym not in targets:
            continue
        url = str(row.get("pdfPath") or "").strip()
        if not url:
            continue
        key = f"{ym}:{url}"
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
        manifest: list[dict] = []
        selected = by_month.get(ym, [])
        print(f"\n{mk}: {len(selected)} file(s)", flush=True)
        if not selected:
            print("  No monthly portfolio rows found for this month.", flush=True)
            (out_dir / "manifest.json").write_text("[]\n", encoding="utf-8")
            continue

        for row in selected:
            title = str(row.get("title") or "").strip()
            tab_name = str(row.get("_tabName") or "").strip()
            date_my = str(row.get("dateMonthYear") or "").strip()
            raw_url = str(row.get("pdfPath") or "").strip()
            url = path_to_download_url(raw_url)
            raw_name = unquote(urlparse(url).path.rsplit("/", 1)[-1])
            fn = safe_filename(raw_name or f"pgim_{mk}.xlsx")
            rec = {
                "month": mk,
                "tab": tab_name,
                "title": title,
                "dateMonthYear": date_my,
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
