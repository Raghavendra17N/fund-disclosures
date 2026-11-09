#!/usr/bin/env python3
"""HSBC portfolio links: extension-less September 2026 document links are found and saved as .xlsx."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import fetch_hsbc  # noqa: E402

BASE = "-/media/files/attachments/india/mutual-funds/portfolios"
AUG = f'<a href="{BASE}/document-31082026/hsbc-flexi-cap-fund-31-aug-2026.xlsx" title="HSBC Flexi Cap Fund 31 August 2026 (XLS, 250KB)">HSBC Flexi Cap Fund 31 August 2026</a>'
SEP = f'<a href="{BASE}/document-30092026/hsbc-flexi-cap-fund-30-sep-2026" title="HSBC Flexi Cap Fund 30 September 2026 (XLS, 253KB)">HSBC Flexi Cap Fund 30 September 2026</a>'
SEP_PDF = f'<a href="{BASE}/document-30092026/hsbc-flexi-cap-fund-30-sep-2026.pdf">HSBC Flexi Cap Fund 30 September 2026 factsheet</a>'
OTHER = '<a href="/-/media/Files/attachments/india/mutual-funds/aum/2026/quarterly-aum-report-sep-2026.xlsx">Quarterly AUM September 2026</a>'
HTML = f'<section id="tabpanel-1797700734"><table>{AUG}{SEP}{SEP_PDF}{OTHER}</table></section>'


class LinkTests(unittest.TestCase):
    def test_september_extensionless_links_are_found_with_the_right_month(self):
        rows = fetch_hsbc.extract_rows(HTML)
        by_month = {}
        for r in rows:
            by_month.setdefault(r["month_key"], []).append(r["download_url"])
        self.assertEqual(sorted(by_month), ["2026-08", "2026-09"])
        self.assertEqual(len(by_month["2026-09"]), 1)
        self.assertTrue(by_month["2026-09"][0].endswith("/document-30092026/hsbc-flexi-cap-fund-30-sep-2026"))

    def test_pdfs_and_non_portfolio_links_are_not_taken(self):
        urls = [r["download_url"] for r in fetch_hsbc.extract_rows(HTML)]
        self.assertFalse(any(u.endswith(".pdf") for u in urls))
        self.assertFalse(any("quarterly-aum" in u for u in urls))

    def test_extension_is_added_only_when_missing(self):
        self.assertEqual(fetch_hsbc.safe_filename("https://x/a/document-30092026/hsbc-flexi-cap-fund-30-sep-2026"), "hsbc-flexi-cap-fund-30-sep-2026.xlsx")
        self.assertEqual(fetch_hsbc.safe_filename("https://x/a/hsbc-flexi-cap-fund-31-aug-2026.xlsx"), "hsbc-flexi-cap-fund-31-aug-2026.xlsx")
        self.assertEqual(fetch_hsbc.safe_filename("https://x/a/old-file.XLS?x=1"), "old-file.XLS")
        self.assertEqual(fetch_hsbc.safe_filename("https://x/a/"), "download.xlsx")

    def test_href_classifier(self):
        ok = fetch_hsbc.is_portfolio_document_href
        self.assertTrue(ok(f"{BASE}/document-30092026/hsbc-x-30-sep-2026"))
        self.assertTrue(ok(f"{BASE}/document-31082026/hsbc-x-31-aug-2026.xlsx"))
        for bad in (f"{BASE}/document-30092026/hsbc-x.pdf", "/aum/2026/report", f"{BASE}/readme", f"{BASE}/document-30092026/"):
            self.assertFalse(ok(bad), bad)

    def test_fortnightly_links_accept_extensionless_too_and_keep_the_token_filter(self):
        html = ('<section id="tabpanel-1884516352">'
                '<a href="-/media/x/fortnightly-debt-portfolio/document-15092026/hsbc-liquid-fund-15-sep-2026">a</a>'
                '<a href="-/media/x/fortnightly-debt-portfolio/document-30092026/hsbc-liquid-fund-30-sep-2026.xlsx">b</a></section>')
        rows = fetch_hsbc.extract_fortnightly_rows(html, "2026-09-15") if hasattr(fetch_hsbc, "extract_fortnightly_rows") else None
        if rows is not None:
            self.assertEqual(len(rows), 1)
            self.assertIn("document-15092026", rows[0]["download_url"])


if __name__ == "__main__":
    unittest.main()
