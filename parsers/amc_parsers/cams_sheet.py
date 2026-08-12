"""CAMS-style single-sheet packs used by SBI / Choice (and several other AMCs).

Layout markers:
  SCHEME NAME : <name>
  PORTFOLIO STATEMENT AS ON : <date>
  Optional leading security code column before instrument name.
"""
from __future__ import annotations

from pathlib import Path

from .common import (
    SchemePortfolio,
    disclosure_type_from_path,
    extract_as_of_from_rows,
    extract_scheme_name_cams,
    load_sheets,
    parse_holdings_table,
    period_from_path,
)


def parse_cams_file(path: Path, *, amc_id: str) -> list[SchemePortfolio]:
    sheets = load_sheets(path)
    out: list[SchemePortfolio] = []
    dtype = disclosure_type_from_path(path)
    period = period_from_path(path)
    for sheet_name, rows in sheets:
        if not rows:
            continue
        low = sheet_name.strip().lower()
        if low in {"index", "contents", "cover", "notes"}:
            continue
        scheme = extract_scheme_name_cams(rows) or sheet_name.strip() or path.stem
        holdings, _meta = parse_holdings_table(rows, prefer_leading_code=True)
        out.append(
            SchemePortfolio(
                amc_id=amc_id,
                disclosure_type=dtype,
                period=period,
                scheme_name=scheme,
                shortcode=sheet_name.strip() or None,
                as_of=extract_as_of_from_rows(rows),
                source_file=path.name,
                sheet_name=sheet_name,
                holdings=holdings,
            )
        )
    return out
