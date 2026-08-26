#!/usr/bin/env python3
"""Validate GCS Raw & Normalized Parquet outputs."""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
import pandas as pd
from google.cloud import storage


def validate_gcp(bucket_name: str, period: str, amc_filter: str | None = None) -> dict:
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    raw_prefix = "fund_holdings/raw/monthly/"
    raw_blobs = [b for b in bucket.list_blobs(prefix=raw_prefix) if period in b.name and (not amc_filter or f"/{amc_filter}/" in b.name)]
    
    norm_prefix = "fund_holdings/normalized/"
    parquet_blobs = [b for b in bucket.list_blobs(prefix=norm_prefix) if b.name.endswith(".parquet") and period in b.name]

    print(f"\n--- [GCP Audit] Raw Files: {len(raw_blobs)}, Parquet Schemes: {len(parquet_blobs)} ---")
    
    total_rows = 0
    errors = []
    schemes_verified = []

    for b in parquet_blobs:
        content = b.download_as_bytes()
        df = pd.read_parquet(io.BytesIO(content))
        row_count = len(df)
        total_rows += row_count
        amfi_code = b.name.split("/")[-1].replace(".parquet", "")

        for col in ["amfi_code", "instrument", "market_value", "pct_nav", "holding_type"]:
            if col not in df.columns:
                errors.append(f"{b.name}: missing column {col}")

        if row_count == 0:
            errors.append(f"{b.name}: 0 rows")

        scheme_name = df["amfi_name"].iloc[0] if "amfi_name" in df.columns else "unknown"
        print(f"  ✓ [AMFI: {amfi_code}] {scheme_name}: {row_count} rows")
        schemes_verified.append({"amfi_code": amfi_code, "rows": row_count})

    passed = len(errors) == 0 and len(parquet_blobs) > 0
    print(f"\n=== GCP Validation Status: {'PASS' if passed else 'FAIL'} (Total Rows: {total_rows}) ===")
    return {"passed": passed, "total_rows": total_rows, "errors": errors}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--period", required=True)
    ap.add_argument("--amc")
    args = ap.parse_args()
    res = validate_gcp(args.bucket, args.period, args.amc)
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
