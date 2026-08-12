#!/usr/bin/env node
/**
 * Repeatable disclosure fetch for a calendar period.
 *
 * Usage:
 *   node src/fetch-period.js --type=monthly --period=2026-06
 *   node src/fetch-period.js --type=monthly --period=2026-06 --amc=sbi-mutual-fund
 *   node src/fetch-period.js --type=monthly --period=2026-06 --list-only
 *   node src/fetch-period.js --adapters
 */
import { existsSync, readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { parsePeriod } from "./lib/period.js";
import { downloadDisclosureFile } from "./lib/download.js";
import { getAdapter, listAdapterIds, adapters } from "./adapters/index.js";
import { createPythonRefAdapter } from "./adapters/pythonRef.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const registry = JSON.parse(
  readFileSync(existsSync(join(root, "registry/amcs.json")) ? join(root, "registry/amcs.json") : join(root, "data/sources/amcs.json"), "utf8"),
);

function arg(name, fallback = undefined) {
  const hit = process.argv.find((a) => a.startsWith(`--${name}=`));
  if (hit) return hit.slice(name.length + 3);
  if (process.argv.includes(`--${name}`)) return true;
  return fallback;
}

function resolveAdapter(amc, type) {
  const cfg = amc.fetch?.[type];
  const name = cfg?.adapter;
  if (!name || name === "unsupported") return null;
  if (name === "python_ref") {
    if (!cfg.script || !cfg.python_slug) {
      throw new Error(`python_ref requires script + python_slug for ${amc.id}`);
    }
    return createPythonRefAdapter({
      script: cfg.script,
      slug: cfg.python_slug,
      extraArgs: cfg.extra_args || [],
    });
  }
  if (!adapters[name]) throw new Error(`Unknown adapter: ${name}`);
  return getAdapter(name);
}

if (arg("adapters")) {
  console.log("Built-in adapters:");
  for (const id of listAdapterIds()) console.log(`  - ${id}`);
  console.log("  - python_ref (per-AMC script via registry)");
  process.exit(0);
}

const type = arg("type", "monthly");
const period = arg("period");
const amcFilter = arg("amc");
const dryRun = Boolean(arg("dry-run", false));
const listOnly = Boolean(arg("list-only", false));
const supportedOnly = arg("supported-only", true) !== "false";

if (!period) {
  console.error(
    "Required: --period=YYYY-MM\nExample: node src/fetch-period.js --type=monthly --period=2026-06 --list-only",
  );
  process.exit(1);
}
if (!["monthly", "fortnightly"].includes(type)) {
  console.error('--type must be "monthly" or "fortnightly"');
  process.exit(1);
}

const parsed = parsePeriod(period);
const amcs = (registry.amcs ?? []).filter((a) => {
  if (amcFilter && a.id !== amcFilter) return false;
  const adapterName = a.fetch?.[type]?.adapter;
  if (supportedOnly && (!adapterName || adapterName === "unsupported"))
    return false;
  return true;
});

if (!amcs.length) {
  console.error("No matching AMCs (need fetch.<type>.adapter in registry).");
  process.exit(1);
}

console.log(
  `Fetch ${type} ${parsed.period} · ${amcs.length} AMC(s)${dryRun ? " · dry-run" : ""}${listOnly ? " · list-only" : ""}\n`,
);

const run = {
  ran_at: new Date().toISOString(),
  type,
  period: parsed.period,
  dryRun,
  listOnly,
  results: [],
};

for (const amc of amcs) {
  const adapterName = amc.fetch?.[type]?.adapter;
  process.stderr.write(`→ ${amc.id} [${adapterName}]\n`);
  try {
    const adapter = resolveAdapter(amc, type);
    if (!adapter) {
      run.results.push({ id: amc.id, name: amc.name, status: "unsupported" });
      continue;
    }
    const listed = await adapter.listFiles({
      amc,
      type,
      period: parsed.period,
    });
    const files = listed.files ?? [];

    const downloads = [];
    if (!listOnly) {
      for (const f of files) {
        const d = await downloadDisclosureFile({
          root,
          type,
          period: parsed.period,
          amcId: amc.id,
          url: f.url,
          filename: f.filename,
          localPath: f.localPath,
          dryRun,
        });
        downloads.push({ ...f, ...d });
        await new Promise((r) => setTimeout(r, 100));
      }
    }

    run.results.push({
      id: amc.id,
      name: amc.name,
      adapter: adapterName,
      status: files.length ? "ok" : "empty",
      notes: listed.notes,
      fileCount: files.length,
      files: listOnly ? files : downloads,
    });
    console.log(
      `  ${amc.name}: ${files.length} file(s)${listed.notes ? ` (${listed.notes})` : ""}`,
    );
  } catch (e) {
    run.results.push({
      id: amc.id,
      name: amc.name,
      adapter: adapterName,
      status: "error",
      error: String(e.message || e),
    });
    console.log(`  ${amc.name}: ERROR ${e.message || e}`);
  }
}

const outDir = join(root, "data/probes");
mkdirSync(outDir, { recursive: true });
const outPath = join(outDir, `fetch-${type}-${parsed.period}.json`);
writeFileSync(outPath, JSON.stringify(run, null, 2) + "\n");

const ok = run.results.filter((r) => r.status === "ok").length;
const empty = run.results.filter((r) => r.status === "empty").length;
const err = run.results.filter((r) => r.status === "error").length;
console.log(
  `\nDone. ok=${ok} empty=${empty} error=${err}\nManifest: ${outPath}`,
);
