# Holdings ingestion: re-runs, manual uploads and the run report

How to run the monthly holdings ingestion so it only does the missing work, how to add a manual upload, and how to read the per-fund report.

## The rule: a fund is done when its parquet is in GCS

Each main fund has one file: `gs://investmentflow-market-data/fund_holdings/normalized/as_of=<YYYY-MM-DD>/<amfi_code>.parquet`. Direct/Regular and Growth/IDCW variants share holdings, so they share this file and appear as one row in the report.

Before fetching, `scripts/gcp/plan_run.py` lists the period's parquet files and decides per AMC:

| Situation | Action |
|---|---|
| No output for the period yet | run |
| Some funds the AMC had last month are still missing | run (only missing funds are uploaded) |
| Every fund from last month is present, or a new AMC already has output | skip |
| `force` / `FORCE_OVERWRITE=true` | run everything and overwrite |

A manual upload counts as done because the planner only looks at what is in GCS. If planning fails, the job logs a warning and runs everything requested.

## Run on GitHub

Actions, "Fund Holdings Ingestion to GCS (Cron)", Run workflow:

- `amc`: `ALL`, or one slug (for example `union-mutual-fund`).
- `period`: `YYYY-MM`, blank for the previous month.
- `force`: leave `false` for normal re-runs (only missing work). `true` re-runs and overwrites AMCs that are already complete.

The scheduled run (13th, 02:00 UTC) behaves like `ALL`, `force=false`. Running it again later is safe and only fills gaps.

## Run from your PC

For AMC sites that block GitHub runners (several returned HTTP 403 on 2026-11-13).

Needs Node 20+, a Python venv with `requirements.txt` and `google-cloud-storage`, and `gcloud auth application-default login`.

```
scripts/pc/run_monthly_on_pc.sh missing 2026-10            # list only, writes nothing
scripts/pc/run_monthly_on_pc.sh missing 2026-10 --write    # fetch only AMCs that still lack funds
scripts/pc/run_monthly_on_pc.sh union-mutual-fund 2026-10 --write   # one AMC
FORCE_OVERWRITE=true scripts/pc/run_monthly_on_pc.sh union-mutual-fund 2026-10 --write   # force
```

Check the line `=== GCP Validation Status: PASS` and the report printed at the end.

## Add a manual upload

1. Produce the normalized parquet for the fund (same schema the exporter writes: one row per holding, columns include `amfi_code`, `amfi_name`, `amc_id`, `as_of`).
2. Upload it as `fund_holdings/normalized/as_of=<month-end>/<amfi_code>.parquet`.
3. Re-run the workflow (or the PC script). That fund is counted as done and is not re-fetched or overwritten. Blobs without `amc_id` metadata are matched to their AMC by reading the `amc_id` column.

To replace a bad file, run with `force`.

## Read the report

After every run the pipeline writes `data/run_report/run_report.md` and `run_report.json`, prints a summary to the log and appends the full table to the GitHub run summary (Actions run page, Summary). A copy is uploaded as the `holdings-run-report-<run id>` artifact on a best-effort basis: if GitHub artifact storage is full, that step fails quietly and the run is unaffected.

Per main fund it shows AMC, status and reason:

- **success**: written to GCS in this run.
- **skipped**: already in GCS (an earlier run or a manual upload), or the AMC was complete and not re-fetched.
- **failed**: the AMC had this fund last month and it is still missing. The reason is the AMC's fetch outcome (for example `HTTP Error 403: Forbidden`, `empty`, missing secret) or "missing from the disclosure or failed parse/mapping".

An AMC with no history and no output shows one row, `(no funds ingested)`.

The job stays green even when funds are missing; look for the `::warning::` annotation and the "Failed" table at the top of the summary.

The report contains only scheme names, AMFI codes, AMC names and counts. Failure reasons are scrubbed of tokens, query strings and file paths.

## Tests

`python3 -m unittest scripts/gcp/test_holdings_run_report.py` (offline: plan, report and reason sanitizing).

## OpenFin fallback for funds an AMC could not deliver (off by default)

For AMFI codes the AMC had last month but that are still missing after the run, `scripts/gcp/openfin_fallback.py` can ask the OpenFin API (`openfin.pocketedge.in`, the same source the backend falls back to when it reads holdings) and write a parquet marked `source=openfin_api`.

- **Date check:** data is accepted only when the API's own `as_of` equals the month-end being ingested (for example `2026-10-31`). Stale months are never written.
- **Never overwrites:** an AMC's own parquet always wins; the fallback only fills holes.
- **Off unless asked:** `OPENFIN_FALLBACK=true`. Restrict with `OPENFIN_FALLBACK_AMCS=edelweiss-mutual-fund` (comma list; empty means every missing fund).
- **Report:** filled funds show as success with the reason "filled from OpenFin API (third party; as_of verified)". `data/run_report/openfin_result.json` lists them.
- **Where it runs:** wired into `cloud_run_job.sh` after the export. The GitHub workflow does not set the variable, so today it is a PC / manual option:

```
OPENFIN_FALLBACK=true OPENFIN_FALLBACK_AMCS=edelweiss-mutual-fund \
  scripts/pc/run_monthly_on_pc.sh missing 2026-10 --write
```
