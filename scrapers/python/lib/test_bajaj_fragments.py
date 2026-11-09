#!/usr/bin/env python3
"""Bajaj: the September 2026 slugs use as-on-30-sep2026 (glued) where August used as-on-31-aug-2026."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import fetch_bajaj as b  # noqa: E402

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def item(slug, url=None, mime=XLSX):
    return {"id": 1, "slug": slug, "title": {"rendered": slug}, "source_url": url or f"https://www.bajajamc.com/wp-content/uploads/{slug}.xlsx", "mime_type": mime}


class FragmentTests(unittest.TestCase):
    def test_variants_cover_hyphenated_glued_and_sept(self):
        self.assertEqual(b.fragment_variants("as-on-30-sep-2026"), ["as-on-30-sep-2026", "as-on-30-sep2026", "as-on-30-sept-2026"])
        self.assertEqual(b.fragment_variants("as-on-31-aug-2026"), ["as-on-31-aug-2026", "as-on-31-aug2026"])

    def test_the_search_key_for_september_is_unchanged(self):
        self.assertEqual(b.month_search_key("2026-09")[0], "as-on-30-sep-2026")

    def test_september_glued_slug_now_matches_the_monthly_matcher(self):
        it = item("bajaj-finserv-flexi-cap-fund_monthly-portfolio-as-on-30-sep2026-xls")
        self.assertTrue(b.is_monthly_for(it, "as-on-30-sep-2026"))

    def test_august_hyphenated_slug_still_matches_and_months_do_not_cross(self):
        aug = item("bajaj-finserv-flexi-cap-fund_monthly-portfolio-as-on-31-aug-2026-xls")
        self.assertTrue(b.is_monthly_for(aug, "as-on-31-aug-2026"))
        self.assertFalse(b.is_monthly_for(aug, "as-on-30-sep-2026"))
        sep = item("bajaj-finserv-flexi-cap-fund_monthly-portfolio-as-on-30-sep2026-xls")
        self.assertFalse(b.is_monthly_for(sep, "as-on-31-aug-2026"))

    def test_fortnightly_files_are_not_taken_as_monthly_and_vice_versa(self):
        fort = item("bajaj-finserv-liquid-fund_fortnightly-portfolio-as-on-30-sep-2026")
        self.assertFalse(b.is_monthly_for(fort, "as-on-30-sep-2026"))
        self.assertTrue(b.is_fortnightly_for(fort, "as-on-30-sep-2026"))
        fort_glued = item("bajaj-finserv-liquid-fund_fortnightly-portfolio-as-on-15-sep2026")
        self.assertTrue(b.is_fortnightly_for(fort_glued, "as-on-15-sep-2026"))
        self.assertFalse(b.is_fortnightly_for(item("bajaj-finserv-flexi-cap-fund_monthly-portfolio-as-on-30-sep2026-xls"), "as-on-30-sep-2026"))

    def test_non_spreadsheets_and_unrelated_media_are_rejected(self):
        pdf = item("bajaj-finserv-flexi-cap-fund_monthly-portfolio-as-on-30-sep2026-pdf", url="https://x/a.pdf", mime="application/pdf")
        self.assertFalse(b.is_monthly_for(pdf, "as-on-30-sep-2026"))
        self.assertFalse(b.is_monthly_for(item("state-wise-aaum-september-2026"), "as-on-30-sep-2026"))


if __name__ == "__main__":
    unittest.main()
