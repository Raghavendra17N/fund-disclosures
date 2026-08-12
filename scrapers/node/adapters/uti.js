import { httpFetch } from "../lib/http.js";
import { parsePeriod } from "../lib/period.js";

async function fetchUtiApi(endpoint, month, year, referer) {
  const url =
    `https://www.utimf.com/api/${endpoint}` +
    `?year=${year}&month=${encodeURIComponent(month)}`;
  const res = await httpFetch(url, {
    headers: { accept: "application/json, text/plain, */*", referer },
  });
  if (!res.ok) return [];
  let payload;
  try {
    payload = JSON.parse(await res.text());
  } catch {
    return [];
  }
  return payload?.rows || [];
}

/**
 * UTI — GET /api/get-consolidate-portfolio-disclosure?year=&month=
 * For fortnightly: tries debt-specific endpoint first, falls back to the
 * general consolidated portfolio (which includes all scheme data for that month).
 */
export const utiAdapter = {
  id: "uti_api",
  async listFiles(ctx) {
    if (ctx.type !== "monthly" && ctx.type !== "fortnightly") {
      return { files: [], notes: `unsupported type ${ctx.type}` };
    }
    const p = parsePeriod(ctx.period);
    const month = p.monthName.toLowerCase();

    let rows = [];
    if (ctx.type === "fortnightly") {
      rows = await fetchUtiApi(
        "get-consolidate-debt-portfolio-disclosure",
        month,
        p.year,
        "https://www.utimf.com/downloads/consolidate-debt-portfolio-disclosure",
      );
      if (!rows.length) {
        rows = await fetchUtiApi(
          "get-consolidate-portfolio-disclosure",
          month,
          p.year,
          "https://www.utimf.com/downloads/consolidate-all-portfolio-disclosure",
        );
      }
    } else {
      rows = await fetchUtiApi(
        "get-consolidate-portfolio-disclosure",
        month,
        p.year,
        "https://www.utimf.com/downloads/consolidate-all-portfolio-disclosure",
      );
    }

    const files = [];
    for (const row of rows) {
      const raw = row.url || row.doc;
      if (!raw) continue;
      files.push({
        url: raw,
        filename:
          decodeURIComponent(new URL(raw).pathname.split("/").pop() || "") ||
          String(row.name || "uti.zip"),
      });
    }
    return { files, notes: `month=${month}` };
  },
};
