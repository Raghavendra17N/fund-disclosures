import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { classifyDisclosureFile } from "./portfolioFilter.js";

const here = dirname(fileURLToPath(import.meta.url));
const registry = JSON.parse(readFileSync(join(here, "..", "..", "..", "registry", "amcs.json"), "utf8"));
const amcs = Array.isArray(registry) ? registry : registry.amcs;
const abakkus = amcs.find((a) => a.id === "abakkus-mutual-fund");

const SEP = { type: "monthly", period: { year: 2026, month: 9 }, storageKey: "2026-09-30" };
const name = "IN_MF_MONTHLY_PORTFOLIO_September_30_2026.xlsx";

test("Abakkus monthly trusts the adapter's month (registry)", () => {
  assert.equal(abakkus.fetch.monthly.trust_adapter_period, true);
});

test("an Abakkus portfolio name with the month spelled out passes the filter with the flag", () => {
  const f = { url: `https://www.abakkusmf.com/uploads/${name}`, filename: name };
  assert.equal(classifyDisclosureFile(f, { ...SEP, trustAdapterPeriod: true }).keep, true);
});
