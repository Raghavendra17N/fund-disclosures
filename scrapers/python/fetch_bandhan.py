#!/usr/bin/env python3
"""
Bandhan Mutual Fund — download **monthly portfolio** spreadsheets (one per scheme) for given YYYY-MM.

Uses the public CMS API:
  GET https://cmsnew.bandhanmutual.com/wp-json/finance-api/v1/posts/monthly-portfolios?page=N&per_page=100

Title ends with the as-on date (e.g. \"31 July 2026\" / \"30 June 2026\").
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

API_BASE = (
    "https://cmsnew.bandhanmutual.com/wp-json/finance-api/v1/posts/monthly-portfolios"
)
REFERER = "https://bandhanmutual.com/downloads/disclosures"

MONTH_NAME_TO_NUM = {
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
}

# End of title: "31 January 2026"
TITLE_DATE_RE = re.compile(
    r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s*$",
    re.I,
)

MONTHLY_DISCLOSURE_TYPE = "Monthly and Half-yearly Disclosures"


def safe_filename(url: str) -> str:
    path = urlparse(url).path
    base = path.rsplit("/", 1)[-1]
    base = unquote(base.split("?")[0])
    if not base or base in (".", ".."):
        base = "download.bin"
    return re.sub(r"[^\w.\-() ]", "_", base).strip()[:200] or "download.bin"


def title_to_month_key(title: str) -> str | None:
    m = TITLE_DATE_RE.search((title or "").strip())
    if not m:
        return None
    _day, month_name, year = m.group(1), m.group(2), m.group(3)
    mm = MONTH_NAME_TO_NUM.get(month_name.lower())
    if not mm:
        return None
    return f"{year}-{mm}"


def fetch_page(page: int, per_page: int = 100) -> list[dict]:
    url = f"{API_BASE}?page={page}&per_page={per_page}"
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Referer": REFERER,
        },
    )
    with urlopen(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8", "ignore")
    data = json.loads(raw)
    if not isinstance(data, dict):
        return []
    rows = data.get("data")
    # Past last page the API omits `data` or returns non-list.
    if not isinstance(rows, list):
        return []
    return rows


def load_rows_for_months(
    month_keys: list[str],
    *,
    max_pages: int = 0,
    expected_per_month: int = 78,
    no_growth_page_limit: int = 20,
) -> dict[str, list[dict]]:
    """
    Paginate disclosures until each month has expected_per_month rows (Bandhan ~78 schemes)
    or the API returns no more pages. Deduplicates by CMS post id.
    """
    per_month: dict[str, list[dict]] = {mk: [] for mk in month_keys}
    seen_ids: set[int] = set()
    page = 1
    no_growth_pages = 0
    while True:
        if max_pages and page > max_pages:
            print(f"  … stopping at --max-pages {max_pages}", flush=True)
            break
        batch = fetch_page(page)
        if not batch:
            print(f"  … page {page}: empty (end of API)", flush=True)
            break

        before_counts = {mk: len(per_month[mk]) for mk in month_keys}
        for row in batch:
            if not isinstance(row, dict):
                continue
            rid = row.get("id")
            for mk in month_keys:
                if not row_matches_month(row, mk):
                    continue
                if rid is not None and rid in seen_ids:
                    break
                if rid is not None:
                    seen_ids.add(rid)
                per_month[mk].append(row)
                break

        after_counts = {mk: len(per_month[mk]) for mk in month_keys}
        if after_counts == before_counts:
            no_growth_pages += 1
        else:
            no_growth_pages = 0

        print(
            f"  … page {page}: batch {len(batch)} | "
            + ", ".join(f"{mk}={len(per_month[mk])}" for mk in month_keys),
            flush=True,
        )

        if expected_per_month > 0 and all(
            len(per_month[mk]) >= expected_per_month for mk in month_keys
        ):
            print("  … reached --expected-per-month — stopping.", flush=True)
            break

        if no_growth_page_limit > 0 and no_growth_pages >= no_growth_page_limit:
            print(
                f"  … no growth for {no_growth_pages} consecutive pages — stopping.",
                flush=True,
            )
            break

        page += 1
        if page > 800:
            raise RuntimeError(
                "Safety stop: exceeded 800 pages — raise --expected-per-month or check API"
            )

    for mk in month_keys:
        per_month[mk].sort(key=lambda r: (r.get("title") or ""))
    return per_month


def file_url_from_row(row: dict) -> str | None:
    acf = row.get("acf_fields") or {}
    files = acf.get("disclosure_files") or []
    if not files:
        return None
    first = files[0]
    if not isinstance(first, dict):
        return None
    link = first.get("document_link") or {}
    if isinstance(link, dict):
        u = link.get("url")
        if u:
            return str(u).strip()
    return None


def row_matches_month(row: dict, month_key: str) -> bool:
    # monthly-portfolios endpoint is already scoped; match by title date only
    if title_to_month_key(row.get("title") or "") != month_key:
        return False
    if not file_url_from_row(row):
        return False
    return True


def download(url: str) -> bytes:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*",
            "Referer": REFERER,
        },
    )
    with urlopen(req, timeout=120) as resp:
        return resp.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Bandhan MF monthly portfolio files")
    parser.add_argument(
        "--months",
        nargs="+",
        default=["2026-01", "2026-02"],
        help="Months as YYYY-MM",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="mf-monthly-holdings root",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max files per month (0 = all)")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Stop after this many API pages (0 = use --expected-per-month heuristic).",
    )
    parser.add_argument(
        "--expected-per-month",
        type=int,
        default=78,
        help="Stop paginating once each month has this many monthly-portfolio rows "
        "(Bandhan had 78 schemes as of early 2026). Use 0 to paginate until API ends (slow).",
    )
    parser.add_argument(
        "--no-growth-page-limit",
        type=int,
        default=20,
        help="Stop if matched counts do not increase for this many consecutive pages.",
    )
    args = parser.parse_args()

    amc_dir = args.root / "amcs" / "bandhan-mutual-fund"

    exp = args.expected_per_month
    print("Scanning disclosures API (paginated until each month is complete)…")
    per_month = load_rows_for_months(
        list(args.months),
        max_pages=args.max_pages,
        expected_per_month=exp,
        no_growth_page_limit=max(0, args.no_growth_page_limit),
    )

    for month_key in args.months:
        selected = list(per_month.get(month_key) or [])
        if args.limit > 0:
            selected = selected[: args.limit]

        out_dir = amc_dir / month_key
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{month_key}: {len(selected)} monthly portfolio file(s)")

        manifest: list[dict] = []
        if not selected:
            print(
                "  No rows matched (check month spelling or whether Bandhan published that month yet)."
            )

        for i, row in enumerate(selected, 1):
            file_url = file_url_from_row(row)
            if not file_url:
                continue
            fname = safe_filename(file_url)
            dest = out_dir / fname
            title = row.get("title") or ""

            rec = {
                "month": month_key,
                "download_url": file_url,
                "saved_as": fname,
                "title": title,
                "cms_id": row.get("id"),
                "disclosures_type": (row.get("acf_fields") or {}).get("disclosures_type"),
                "published": row.get("date"),
            }

            if args.dry_run:
                print(f"  [{i}] {fname}")
                manifest.append({**rec, "sha256": "", "dry_run": True})
                continue

            try:
                body = download(file_url)
                h = hashlib.sha256(body).hexdigest()
                dest.write_bytes(body)
                manifest.append({**rec, "sha256": h})
                print(f"  [{i}] OK {fname} ({len(body)} bytes)")
            except Exception as e:
                manifest.append({**rec, "sha256": "", "error": str(e)})
                print(f"  [{i}] ERR {fname}: {e}")

        man_path = out_dir / "manifest.json"
        man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Wrote {man_path}")


if __name__ == "__main__":
    main()
