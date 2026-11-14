#!/usr/bin/env bash
set -eo pipefail

# Auto-compute previous calendar month (e.g. 2026-08 when running in Sep 2026) if PERIOD is not explicitly set
if [ -z "$PERIOD" ]; then
  PERIOD=$(python3 -c "from datetime import datetime, timedelta; now = datetime.now(); print((now.replace(day=1) - timedelta(days=1)).strftime('%Y-%m'))")
fi
TYPE="${TYPE:-monthly}"
AMC="${AMC:-}"
GCS_BUCKET="${GCS_BUCKET:-}"
PARQUET_ONLY="${PARQUET_ONLY:-true}"

PARQUET_FLAG=""
if [ "$PARQUET_ONLY" = "true" ] || [ "$PARQUET_ONLY" = "1" ]; then
  PARQUET_FLAG="--parquet-only"
fi

echo "================================================================="
echo " GCP Cloud Run Job: Fund Disclosures Ingestion"
echo " Period:       $PERIOD"
echo " AMC:          ${AMC:-ALL}"
echo " GCS Bucket:   ${GCS_BUCKET:-NONE}"
echo " Parquet Only: ${PARQUET_ONLY:-false}"
echo "================================================================="

# 0. Plan (idempotent re-runs): process only AMCs that still miss funds for this period in GCS.
# A manual upload of <amfi_code>.parquet counts as done. FORCE_OVERWRITE=true re-runs everything.
# If planning fails the job falls back to the full requested set; it never blocks ingestion.
FETCH_AMC="$AMC"
if [ -n "$GCS_BUCKET" ]; then
  FETCH_AMC=$(python3 scripts/gcp/plan_run.py --period="$PERIOD" --bucket="$GCS_BUCKET" --cadence="$TYPE" --amc="$AMC" || echo "$AMC")
  if [ -z "$FETCH_AMC" ]; then
    echo " Nothing to ingest: every requested AMC is already complete in GCS for $PERIOD (set force=true to re-run)."
  fi
fi

if [ -n "$GCS_BUCKET" ] && [ -z "$FETCH_AMC" ]; then
  : # skip fetch, parse and export; the report below still runs
else
  # 1. Fetch (--amc accepts a comma separated list)
  if [ -n "$FETCH_AMC" ]; then
    node scrapers/node/fetch-period.js --type="$TYPE" --period="$PERIOD" --amc="$FETCH_AMC" --concurrency="${CONCURRENCY:-5}"
  else
    node scrapers/node/fetch-period.js --type="$TYPE" --period="$PERIOD" --concurrency="${CONCURRENCY:-5}"
  fi

  # 2. Parse (only what was fetched exists on disk)
  case "$FETCH_AMC" in
    ""|*,*) python3 parsers/run_amc_parser.py --type="$TYPE" --period="$PERIOD" --all ;;
    *)      python3 parsers/run_amc_parser.py --type="$TYPE" --period="$PERIOD" --amc="$FETCH_AMC" ;;
  esac

  # 3. Enrich
  python3 scripts/enrich_holdings_identifiers.py --allow-incomplete

  # 4. GCS Export & Audit (exporter skips parquet files already in GCS unless force)
  if [ -n "$GCS_BUCKET" ]; then
    python3 scripts/gcp/gcp_exporter.py --period="$PERIOD" --bucket="$GCS_BUCKET" --cadence="$TYPE" $PARQUET_FLAG
    python3 scripts/gcp/validate_gcp_output.py --period="$PERIOD" --bucket="$GCS_BUCKET" ${AMC:+--amc="$AMC"}
  fi
fi

# 5. Per-fund run report (never fails the job)
if [ -n "$GCS_BUCKET" ]; then
  python3 scripts/gcp/run_report.py --period="$PERIOD" --bucket="$GCS_BUCKET" --cadence="$TYPE" || true
fi

echo "================================================================="
echo " GCP Job Complete"
echo "================================================================="
