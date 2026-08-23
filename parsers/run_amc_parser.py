#!/usr/bin/env python3
"""Run AMC-wise portfolio parsers.

Examples:
  .venv/bin/python3 scripts/run_amc_parser.py --all-fixtures
  .venv/bin/python3 scripts/run_amc_parser.py --amc=nj-mutual-fund --fixtures
  .venv/bin/python3 scripts/run_amc_parser.py --amc=sbi-mutual-fund --type=monthly --period=latest --limit=2
  .venv/bin/python3 scripts/run_amc_parser.py --list
"""
from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))  # compat shim
sys.path.insert(0, str(ROOT / "parsers"))  # canonical parsers win

from amc_parsers.common import (  # noqa: E402
    write_amc_schemes_index,
    write_scheme_portfolio,
)
from amc_parsers.registry import get_parser, list_amcs  # noqa: E402

_FIXTURES_REG = ROOT / "registry" / "parser_fixtures.json"
_FIXTURES_OLD = ROOT / "data" / "sources" / "parser_fixtures.json"
FIXTURES = _FIXTURES_REG if _FIXTURES_REG.exists() else _FIXTURES_OLD


def load_fixtures() -> dict:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


def iter_amc_files(amc_id: str, disclosure_type: str, period: str) -> list[Path]:
    d = ROOT / "data" / "disclosures" / disclosure_type / period / amc_id
    if not d.is_dir():
        return []
    files = []
    for p in sorted(d.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".xlsx", ".xls", ".xlsm", ".xlsb", ".zip"}:
            continue
        files.append(p)
    return files


def _call_parser(parser, path: Path, *, workbook_limit: int | None):
    kwargs = {}
    if workbook_limit is not None:
        try:
            sig = inspect.signature(parser)
            if "workbook_limit" in sig.parameters:
                kwargs["workbook_limit"] = workbook_limit
        except (TypeError, ValueError):
            # functools.partial — dig into keywords / wrapped
            if getattr(parser, "keywords", None) is not None:
                kwargs["workbook_limit"] = workbook_limit
    try:
        return parser(path, **kwargs)
    except TypeError:
        return parser(path)


def _flush_schemes_index(
    amc_id: str,
    portfolios: list,
    *,
    out_base: Path | None = None,
) -> None:
    """Persist schemes.json for whatever portfolios we have so far.

    Portfolios are written per file; historically the index was only written at
    the end of parse_paths. A kill/timeout mid-AMC (common for Mirae’s ~100
    single-scheme workbooks) left portfolio.json folders with no schemes.json,
    and enrich skipped the whole AMC. Flush after each file + in finally.
    """
    if not portfolios:
        return
    by_key: dict[tuple[str, str], list] = {}
    for p in portfolios:
        by_key.setdefault((p.disclosure_type, p.period), []).append(p)
    for (dtype, period), items in by_key.items():
        dest_root = out_base or (ROOT / "data" / "parsed" / dtype / period / amc_id)
        write_amc_schemes_index(dest_root, items)


def parse_paths(
    amc_id: str,
    paths: list[Path],
    *,
    out_base: Path | None = None,
    workbook_limit: int | None = None,
) -> dict:
    parser = get_parser(amc_id)
    all_portfolios = []
    errors = []
    try:
        for path in paths:
            try:
                portfolios = _call_parser(parser, path, workbook_limit=workbook_limit)
            except Exception as e:
                errors.append({"file": path.name, "error": str(e)})
                continue
            all_portfolios.extend(portfolios)
            for p in portfolios:
                dest_root = out_base or (
                    ROOT / "data" / "parsed" / p.disclosure_type / p.period / p.amc_id
                )
                try:
                    write_scheme_portfolio(dest_root, p)
                except Exception as e:
                    errors.append(
                        {
                            "file": path.name,
                            "scheme": getattr(p, "shortcode", None) or getattr(p, "scheme_name", None),
                            "error": f"write_scheme_portfolio: {e}",
                        }
                    )
            # Keep schemes.json in sync after every file so a mid-run interrupt
            # cannot orphan portfolio folders without an enrichable index.
            _flush_schemes_index(amc_id, all_portfolios, out_base=out_base)
    finally:
        _flush_schemes_index(amc_id, all_portfolios, out_base=out_base)

    return {
        "amc_id": amc_id,
        "files": len(paths),
        "schemes": len(all_portfolios),
        "holdings": sum(len(p.holdings) for p in all_portfolios),
        "errors": errors,
        "schemes_detail": [
            {
                "scheme": p.scheme_name,
                "shortcode": p.shortcode,
                "as_of": p.as_of,
                "holdings": len(p.holdings),
                "source_file": p.source_file,
                "type": p.disclosure_type,
                "period": p.period,
            }
            for p in all_portfolios
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--amc", help="AMC id (e.g. nj-mutual-fund)")
    ap.add_argument("--all", action="store_true", help="Parse every registered AMC for --type/--period")
    ap.add_argument("--type", choices=["monthly", "fortnightly"], help="Disclosure cadence")
    ap.add_argument("--period", default="latest", help="YYYY-MM or latest")
    ap.add_argument("--limit", type=int, default=0, help="Max files to parse (0=all)")
    ap.add_argument("--file", action="append", default=[], help="Explicit file path(s)")
    ap.add_argument("--fixtures", action="store_true", help="Parse fixture files for --amc")
    ap.add_argument("--all-fixtures", action="store_true", help="Parse fixtures for all AMCs")
    ap.add_argument("--list", action="store_true", help="List registered AMC parsers")
    ap.add_argument(
        "--summary-only",
        action="store_true",
        help="Print compact per-AMC summary (used with --all-fixtures)",
    )
    args = ap.parse_args()

    if args.list:
        amcs = list_amcs()
        print(json.dumps({"count": len(amcs), "amcs": amcs}, indent=2))
        return 0

    reports = []
    if args.all_fixtures or args.fixtures:
        fixtures = load_fixtures()
        amc_ids = list(fixtures.keys()) if args.all_fixtures else [args.amc]
        if not args.all_fixtures and not args.amc:
            raise SystemExit("--fixtures requires --amc")
        for amc_id in amc_ids:
            if amc_id not in fixtures:
                raise SystemExit(f"No fixtures for {amc_id}")
            paths = []
            for cadence, entries in fixtures[amc_id].items():
                if cadence == "notes" or not isinstance(entries, list):
                    continue
                for rel in entries:
                    p = ROOT / rel
                    if not p.exists():
                        print(f"missing fixture: {p}", file=sys.stderr)
                        continue
                    paths.append(p)
            # Fixture mode: limit zip/mega expansion to 2 workbooks / schemes
            reports.append(parse_paths(amc_id, paths, workbook_limit=2))
    else:
        if args.all:
            if not args.type:
                raise SystemExit("--type required with --all")
            for amc_id in list_amcs():
                paths = iter_amc_files(amc_id, args.type, args.period)
                if args.limit:
                    paths = paths[: args.limit]
                if not paths:
                    reports.append(
                        {
                            "amc_id": amc_id,
                            "files": 0,
                            "schemes": 0,
                            "holdings": 0,
                            "errors": [],
                            "schemes_detail": [],
                        }
                    )
                    continue
                reports.append(parse_paths(amc_id, paths))
        elif not args.amc:
            raise SystemExit("Need --amc or --all (or --all-fixtures / --list)")
        else:
            if args.file:
                paths = [Path(f) for f in args.file]
            else:
                if not args.type:
                    raise SystemExit("--type required unless --fixtures/--file")
                paths = iter_amc_files(args.amc, args.type, args.period)
                if args.limit:
                    paths = paths[: args.limit]
            reports.append(parse_paths(args.amc, paths))

    if args.summary_only:
        summary = []
        for r in reports:
            summary.append(
                {
                    "amc_id": r["amc_id"],
                    "files": r["files"],
                    "schemes": r["schemes"],
                    "holdings": r["holdings"],
                    "errors": len(r["errors"]),
                    "error_samples": r["errors"][:2],
                }
            )
        ok = sum(1 for s in summary if s["schemes"] > 0 and s["errors"] == 0)
        weak = sum(1 for s in summary if s["schemes"] == 0 or s["errors"])
        print(
            json.dumps(
                {
                    "amcs": len(summary),
                    "ok": ok,
                    "weak_or_empty": weak,
                    "total_schemes": sum(s["schemes"] for s in summary),
                    "total_holdings": sum(s["holdings"] for s in summary),
                    "rows": summary,
                },
                indent=2,
            )
        )
    else:
        print(json.dumps(reports if len(reports) > 1 else reports[0], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
