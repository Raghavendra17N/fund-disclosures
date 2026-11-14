#!/usr/bin/env python3
"""Decide which AMCs still need ingesting for a period (idempotent re-runs).

Prints the comma separated AMC ids to process on stdout (empty = nothing to do); the decision table goes to
stderr and to data/run_report/plan.json for the run report. FORCE_OVERWRITE=true / --force re-runs everything.
Any failure here exits 0 with the full requested list so the planner can never block ingestion.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from holdings_state import list_state, plan_amcs, prev_period  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def registry_amc_ids(cadence: str) -> list:
    reg = json.loads((ROOT / "registry" / "amcs.json").read_text(encoding="utf-8"))
    out = []
    for a in reg.get("amcs", []):
        adapter = (a.get("fetch", {}).get(cadence) or {}).get("adapter")
        if adapter and adapter != "unsupported":
            out.append(a["id"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", required=True)
    ap.add_argument("--bucket", required=True)
    ap.add_argument("--cadence", default="monthly")
    ap.add_argument("--amc", default="", help="Comma separated AMC ids (empty = all)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    force = args.force or os.getenv("FORCE_OVERWRITE", "").lower() in {"1", "true", "yes"}
    requested = [s.strip() for s in args.amc.split(",") if s.strip()] or registry_amc_ids(args.cadence)
    out_dir = ROOT / "data" / "run_report"
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        from google.cloud import storage

        bucket = storage.Client().bucket(args.bucket)
        plan = plan_amcs(
            requested,
            list_state(bucket, args.period),
            list_state(bucket, prev_period(args.period), resolve_missing_amc=False),
            force=force,
        )
    except Exception as exc:  # never block ingestion because the planner failed
        print(f"[plan] WARNING: could not read GCS state ({type(exc).__name__}); running all requested AMCs", file=sys.stderr)
        plan = [{"amc_id": a, "action": "run", "reason": "planner unavailable", "have": 0, "expected": 0} for a in requested]

    (out_dir / "plan.json").write_text(json.dumps({"period": args.period, "force": force, "plan": plan}, indent=2) + "\n")
    skipped = [p for p in plan if p["action"] == "skip"]
    run = [p for p in plan if p["action"] == "run"]
    print(f"[plan] period={args.period} force={force}: {len(run)} AMC(s) to run, {len(skipped)} already complete (skipped)", file=sys.stderr)
    for p in skipped:
        print(f"[plan]   SKIP {p['amc_id']}: {p['reason']}", file=sys.stderr)
    for p in run:
        print(f"[plan]   RUN  {p['amc_id']}: {p['reason']}", file=sys.stderr)
    print(",".join(p["amc_id"] for p in run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
