#!/usr/bin/env python3
"""Optional last-resort fill for funds an AMC scrape could not deliver (off by default).

For AMFI codes the AMC had last month but that are still missing from GCS for this period, ask the OpenFin API
(the same third-party source the backend falls back to at read time) and write a parquet marked
source=openfin_api. Safety rules:
  * only data whose own as_of equals the month-end being ingested is accepted (never a stale month);
  * never overwrites an existing parquet (an AMC's own file always wins);
  * off unless OPENFIN_FALLBACK=true or --enable; restrict with OPENFIN_FALLBACK_AMCS=a,b;
  * logs only AMFI codes, AMC slugs and counts: no holdings values.
Never fails the job: any problem is reported and the script exits 0.
"""
from __future__ import annotations

import argparse
import calendar
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from holdings_state import fund_name, list_state, prev_period, sanitize_reason  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "run_report"
API = "https://openfin.pocketedge.in/api/v1/holdings/{code}?as_of={as_of}"


def month_end(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def accept_response(data: Any, target_as_of: str) -> Optional[List[Dict[str, Any]]]:
    """Holdings list if the response is for exactly target_as_of (ISO date), else None."""
    if not isinstance(data, dict):
        return None
    got = str(data.get("as_of") or "")[:10]
    items = data.get("holdings")
    if got != target_as_of or not isinstance(items, list) or not items:
        return None
    return items


def to_exporter_rows(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map OpenFin items to the dict shape gcp_exporter.shape_holding_row expects."""
    rows = []
    for it in items:
        name = str(it.get("instrument") or it.get("company_name") or it.get("name") or "").strip()
        if not name:
            continue
        rows.append({
            "instrument": name,
            "isin": it.get("isin"),
            "industry": it.get("industry") or it.get("sector"),
            "rating": it.get("rating"),
            "pct_nav": it.get("pct_nav") if it.get("pct_nav") is not None else (it.get("weight") if it.get("weight") is not None else it.get("percentage")),
            "market_value": it.get("market_value"),
            "quantity": it.get("quantity"),
            "section": it.get("section"),
        })
    return rows


def default_fetch(code: str, as_of: str) -> Any:
    req = urllib.request.Request(API.format(code=code, as_of=as_of), headers={"User-Agent": "InvestmentFlow-Ingestion/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8")) if resp.status == 200 else None


def run(bucket_name: str, period: str, enable: bool, amcs: List[str], fetch: Callable[[str, str], Any] = default_fetch) -> Dict[str, Any]:
    result: Dict[str, Any] = {"period": period, "enabled": enable, "filled": [], "skipped": []}
    if not enable:
        print("[openfin] fallback is off (set OPENFIN_FALLBACK=true to enable)")
        return result
    import io

    import pandas as pd
    from google.cloud import storage

    from gcp_exporter import shape_holding_row  # lazy: needs pandas / google-cloud-storage

    bucket = storage.Client().bucket(bucket_name)
    target = month_end(period)
    current = list_state(bucket, period)
    previous = list_state(bucket, prev_period(period), resolve_missing_amc=False)
    missing = {c: i for c, i in previous.items() if c not in current and (not amcs or i.get("amc_id") in amcs)}
    print(f"[openfin] {len(missing)} fund(s) missing for {target}; trying the fallback (as_of must equal {target})")
    for code, info in sorted(missing.items()):
        try:
            items = accept_response(fetch(code, target), target)
        except Exception as exc:
            result["skipped"].append({"amfi_code": code, "amc_id": info.get("amc_id", ""), "reason": f"api error: {sanitize_reason(str(exc))}"})
            continue
        rows = to_exporter_rows(items or [])
        if not rows:
            result["skipped"].append({"amfi_code": code, "amc_id": info.get("amc_id", ""), "reason": f"no data with as_of {target}"})
            continue
        path = f"fund_holdings/normalized/as_of={target}/{code}.parquet"
        blob = bucket.blob(path)
        if blob.exists():  # an AMC's own file always wins
            continue
        df = pd.DataFrame([shape_holding_row(r) for r in rows])
        df["amfi_code"], df["amc_id"], df["as_of"] = code, info.get("amc_id", ""), target
        df["amfi_name"] = fund_name(bucket, prev_period(period), info.get("as_of", ""), code)  # same fund, last month's name
        df["source_file"] = "openfin_api"
        buf = io.BytesIO()
        df.to_parquet(buf, index=False, engine="pyarrow", compression="snappy")
        buf.seek(0)
        blob.metadata = {"amfi_code": code, "amc_id": info.get("amc_id", ""), "as_of": target, "row_count": str(len(df)), "source": "openfin_api"}
        blob.upload_from_file(buf, content_type="application/octet-stream")
        result["filled"].append({"amfi_code": code, "amc_id": info.get("amc_id", ""), "rows": len(df)})
        print(f"[openfin] filled {code} ({info.get('amc_id', '')}, {len(df)} rows)")
    print(f"[openfin] filled={len(result['filled'])} skipped={len(result['skipped'])}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", required=True)
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--enable", action="store_true")
    args = ap.parse_args()
    enable = args.enable or os.getenv("OPENFIN_FALLBACK", "").lower() in {"1", "true", "yes"}
    amcs = [s.strip() for s in os.getenv("OPENFIN_FALLBACK_AMCS", "").split(",") if s.strip()]
    try:
        result = run(args.bucket, args.period, enable, amcs)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "openfin_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        print(f"[openfin] WARNING: fallback failed ({type(exc).__name__}: {sanitize_reason(str(exc))}); continuing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
