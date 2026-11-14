#!/usr/bin/env python3
"""Per-fund ingestion run report: which main funds succeeded, failed or were skipped, with AMC and reason.

One row per main fund (one AMFI code / one parquet): the Direct/Regular and Growth/IDCW variants share a
holdings file, so they are already a single row. Expected funds are last month's funds for the AMC.

Writes data/run_report/run_report.{json,md}, prints a compact log block and appends the Markdown to
$GITHUB_STEP_SUMMARY. It never fails the job (always exits 0) and handles missing inputs. Only scheme names,
AMFI codes, AMC slugs and counts are written: no holdings values, tokens or file paths.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from holdings_state import fund_name, list_state, prev_period, sanitize_reason  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "run_report"


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def fetch_outcomes(cadence: str, period: str) -> Dict[str, Dict[str, str]]:
    """{amc_id: {"name", "status", "reason"}} from the fetch manifest(s) of this run."""
    out: Dict[str, Dict[str, str]] = {}
    probes = ROOT / "data" / "probes"
    for path in sorted(probes.glob(f"fetch-{cadence}-{period}*.json")) if probes.exists() else []:
        data = _load(path) or {}
        for r in data.get("results", []) or []:
            status = r.get("status") or "unknown"
            note = r.get("error") or r.get("notes") or ""
            out[r.get("id", "")] = {"name": r.get("name") or "", "status": status, "reason": sanitize_reason(note)}
    return out


def build_report(
    period: str,
    amc_ids: List[str],
    amc_names: Dict[str, str],
    after: Dict[str, Dict[str, str]],
    previous: Dict[str, Dict[str, str]],
    export: Optional[dict],
    plan: Optional[dict],
    outcomes: Dict[str, Dict[str, str]],
    names: Dict[str, str],
    openfin: Optional[dict] = None,
) -> Dict[str, Any]:
    """Pure: combine the inputs into rows. `names` maps AMFI code -> main fund name (best effort)."""
    uploaded = {u["amfi_code"]: u for u in (export or {}).get("uploaded", [])}
    exporter_skipped = {u["amfi_code"]: u for u in (export or {}).get("already_in_gcs", [])}
    filled = {f["amfi_code"] for f in (openfin or {}).get("filled", [])}
    plan_by_amc = {p["amc_id"]: p for p in (plan or {}).get("plan", [])}
    rows: List[Dict[str, str]] = []

    def amc_label(a: str) -> str:
        return amc_names.get(a) or outcomes.get(a, {}).get("name") or a

    # Funds present in GCS after the run: success (written now) or skipped (already there, incl. manual uploads).
    for code, info in sorted(after.items(), key=lambda kv: (kv[1].get("amc_id", ""), kv[0])):
        amc = info.get("amc_id", "")
        name = (uploaded.get(code) or exporter_skipped.get(code) or {}).get("scheme_name") or names.get(code) or f"AMFI {code}"
        if code in filled:
            status, why = "success", "filled from OpenFin API (third party; as_of verified; AMC file still missing)"
        elif code in uploaded:
            status, why = "success", "ingested in this run"
        elif plan_by_amc.get(amc, {}).get("action") == "skip":
            status, why = "skipped", "AMC already complete in GCS, not re-fetched"
        else:
            status, why = "skipped", "already in GCS (earlier run or manual upload)"
        rows.append({"fund": name, "amfi_code": code, "amc_id": amc, "amc": amc_label(amc), "status": status, "reason": why})

    # Funds the AMC had last month that are still missing: failed, with the AMC's fetch outcome as the reason.
    for code, info in sorted(previous.items(), key=lambda kv: (kv[1].get("amc_id", ""), kv[0])):
        if code in after:
            continue
        amc = info.get("amc_id", "")
        oc = outcomes.get(amc)
        if oc is None:
            why = "AMC not run in this job" if plan_by_amc.get(amc, {}).get("action") != "run" else "AMC produced no result"
        elif oc["status"] in ("error", "empty", "unsupported", "timeout"):
            why = f"AMC fetch {oc['status']}" + (f": {oc['reason']}" if oc["reason"] else "")
        else:
            why = "AMC fetched, but this fund is missing from the disclosure or failed parse/mapping"
        rows.append({"fund": names.get(code) or f"AMFI {code}", "amfi_code": code, "amc_id": amc, "amc": amc_label(amc), "status": "failed", "reason": why})

    # AMCs with no fund row at all (nothing now, nothing last month): one AMC-level failure row.
    seen = {r["amc_id"] for r in rows}
    for amc in amc_ids:
        if amc in seen:
            continue
        oc = outcomes.get(amc)
        if oc is None:
            continue  # not run and no history: nothing to report
        why = f"AMC fetch {oc['status']}" + (f": {oc['reason']}" if oc["reason"] else "")
        if oc["status"] == "ok":
            why = "AMC fetched but no fund was ingested (parse or mapping)"
        rows.append({"fund": "(no funds ingested)", "amfi_code": "", "amc_id": amc, "amc": amc_label(amc), "status": "failed", "reason": why})

    amcs: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        a = amcs.setdefault(r["amc_id"], {"amc": r["amc"], "success": 0, "failed": 0, "skipped": 0})
        a[r["status"]] += 1
    totals = {k: sum(1 for r in rows if r["status"] == k) for k in ("success", "failed", "skipped")}
    return {"period": period, "totals": totals, "amcs": amcs, "funds": rows}


def render_markdown(report: Dict[str, Any], full: bool = True) -> str:
    t = report["totals"]
    head = "FAILED" if t["failed"] else "COMPLETE"
    lines = [
        f"## Fund holdings ingestion report: {report['period']} ({head})",
        "",
        f"**{t['success']} funds ingested, {t['skipped']} already in GCS (skipped), {t['failed']} failed.** One row per main fund; Direct/Regular and Growth/IDCW share holdings.",
        "",
    ]
    failed = [r for r in report["funds"] if r["status"] == "failed"]
    if failed:
        lines += ["### Failed", "", "| AMC | Main fund | AMFI | Reason |", "|---|---|---|---|"]
        lines += [f"| {r['amc']} | {r['fund']} | {r['amfi_code']} | {r['reason']} |" for r in failed]
        lines.append("")
    lines += ["### By AMC", "", "| AMC | Ingested | Skipped | Failed |", "|---|---|---|---|"]
    for a in sorted(report["amcs"].values(), key=lambda x: (-x["failed"], x["amc"])):
        lines.append(f"| {a['amc']} | {a['success']} | {a['skipped']} | {a['failed']} |")
    if full:
        lines += ["", "### All funds", "", "| Status | AMC | Main fund | AMFI | Reason |", "|---|---|---|---|---|"]
        order = {"failed": 0, "success": 1, "skipped": 2}
        for r in sorted(report["funds"], key=lambda r: (order[r["status"]], r["amc"], r["fund"])):
            lines.append(f"| {r['status']} | {r['amc']} | {r['fund']} | {r['amfi_code']} | {r['reason']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", required=True)
    ap.add_argument("--bucket", default="")
    ap.add_argument("--cadence", default="monthly")
    args = ap.parse_args()
    try:
        reg = _load(ROOT / "registry" / "amcs.json") or {}
        amc_names = {a["id"]: a.get("name", a["id"]) for a in reg.get("amcs", [])}
        names: Dict[str, str] = {}
        openfin = _load(OUT_DIR / "openfin_result.json")
        filled_codes = {f["amfi_code"] for f in (openfin or {}).get("filled", [])}
        after: Dict[str, Dict[str, str]] = {}
        previous: Dict[str, Dict[str, str]] = {}
        if args.bucket:
            from google.cloud import storage

            bucket = storage.Client().bucket(args.bucket)
            after = list_state(bucket, args.period)
            previous = list_state(bucket, prev_period(args.period), resolve_missing_amc=False)
            for code, info in previous.items():
                if code not in after or code in filled_codes:  # failed or fallback-filled funds need a name
                    names[code] = fund_name(bucket, args.period, info["as_of"], code)
        report = build_report(
            args.period, list(amc_names), amc_names, after, previous,
            _load(OUT_DIR / "export_result.json"), _load(OUT_DIR / "plan.json"),
            fetch_outcomes(args.cadence, args.period), names, openfin,
        )
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / "run_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (OUT_DIR / "run_report.md").write_text(render_markdown(report), encoding="utf-8")
        print(render_markdown(report, full=False))
        summary = os.getenv("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(render_markdown(report))
        if report["totals"]["failed"]:
            print(f"::warning::Holdings ingestion {args.period}: {report['totals']['failed']} fund(s) missing, see the run summary")
    except Exception as exc:  # the report must never fail the job
        print(f"[report] WARNING: could not build the run report ({type(exc).__name__}: {sanitize_reason(str(exc))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
