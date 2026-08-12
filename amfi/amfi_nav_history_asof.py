#!/usr/bin/env python3
"""Download AMFI NAV History for a single day and filter funds.json to that universe.

Schemes that only appear in later NAVAll dumps (e.g. August launches) drop out of
matching, so disclosure ↔ AMFI gaps shrink to funds that actually operated as-of
the disclosure cut-off.

Default as-of date: 31-Jul-2026
  https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?frmdt=31-Jul-2026&todt=31-Jul-2026

Writes:
  data/amfi/NAVHistory_YYYY-MM-DD.txt
  data/amfi/active_codes_YYYY-MM-DD.json
  data/amfi/schemes_asof_YYYY-MM-DD.json
  data/amfi/funds_asof_YYYY-MM-DD.json
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime
from pathlib import Path


PORTAL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx"


def parse_dd_mon_yyyy(s: str) -> datetime:
    return datetime.strptime(s, "%d-%b-%Y")


def asof_token(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def portal_date(dt: datetime) -> str:
    return dt.strftime("%d-%b-%Y")


def download(frm: datetime, to: datetime, dest: Path) -> None:
    url = f"{PORTAL}?frmdt={portal_date(frm)}&todt={portal_date(to)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def parse_history(text: str) -> list[dict]:
    idx = text.find("Scheme Code;")
    if idx >= 0:
        text = text[idx:]

    rows: list[dict] = []
    amc = None
    cat = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("Scheme Code;"):
            continue
        if ";" not in line:
            if (
                line.startswith("Open Ended")
                or line.startswith("Close Ended")
                or line.startswith("Interval")
            ):
                cat = line
            elif "Mutual Fund" in line:
                amc = line
            continue
        parts = line.split(";")
        if len(parts) < 5:
            continue
        code = parts[0].strip()
        if not code.isdigit():
            continue

        def cell(i: int) -> str | None:
            if i >= len(parts):
                return None
            v = parts[i].strip()
            if not v or v == "-":
                return None
            return v

        rows.append(
            {
                "amfi_code": code,
                "name": parts[1].strip(),
                "isin_growth_or_payout": cell(2),
                "isin_div_reinvestment": cell(3),
                "nav": cell(4),
                "nav_date": cell(7),
                "amc_name": amc,
                "category": cat,
            }
        )
    return rows


def filter_funds(funds: list[dict], active_codes: set[str]) -> tuple[list[dict], list[dict]]:
    kept: list[dict] = []
    dropped: list[dict] = []
    for f in funds:
        codes = set(f.get("amfi_codes") or [])
        live = codes & active_codes
        if not live:
            dropped.append(f)
            continue
        row = dict(f)
        row["amfi_codes_active"] = sorted(live)
        row["amfi_codes_inactive"] = sorted(codes - active_codes)
        if row.get("canonical_amfi_code") not in live:
            row["canonical_amfi_code"] = row["amfi_codes_active"][0]
        kept.append(row)
    return kept, dropped


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--asof", default="31-Jul-2026", help="dd-Mon-YYYY (default 31-Jul-2026)")
    ap.add_argument("--input", default="", help="Use existing NAV history file instead of download")
    ap.add_argument("--funds", default="data/amfi/funds.json")
    ap.add_argument("--out-dir", default="data/amfi")
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args()

    asof = parse_dd_mon_yyyy(args.asof)
    token = asof_token(asof)
    out_dir = Path(args.out_dir)
    hist_path = Path(args.input) if args.input else out_dir / f"NAVHistory_{token}.txt"

    if not args.skip_download and not args.input:
        print(f"Downloading NAV history for {portal_date(asof)} …")
        download(asof, asof, hist_path)

    text = hist_path.read_text(encoding="utf-8", errors="replace")
    schemes = parse_history(text)
    active_codes = {r["amfi_code"] for r in schemes}

    funds = json.loads(Path(args.funds).read_text(encoding="utf-8"))
    kept, dropped = filter_funds(funds, active_codes)

    (out_dir / f"active_codes_{token}.json").write_text(
        json.dumps(sorted(active_codes), indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / f"schemes_asof_{token}.json").write_text(
        json.dumps(schemes, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    funds_asof = out_dir / f"funds_asof_{token}.json"
    funds_asof.write_text(json.dumps(kept, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = {
        "asof": portal_date(asof),
        "source": str(hist_path),
        "active_plan_codes": len(active_codes),
        "base_funds_before": len(funds),
        "base_funds_after": len(kept),
        "base_funds_dropped": len(dropped),
        "funds_asof_path": str(funds_asof),
    }
    (out_dir / f"asof_summary_{token}.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        f"As-of {portal_date(asof)}: {len(active_codes)} plan codes → "
        f"{len(kept)} base funds (dropped {len(dropped)} of {len(funds)})\n"
        f"Wrote {funds_asof}"
    )


if __name__ == "__main__":
    main()
