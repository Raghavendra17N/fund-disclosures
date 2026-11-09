#!/usr/bin/env python3
"""Abakkus: the page now carries its data in <script id="verticals-data">; the old inline assignment still works."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import fetch_abakkus as a  # noqa: E402

VERTICALS = [
    {
        "id": 29,
        "title": "Monthly Portfolio Disclosures",
        "sections": [
            {
                "title": "2026-2027",
                "subSections": [
                    {
                        "title": "2026-2027",
                        "items": [
                            {
                                "title": "September 30, 2026",
                                "downloadMedia": {"url": "/uploads/IN_MF_MONTHLY_PORTFOLIO_September_30_2026.xlsx"},
                            }
                        ],
                    }
                ],
            }
        ],
    },
    {"id": 30, "title": "Other", "sections": []},
]

NEW_STYLE = (
    "<html><body><script id=\"verticals-data\" type=\"application/json\">"
    + json.dumps(VERTICALS)
    + "</script><script>const verticals = JSON.parse(document.getElementById('verticals-data').textContent);</script></body></html>"
)
OLD_STYLE = "<script>const verticals = " + json.dumps(VERTICALS) + ";</script>"


class VerticalsTests(unittest.TestCase):
    def test_data_script_tag_is_read(self):
        rows = a.extract_rows_from_verticals(NEW_STYLE)
        self.assertEqual([(r["year"], r["month"]) for r in rows], [(2026, 9)])
        self.assertTrue(rows[0]["url"].endswith("IN_MF_MONTHLY_PORTFOLIO_September_30_2026.xlsx"))

    def test_old_inline_assignment_still_works(self):
        rows = a.extract_rows_from_verticals(OLD_STYLE)
        self.assertEqual([(r["year"], r["month"]) for r in rows], [(2026, 9)])

    def test_page_with_neither_gives_no_rows(self):
        self.assertEqual(a.extract_rows_from_verticals("<html>no data here</html>"), [])
        self.assertEqual(a.load_verticals_json(""), [])


if __name__ == "__main__":
    unittest.main()
