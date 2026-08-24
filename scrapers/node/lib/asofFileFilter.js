/** Match disclosure filenames/URLs to a calendar as-of day (mid-month vs month-end). */

const AS_OF_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

export function parseStorageKeyDay(storageKey) {
  const m = AS_OF_RE.exec(String(storageKey || ""));
  if (!m) return null;
  return Number(m[3]);
}

/**
 * When fetching into portfolios/asof/YYYY-MM-DD/, keep only files for that slice.
 * @param {{ filename?: string, url?: string }} file
 * @param {string | undefined} storageKey YYYY-MM-DD
 * @param {'monthly'|'fortnightly'} cadence
 */
export function fileMatchesStorageKey(file, storageKey, cadence = "fortnightly") {
  if (!storageKey || !AS_OF_RE.test(storageKey)) return true;
  const day = parseStorageKeyDay(storageKey);
  if (day == null) return true;

  const blob = `${file.filename || ""} ${file.url || ""}`.toLowerCase();
  const isMid = day <= 15;

  // Explicit opposite slice — reject month-end when we want mid-month (and vice versa).
  const monthEndHints = [
    /\b31(?:st)?\s*(?:july|jul|aug|jan|feb|mar|apr|may|jun|sep|oct|nov|dec)/,
    /(?:july|jul|aug|jan|feb|mar|apr|may|jun|sep|oct|nov|dec)\s+31(?:st)?(?:\b|[,\s_])/,
    /-31[-_.]0?\d[-_.]20\d{2}/,
    /[-_.]31[-_.](?:0?\d|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/,
    /as on 31/,
    /monthly portfolio/,
  ];
  const midMonthHints = [
    /\b15(?:th)?\s*(?:july|jul|aug|jan|feb|mar|apr|may|jun|sep|oct|nov|dec)/,
    /(?:july|jul|aug|jan|feb|mar|apr|may|jun|sep|oct|nov|dec)\s+15(?:th)?(?:\b|[,\s_])/,
    /-15[-_.]0?\d[-_.]20\d{2}/,
    /[-_.]15[-_.](?:0?\d|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/,
    /1-15\s+(?:july|jul|aug|jan|feb|mar|apr|may|jun|sep|oct|nov|dec)/,
    /mid[-\s]?month/,
    /midmonth/,
  ];

  if (cadence === "fortnightly") {
    if (isMid) {
      if (monthEndHints.some((re) => re.test(blob))) return false;
      // Prefer explicit mid-month signal when present in batch; otherwise allow
      // generic fortnightly filenames without a 31.
      return true;
    }
    if (midMonthHints.some((re) => re.test(blob)) && !monthEndHints.some((re) => re.test(blob))) {
      return false;
    }
  }

  if (cadence === "monthly" && !isMid) {
    if (midMonthHints.some((re) => re.test(blob)) && !monthEndHints.some((re) => re.test(blob))) {
      return false;
    }
  }

  return true;
}

export function filterFilesForStorageKey(files, storageKey, cadence) {
  if (!storageKey || !AS_OF_RE.test(storageKey)) return files;
  return files.filter((f) => fileMatchesStorageKey(f, storageKey, cadence));
}
