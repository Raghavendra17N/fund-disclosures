import test from "node:test";
import assert from "node:assert/strict";
import { extractAllYearMonths, blobMatchesYearMonth } from "./disclosureDates.js";
import { classifyDisclosureFile } from "./portfolioFilter.js";

const SEP = { type: "monthly", period: { year: 2026, month: 9 }, storageKey: "2026-09-30" };
const classify = (name, opts = SEP) => classifyDisclosureFile({ url: `https://vatseelabs-s3.kotakmf.com/${name}`, filename: name }, opts);

test("CamelCase month + year with no separators is read (Kotak consolidated)", () => {
  assert.deepEqual(extractAllYearMonths("ConsolidatedSEBIPortfolioSeptember2026.xlsx"), [{ year: 2026, month: 9 }]);
  assert.equal(blobMatchesYearMonth("ConsolidatedSEBIPortfolioSeptember2026.xlsx", 2026, 9), true);
  assert.equal(blobMatchesYearMonth("ConsolidatedSEBIPortfolioSeptember2026.xlsx", 2026, 8), false);
  assert.deepEqual(extractAllYearMonths("MonthlyPortfolioSep2026.xlsx"), [{ year: 2026, month: 9 }]);
  assert.deepEqual(extractAllYearMonths("FundPortfolioAugust2026.xlsx"), [{ year: 2026, month: 8 }]);
});

test("the Kotak September file is now kept for the 2026-09-30 slice, the 15 September fortnightly stays rejected", () => {
  assert.deepEqual(classify("ConsolidatedSEBIPortfolioSeptember2026.xlsx"), { keep: true, reason: "month_in_name" });
  assert.equal(classify("FortnightlyPortfolioSeptember302026.xlsx").keep, true);
  const mid = classify("FortnightlyPortfolioSeptember152026.xlsx");
  assert.equal(mid.keep, false);
  assert.equal(mid.reason, "wrong_as_of_slice");
});

test("a CamelCase file for another month is still rejected as the wrong month", () => {
  const r = classify("ConsolidatedSEBIPortfolioAugust2026.xlsx");
  assert.equal(r.keep, false);
  assert.equal(r.reason, "wrong_month");
});

test("lowercase and ordinary words never produce a month", () => {
  assert.deepEqual(extractAllYearMonths("mayor2026.xlsx"), []);
  assert.deepEqual(extractAllYearMonths("Decimal2026.xlsx"), []);
  assert.deepEqual(extractAllYearMonths("Portfolio2026.xlsx"), []);
  assert.deepEqual(extractAllYearMonths("PortfolioMayor2026.xlsx"), []);
  assert.deepEqual(extractAllYearMonths("ProDec20261.xlsx"), []);          // five digits: not a year
});

test("existing separator styles are unchanged", () => {
  assert.deepEqual(extractAllYearMonths("Monthly Portfolio September 2026.xlsx"), [{ year: 2026, month: 9 }]);
  assert.deepEqual(extractAllYearMonths("sml250_aug2026.xlsx"), [{ year: 2026, month: 8 }]);
  assert.deepEqual(extractAllYearMonths("as-on-August-31,-2026"), [{ year: 2026, month: 8 }]);
});
