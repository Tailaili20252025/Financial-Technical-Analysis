"""Run TA versus percentage and ATR swing methods through shared Steps 3-6.

Requires the accompanying backtesting additions. No third-party broker framework
is used. Algorithm attributes and common trading conditions live in the plan.
"""
import argparse
import csv
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from swingpoints.data import load_prices
from swingpoints.swing_comparison import (SwingComparisonSettings, audit_swing_prefixes,
    measure_detection, pair_pnl, plot_detection, plot_swings, point_signature,
    require_methods, summarize_methods)

ROOT = Path(__file__).resolve().parent


def run(plan_path, output, settings=None):
    """Rerun a complete comparison, recording observed timing and exact outputs."""
    try:
        from backtest import run as run_backtest, write_csv
        from swingpoints.backtesting import prepare_block, validate_plan
    except ModuleNotFoundError as exc:
        raise ValueError("Apply the backtesting package first; backtest.py and swingpoints/trading.py are required") from exc
    settings = settings or SwingComparisonSettings()
    plan_path, output = Path(plan_path).resolve(), Path(output).resolve()
    plan = json.loads(plan_path.read_text())
    periods, methods, trend, breakout, scenarios = validate_plan(plan)
    require_methods(methods)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty output directory")
    output.mkdir(parents=True, exist_ok=True)
    metadata = dict(status="running", started_utc=datetime.now(timezone.utc).isoformat(),
                    scope="Two Step 1-2 alternatives versus traditional TA; shared Steps 3-6 and trade engine",
                    python=sys.version, platform=platform.platform(), plan=plan,
                    measurements=dict(timing_repetitions=settings.timing_repetitions,
                                      preview_bars=settings.preview_bars),
                    code_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in [Path(__file__), ROOT/"swingpoints/swing_comparison.py"]})
    meta_path = output/"comparison_experiment.json"
    meta_path.write_text(json.dumps(metadata, indent=2)+"\n")
    try:
        portfolios = run_backtest(plan_path, output/"backtest")
        data_dir = (plan_path.parent/plan["data_dir"]).resolve()
        data = {s: load_prices(data_dir/(s+".csv")) for s in plan["symbols"]}
        detection, prefix_checks, examples, points_out = [], [], [], []
        for period in periods:
            for symbol, bars in data.items():
                for method in methods:
                    block = prepare_block(bars, period, method, trend, breakout, plan["minimum_warmup_bars"])
                    metrics, points = measure_detection(block.bars, method, block.start_index, settings)
                    if point_signature(points) != point_signature(block.analysis.points):
                        raise AssertionError("Measured detector and application pipeline disagree")
                    metrics.update(symbol=symbol, period=period.name,
                        method_attributes=json.dumps(method.metadata()["settings"], sort_keys=True),
                        trendlines_created_in_test=sum(l.second.confirmed_index >= block.start_index for l in block.analysis.lines),
                        confirmed_break_events=len(block.events))
                    detection.append(metrics)
                    cuts = [block.start_index+1, block.start_index+(len(block.bars)-block.start_index)//2, len(block.bars)]
                    prefix_checks.extend(dict(symbol=symbol, period=period.name, **check)
                                         for check in audit_swing_prefixes(block.bars, method, cuts))
                    for p in points:
                        if p.confirmed_index >= block.start_index:
                            points_out.append(dict(symbol=symbol, period=period.name, method=method.key,
                                kind=p.kind, pivot_bar=p.pivot_index+1, confirmed_bar=p.confirmed_index+1,
                                pivot_time=p.pivot_time.isoformat(), confirmed_at=p.confirmed_at.isoformat(),
                                price=p.price, delay_bars=p.confirmed_index-p.pivot_index,
                                threshold_price=getattr(p, "threshold_price", None),
                                atr_at_pivot=getattr(p, "atr_at_pivot", None)))
                    if period == periods[-1] and symbol == plan["symbols"][0]:
                        examples.append(block)
            print("Swing diagnostics completed:", period.name, flush=True)
        with (output/"backtest/summary.csv").open(newline="") as f:
            rows = list(csv.DictReader(f))
        pairs = pair_pnl(rows)
        totals = summarize_methods(rows, detection, portfolios)
        write_csv(output/"detection_metrics.csv", [dict(r, detector_runs_ms=json.dumps(r["detector_runs_ms"])) for r in detection])
        write_csv(output/"paired_pnl_vs_ta.csv", pairs)
        write_csv(output/"method_totals.csv", totals)
        fields = ["symbol", "period", "method", "kind", "pivot_bar", "confirmed_bar", "pivot_time", "confirmed_at", "price", "delay_bars", "threshold_price", "atr_at_pivot"]
        with (output/"confirmed_swings.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fields, lineterminator="\n")
            writer.writeheader(); writer.writerows(points_out)
        (output/"swing_prefix_checks.json").write_text(json.dumps(prefix_checks, indent=2)+"\n")
        plot_swings(output/"swing_and_trendline_comparison.png", examples, settings.preview_bars)
        plot_detection(output/"detection_comparison.png", totals)
        validation = json.loads((output/"backtest/validation.json").read_text())
        metadata.update(status="completed", completed_utc=datetime.now(timezone.utc).isoformat(),
            input_rows=sum(len(v) for v in data.values()), stocks=len(data),
            backtest_runs=len(rows), paired_comparisons=len(pairs),
            swing_prefix_checks=len(prefix_checks), arithmetic_audits=validation["audited_runs"],
            maximum_equity_error=validation["maximum_equity_error"],
            shared_rules=dict(trend=plan["trend_settings"], breakout=plan["breakout_settings"], trades=plan["trade_settings"]),
            figure_symbol=plan["symbols"][0], figure_period=periods[-1].name,
            output_sha256={str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted(output.rglob("*")) if p.is_file() and p != meta_path})
        meta_path.write_text(json.dumps(metadata, indent=2)+"\n")
    except Exception as exc:
        metadata.update(status="failed", error=str(exc))
        meta_path.write_text(json.dumps(metadata, indent=2)+"\n")
        raise
    return totals


def main():
    """Run the comparison from the project directory using the normal Python environment."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT/"swing_comparison_plan.json")
    parser.add_argument("--output", type=Path, default=ROOT/"swing_method_results/latest")
    parser.add_argument("--timing-repetitions", type=int, default=3)
    parser.add_argument("--preview-bars", type=int, default=160)
    args = parser.parse_args()
    try:
        run(args.plan, args.output, SwingComparisonSettings(args.timing_repetitions, args.preview_bars))
    except (ValueError, TypeError, OSError) as exc:
        parser.error(str(exc))
    print("Results:", args.output.resolve())


if __name__ == "__main__":
    main()
