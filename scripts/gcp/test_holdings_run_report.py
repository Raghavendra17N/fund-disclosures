#!/usr/bin/env python3
"""Offline tests for the idempotent plan and the per-fund run report (no GCS, no network)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from holdings_state import clean_name, code_from_blob, maturity_hint, plan_amcs, prev_period, sanitize_reason  # noqa: E402
from run_report import build_report, render_markdown  # noqa: E402


def st(**amc_codes):
    return {c: {"amc_id": a.replace("_", "-"), "as_of": "2026-10-31"} for a, cs in amc_codes.items() for c in cs}


class PlanTests(unittest.TestCase):
    def test_prev_period_wraps_year(self):
        self.assertEqual(prev_period("2026-01"), "2025-12")
        self.assertEqual(prev_period("2026-10"), "2026-09")

    def test_skip_complete_run_missing_and_empty(self):
        prev = st(a=["1", "2"], b=["3"], c=["4"])
        cur = st(a=["1", "2"], b=[])  # a complete, b nothing, c nothing
        cur.update({"9": {"amc_id": "d", "as_of": "2026-10-31"}})  # manual upload for an AMC with no history
        plan = {p["amc_id"]: p for p in plan_amcs(["a", "b", "c", "d"], cur, prev)}
        self.assertEqual(plan["a"]["action"], "skip")
        self.assertEqual(plan["b"]["action"], "run")
        self.assertEqual(plan["c"]["action"], "run")
        self.assertEqual(plan["d"]["action"], "skip")

    def test_partial_amc_runs(self):
        plan = plan_amcs(["a"], st(a=["1"]), st(a=["1", "2"]))
        self.assertEqual(plan[0]["action"], "run")
        self.assertIn("1 of 2", plan[0]["reason"])

    def test_force_runs_everything(self):
        plan = plan_amcs(["a"], st(a=["1"]), st(a=["1"]), force=True)
        self.assertEqual(plan[0]["action"], "run")

    def test_blob_parse(self):
        self.assertEqual(code_from_blob("fund_holdings/normalized/as_of=2026-10-31/151067.parquet"), ("2026-10-31", "151067"))
        self.assertIsNone(code_from_blob("fund_holdings/catalog/x.json"))


class ReportTests(unittest.TestCase):
    def test_rows_and_reasons(self):
        after = st(a=["1", "2"], b=["5"])
        prev = st(a=["1", "2", "3"], b=["5"], c=["7"])
        export = {"uploaded": [{"amfi_code": "1", "scheme_name": "Alpha Fund", "amc_id": "a", "rows": 10}], "already_in_gcs": []}
        plan = {"plan": [{"amc_id": "b", "action": "skip"}, {"amc_id": "a", "action": "run"}, {"amc_id": "c", "action": "run"}]}
        outcomes = {"a": {"name": "A MF", "status": "ok", "reason": ""}, "c": {"name": "C MF", "status": "error", "reason": "HTTPError: HTTP Error 403: Forbidden"}}
        names = {"3": "Gamma Fund", "7": "Seven Fund"}
        rep = build_report("2026-10", ["a", "b", "c", "e"], {"a": "A MF", "b": "B MF", "c": "C MF", "e": "E MF"}, after, prev, export, plan, outcomes, names)
        by = {r["amfi_code"]: r for r in rep["funds"]}
        self.assertEqual(by["1"]["status"], "success")
        self.assertEqual(by["1"]["fund"], "Alpha Fund")
        self.assertEqual(by["2"]["status"], "skipped")
        self.assertEqual(by["5"]["reason"], "AMC already complete in GCS, not re-fetched")
        self.assertEqual(by["3"]["status"], "failed")
        self.assertIn("missing from the disclosure", by["3"]["reason"])
        self.assertEqual(by["7"]["status"], "failed")
        self.assertIn("403", by["7"]["reason"])
        self.assertEqual(rep["totals"], {"success": 1, "failed": 2, "skipped": 2})
        md = render_markdown(rep)
        self.assertIn("Seven Fund", md)
        self.assertIn("FAILED", md)

    def test_amc_with_no_history_and_no_output(self):
        rep = build_report("2026-10", ["e"], {"e": "E MF"}, {}, {}, None, None,
                           {"e": {"name": "E MF", "status": "empty", "reason": "python ok but empty"}}, {})
        self.assertEqual(rep["funds"][0]["fund"], "(no funds ingested)")
        self.assertEqual(rep["funds"][0]["status"], "failed")


class SanitizeTests(unittest.TestCase):
    def test_traceback_reduced_to_error_line(self):
        raw = 'Traceback File "/home/runner/work/a/b/c.py", line 85 | urlopen | urllib.error.HTTPError: HTTP Error 403: Forbidden'
        self.assertEqual(sanitize_reason(raw), "urllib.error.HTTPError: HTTP Error 403: Forbidden")

    def test_secrets_and_query_removed(self):
        out = sanitize_reason("GET https://x.com/a?token=abc123 failed key=SECRET")
        self.assertNotIn("abc123", out)
        self.assertNotIn("SECRET", out)


class OpenFinTests(unittest.TestCase):
    def test_month_end_and_date_gate(self):
        from openfin_fallback import accept_response, month_end, to_exporter_rows
        self.assertEqual(month_end("2026-10"), "2026-10-31")
        self.assertEqual(month_end("2026-02"), "2026-02-28")
        good = {"as_of": "2026-10-31", "holdings": [{"company_name": "X Ltd", "weight": 5.0}]}
        self.assertEqual(len(accept_response(good, "2026-10-31")), 1)
        # stale month, missing date, empty list and junk are all rejected
        self.assertIsNone(accept_response({"as_of": "2026-09-30", "holdings": good["holdings"]}, "2026-10-31"))
        self.assertIsNone(accept_response({"holdings": good["holdings"]}, "2026-10-31"))
        self.assertIsNone(accept_response({"as_of": "2026-10-31", "holdings": []}, "2026-10-31"))
        self.assertIsNone(accept_response("oops", "2026-10-31"))
        rows = to_exporter_rows(good["holdings"] + [{"weight": 1}])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["instrument"], "X Ltd")
        self.assertEqual(rows[0]["pct_nav"], 5.0)

    def test_report_marks_openfin_fill(self):
        rep = build_report("2026-10", ["a"], {"a": "A MF"}, st(a=["1"]), st(a=["1"]), None, None, {}, {"1": "Alpha"},
                           {"filled": [{"amfi_code": "1"}]})
        self.assertIn("OpenFin", rep["funds"][0]["reason"])
        self.assertEqual(rep["funds"][0]["status"], "success")


class NameTests(unittest.TestCase):
    def test_clean_name_decodes_entities(self):
        self.assertEqual(clean_name("Large &amp; Mid Cap Fund"), "Large & Mid Cap Fund")
        self.assertEqual(clean_name("UTI Children&#39;s Hybrid Fund"), "UTI Children's Hybrid Fund")
        self.assertEqual(clean_name("IL&amp;amp;FS"), "IL&FS")
        self.assertEqual(clean_name(None), "")

    def test_maturity_hint(self):
        self.assertEqual(maturity_hint("Axis Nifty SDL September 2026 Debt Index Fund", "2026-10"), "Sep 2026")
        self.assertEqual(maturity_hint("HDFC Nifty SDL Oct 2026 Index Fund", "2026-10"), "Oct 2026")
        self.assertEqual(maturity_hint("Nifty SDL Apr 2027 Index Fund", "2026-10"), "")
        self.assertEqual(maturity_hint("Edelweiss Large Cap Fund", "2026-10"), "")

    def test_report_flags_matured_and_cleans_names(self):
        rep = build_report("2026-10", ["a"], {"a": "A &amp; B MF"}, {}, st(a=["1"]), None, None,
                           {"a": {"name": "", "status": "ok", "reason": ""}}, {"1": "Nifty SDL Sep 2026 Fund &amp; Co"})
        row = rep["funds"][0]
        self.assertEqual(row["status"], "failed")
        self.assertIn("likely matured", row["reason"])
        self.assertEqual(row["fund"], "Nifty SDL Sep 2026 Fund & Co")
        self.assertEqual(row["amc"], "A & B MF")


if __name__ == "__main__":
    unittest.main()
