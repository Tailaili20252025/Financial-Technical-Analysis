"""Rebuild the 60-stock parameter-search sample from the pinned public archive.

python prepare_parameter_data.py --source-zip /path/sandp500.zip
The normalized data is already included; this is a reproducibility command.
"""
import argparse
import io
import json
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

from prepare_backtest_data import SOURCE_URL, SYMBOLS as ORIGINAL_SYMBOLS, prepare
from swingpoints.data import load_prices
from swingpoints.parameter_selection import validate_plan

ROOT = Path(__file__).resolve().parent


def prepare_data(raw, output, plan):
    """Preserve source values, enforce equal calendars and record cohort roles."""
    validate_plan(plan)
    symbols = plan["development_symbols"] + plan["heldout_symbols"]
    manifest = prepare(raw, output, symbols)
    calendar = None
    for symbol in symbols:
        bars = load_prices(Path(output) / f"{symbol}.csv")
        dates = [b.timestamp for b in bars]
        if calendar is not None and dates != calendar:
            raise ValueError(f"Different session calendar for {symbol}; no filling is allowed")
        calendar = dates
    manifest.update(
        selection=f"{len(symbols)} predeclared archival stocks; {len(plan['development_symbols'])} development and {len(plan['heldout_symbols'])} held out from parameter selection",
        development_symbols=plan["development_symbols"], heldout_symbols=plan["heldout_symbols"],
        selection_basis="Coverage and sector variety only, fixed before parameter-search P/L; not a point-in-time investable universe",
        expansion=f"{len(set(symbols)-set(ORIGINAL_SYMBOLS))} additional ticker histories beyond the previous 20; broader stock coverage, not newer dates",
        quality_checks="Exact pinned raw hash, required OHLCV columns, positive OHLC, unique sorted dates, identical observed calendars; no imputation",
        quality_exclusions=["ORCL and BMY have 1,257 rather than 1,259 rows", "DHR has a shorter history and missing OHLC values"],
        previously_examined_periods="These historical dates were used in earlier project research; this is an exploratory chronological evaluation, not a pristine future-market test")
    (Path(output) / "source_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    return manifest


def main():
    """Read a local CSV/ZIP or download the exact publisher snapshot."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--source-csv", type=Path)
    group.add_argument("--source-zip", type=Path)
    parser.add_argument("--plan", type=Path, default=ROOT / "parameter_search_plan.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    output = args.output or args.plan.resolve().parent / plan["data_dir"]
    if args.source_csv:
        raw = args.source_csv.read_bytes()
    else:
        if args.source_zip:
            archive = args.source_zip.read_bytes()
        else:
            with urlopen(SOURCE_URL, timeout=60) as response:
                archive = response.read()
        with ZipFile(io.BytesIO(archive)) as zipped:
            raw = zipped.read("all_stocks_5yr.csv")
    manifest = prepare_data(raw, output, plan)
    print(f"Prepared {manifest['selected_rows']:,} bars in {len(manifest['files'])} files: {output}")


if __name__ == "__main__":
    main()
