#!/usr/bin/env python3
"""
Bank of India Mutual Fund (boimf.in) — download **monthly portfolio** workbooks for given YYYY-MM.

Uses the same JSON API as the investor site (Sitefinity + AjaxService.asmx):
  POST https://www.boimf.in/AjaxService.asmx/GetDocuments
  Content-Type: application/json;charset=utf-8

Payload mirrors `AjaxCall.js` → `NoCategoryCall` for the **Monthly Portfolio** tab:
  LibraryName: \"InvestorCorner\"
  folderName: \"MONTHLY PORTFOLIO\"  (tab title uppercased in JS)
  CategoryValue: \"no\"

The feed also contains older weekly liquid portfolio rows with different `DocName` patterns;
by default we only keep documents matching:
  MONTHLY-PORTFOLIO - <DD>-<MONTH>-<YYYY>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

BASE = "https://www.boimf.in"
AJAX_URL = f"{BASE}/AjaxService.asmx/GetDocuments"
REFERER = f"{BASE}/investor-corner"

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

# e.g. MONTHLY-PORTFOLIO - 28-FEBRUARY-2026
STANDARD_MONTHLY_RE = re.compile(
    r"MONTHLY-PORTFOLIO\s*-\s*\d{1,2}-([A-Za-z]+)-(\d{4})\s*$",
    re.I,
)


def safe_filename(url: str) -> str:
    path = urlparse(url).path
    base = path.rsplit("/", 1)[-1]
    base = unquote(base.split("?")[0])
    if not base or base in (".", ".."):
        base = "download.bin"
    return re.sub(r"[^\w.\-() ]", "_", base).strip()[:200] or "download.bin"


def docname_to_month_key(doc_name: str) -> str | None:
    m = STANDARD_MONTHLY_RE.search((doc_name or "").strip())
    if not m:
        return None
    mon_word, year = m.group(1), m.group(2)
    mm = MONTH_NAME_TO_NUM.get(mon_word.lower())
    if not mm:
        return None
    return f"{year}-{mm}"


def fetch_document_index() -> list[dict]:
    payload = {
        "pagno": 0,
        "category": None,
        "fromDate": None,
        "toDate": None,
        "LibraryName": "InvestorCorner",
        "folderName": "MONTHLY PORTFOLIO",
        "CategoryValue": "no",
    }
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        AJAX_URL,
        data=data,
        method="POST",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json;charset=utf-8",
            "Accept": "application/json",
            "Referer": REFERER,
        },
    )
    with urlopen(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8", "ignore")
    outer = json.loads(raw)
    inner = json.loads(outer.get("d") or "{}")
    docs = inner.get("Documents")
    if not isinstance(docs, list):
        return []
    return [d for d in docs if isinstance(d, dict)]


def pick_for_months(
    docs: list[dict],
    month_keys: list[str],
) -> dict[str, dict]:
    """
    For each requested YYYY-MM, pick one row: prefer standard MONTHLY-PORTFOLIO name;
    if multiple (shouldn't happen), keep the one with lexicographically greatest DocName.
    """
    want = set(month_keys)
    per_month: dict[str, list[dict]] = {k: [] for k in month_keys}

    for row in docs:
        name = row.get("DocName") or ""
        mk = docname_to_month_key(name)
        if mk is None:
            continue
        if mk in want:
            per_month[mk].append(row)

    chosen: dict[str, dict] = {}
    for mk in month_keys:
        rows = per_month.get(mk) or []
        if not rows:
            continue
        rows.sort(key=lambda r: (r.get("DocName") or ""), reverse=True)
        chosen[mk] = rows[0]
    return chosen


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
    parser = argparse.ArgumentParser(
        description="Fetch Bank of India MF monthly portfolio (consolidated xlsx per month)"
    )
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
    parser.add_argument("--fortnightly", action="store_true", help="Fetch fortnightly debt portfolios when supported")
    args = parser.parse_args()

    amc_dir = args.root / "amcs" / "bank-of-india-mutual-fund"

    print("POST GetDocuments (InvestorCorner / MONTHLY PORTFOLIO)…")
    docs = fetch_document_index()
    print(f"  … {len(docs)} row(s) in index", flush=True)

    selected = pick_for_months(docs, list(args.months))

    for month_key in args.months:
        out_dir = amc_dir / month_key
        out_dir.mkdir(parents=True, exist_ok=True)

        row = selected.get(month_key)
        print(f"\n{month_key}:", end=" ")
        if not row:
            print("no standard MONTHLY-PORTFOLIO row (see listing on site).")
            manifest: list[dict] = []
            man_path = out_dir / "manifest.json"
            man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            continue

        file_url = (row.get("FolderUrl") or "").strip()
        title = row.get("DocName") or ""
        fname = safe_filename(file_url) if file_url else "monthly-portfolio.xlsx"

        rec = {
            "month": month_key,
            "download_url": file_url,
            "saved_as": fname,
            "title": title,
            "folder_id": row.get("FolderID"),
        }

        if args.dry_run:
            print(f"would save {fname}")
            manifest = [{**rec, "sha256": "", "dry_run": True}]
        else:
            try:
                body = download(file_url)
                h = hashlib.sha256(body).hexdigest()
                dest = out_dir / fname
                dest.write_bytes(body)
                manifest = [{**rec, "sha256": h}]
                print(f"OK {fname} ({len(body)} bytes)")
            except Exception as e:
                manifest = [{**rec, "sha256": "", "error": str(e)}]
                print(f"ERR: {e}")

        man_path = out_dir / "manifest.json"
        man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Wrote {man_path}")


if __name__ == "__main__":
    main()
