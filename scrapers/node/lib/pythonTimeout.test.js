import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { DEFAULT_PYTHON_TIMEOUT_MS, resolvePythonTimeoutMs } from "./pythonTimeout.js";

test("the AMC's own timeout wins, then the environment, then the 120 s default", () => {
  assert.equal(resolvePythonTimeoutMs(600000, { PYTHON_REF_TIMEOUT_MS: "300000" }), 600000);
  assert.equal(resolvePythonTimeoutMs(undefined, { PYTHON_REF_TIMEOUT_MS: "300000" }), 300000);
  assert.equal(resolvePythonTimeoutMs(undefined, {}), DEFAULT_PYTHON_TIMEOUT_MS);
  assert.equal(DEFAULT_PYTHON_TIMEOUT_MS, 120000);
});

test("zero, negative and non-numeric values are ignored", () => {
  assert.equal(resolvePythonTimeoutMs(0, {}), 120000);
  assert.equal(resolvePythonTimeoutMs(-5, { PYTHON_REF_TIMEOUT_MS: "abc" }), 120000);
  assert.equal(resolvePythonTimeoutMs("x", { PYTHON_REF_TIMEOUT_MS: "-1" }), 120000);
});

test("Bandhan monthly and fortnightly get a 10 minute budget in the registry", () => {
  const here = dirname(fileURLToPath(import.meta.url));
  const registry = JSON.parse(readFileSync(join(here, "..", "..", "..", "registry", "amcs.json"), "utf8"));
  const amcs = Array.isArray(registry) ? registry : registry.amcs;
  const b = amcs.find((a) => a.id === "bandhan-mutual-fund");
  assert.equal(b.fetch.monthly.timeout_ms, 600000);
  assert.equal(b.fetch.fortnightly.timeout_ms, 600000);
});
