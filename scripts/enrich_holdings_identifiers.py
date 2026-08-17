#!/usr/bin/env python3
"""Attach scheme identifiers to parsed portfolios and write a B2 upload manifest.

Looks up AMFI parent codes from registry/disclosure_shortcode_map.json.
Keeps the newest as_of per (amc_id, identity) across the given parsed roots.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "registry" / "disclosure_shortcode_map.json"
AMC_PATH = ROOT / "registry" / "amcs.json"
OUT_MANIFEST = ROOT / "data" / "parsed" / "b2_holdings_manifest.json"

JUNK_FOLDER = re.compile(
    r"(?i)^(common notes|index|contents|cover|notes|disclaimer|risk.?o.?meter)$"
)


def normalize_shortcode(label: str | None) -> str | None:
    s = re.sub(r"[^A-Za-z0-9]", "", (label or "").strip())
    return s.upper() if s else None


def load_amc_names() -> dict[str, dict]:
    data = json.loads(AMC_PATH.read_text(encoding="utf-8"))
    out = {}
    for row in data.get("amcs") or []:
        out[row["id"]] = {
            "amc_name": row.get("name") or row.get("amc_name"),
            "amfi_mf_id": row.get("amfi_mf_id"),
        }
    return out


def load_shortcode_map() -> dict[str, dict]:
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for row in data.get("entries") or []:
        amc_id = (row.get("amc_id") or "").strip()
        raw = (row.get("shortcode") or "").strip()
        amfi = str(row.get("canonical_amfi_code") or "").strip()
        if not amc_id or not raw or not amfi:
            continue
        compact = normalize_shortcode(raw)
        keys = {raw, raw.casefold()}
        if compact:
            keys.add(compact)
        for alias in row.get("aliases") or []:
            a = (alias or "").strip()
            if not a:
                continue
            keys.add(a)
            keys.add(a.casefold())
            ac = normalize_shortcode(a)
            if ac:
                keys.add(ac)
        payload = {
            "amfi_code": amfi,
            "amfi_name": row.get("amfi_base_name") or row.get("disclosure_label"),
            "map_shortcode": raw,
            "confidence": row.get("confidence"),
        }
        for k in keys:
            out.setdefault(f"{amc_id}::{k}", payload)
    return out


DATE_TAIL = re.compile(
    r"(?i)[_\s\-]+(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\s*\d{1,2},?\s*\d{4}\s*$"
)


def peel_labels(*labels: str | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in labels:
        if not raw:
            continue
        candidates = [raw.strip()]
        peeled = DATE_TAIL.sub("", raw).strip(" _-,")
        if peeled:
            candidates.append(peeled)
        for c in candidates:
            if c and c not in seen:
                seen.add(c)
                out.append(c)
    return out


def resolve_amfi(amap: dict, amc_id: str, *labels: str | None) -> dict | None:
    for label in peel_labels(*labels):
        for key in (label, label.casefold(), normalize_shortcode(label)):
            if not key:
                continue
            hit = amap.get(f"{amc_id}::{key}")
            if hit:
                return hit
    return None


def safe_slug(s: str) -> str:
    out = re.sub(r"[^\w.\-() ]+", "_", (s or "").strip())
    out = re.sub(r"\s+", " ", out).strip(" ._")
    return out[:180] or "unknown"


def iter_schemes(parsed_root: Path):
    if not parsed_root.is_dir():
        return
    for amc_dir in sorted(p for p in parsed_root.iterdir() if p.is_dir()):
        idx = amc_dir / "schemes.json"
        if not idx.exists():
            continue
        items = json.loads(idx.read_text(encoding="utf-8"))
        for s in items:
            folder = s.get("folder") or safe_slug(s.get("shortcode") or s.get("scheme") or "")
            pj = amc_dir / folder / "portfolio.json"
            if not pj.exists():
                continue
            yield amc_dir.name, s, pj


def main() -> int:
    roots = [
        ROOT / "data" / "parsed" / "monthly" / "2026-07",
        ROOT / "data" / "parsed" / "monthly" / "latest",
        ROOT / "data" / "parsed" / "fortnightly" / "2026-07",
        ROOT / "data" / "parsed" / "fortnightly" / "latest",
    ]
    amap = load_shortcode_map()
    amcs = load_amc_names()
    best: dict[tuple[str, str], dict] = {}

    for parsed_root in roots:
        if not parsed_root.exists():
            continue
        parts = parsed_root.parts
        dtype = "monthly" if "monthly" in parts else "fortnightly"
        period = parsed_root.name
        for amc_id, s, pj in iter_schemes(parsed_root):
            folder = s.get("folder") or ""
            if JUNK_FOLDER.match(folder) or JUNK_FOLDER.match(s.get("shortcode") or ""):
                continue
            payload = json.loads(pj.read_text(encoding="utf-8"))
            meta = payload.get("meta") or {}
            as_of = meta.get("as_of") or s.get("as_of")
            shortcode = meta.get("shortcode") or s.get("shortcode")
            scheme_name = meta.get("scheme_name") or s.get("scheme")
            identity = (
                normalize_shortcode(shortcode)
                or (scheme_name or "").casefold().strip()
                or folder.casefold()
            )
            key = (amc_id, identity)
            prev = best.get(key)
            if prev:
                prev_as = prev.get("as_of") or ""
                new_as = as_of or ""
                if new_as < prev_as:
                    continue
                if new_as == prev_as and prev.get("disclosure_type") == "monthly" and dtype != "monthly":
                    continue
                if new_as == prev_as and prev.get("period") != "latest" and period == "latest":
                    continue
            amfi = resolve_amfi(amap, amc_id, shortcode, scheme_name, folder, s.get("scheme"))
            amc_info = amcs.get(amc_id) or {}
            scheme_id = (amfi or {}).get("amfi_code") or shortcode or folder
            ident = {
                "scheme_id": str(scheme_id),
                "amc_id": amc_id,
                "amc_name": amc_info.get("amc_name"),
                "amfi_mf_id": amc_info.get("amfi_mf_id"),
                "amfi_code": (amfi or {}).get("amfi_code"),
                "amfi_name": (amfi or {}).get("amfi_name"),
                "shortcode": shortcode,
                "scheme_name": scheme_name,
                "as_of": as_of,
                "disclosure_type": meta.get("disclosure_type") or dtype,
                "period": meta.get("period") or period,
                "source_file": meta.get("source_file") or s.get("source_file"),
                "sheet_name": meta.get("sheet_name") or s.get("sheet_name"),
                "folder": folder,
                "holding_count": len(payload.get("holdings") or []),
                "map_confidence": (amfi or {}).get("confidence"),
            }
            meta.update({k: v for k, v in ident.items() if v is not None})
            payload["meta"] = meta
            best[key] = {
                **ident,
                "local_path": str(pj.relative_to(ROOT)),
                "b2_key": (
                    f"fund-disclosures/holdings/latest/{amc_id}/{safe_slug(str(scheme_id))}/portfolio.json"
                ),
                "payload": payload,
            }

    rows = []
    mapped = 0
    for rec in best.values():
        payload = rec.pop("payload")
        local = ROOT / rec["local_path"]
        local.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if rec.get("amfi_code"):
            mapped += 1
        rows.append(rec)

    rows.sort(key=lambda r: (r["amc_id"], r.get("scheme_name") or ""))
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scheme_count": len(rows),
        "with_amfi_code": mapped,
        "without_amfi_code": len(rows) - mapped,
        "b2_prefix": "fund-disclosures/holdings/latest/",
        "schemes": rows,
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "schemes": len(rows),
                "with_amfi_code": mapped,
                "without_amfi_code": len(rows) - mapped,
                "manifest": str(OUT_MANIFEST.relative_to(ROOT)),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
