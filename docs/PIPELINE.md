# Fund disclosures month-end pipeline

Canonical layout:

```text
registry/     AMC registry, parser families, shortcode map, fixtures
scrapers/     Node fetch CLI + Python AMC fetchers
parsers/      Excel → holdings
amfi/         NAVAll / as-of / populate-scheme parents
matching/     disclosure↔AMFI match, incremental new parents, Excel export
qc/           allocation / holdings compare
exports/      mapping snapshots (+ exports/baseline freeze)
data/         disclosures, parsed, amfi dumps (mostly gitignored)
```

## Month-end loop

From repo root (`fund-disclosures/`):

```bash
# 1) Fetch AMC packs for a period
npm run fetch -- --type=monthly --period=2026-07
npm run fetch -- --type=fortnightly --period=2026-07

# 2) Parse holdings (family parsers)
npm run parse:amc -- --type=monthly --period=latest
# or fixtures smoke:
npm run parse:amc:fixtures

# 3) Refresh AMFI universe
npm run amfi:catalog          # NAVAll → data/amfi/
npm run amfi:asof -- --asof=31-Jul-2026
npm run amfi:parents          # populate-scheme active parents

# 4) Match disclosures ↔ AMFI (reuse shortcodes)
npm run amfi:match:reuse
npm run amfi:new-parents      # diff new parents vs map; proposals JSON
npm run amfi:coverage

# 5) Export mapping workbook
npm run export:mapping
```

## Mapping grain

- **Parent** = AMFI scheme / populate-scheme id (e.g. `1450`)
- **Plan** = NAVAll Scheme Code (Direct/Regular × Growth/IDCW)
- **Disclosure** = AMC pack fund/sheet (often keyed by shortcode)

Maps:

- `data/sources/disclosure_to_amfi_global_mapping.json`
- `data/sources/amfi_navall_to_disclosure_global_mapping.json`
- `registry/disclosure_shortcode_map.json` (canonical; `data/sources/` is a symlink)

Baseline freeze: `exports/baseline/`.

## Secrets

- `EDELWEISS_API_SECRET` — required for Edelweiss statutory API fetch
- Holdings API object storage: `B2_KEY_ID`, `B2_APPLICATION_KEY` (see `holdings-browser/.env.example`)

## Compat

Old entrypoints under `src/` and `scripts/` are thin shims to the new layout.
