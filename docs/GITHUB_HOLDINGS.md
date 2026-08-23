# GitHub holdings store (deduped portfolios, zero paid cloud)

Public AMFI holdings live on GitHub under a dedicated data account and are read
via **jsDelivr**. No card-on-file cloud.

## Accounts / repo

| Role | Value |
|------|--------|
| Data account | `kushagra-agarwal-a` |
| Data repo | [`fund-holdings-data`](https://github.com/kushagra-agarwal-a/fund-holdings-data) (public) |
| Pipeline repo | [`subscriptionmanager26-png/fund-disclosures`](https://github.com/subscriptionmanager26-png/fund-disclosures) |

## Dedup model (important)

AMFI lists ~8600 **schemes** (share classes). Most siblings share one portfolio book.

| Layer | Typical count | Stored as |
|------|---------------|-----------|
| Schemes | ~8607 | Catalog rows only |
| Unique portfolios | ~1942 | `portfolios/latest/{portfolio_id}.json` |
| Local seed available | ~local unique books | Uploaded when `local_path` exists |

**Never** upload one holdings file per AMFI code. Upload one file per `portfolio_id`,
then link every child scheme to it in the catalog.

`portfolio_id` is the id already used in B2 paths:

`fund-disclosures/holdings/latest/{amc}/{portfolio_id}/portfolio.json`

Sibling share-classes always share that id. A few distinct AMFI “parents” can also
collapse onto the same id (legacy plan codes).

## Object layout

```text
portfolios/latest/{portfolio_id}.json
catalog/amfi-lookup.json
portfolios/asof/{yyyy-mm}/{portfolio_id}.json   # optional
meta.json
```

### Portfolio object

```json
{
  "portfolio_id": "152310",
  "member_amfi_codes": ["152307", "152308", "152309", "152310"],
  "scheme": { "...canonical parent / representative scheme card..." },
  "meta": { "as_of": "...", "holding_count": 61, "portfolio_id": "152310", "member_count": 4 },
  "holdings": [ /* shaped rows */ ]
}
```

### Catalog row (excerpt)

```json
{
  "amfi_code": "152309",
  "parent_amfi": "152310",
  "name": "…",
  "has_holdings": true,
  "portfolio_id": "152310",
  "portfolio_key": "portfolios/latest/152310.json",
  "portfolio_url": "https://cdn.jsdelivr.net/gh/kushagra-agarwal-a/fund-holdings-data@main/portfolios/latest/152310.json"
}
```

## How to access (API / CDN)

### Two-hop CDN (no server required)

1. Fetch catalog (cache aggressively):

```text
https://cdn.jsdelivr.net/gh/kushagra-agarwal-a/fund-holdings-data@main/catalog/amfi-lookup.json
```

2. Look up AMFI code → `portfolio_id` / `portfolio_url`.

3. Fetch the shared portfolio:

```text
https://cdn.jsdelivr.net/gh/kushagra-agarwal-a/fund-holdings-data@main/portfolios/latest/{portfolio_id}.json
```

4. Overlay the requesting scheme’s name/NAV from the catalog row onto the payload
   if you need share-class-specific fields (the portfolio object carries the
   canonical scheme card only).

### Optional thin resolve API (later)

A free Vercel/holdings-browser route can wrap the two hops:

| Route | Behavior |
|--------|----------|
| `GET /v1/catalog` | catalog (or redirect to CDN) |
| `GET /v1/holdings/:amfi` | resolve catalog → portfolio → return shaped for that AMFI |
| `GET /v1/portfolios/:id` | raw shared portfolio |

Not required for v1; CDN URLs are enough.

### Direct portfolio fetch

If you already know `portfolio_id` (parent book id), skip the catalog and hit
`portfolios/latest/{id}.json` directly.

## Sync

```bash
export GH_TOKEN='github_pat_…'   # contents:read/write on fund-holdings-data

node scripts/sync-holdings-to-github.mjs --limit=20 --dry-run
node scripts/sync-holdings-to-github.mjs --limit=50 --push
node scripts/sync-holdings-to-github.mjs --push          # all local unique portfolios
node scripts/sync-holdings-to-github.mjs --asof=2026-07 --push
```

`--limit` caps **unique portfolios**, not schemes.

Env overrides: `HOLDINGS_DATA_OWNER`, `HOLDINGS_DATA_REPO`, `HOLDINGS_DATA_BRANCH`.

## Smoke test

```bash
curl -sS 'https://cdn.jsdelivr.net/gh/kushagra-agarwal-a/fund-holdings-data@main/meta.json'
# pick a child AMFI from catalog, read portfolio_id, then:
curl -sS 'https://cdn.jsdelivr.net/gh/kushagra-agarwal-a/fund-holdings-data@main/portfolios/latest/152310.json' | head -c 400
```

## Quotas

- GitHub soft ~1 GB / hard ~5 GB per repo — ~2k portfolios is fine.
- jsDelivr free CDN; pin `@<sha>` for immutable production reads.
- No R2 / Workers / paid object store.

## Security

Never commit PATs. If a token was pasted into chat, revoke it and mint a fresh
contents-only token for sync.
