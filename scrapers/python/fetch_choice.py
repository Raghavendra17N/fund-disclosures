#!/usr/bin/env python3
"""
Choice Mutual Fund — download **monthly portfolio** files for given YYYY-MM.

The disclosures page is a Next.js app; listings come from a public JSON API:

  POST https://choicemf.com/api/monthly-portfolio-report/portfolio-website-list
  Body: {}

Response `body.data` is a list of:
  { \"scheme_name\": str, \"reports\": [ { \"report_date\": \"YYYY-MM-DD\", \"file_path\": \"...\" } ] }

Files are served from:

  https://doc.choicemf.com/<file_path>

Paths may contain Unicode punctuation (e.g. en-dash); we percent-encode before GET.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import http.cookiejar
import urllib.request
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlunparse, urlparse

API_URL = "https://choicemf.com/api/monthly-portfolio-report/portfolio-website-list"
DOC_BASE = "https://doc.choicemf.com/"
PAGE_REF = "https://choicemf.com/disclosures/monthly-portfolio"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Referer": PAGE_REF,
    "Origin": "https://choicemf.com",
}


def encode_url_for_http(url: str) -> str:
    p = urlparse(url.strip())
    path = quote(p.path, safe="/%")
    return urlunparse((p.scheme, p.netloc, path, p.params, p.query, p.fragment))


def safe_filename(url: str, scheme_name: str, month_key: str) -> str:
    path = urlparse(url).path
    base = path.rsplit("/", 1)[-1]
    base = unquote(base.split("?")[0])
    base = base.replace("\u2013", "-").replace("\u2014", "-")
    if not base or base in (".", ".."):
        safe_scheme = re.sub(r"[^\w.\-]", "_", scheme_name)[:60]
        base = f"{safe_scheme}_{month_key}.xlsx"
    return re.sub(r"[^\w.\-() ]", "_", base).strip()[:200] or "download.bin"


def report_date_to_month_key(report_date: str) -> str | None:
    """YYYY-MM-DD -> YYYY-MM"""
    m = re.match(r"^(\d{4})-(\d{2})-\d{2}$", (report_date or "").strip())
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}"


def fetch_listing(opener: urllib.request.OpenerDirector) -> list[dict]:
    data = json.dumps({}).encode("utf-8")
    req = urllib.request.Request(API_URL, data=data, headers=HEADERS, method="POST")
    with opener.open(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", "ignore")
    payload = json.loads(raw)
    body = payload.get("body") or {}
    rows = body.get("data")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def flatten_reports(
    listing: list[dict],
    month_keys: set[str],
) -> list[tuple[str, str, str, str]]:
    """
    Returns list of (month_key, scheme_name, file_path, download_url).
    """
    out: list[tuple[str, str, str, str]] = []
    for scheme in listing:
        name = str(scheme.get("scheme_name") or "").strip() or "scheme"
        reports = scheme.get("reports")
        if not isinstance(reports, list):
            continue
        for rep in reports:
            if not isinstance(rep, dict):
                continue
            rd = str(rep.get("report_date") or "").strip()
            fp = str(rep.get("file_path") or "").strip().lstrip("/")
            if not fp:
                continue
            mk = report_date_to_month_key(rd)
            if not mk or mk not in month_keys:
                continue
            url = urljoin(DOC_BASE, fp)
            out.append((mk, name, fp, url))
    return out


def download(opener: urllib.request.OpenerDirector, url: str) -> bytes:
    safe = encode_url_for_http(url)
    req = urllib.request.Request(
        safe,
        headers={
            "User-Agent": HEADERS["User-Agent"],
            "Accept": "*/*",
            "Referer": PAGE_REF,
        },
        method="GET",
    )
    with opener.open(req, timeout=120) as resp:
        return resp.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Choice MF monthly portfolio files")
    parser.add_argument("--months", nargs="+", default=["2026-01", "2026-02"], help="YYYY-MM")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="mf-monthly-holdings root",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    want = set(args.months)
    amc_dir = args.root / "amcs" / "choice-mutual-fund"
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    print(f"POST {API_URL} …", flush=True)
    listing = fetch_listing(opener)
    print(f"  … {len(listing)} scheme row(s) in API", flush=True)

    rows = flatten_reports(listing, want)
    by_month: dict[str, list[tuple[str, str, str, str]]] = {k: [] for k in args.months}
    for item in rows:
        mk = item[0]
        if mk in by_month:
            by_month[mk].append(item)

    for month_key in args.months:
        out_dir = amc_dir / month_key
        out_dir.mkdir(parents=True, exist_ok=True)
        batch = by_month.get(month_key) or []
        print(f"\n{month_key}: {len(batch)} file(s)", flush=True)
        manifest: list[dict] = []

        if not batch:
            print("  No reports for this month in API response.", flush=True)

        for i, (_mk, scheme_name, file_path, file_url) in enumerate(batch, 1):
            fname = safe_filename(file_url, scheme_name, month_key)
            rec = {
                "month": month_key,
                "scheme_name": scheme_name,
                "report_path": file_path,
                "download_url": file_url,
                "saved_as": fname,
            }
            if args.dry_run:
                print(f"  [{i}] {fname}", flush=True)
                manifest.append({**rec, "sha256": "", "dry_run": True})
                continue
            try:
                body = download(opener, file_url)
                h = hashlib.sha256(body).hexdigest()
                (out_dir / fname).write_bytes(body)
                manifest.append({**rec, "sha256": h})
                print(f"  [{i}] OK {fname} ({len(body)} bytes)", flush=True)
            except Exception as e:
                manifest.append({**rec, "sha256": "", "error": str(e)})
                print(f"  [{i}] ERR {fname}: {e}", flush=True)

        man_path = out_dir / "manifest.json"
        man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Wrote {man_path}", flush=True)


if __name__ == "__main__":
    main()
