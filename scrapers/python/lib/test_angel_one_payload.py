#!/usr/bin/env python3
"""Angel One: disclosuresData is found wherever it sits in the __next_f payload (old and current layouts)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import fetch_angel_one as a  # noqa: E402

RECORDS = {
    "42": {"fields": {"Form_Type": "Disclosures", "Sub_Section": "Disclosure of Soft Dollar Arrangements",
                      "post_guid": ["https://cms.angelonemf.com/amc-cms/wp-content/uploads/formidable/20/Soft-Dollar.pdf"]}},
    "900": {"fields": {"Sub_Section": "Portfolio Disclosures", "Dropdown": "Monthly", "Dropdown2": "September 2026",
                       "post_guid": ["https://cms.angelonemf.com/amc-cms/wp-content/uploads/formidable/20/Monthly-Portfolio-September-2026-Angel-One-Gold-ETF-FOF-1-1.xlsx"]}},
    "901": {"fields": {"Sub_Section": "Portfolio Disclosures", "Dropdown": "Monthly", "Dropdown2": "",
                       "post_guid": ["https://cms.angelonemf.com/amc-cms/wp-content/uploads/formidable/20/Monthly-Portfolio-August-2026-Angel-One-Silver-ETF.xlsx"]}},
    "902": {"fields": {"Sub_Section": "Portfolio Disclosures", "Dropdown": "Half Yearly", "Dropdown2": "September 2026",
                       "post_guid": ["https://cms.angelonemf.com/amc-cms/wp-content/uploads/formidable/20/Half-Yearly-Portfolio-Sep-2025-Angel-One-X.xlsx"]}},
}


def page(payload_obj: str) -> str:
    """HTML with one self.__next_f.push([1,"<escaped>"]) chunk carrying the given RSC-style text."""
    escaped = json.dumps(payload_obj)[1:-1]
    return f'<html><script>self.__next_f.push([1,"{escaped}"])</script></html>'


class PayloadTests(unittest.TestCase):
    def test_current_layout_disclosures_nested_under_page_props(self):
        payload = "5:" + json.dumps(["$", "div", None, {"lang": "en", "children": [{"a": 1}], "disclosuresData": RECORDS}])
        html = page(payload)
        rows = a.extract_rows(html)
        keys = {(r["year"], r["month"]) for r in rows}
        self.assertEqual(keys, {(2026, 9), (2026, 8)})                       # half-yearly and the soft-dollar PDF are excluded
        sep = [r for r in rows if r["month"] == 9]
        self.assertEqual(len(sep), 1)
        self.assertTrue(sep[0]["url"].endswith("Monthly-Portfolio-September-2026-Angel-One-Gold-ETF-FOF-1-1.xlsx"))

    def test_older_layout_with_disclosures_at_the_top_still_works(self):
        payload = "5:" + json.dumps([None, {"disclosuresData": RECORDS}])
        self.assertEqual({(r["year"], r["month"]) for r in a.extract_rows(page(payload))}, {(2026, 9), (2026, 8)})

    def test_month_comes_from_the_file_name_when_the_dropdown_is_empty(self):
        payload = "5:" + json.dumps([None, {"lang": "en", "disclosuresData": {"901": RECORDS["901"]}}])
        rows = a.extract_rows(page(payload))
        self.assertEqual([(r["year"], r["month"]) for r in rows], [(2026, 8)])

    def test_decoder_helper_edge_cases(self):
        self.assertIsNone(a._decode_disclosures_object("no such key"))
        self.assertIsNone(a._decode_disclosures_object('"disclosuresData":{}'))                # empty object is not data
        self.assertIsNone(a._decode_disclosures_object('"disclosuresData":{"a":'))             # truncated
        self.assertEqual(a._decode_disclosures_object('x "disclosuresData":{"a":{"b":"}"}} tail'), {"a": {"b": "}"}})

    def test_a_page_without_the_data_still_raises_the_same_error(self):
        with self.assertRaises(ValueError):
            a.extract_props("<html>nothing here</html>")


if __name__ == "__main__":
    unittest.main()
