#!/usr/bin/env python3
"""
Canara Robeco Mutual Fund — download **monthly portfolio** files for given YYYY-MM.

Strategy (from site behaviour):
  1) GET the base page and extract the embedded `monthsByYear` map from JS (which
     year/month combos exist — no guessing).
  2) For each requested month, GET the filtered page:
       {PAGE_URL}?filteryear=YYYY&filtermonth=MM
  3) Parse `.form-container-right-card-pdf` for `<a href>` download links.

Requires: `beautifulsoup4` (see `scripts/requirements-extractor.txt`).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import http.cookiejar
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.parse import quote, unquote, urlunparse, urlparse

BASE_URL = "https://www.canararobeco.com"
PAGE_URL_MONTHLY = (
    f"{BASE_URL}/documents/statutory-disclosures/scheme-dashboard/scheme-monthly-portfolio/"
)
PAGE_URL_FORTNIGHTLY = (
    f"{BASE_URL}/documents/statutory-disclosures/fortnightly-portfolio-disclosure-debt/"
)
# Back-compat alias
PAGE_URL = PAGE_URL_MONTHLY

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# Fallback if `monthsByYear` is missing from HTML (older template / parse failure).
MONTHS_BY_YEAR_FALLBACK: dict[str, list[str]] = {
    "2026": ["02", "01"],
    "2025": ["12", "11", "10", "09", "08", "07", "06", "05", "04", "03", "02", "01"],
    "2024": ["12", "11", "10", "09", "08", "07", "06", "05", "04", "03", "02", "01"],
    "2023": ["12", "11", "10", "09", "08", "07", "06", "05", "04", "03", "02", "01"],
    "2022": ["12", "11", "10", "09", "08", "07", "06", "05", "04", "03", "02", "01"],
}

FILE_EXT_RE = re.compile(
    r"\.(pdf|xlsx|xls|zip|csv)(\?|$)",
    re.I,
)


def _require_bs4():
    try:
        from bs4 import BeautifulSoup  # type: ignore

        return BeautifulSoup
    except ImportError as e:
        raise SystemExit(
            "This script requires beautifulsoup4. Install: pip install beautifulsoup4\n"
            "Or: pip install -r scripts/requirements-extractor.txt"
        ) from e


def encode_url_for_http(url: str) -> str:
    """
    Convert an IRI (Unicode in path/query) to an ASCII URI urllib can send.
    Canara file URLs may contain en-dashes (U+2013) in path segments.
    """
    p = urlparse(url.strip())
    path = quote(p.path, safe="/%")
    return urlunparse((p.scheme, p.netloc, path, p.params, p.query, p.fragment))


def safe_filename(url: str) -> str:
    path = urlparse(url).path
    base = path.rsplit("/", 1)[-1]
    base = unquote(base.split("?")[0])
    # Normalize Unicode punctuation often seen in CMS-generated filenames
    base = base.replace("\u2013", "-").replace("\u2014", "-")
    if not base or base in (".", ".."):
        base = "download.bin"
    return re.sub(r"[^\w.\-() ]", "_", base).strip()[:200] or "download.bin"


def extract_js_object(html: str, var_name: str) -> str | None:
    """Extract a balanced `{ ... }` object after `const var_name =`."""
    m = re.search(
        rf"const\s+{re.escape(var_name)}\s*=\s*",
        html,
    )
    if not m:
        return None
    start = m.end()
    depth = 0
    i = start
    n = len(html)
    while i < n:
        c = html[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return html[start : i + 1]
        i += 1
    return None


def fetch_months_by_year(
    opener: urllib.request.OpenerDirector,
    page_url: str = PAGE_URL_MONTHLY,
) -> dict[str, list[str]]:
    """
    Parse `monthsByYear` from base page JS.
    Returns {"2026": ["02", "01", ...], ...} with months as zero-padded strings.
    """
    text = _http_get_text(page_url, referer=page_url)

    raw = extract_js_object(text, "monthsByYear")
    if not raw:
        print("  ⚠ monthsByYear not found — using fallback map", flush=True)
        return {k: list(v) for k, v in MONTHS_BY_YEAR_FALLBACK.items()}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  ⚠ monthsByYear JSON parse failed ({e}) — using fallback map", flush=True)
        return {k: list(v) for k, v in MONTHS_BY_YEAR_FALLBACK.items()}

    # Shape: {"2026": {"02": true, "01": true}, ...}
    result: dict[str, list[str]] = {}
    for year, months_dict in data.items():
        if not isinstance(months_dict, dict):
            continue
        keys = [str(k).zfill(2) for k in months_dict.keys()]
        result[str(year)] = sorted(keys, reverse=True)

    total = sum(len(v) for v in result.values())
    print(f"  ✓ monthsByYear: {len(result)} years, {total} year-month combos", flush=True)
    return result


def _http_get_text(url: str, *, referer: str) -> str:
    """Prefer curl_cffi (TLS fingerprint) — Canara returns 403 to plain urllib."""
    try:
        from curl_cffi import requests as creq  # type: ignore

        r = creq.get(
            url,
            headers={**HEADERS, "Referer": referer},
            impersonate="chrome124",
            timeout=60,
        )
        r.raise_for_status()
        return r.text
    except Exception:
        pass
    req = urllib.request.Request(url, headers={**HEADERS, "Referer": referer}, method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "ignore")


def _http_get_bytes(url: str, *, referer: str) -> bytes:
    safe_url = encode_url_for_http(url)
    try:
        from curl_cffi import requests as creq  # type: ignore

        r = creq.get(
            safe_url,
            headers={**HEADERS, "Referer": referer, "Accept": "*/*"},
            impersonate="chrome124",
            timeout=120,
        )
        r.raise_for_status()
        return r.content
    except Exception:
        pass
    req = urllib.request.Request(
        safe_url,
        headers={**HEADERS, "Referer": referer, "Accept": "*/*"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def _links_from_html(html: str, *, year: str, month: str) -> tuple[list[tuple[str, str]], int]:
    """Parse one filtered page → (rows, max_pagination)."""
    BeautifulSoup = _require_bs4()
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find(class_="form-container-right-card-pdf")
    rows: list[tuple[str, str]] = []
    if container:
        for a in container.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            if not href or href == "#":
                continue
            href_l = href.lower()
            if (not FILE_EXT_RE.search(href_l)) and (
                "wp-content/uploads" not in href_l and "download" not in href_l
            ):
                continue

            full = href if href.startswith("http") else urllib.parse.urljoin(BASE_URL, href)
            label = (a.get_text(strip=True) or "").strip()
            if label.lower() == "download":
                item = a.find_parent(class_="pdf-item") or a.parent
                title_el = item.select_one(".pdf-title") if item else None
                if title_el:
                    label = title_el.get_text(strip=True)
            if not label:
                label = f"portfolio-{year}-{month}"
            rows.append((label, full))

    max_page = 1
    pag = soup.find(class_="custom-pagination")
    if pag:
        for a in pag.find_all("a", href=True):
            m = re.search(r"pagination=(\d+)", a.get("href") or "")
            if m:
                max_page = max(max_page, int(m.group(1)))
    return rows, max_page


def fetch_links_for_month(
    opener: urllib.request.OpenerDirector,
    year: str,
    month: str,
    *,
    page_url: str = PAGE_URL_MONTHLY,
) -> list[tuple[str, str]]:
    """Return list of (label, absolute_url) across all pagination pages.

    Canara's scheme-monthly dashboard pages ~10 files per `pagination=N` page.
    Older code only read page 1 and missed Equity Hybrid / Large Cap / etc.
    """
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    max_page = 1
    page = 1
    while page <= max_page:
        qs = urllib.parse.urlencode(
            {"filteryear": year, "filtermonth": month, "pagination": page}
        )
        url = f"{page_url}?{qs}"
        html = _http_get_text(url, referer=page_url)
        rows, max_page = _links_from_html(html, year=year, month=month)
        for label, u in rows:
            if u in seen:
                continue
            seen.add(u)
            out.append((label, u))
        page += 1
        if page > 20:  # safety
            break
    return out


def download(
    opener: urllib.request.OpenerDirector,
    url: str,
    *,
    referer: str = PAGE_URL_MONTHLY,
) -> bytes:
    return _http_get_bytes(url, referer=referer)


def month_key_to_parts(month_key: str) -> tuple[str, str]:
    parts = month_key.strip().split("-")
    if len(parts) != 2:
        raise ValueError(f"Expected YYYY-MM, got {month_key!r}")
    y, mm = parts[0], parts[1].zfill(2)
    if len(y) != 4 or not y.isdigit():
        raise ValueError(f"Bad year in {month_key!r}")
    if not (mm.isdigit() and 1 <= int(mm) <= 12):
        raise ValueError(f"Bad month in {month_key!r}")
    return y, mm


def month_available(months_by_year: dict[str, list[str]], year: str, month: str) -> bool:
    months = months_by_year.get(year)
    if not months:
        return False
    m2 = month.zfill(2)
    return m2 in months or month in months


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Canara Robeco MF monthly portfolio file(s) per YYYY-MM",
    )
    parser.add_argument(
        "--months",
        nargs="+",
        default=["2026-01", "2026-02"],
        help="Calendar months as YYYY-MM",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="mf-monthly-holdings root",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max files per month (0 = all links in the card)",
    )
    parser.add_argument(
        "--skip-unavailable",
        action="store_true",
        help="If a month is not listed in monthsByYear, skip instead of erroring.",
    )
    parser.add_argument(
        "--fortnightly",
        action="store_true",
        help="Fetch debt fortnightly portfolio page (not scheme-monthly dashboard).",
    )
    args = parser.parse_args()

    _require_bs4()  # fail fast

    page_url = PAGE_URL_FORTNIGHTLY if args.fortnightly else PAGE_URL_MONTHLY
    kind = "fortnightly-debt" if args.fortnightly else "monthly"

    amc_dir = args.root / "amcs" / "canara-robeco-mutual-fund"
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    print(f"Fetching {kind} base page for monthsByYear …", flush=True)
    months_by_year = fetch_months_by_year(opener, page_url=page_url)

    for month_key in args.months:
        year, month = month_key_to_parts(month_key)
        out_dir = amc_dir / month_key
        out_dir.mkdir(parents=True, exist_ok=True)

        if not month_available(months_by_year, year, month):
            msg = (
                f"{month_key} is not listed in monthsByYear for this site "
                f"(year {year} has: {months_by_year.get(year, [])})"
            )
            if args.skip_unavailable:
                print(f"\n{month_key}: SKIP — {msg}", flush=True)
                (out_dir / "manifest.json").write_text("[]\n", encoding="utf-8")
                continue
            raise SystemExit(f"Error: {msg}")

        print(f"\n{month_key}: GET filtered {kind} page …", flush=True)
        rows = fetch_links_for_month(opener, year, month, page_url=page_url)
        if args.limit > 0:
            rows = rows[: args.limit]

        print(f"  … {len(rows)} file link(s)", flush=True)
        manifest: list[dict] = []

        if not rows:
            print("  No links in .form-container-right-card-pdf (empty or blocked).", flush=True)

        for i, (label, file_url) in enumerate(rows, 1):
            fname = safe_filename(file_url)
            rec = {
                "month": month_key,
                "download_url": file_url,
                "saved_as": fname,
                "label": label,
                "source": kind,
            }
            if args.dry_run:
                print(f"  [{i}] {fname}", flush=True)
                manifest.append({**rec, "sha256": "", "dry_run": True})
                continue
            try:
                body = download(opener, file_url, referer=page_url)
                h = hashlib.sha256(body).hexdigest()
                dest = out_dir / fname
                dest.write_bytes(body)
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
