#!/usr/bin/env node
/**
 * Collect portfolios for a calendar as-of date from data/parsed/{cadence}/{YYYY-MM}.
 *
 * Used by sync-holdings-to-github.mjs for historical trees:
 *   portfolios/asof/YYYY-MM-DD/{portfolio_id}.json
 */
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const AS_OF_RE = /^\d{4}-\d{2}-\d{2}$/;
const PERIOD_RE = /^\d{4}-\d{2}$/;

export function normalizeAsOf(raw) {
  const s = String(raw || "").trim();
  if (AS_OF_RE.test(s)) return s;
  if (PERIOD_RE.test(s)) {
    // YYYY-MM → month-end (convenience)
    const [y, m] = s.split("-").map(Number);
    const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
    return `${s}-${String(last).padStart(2, "0")}`;
  }
  return "";
}

export function sourcePeriodFromAsOf(asOf) {
  return String(asOf || "").slice(0, 7);
}

function walkPortfolioFiles(dir, out = []) {
  if (!existsSync(dir)) return out;
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    let st;
    try {
      st = statSync(p);
    } catch {
      continue;
    }
    if (st.isDirectory()) walkPortfolioFiles(p, out);
    else if (name === "portfolio.json") out.push(p);
  }
  return out;
}

/**
 * @returns {Map<string, { portfolio_id: string, local_path: string, meta: object, members: string[] }>}
 */
export function collectAsOfPortfolios({
  root,
  cadence,
  sourcePeriod,
  asOf,
  catalogLookup = null,
}) {
  const period = sourcePeriod || sourcePeriodFromAsOf(asOf);
  const base = join(root, "data", "parsed", cadence, period);
  const byId = new Map();
  if (!existsSync(base)) return byId;

  for (const abs of walkPortfolioFiles(base)) {
    let payload;
    try {
      payload = JSON.parse(readFileSync(abs, "utf8"));
    } catch {
      continue;
    }
    const meta = payload?.meta || {};
    const fileAsOf = String(meta.as_of || meta.as_of || "").slice(0, 10);
    if (fileAsOf !== asOf) continue;
    const id = String(meta.amfi_code || meta.scheme_id || "").trim();
    if (!/^\d{4,8}$/.test(id)) continue;

    const rel = abs.startsWith(root) ? abs.slice(root.length + 1) : abs;
    let entry = byId.get(id);
    if (!entry) {
      entry = {
        portfolio_id: id,
        local_path: rel,
        meta,
        members: [],
        payload,
      };
      byId.set(id, entry);
    } else {
      // Prefer richer books
      const prevN = (entry.payload?.holdings || []).length;
      const nextN = (payload.holdings || []).length;
      if (nextN >= prevN) {
        entry.local_path = rel;
        entry.meta = meta;
        entry.payload = payload;
      }
    }
  }

  // Attach sibling share-classes from catalog when available
  if (catalogLookup) {
    for (const row of Object.values(catalogLookup)) {
      const pid = String(row.portfolio_id || row.parent_amfi || row.amfi_code || "");
      const entry = byId.get(pid);
      if (!entry) continue;
      const amfi = String(row.amfi_code || "");
      if (amfi && !entry.members.includes(amfi)) entry.members.push(amfi);
    }
  }

  for (const entry of byId.values()) {
    if (!entry.members.length) entry.members.push(entry.portfolio_id);
    entry.members.sort();
  }
  return byId;
}

export function mergeFilings(existing, next) {
  const byKey = new Map();
  for (const f of [...(existing?.filings || []), next]) {
    if (!f?.as_of) continue;
    byKey.set(`${f.as_of}::${f.cadence || ""}`, f);
  }
  const filings = [...byKey.values()].sort((a, b) =>
    String(b.as_of).localeCompare(String(a.as_of)),
  );
  return {
    generated_at: new Date().toISOString(),
    filings,
  };
}

export function attachAvailableAsOf(catalog, asOfDatesByPortfolio) {
  const out = { ...catalog };
  for (const [code, row] of Object.entries(out)) {
    const pid = row?.portfolio_id ? String(row.portfolio_id) : "";
    const dates = pid ? asOfDatesByPortfolio.get(pid) : null;
    if (dates?.size) {
      out[code] = {
        ...row,
        available_as_of: [...dates].sort().reverse(),
      };
    }
  }
  return out;
}

export function scanExistingAsOfDirs(outDir) {
  /** @type {Map<string, Set<string>>} portfolio_id → as_of dates */
  const map = new Map();
  const asofRoot = join(outDir, "portfolios", "asof");
  if (!existsSync(asofRoot)) return map;
  for (const date of readdirSync(asofRoot)) {
    if (!AS_OF_RE.test(date)) continue;
    const dir = join(asofRoot, date);
    let st;
    try {
      st = statSync(dir);
    } catch {
      continue;
    }
    if (!st.isDirectory()) continue;
    for (const name of readdirSync(dir)) {
      if (!name.endsWith(".json")) continue;
      const id = name.replace(/\.json$/, "");
      if (!map.has(id)) map.set(id, new Set());
      map.get(id).add(date);
    }
  }
  return map;
}
