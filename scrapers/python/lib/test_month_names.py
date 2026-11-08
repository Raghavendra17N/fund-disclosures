#!/usr/bin/env python3
"""Month-name parsing: full names, 3-letter abbreviations and SEPT, any letter case, for the shared helper and the Bank of India, HSBC and IL&FS fetchers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from month_names import MONTH_WORD_PATTERN, month_key, month_number  # noqa: E402
import fetch_boi  # noqa: E402
import fetch_hsbc  # noqa: E402
import fetch_ilfs  # noqa: E402

FULL = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


class MonthHelperTests(unittest.TestCase):
    def test_every_full_name_and_three_letter_abbreviation_in_any_case(self):
        for i, name in enumerate(FULL, start=1):
            for variant in (name, name.upper(), name.title(), name[:3], name[:3].upper(), name[:3].title()):
                self.assertEqual(month_number(variant), i, variant)

    def test_sept_and_trailing_dot_and_spaces(self):
        for v in ("sept", "SEPT", "Sept.", " SEP ", "Sep."):
            self.assertEqual(month_number(v), 9, v)

    def test_non_months_are_none_not_guessed(self):
        for v in (None, "", "   ", "smarch", "septem", "se", "13", "SEPTEMBERS", "Mon"):
            self.assertIsNone(month_number(v), v)

    def test_month_key_validates_the_year(self):
        self.assertEqual(month_key("SEP", "2026"), "2026-09")
        self.assertEqual(month_key("august", 2026), "2026-08")
        for bad in (None, "", "26", "abcd", "1800", "3000"):
            self.assertIsNone(month_key("sep", bad), bad)
        self.assertIsNone(month_key("xyz", "2026"))

    def test_pattern_prefers_the_longest_word(self):
        import re
        rx = re.compile("(" + MONTH_WORD_PATTERN + ")", re.I)
        for text, expected in (("september", "september"), ("SEPTEMBER", "SEPTEMBER"), ("sept", "sept"), ("sep", "sep"), ("august", "august"), ("aug", "aug")):
            self.assertEqual(rx.match(text).group(1), expected, text)


class BankOfIndiaTests(unittest.TestCase):
    def test_the_two_real_document_names(self):
        self.assertEqual(fetch_boi.docname_to_month_key("MONTHLY-PORTFOLIO - 30-SEP-2026"), "2026-09")
        self.assertEqual(fetch_boi.docname_to_month_key("MONTHLY-PORTFOLIO - 31-AUGUST-2026"), "2026-08")

    def test_other_styles_and_case(self):
        cases = {
            "MONTHLY-PORTFOLIO - 28-FEBRUARY-2026": "2026-02",
            "MONTHLY-PORTFOLIO - 30-APR-2024": "2024-04",
            "monthly-portfolio - 31-oct-2026": "2026-10",
            "MONTHLY-PORTFOLIO - 30-SEPT-2026": "2026-09",
            "MONTHLY-PORTFOLIO - 31-JULY-2026": "2026-07",
        }
        for name, expected in cases.items():
            self.assertEqual(fetch_boi.docname_to_month_key(name), expected, name)

    def test_garbage_stays_unparsed(self):
        for name in ("MONTHLY-PORTFOLIO - 3A1-AUGUST-2024", "MONTHLY-PORTFOLIO - 30-XYZ-2026", "FORTNIGHTLY", "", None):
            self.assertIsNone(fetch_boi.docname_to_month_key(name), name)

    def test_pick_for_months_now_selects_september(self):
        docs = [{"DocName": "MONTHLY-PORTFOLIO - 30-SEP-2026"}, {"DocName": "MONTHLY-PORTFOLIO - 31-AUGUST-2026"}]
        picked = fetch_boi.pick_for_months(docs, ["2026-09", "2026-08"])
        self.assertEqual(picked["2026-09"]["DocName"], "MONTHLY-PORTFOLIO - 30-SEP-2026")
        self.assertEqual(picked["2026-08"]["DocName"], "MONTHLY-PORTFOLIO - 31-AUGUST-2026")


class HsbcTests(unittest.TestCase):
    def test_abbreviated_full_and_mixed_case_text(self):
        cases = {
            "HSBC Large Cap Fund Sep 2026": "2026-09",
            "hsbc flexi cap fund - September 2026": "2026-09",
            "Monthly portfolio SEPT-2026": "2026-09",
            "Portfolio, sep, 2026": "2026-09",
            "Portfolio AUG 2026": "2026-08",
            "hsbc-banking-and-psu-debt-fund-31-jul-2026 July 2026": "2026-07",
        }
        for text, expected in cases.items():
            self.assertEqual(fetch_hsbc.text_to_month_key(text), expected, text)

    def test_no_false_matches_inside_other_words(self):
        for text in ("Market 2026", "Summary 2026", "Remarks 2026", "no date here", ""):
            self.assertIsNone(fetch_hsbc.text_to_month_key(text), text)


class IlfsTests(unittest.TestCase):
    def test_file_names_with_abbreviations_full_names_and_separators(self):
        cases = {
            "https://x/IL&FS Portfolio_Sep-2026.xlsx": "2026-09",
            "https://x/Monthly Portfolio September 2026.xlsx": "2026-09",
            "https://x/portfolio_aug_2026.xls": "2026-08",
            "https://x/PORTFOLIO-SEPT2026.xlsx": "2026-09",
        }
        for text, expected in cases.items():
            self.assertEqual(fetch_ilfs.text_to_month_key(text), expected, text)

    def test_no_false_matches_inside_other_words(self):
        for text in ("https://x/summary2026.xlsx", "https://x/format2026.pdf", "https://x/nothing.xlsx"):
            self.assertIsNone(fetch_ilfs.text_to_month_key(text), text)


if __name__ == "__main__":
    unittest.main()
