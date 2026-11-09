import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { classifyDisclosureFile } from "./portfolioFilter.js";

const here = dirname(fileURLToPath(import.meta.url));
const registry = JSON.parse(readFileSync(join(here, "..", "..", "..", "registry", "amcs.json"), "utf8"));
const amcs = Array.isArray(registry) ? registry : registry.amcs;
const oldBridge = amcs.find((a) => a.id === "old-bridge-mutual-fund");

const SEP = { type: "monthly", period: { year: 2026, month: 9 }, storageKey: "2026-09-30" };
const file = (name) => ({ url: `https://www.oldbridgemf.com/uploads/${name}`, filename: name });

test("Old Bridge monthly trusts the adapter's month (registry)", () => {
  assert.equal(oldBridge.fetch.monthly.trust_adapter_period, true);
  assert.equal(oldBridge.fetch.fortnightly.adapter, "unsupported");
});

test("Old Bridge September files with a Sept_26 name are rejected without the flag and kept with it", () => {
  const names = ["OBMF_Flexi_Cap_Portfolio_Sept_26_0cfdd46aac.xlsx", "OBMF_Arbitrage_Portfolio_Sept_26_05ec97d1b0.xlsx", "OBMF_Focused_Portfolio_Sept_26_ffe4009490.xlsx"];
  for (const n of names) {
    assert.equal(classifyDisclosureFile(file(n), SEP).keep, false, `${n} without the flag (the reported rejection)`);
    assert.deepEqual(classifyDisclosureFile(file(n), { ...SEP, trustAdapterPeriod: true }), { keep: true, reason: "adapter_period" }, n);
  }
});

test("trusting the adapter does not let non-portfolio packs through", () => {
  const overlap = classifyDisclosureFile(file("Monthly_Overlap_September_2026_d5efacca71.xlsx"), { ...SEP, trustAdapterPeriod: true });
  assert.equal(overlap.keep, false);
  assert.equal(overlap.reason, "excluded_non_portfolio");
  const half = classifyDisclosureFile(file("OBMF_Half_Yearly_Financials_Sept_26_d321798b04.xlsx"), { ...SEP, trustAdapterPeriod: true });
  assert.equal(half.keep, false);
  assert.equal(classifyDisclosureFile(file("Notice_Upload_of_Monthly_Portfolio_Sept_26_20e5cc2e37.pdf"), { ...SEP, trustAdapterPeriod: true }).keep, false);
});
