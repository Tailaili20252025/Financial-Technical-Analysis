"""CSV/JSON loading and strict validation; no prices are silently imputed."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


class DataError(ValueError):
    """A readable error in the input file or its price records."""


@dataclass(frozen=True)
class Bar:
    """One completed bar. Timestamps retain the input's timezone convention."""

    timestamp: datetime
    high: float
    low: float
    close: float
    open: float | None = None


def _timestamp(value, row: int) -> datetime:
    """
    Parse a timestamp while preserving the timezone convention in the input.

    Accepts DD/MM/YY or DD/MM/YYYY with hours and minutes, optionally seconds.
    A trailing Z in an ISO timestamp is interpreted as UTC.

    Args:
        value (str): An ISO 8601 or supported day-first date/time string.
        row (int): One-based input record number for error messages.

    Result:
        datetime: The parsed timestamp; no timezone is assigned to a naive input.

    Exception:
        DataError: If the value is not a nonempty string or no format matches.
    """
    if not isinstance(value, str) or not value.strip():
        raise DataError(f"Record {row}: timestamp must be a nonempty date/time string.")
    value = value.strip()
    # ISO 8601 is preferred. Explicit day-first formats support the supplied CSV.
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%d/%m/%y %H:%M", "%d/%m/%Y %H:%M", "%d/%m/%y %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                pass
    raise DataError(f"Record {row}: invalid timestamp {value!r}; use ISO 8601 or DD/MM/YY HH:MM.")


def _number(value, name: str, row: int) -> float:
    """
    Convert a price field to a finite, strictly positive floating-point number.

    Args:
        value: A number or numeric string to validate; booleans are rejected.
        name (str): Field name, such as high, low or close.
        row (int): One-based input record number for error messages.

    Result:
        float: The validated price.

    Exception:
        DataError: If conversion fails, the value is boolean, nonfinite or not positive.
    """
    try:
        if isinstance(value, bool):
            raise ValueError
        number = float(value)
    except (ValueError, TypeError):
        raise DataError(f"Record {row}: {name} must be a number, got {value!r}.") from None
    if not math.isfinite(number) or number <= 0:
        raise DataError(f"Record {row}: {name} must be finite and positive.")
    return number


def load_prices(path: str | Path) -> list[Bar]:
    """
    Load and validate prices for one instrument from a CSV or JSON file.

    Required fields are timestamp, high, low and close. Open is optional but
    validated when present. Names are case-insensitive; CSV supports comma,
    semicolon and tab delimiters. JSON accepts a record array or a data array
    inside an object. Low must not exceed Open/Close, which must not exceed High.
    Duplicate records are rejected and missing prices are never filled.

    Args:
        path (str or Path): Path to the input .csv or .json file.

    Result:
        list[Bar]: A nonempty list of validated bars sorted by timestamp.

    Exception:
        DataError: If reading or decoding fails, the format is unsupported, or
            records contain missing fields, invalid prices/dates, duplicate timestamps
            or mixed timezone-aware and timezone-naive timestamps.
    """
    path = Path(path)
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            if path.suffix.lower() == ".csv":
                sample = stream.read(4096)
                stream.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                except csv.Error:
                    dialect = csv.excel
                reader = csv.DictReader(stream, dialect=dialect)
                headers = reader.fieldnames or []
                normalized = [h.strip().lower() for h in headers]
                if len(normalized) != len(set(normalized)):
                    raise DataError("CSV contains duplicate column names.")
                records = list(reader)
            elif path.suffix.lower() == ".json":
                records = json.load(stream)
                if isinstance(records, dict):
                    records = records.get("data")
            else:
                raise DataError("Unsupported file type: choose .csv or .json.")
    except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
        raise DataError(f"Cannot read {path.name}: {exc}") from exc

    if not isinstance(records, list) or not records:
        raise DataError("Expected at least one record (JSON: an array or a 'data' array).")
    bars = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict) or any(not isinstance(key, str) for key in record):
            raise DataError(f"Record {index}: expected named fields; check CSV column counts or JSON objects.")
        clean = {key.strip().lower(): value for key, value in record.items()}
        if len(clean) != len(record):
            raise DataError(f"Record {index}: duplicate field names after normalization.")
        missing = {"timestamp", "high", "low", "close"} - clean.keys()
        if missing:
            raise DataError(f"Record {index}: missing fields: {', '.join(sorted(missing))}.")
        timestamp = _timestamp(clean["timestamp"], index)
        high, low, close = (_number(clean[name], name, index) for name in ("high", "low", "close"))
        opening = _number(clean["open"], "open", index) if "open" in clean else None
        if not low <= close <= high or (opening is not None and not low <= opening <= high):
            raise DataError(f"Record {index}: require low <= open/close <= high.")
        bars.append(Bar(timestamp, high, low, close, opening))

    if len({bar.timestamp.utcoffset() is None for bar in bars}) > 1:
        raise DataError("Do not mix timestamps with and without timezone offsets.")
    bars.sort(key=lambda bar: bar.timestamp)
    if any(a.timestamp == b.timestamp for a, b in zip(bars, bars[1:])):
        raise DataError("Duplicate timestamps found; supply one bar per time for one instrument.")
    return bars
