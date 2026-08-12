# Fund Disclosures

Toolkit for Indian mutual fund **portfolio disclosures** (Excel packs) and **AMFI parent mapping**.

## Pillars

1. **AMC fetch** (monthly + fortnightly) — `scrapers/`
2. **Excel → holdings parsers** — `parsers/`
3. **Disclosure ↔ AMFI parent maps** — `data/sources/*mapping*.json` + `exports/`
4. **AMFI universe** (NAVAll + active parents) — `amfi/`
5. **Matching / new-parent proposals** — `matching/`

Also: **QC** (`qc/`), **registry** (`registry/`), **pipeline docs** (`docs/PIPELINE.md`).

## Quick start

```bash
cd fund-disclosures
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

npm run list -- --stats
npm run fetch -- --type=monthly --period=2026-07 --list-only
npm run parse:amc -- --list
npm run amfi:new-parents
npm run export:mapping
```

Node ≥ 20. See [docs/PIPELINE.md](docs/PIPELINE.md) for the full month-end loop.

## Layout

```text
registry/     amcs.json, parser families, shortcode map, fixtures
scrapers/     node/ (fetch CLI) + python/ (AMC fetchers)
parsers/      AMC Excel parsers
amfi/         NAVAll / as-of / populate-scheme
matching/     match, incremental new parents, Excel export
qc/           holdings compare + external verify
exports/      mapping workbooks (+ exports/baseline freeze)
data/         disclosures/, parsed/, amfi/ (gitignored blobs)
docs/         runbooks
scripts/      thin compat shims
src/          thin compat shims
```

## Policy

- **AMC-direct only** (no Advisorkhoj as primary source).
- In scope: fortnightly + monthly. Semi-annual deferred.
- Edelweiss fetch requires `EDELWEISS_API_SECRET`.

## Mapping status (baseline)

Frozen under `exports/baseline/` after Aug 2026 QC:

- Disclosure rows mapped ≈ **2386 / 2387** (Taurus IE pool ignored)
- Shortcode map: `registry/disclosure_shortcode_map.json`
