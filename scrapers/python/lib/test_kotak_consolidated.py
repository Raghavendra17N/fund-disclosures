#!/usr/bin/env python3
"""Kotak monthly: keep the Consolidated SEBI Portfolio pack, not the fortnightly ones beside it."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import fetch_kotak as k  # noqa: E402

SEP = "2026-09"
CONS = (SEP, "https://www.kotakmf.com/Forms/Consolidated-SEBI-Portfolio-30-Sep-2026.xlsx", "Consolidated SEBI Portfolio as on 30-Sep-2026")
FN15 = (SEP, "https://www.kotakmf.com/Forms/Fortnightly-Portfolio-15-Sep-2026.xlsx", "Fortnightly Portfolio 15-Sep-2026")
FN30 = (SEP, "https://www.kotakmf.com/Forms/Fortnightly-Portfolio-30-Sep-2026.xlsx", "Fortnightly Portfolio 30-Sep-2026")
OTHER = (SEP, "https://www.kotakmf.com/Forms/Monthly-Portfolio-Kotak-Flexicap.xlsx", "Monthly portfolio")


class PreferConsolidatedTests(unittest.TestCase):
    def test_consolidated_pack_wins_over_fortnightly(self):
        self.assertEqual(k.prefer_monthly_consolidated([FN15, CONS, FN30, OTHER]), [CONS])

    def test_without_consolidated_keeps_non_fortnightly_and_month_end(self):
        self.assertEqual(k.prefer_monthly_consolidated([FN15, FN30, OTHER]), [FN30, OTHER])

    def test_each_month_is_decided_on_its_own(self):
        aug_fn = ("2026-08", "https://x/Fortnightly-31-Aug-2026.xlsx", "Fortnightly 31-Aug-2026")
        self.assertEqual(k.prefer_monthly_consolidated([CONS, FN15, aug_fn]), [CONS, aug_fn])

    def test_hint_matches_url_spellings(self):
        for u in ("ConsolidatedSEBIPortfolio.xlsx", "Consolidated_SEBI_Portfolio.xlsx", "consolidated-sebi-portfolio.xlsx"):
            self.assertTrue(k.is_consolidated_sebi_row(u, ""), u)
        self.assertFalse(k.is_consolidated_sebi_row("Fortnightly.xlsx", "Fortnightly Portfolio"))


if __name__ == "__main__":
    unittest.main()
