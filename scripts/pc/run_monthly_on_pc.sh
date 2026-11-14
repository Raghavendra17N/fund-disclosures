#!/usr/bin/env bash
# Run ONE AMC's monthly holdings ingestion from a home/office PC (for AMC sites that refuse GitHub-hosted runners).
#
# Usage:   scripts/pc/run_monthly_on_pc.sh <amc-slug|missing> <YYYY-MM> [--write]
#          "missing" = every AMC that still lacks funds in GCS for the period (manual uploads count as done).
#          Set FORCE_OVERWRITE=true to re-run AMCs that are already complete. A per-fund report is printed at the end.
# Example: scripts/pc/run_monthly_on_pc.sh union-mutual-fund 2026-09          (listing only, writes nothing)
#          scripts/pc/run_monthly_on_pc.sh union-mutual-fund 2026-09 --write  (fetch, parse, export to the bucket)
#
# Needs: Node 20+, a Python venv with requirements.txt + google-cloud-storage (curl_cffi is in requirements.txt),
# and Google credentials able to write to the bucket (gcloud auth application-default login).
# Writes only fund_holdings/normalized/as_of=<month-end>/ objects for that AMC plus the two catalog maps; never overwrites
# (FORCE_OVERWRITE=false) and exports parquet only. Run one AMC at a time and check the exporter's PASS line.
set -euo pipefail

AMC_SLUG="${1:?amc slug required, e.g. union-mutual-fund}"
PERIOD="${2:?period required as YYYY-MM}"
MODE="${3:-}"

cd "$(dirname "$0")/../.."

# Use the Python you launched this from (your activated venv), not the system / Store "python3".
if [ -z "${PYTHON_BIN:-}" ] && command -v python >/dev/null 2>&1; then PYTHON_BIN="$(command -v python)"; fi
export PYTHON_BIN

if ! [[ "$PERIOD" =~ ^[0-9]{4}-(0[1-9]|1[0-2])$ ]]; then
  echo "period must look like 2026-09" >&2
  exit 2
fi

LIST_ARGS=(--type=monthly --period="$PERIOD")
[ "$AMC_SLUG" != "missing" ] && LIST_ARGS+=(--amc="$AMC_SLUG")
echo "== Listing $AMC_SLUG $PERIOD (read-only) =="
node scrapers/node/fetch-period.js "${LIST_ARGS[@]}" --list-only

if [ "$MODE" != "--write" ]; then
  echo "Listing only. Re-run with --write to fetch, parse and export to the bucket."
  exit 0
fi

export GCS_BUCKET="${GCS_BUCKET:-investmentflow-market-data}"
if [ "$AMC_SLUG" = "missing" ]; then export AMC=""; else export AMC="$AMC_SLUG"; fi
export TYPE=monthly PERIOD="$PERIOD"
export PARQUET_ONLY=true FORCE_OVERWRITE="${FORCE_OVERWRITE:-false}" CLOUD_PROVIDER=gcp
export CONCURRENCY=5 AMC_TIMEOUT_MS=360000 FETCH_TIMEOUT_MS=180000 PYTHONUTF8=1

echo "== Writing $AMC_SLUG $PERIOD to gs://$GCS_BUCKET (no overwrite, parquet only) =="
bash scripts/gcp/cloud_run_job.sh
echo "Check the line '=== GCP Validation Status: PASS' above before running the next AMC."
