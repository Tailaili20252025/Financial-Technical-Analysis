"""Run selected swing strategies through one pipeline, with optional parameter grids."""
import argparse
import csv
import itertools
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from matplotlib.figure import Figure
from swingpoints.methods import METHODS, create_method
from swingpoints.pipeline import run_analysis
from swingpoints.trendlines import TrendSettings
from swingpoints.indicators import IndicatorSettings
from swingpoints.breakouts import BreakoutSettings, breakout_summary
from swingpoints.trading_cli import add_trade_arguments, trade_settings_from_args


@dataclass
class ExperimentSettings:
    """Editable class attributes; grids use each strategy's settings field names."""
    swing_grids: dict = field(default_factory=lambda: {
        "ta": {"window": [1, 2, 5]},
        "percentage": {"reversal_percent": [2.0, 5.0, 8.0]},
        "atr": {"atr_multiplier": [1.0, 2.0, 3.0]},
        "prominence": {"min_prominence_percent": [1.0, 3.0, 5.0]},
    })
    trend_grid: dict = field(default_factory=dict)  # Shared TrendSettings attribute -> value list.
    max_runs: int = 100  # Reject oversized grids before creating any output.


def settings_product(settings_type, grid, max_runs=100):
    """Validate field names and bound product size before materializing settings."""
    defaults = asdict(settings_type())
    if not isinstance(grid, dict) or set(grid)-set(defaults):
        raise ValueError(f"Grid keys must be attributes of {settings_type.__name__}")
    count = 1
    for values in grid.values():
        if not isinstance(values, list) or not values:
            raise ValueError("Grid values must be nonempty lists")
        count *= len(values)
    if count > max_runs:
        raise ValueError(f"Grid exceeds {max_runs} runs")
    return [settings_type(**dict(zip(grid, values))) for values in itertools.product(*grid.values())]


def main(argv=None):
    """Write independent result directories, summary tables and a comparison plot."""
    parser = argparse.ArgumentParser(description=__doc__)
    add_trade_arguments(parser)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("method_results"))
    parser.add_argument("--methods", nargs="+", choices=list(METHODS), default=list(METHODS))
    parser.add_argument("--until", type=int)
    parser.add_argument("--sweep", action="store_true", help="use ExperimentSettings default parameter grids")
    parser.add_argument("--grid", type=Path, help="JSON containing swing_grids and/or trend_grid")
    parser.add_argument("--break-confirmation-bars", type=int, default=2)
    parser.add_argument("--break-observation-bars", type=int, default=5)
    args = parser.parse_args(argv)
    experiment = ExperimentSettings()
    try:
        breakout_settings = BreakoutSettings(args.break_confirmation_bars, args.break_observation_bars)
        trade_settings = trade_settings_from_args(args)
        if args.grid:
            supplied = json.loads(args.grid.read_text())
            if not isinstance(supplied, dict) or set(supplied)-{"swing_grids", "trend_grid"}:
                raise ValueError("Grid JSON needs swing_grids and/or trend_grid")
            experiment.swing_grids = supplied.get("swing_grids", {})
            experiment.trend_grid = supplied.get("trend_grid", {})
        elif args.sweep:
            experiment.swing_grids = {k: v for k, v in experiment.swing_grids.items() if k in args.methods}
        else:
            experiment.swing_grids = {}
        if not isinstance(experiment.swing_grids, dict) or set(experiment.swing_grids)-set(METHODS):
            raise ValueError("swing_grids keys must be strategy names")
        if set(experiment.swing_grids)-set(args.methods):
            raise ValueError("Grid contains a method excluded by --methods")
        trends = settings_product(TrendSettings, experiment.trend_grid, experiment.max_runs)
        jobs = []
        for name in dict.fromkeys(args.methods):
            settings = settings_product(METHODS[name].settings_type, experiment.swing_grids.get(name, {}), experiment.max_runs)
            jobs.extend((name, swing, trend) for swing in settings for trend in trends)
        if len(jobs) > experiment.max_runs:
            raise ValueError(f"Reduce grid to at most {experiment.max_runs} total runs")
        # Validate all jobs and source path before the first run writes results.
        for name, swing, trend in jobs:
            METHODS[name](swing)
        if not args.input.is_file():
            raise ValueError(f"Missing input: {args.input}")
        for name in ("comparison.csv", "comparison.json", "comparison.png"):
            if (args.output/name).resolve() == args.input.resolve():
                raise ValueError("Comparison output would overwrite the input; choose another directory")
        rows = []
        for number, (name, swing, trend) in enumerate(jobs, 1):
            run_name = f"{number:03d}_{name}"
            result = run_analysis(args.input, args.output/run_name, METHODS[name](swing),
                                  trend, IndicatorSettings(), args.until, breakout_settings=breakout_settings, trade_settings=trade_settings)
            row = {"run": run_name, "method": name, "settings": json.dumps(asdict(swing)),
                   "trend_settings": json.dumps(asdict(trend)), "bars": len(result.bars),
                   "swing_highs": sum(p.kind == "high" for p in result.points),
                   "swing_lows": sum(p.kind == "low" for p in result.points),
                   "mean_delay": sum(p.confirmed_index-p.pivot_index for p in result.points)/len(result.points) if result.points else None,
                   "trend_candidates": len(result.lines), "displayed": len(result.selected)}
            stats = breakout_summary(result.events, breakout_settings, result.method.basis)
            row.update({"breakout_settings": json.dumps(asdict(breakout_settings)),
                        **{"step4_" + k: stats[k] for k in ("status", "candidate_events", "confirmed", "false_breakouts",
                          "false_breakdowns", "pending", "fully_observed_candidates", "failure_rate_full_windows")}})
            trade_stats = result.trading.summary()
            row.update({"trade_settings": json.dumps(asdict(trade_settings)),
                        **{"step56_"+key: trade_stats[key] for key in ("status", "trades", "closed_trades", "open_trades",
                           "realized_net_pnl", "unrealized_net_pnl", "final_equity", "win_rate_percent", "max_drawdown_percent")}})
            rows.append(row)
            print(f"{run_name}: {len(result.points)} swings, {len(result.lines)} trendlines", flush=True)
        with (args.output/"comparison.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
        (args.output/"comparison.json").write_text(json.dumps(rows, indent=2))
        fig = Figure(figsize=(12, 8))
        axes = fig.subplots(2, 1)
        x = list(range(len(rows)))
        labels = [r["run"] for r in rows]
        axes[0].bar(x, [r["swing_highs"]+r["swing_lows"] for r in rows], color="#475569")
        axes[0].set_ylabel("Confirmed swings")
        axes[1].bar(x, [r["mean_delay"] or 0 for r in rows], color="#607d70")
        axes[1].set_ylabel("Mean confirmation delay (bars)")
        for ax in axes:
            ax.set_xticks(x, labels, rotation=30, ha="right")
            ax.grid(axis="y", alpha=.2)
        fig.suptitle(args.input.name + " | Swing method comparison\nSettings in comparison.csv; no swings = undefined delay")
        fig.tight_layout(rect=(0, 0, 1, .93))
        fig.savefig(args.output/"comparison.png", dpi=150)
        fig.clear()
    except (ValueError, TypeError, OSError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
