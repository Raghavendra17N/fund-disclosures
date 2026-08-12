#!/usr/bin/env python3
"""The Wealth Company — fortnightly and monthly portfolio downloads.

Pages:
  https://www.wealthcompanyamc.in/literature-forms/portfolio-documents/fortnightly/
  https://www.wealthcompanyamc.in/literature-forms/portfolio-documents/monthly/

Labels and /uploads/*Portfolio* paths are embedded in the HTML (MUI/Next).
Pair first N labels with upload paths in document order.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

BASE = "https://www.wealthcompanyamc.in"
FN_URL = f"{BASE}/literature-forms/portfolio-documents/fortnightly/"
MO_URL = f"{BASE}/literature-forms/portfolio-documents/monthly/"
HEADERS = {"User-Agent": "Mozilla/5.0"}
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
FN_LABEL_RE = re.compile(
    r"Fortnightly - The Wealth Company [^\"<>]+? - "
    r"((January|February|March|April|May|June|July|August|September|October|November|December)"
    r" \d{1,2}, 20\d{2})",
    re.I,
)
MO_LABEL_RE = re.compile(
    r"Monthly - The Wealth Company [^\"<>]+? - "
    r"((January|February|March|April|May|June|July|August|September|October|November|December)"
    r" \d{1,2}, 20\d{2})",
    re.I,
)
FN_UPLOAD_RE = re.compile(r"/uploads/Fortnightly_Portfolio[\w.-]+\.(?:xlsx?|xlsb)", re.I)
MO_UPLOAD_RE = re.compile(r"/uploads/Monthly_[Pp]ortfolio[\w.-]+\.(?:xlsx?|xlsb)", re.I)


def ssl_ctx(insecure: bool) -> ssl.SSLContext:
    if insecure:
        return ssl._create_unverified_context()
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def parse_ym(label_date: str) -> tuple[int, int] | None:
    m = re.match(r"([A-Za-z]+)\s+\d{1,2},\s*(20\d{2})", label_date.strip())
    if not m:
        return None
    mon = MONTHS.get(m.group(1).lower())
    return (int(m.group(2)), mon) if mon else None


def collect_pairs(text: str, *, label_re: re.Pattern[str], upload_re: re.Pattern[str]) -> list[dict]:
    labels = [m.group(1) for m in label_re.finditer(text)]
    uploads = []
    seen: set[str] = set()
    for u in upload_re.findall(text):
        if u not in seen:
            seen.add(u)
            uploads.append(u)
    pairs = []
    for i, lab in enumerate(labels):
        if i >= len(uploads):
            break
        ym = parse_ym(lab)
        if not ym:
            continue
        pairs.append({"year": ym[0], "month": ym[1], "label": lab, "path": uploads[i]})
    return pairs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", nargs="+", required=True)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--fortnightly", action="store_true")
    ap.add_argument("--insecure-ssl", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    page = FN_URL if args.fortnightly else MO_URL
    label_re = FN_LABEL_RE if args.fortnightly else MO_LABEL_RE
    upload_re = FN_UPLOAD_RE if args.fortnightly else MO_UPLOAD_RE

    ctx = ssl_ctx(args.insecure_ssl)
    req = urllib.request.Request(page, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
        html = resp.read().decode("utf-8", "ignore")
    text = html.replace('\\"', '"').replace("\\/", "/")
    pairs = collect_pairs(text, label_re=label_re, upload_re=upload_re)

    targets = set()
    for mk in args.months:
        y, m = mk.split("-")
        targets.add((int(y), int(m)))

    amc = args.root / "amcs" / "the-wealth-company-mutual-fund"
    for y, m in sorted(targets):
        mk = f"{y}-{m:02d}"
        out = amc / mk
        out.mkdir(parents=True, exist_ok=True)
        for p in out.iterdir():
            if p.is_file():
                p.unlink()
        selected = [r for r in pairs if (r["year"], r["month"]) == (y, m)]
        uniq = []
        seenp: set[str] = set()
        for r in selected:
            if r["path"] in seenp:
                continue
            seenp.add(r["path"])
            uniq.append(r)
        kind = "fortnightly" if args.fortnightly else "monthly"
        print(f"{mk} ({kind}): {len(uniq)} file(s)")
        manifest = []
        for r in uniq:
            url = urljoin(BASE + "/", r["path"])
            fn = re.sub(r"[^\w.\-]+", "_", r["path"].rsplit("/", 1)[-1])[:180]
            rec = {"month": mk, "title": r["label"], "download_url": url, "saved_as": fn}
            if args.dry_run:
                manifest.append(rec)
                print(f"  DRY {fn}")
                continue
            with urllib.request.urlopen(
                urllib.request.Request(url, headers={**HEADERS, "Referer": page}),
                timeout=120,
                context=ctx,
            ) as resp:
                body = resp.read()
            (out / fn).write_bytes(body)
            manifest.append({**rec, "sha256": hashlib.sha256(body).hexdigest()})
            print(f"  OK {fn} ({len(body)} bytes)")
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
