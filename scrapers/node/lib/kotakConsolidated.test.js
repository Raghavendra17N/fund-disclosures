import test from "node:test";
import assert from "node:assert/strict";
import { classifyDisclosureFile } from "./portfolioFilter.js";

const SEP = { type: "monthly", period: { year: 2026, month: 9 }, storageKey: "2026-09-30" };
const file = (name) => ({ url: `https://www.kotakmf.com/Forms/${name}`, filename: name });

test("Consolidated SEBI Portfolio is no longer dropped by the sebi exclusion", () => {
  for (const n of ["Consolidated-SEBI-Portfolio-30-Sep-2026.xlsx", "ConsolidatedSEBIPortfolio_30Sep2026.xlsx", "Consolidated_SEBI_Portfolio_30-Sep-2026.xlsx"]) {
    const r = classifyDisclosureFile(file(n), SEP);
    assert.notEqual(r.reason, "excluded_non_portfolio", n);
  }
});

test("other SEBI-named non-portfolio packs stay excluded", () => {
  const r = classifyDisclosureFile(file("SEBI-Circular-Annexure-30-Sep-2026.xlsx"), SEP);
  assert.equal(r.keep, false);
  assert.equal(r.reason, "excluded_non_portfolio");
});

test("a month-end fortnightly file still passes the monthly filter (the as-of slice, not its name, decides)", () => {
  assert.equal(classifyDisclosureFile(file("Fortnightly-Portfolio-30-Sep-2026.xlsx"), SEP).keep, true);
  assert.equal(classifyDisclosureFile(file("Fortnightly-Portfolio-15-Sep-2026.xlsx"), SEP).keep, false);
});
