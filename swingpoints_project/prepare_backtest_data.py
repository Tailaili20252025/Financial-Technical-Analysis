"""Prepare the frozen Kaggle/IEX sample in the application's OHLCV schema.

Usage: python prepare_backtest_data.py --source-csv /path/all_stocks_5yr.csv
Omit --source-csv to download the public archive. Only selected symbols are saved.
"""
import argparse
import csv
import hashlib
import io
import json
from datetime import date
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

from swingpoints.data import load_prices

ROOT = Path(__file__).resolve().parent
SOURCE_URL = "https://www.kaggle.com/api/v1/datasets/download/camnugent/sandp500"
SOURCE_PAGE = "https://www.kaggle.com/datasets/camnugent/sandp500"
SOURCE_SHA256 = "6aea253cd19de60b568143991aaf1fa482456565c389205658d236e595e716cf"
SYMBOLS = "AAPL MSFT AMZN GOOGL JPM BAC XOM CVX JNJ PFE PG KO WMT HD GE BA CAT MMM DIS VZ".split()
FIELDS = ["timestamp", "open", "high", "low", "close", "volume"]


def prepare(raw, output, symbols=SYMBOLS):
    """Verify the source snapshot and split symbols without changing prices.

    Args:
        raw: Bytes of the publisher's all_stocks_5yr.csv file.
        output: Directory for normalized files and source_manifest.json.
        symbols: Unique source ticker labels to extract.
    Returns:
        Manifest containing source and normalized-file hashes and row counts.
    Raises:
        ValueError: Snapshot hash, schema, date order or OHLCV validation fails.
    """
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SOURCE_SHA256:
        raise ValueError("Source snapshot changed: expected SHA256 " + SOURCE_SHA256 + "; got " + digest)
    if not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("Select at least one symbol with no duplicates")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if reader.fieldnames != ["date", "open", "high", "low", "close", "volume", "Name"]:
        raise ValueError("Unexpected source columns")
    rows = {s: [] for s in symbols}
    source_count, universe = 0, set()
    for row in reader:
        source_count += 1
        universe.add(row["Name"])
        if row["Name"] in rows:
            # date.fromisoformat rejects malformed/non-ISO dates.
            rows[row["Name"]].append(dict(timestamp=date.fromisoformat(row["date"]).isoformat(),
                                         **{k: row[k] for k in FIELDS[1:]}))
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for symbol, values in rows.items():
        if not values:
            raise ValueError("No observations for " + symbol)
        dates = [r["timestamp"] for r in values]
        if dates != sorted(dates) or len(set(dates)) != len(dates):
            raise ValueError("Unsorted/duplicate dates for " + symbol)
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(values)
        path = output / (symbol + ".csv")
        path.write_text(stream.getvalue(), encoding="utf-8")
        bars = load_prices(path)
        if any(b.open is None or b.volume is None or b.low <= 0 for b in bars):
            raise ValueError("Positive OHLC and nonmissing volume required for " + symbol)
        records.append(dict(symbol=symbol, file=path.name, rows=len(bars),
                            first_date=dates[0], last_date=dates[-1],
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    manifest = dict(source_page=SOURCE_PAGE, download_url=SOURCE_URL,
                    source_file="all_stocks_5yr.csv", source_sha256=digest,
                    source_rows=source_count, source_symbols=len(universe),
                    publisher="Cam Nugent on Kaggle", publisher_license="CC0 Public Domain",
                    upstream="IEX, as identified by the archive's getSandP.py download script",
                    selection="20 predeclared large-cap stocks across sectors; not a point-in-time S&P 500 universe",
                    preparation="date renamed timestamp; Name split into files; prices and volume preserved; no imputation",
                    limitations=["Historical static snapshot, not a current market feed",
                                 "Constituent selection can introduce survivorship bias",
                                 "Corporate-action/adjustment methodology is not independently certified",
                                 "No dividends, splits ledger, delisting returns or short-availability history"],
                    files=records, selected_rows=sum(r["rows"] for r in records))
    (output / "source_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    return manifest


def main():
    """Download or read the pinned archive and prepare application-ready CSVs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-csv", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "backtest")
    args = parser.parse_args()
    if args.source_csv:
        raw = args.source_csv.read_bytes()
    else:
        with urlopen(SOURCE_URL, timeout=120) as response:
            archive = response.read()
        with ZipFile(io.BytesIO(archive)) as z:
            raw = z.read("all_stocks_5yr.csv")
    manifest = prepare(raw, args.output)
    print(f"Prepared {manifest['selected_rows']:,} bars across {len(manifest['files'])} stocks in {args.output}")


if __name__ == "__main__":
    main()
