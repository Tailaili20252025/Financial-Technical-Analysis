"""Write portable results with explicit causal timing and run metadata."""

from __future__ import annotations

from dataclasses import asdict
import csv
import hashlib
import json
from pathlib import Path

from .data import Bar
from .detector import SwingPoint
from .trendlines import TrendSettings, detect_trendlines, select_trendlines

TREND_FIELDS = ["line_id", "direction", "basis", "anchor1_bar", "anchor1_time", "anchor1_price",
                "anchor2_bar", "anchor2_time", "anchor2_price", "created_bar", "created_at",
                "slope_per_minute", "tolerance_price", "touch_count", "touch_bars",
                "touch_confirmed_bars", "status", "broken_bar", "broken_at", "end_bar", "end_time", "displayed"]

FIELDS = ["kind", "price", "pivot_bar", "pivot_time", "confirmed_bar", "confirmed_at", "delay_bars", "basis"]


def export_results(output: str | Path, source: str | Path, bars: list[Bar],
                   points: list[SwingPoint], window: int, basis: str, figure, lines=None, settings=None) -> Path:
    """
    Save the supplied analysis as a chart, swing tables and a run summary.

    Writes prices.png, swing_points.csv/json, trendlines.csv/json and run_summary.json.
    Existing result files are replaced. The summary describes the observed prefix,
    but the hash covers the complete source file. Export is not atomic: a later
    I/O failure can leave earlier result files written.

    Args:
        output (str or Path): Destination directory; created if necessary.
        source (str or Path): Existing input file, read to calculate its SHA-256 hash.
        bars (list[Bar]): Nonempty chronological list of observed, validated bars.
        points (list[SwingPoint]): Confirmed swings belonging to those observed bars.
        window (int): Detector window used for this analysis.
        basis (str): Detector price basis used for this analysis.
        figure (matplotlib.figure.Figure): The chart to save as a PNG.
        lines (list[TrendLine] or None): Candidate history; None computes it from bars.
        settings (TrendSettings or None): Settings used to detect and select lines.

    Result:
        Path: The output directory, in the same relative/absolute form as supplied.

    Exception:
        ValueError: If an output path would overwrite the input file, or automatic
            trend detection receives inconsistent events or timestamps.
        OSError: If directories/files cannot be created, written or read.
        IndexError: If bars is empty; callers must supply at least one bar.
    """
    output, source = Path(output), Path(source)
    names = ("prices.png", "swing_points.csv", "swing_points.json", "run_summary.json", "trendlines.csv", "trendlines.json")
    if any((output / name).resolve() == source.resolve() for name in names):
        raise ValueError("Output paths would overwrite the input file; choose another output directory.")
    settings = settings or TrendSettings()
    if lines is None:
        lines = detect_trendlines(bars, points, settings)
    selected_ids = {line.line_id for line in select_trendlines(lines, settings)}
    trend_records = [line.as_record(bars, line.line_id in selected_ids) for line in lines]
    output.mkdir(parents=True, exist_ok=True)
    records = [point.as_record() for point in points]
    with (output / "swing_points.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(records)
    (output / "swing_points.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    with (output / "trendlines.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TREND_FIELDS)
        writer.writeheader()
        for record in trend_records:
            writer.writerow({**record, "touch_bars": json.dumps(record["touch_bars"]),
                             "touch_confirmed_bars": json.dumps(record["touch_confirmed_bars"])})
    (output / "trendlines.json").write_text(json.dumps(trend_records, indent=2), encoding="utf-8")
    nonminute = sum((b.timestamp-a.timestamp).total_seconds() != 60 for a, b in zip(bars, bars[1:]))
    summary = {
        "source_name": source.name,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "observed_bars": len(bars), "first_timestamp": bars[0].timestamp.isoformat(),
        "last_timestamp": bars[-1].timestamp.isoformat(), "window": window, "basis": basis,
        "trend_settings": asdict(settings),
        "trendline_candidates": len(lines), "trendlines_displayed": len(selected_ids),
        "trendlines_up": sum(line.kind == "up" for line in lines),
        "trendlines_down": sum(line.kind == "down" for line in lines),
        "trendline_timing_rule": "Created at second anchor confirmation; dashed segment is retrospective. Stop at first crossing beyond tolerance.",
        "trendline_time_axis": "Elapsed minutes, including gaps; no extrapolation beyond observed history.",
        "swing_highs": sum(p.kind == "high" for p in points),
        "swing_lows": sum(p.kind == "low" for p in points),
        "intervals_not_one_minute": nonminute,
        "timing_rule": "At completed bar t, test pivot t-window using only bars <= t.",
        "gap_policy": "No filling; window counts observations, including across gaps/sessions.",
    }
    (output / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    figure.savefig(output / "prices.png", dpi=160)
    return output
