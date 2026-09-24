"""Entry point. Examples: python app.py data/data.csv; python app.py --gui."""

import argparse
import sys
from pathlib import Path
from dataclasses import fields
from swingpoints.indicators import IndicatorSettings

from swingpoints import DataError, detect_swings, load_prices
from swingpoints.trendlines import TrendSettings, detect_trendlines, select_trendlines


def positive_integer(value: str) -> int:
    """
    Convert an input string to an integer greater than or equal to 1.

    Args:
        value (str): The command-line argument to convert.

    Result:
        int: The converted integer, which is at least 1.

    Exception:
        argparse.ArgumentTypeError: If conversion fails or the integer is below 1.
    """
    try:
        number = int(value)
        if number < 1:
            raise ValueError
        return number
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer of at least 1") from None


def main(argv=None) -> int:
    """
    Parse command-line options and run the price analysis or desktop interface.

    CLI mode loads prices, optionally limits the observed history, detects swings,
    plots the results and saves nine output files, including eight indicators. GUI mode starts the Tk event
    loop. Existing result files in the selected output directory are replaced.

    Args:
        argv (list[str] or None): Arguments without the script name. None uses
            the arguments supplied to the current Python process.

    Result:
        int: 0 on success, or 1 for handled loading, analysis, export or GUI errors.

    Exception:
        SystemExit: Raised by argparse for help (0) or invalid arguments (2).
        Handled runtime errors are printed to standard error and return 1.
    """
    parser = argparse.ArgumentParser(description="Steps 1-3: load CSV/JSON, plot prices, confirmed swings and trendlines.")
    parser.add_argument("input", nargs="?", type=Path, help="CSV or JSON price file")
    parser.add_argument("--window", type=positive_integer, default=2, help="bars on each side of a pivot (default: 2)")
    parser.add_argument("--basis", choices=["close", "high-low"], default="close", help="series used to detect swings")
    parser.add_argument("--until", type=positive_integer, help="only observe the first N sorted bars (replay cutoff)")
    parser.add_argument("--output", type=Path, default=Path("output"), help="output directory (default: output)")
    parser.add_argument("--show", action="store_true", help="also open a Matplotlib chart window")
    parser.add_argument("--gui", action="store_true", help="open desktop app with file picker, chart and table")
    parser.add_argument("--trend-tolerance", type=float, default=0.5,
                        help="touch/break tolerance as percent of first anchor price (default: 0.5)")
    parser.add_argument("--trend-lookback", type=positive_integer, default=20,
                        help="previous same-kind swings to try per second anchor (default: 20)")
    parser.add_argument("--min-touches", type=positive_integer, default=2,
                        help="minimum confirmed touches for displaying a line (at least 2)")
    parser.add_argument("--max-trendlines", type=positive_integer, default=3,
                        help="maximum displayed lines per direction (default: 3)")
    defaults = IndicatorSettings()
    for field in fields(defaults):
        if field.name == "vwap_reset":
            parser.add_argument("--vwap-reset", choices=["session", "cumulative"], default=defaults.vwap_reset,
                                help="VWAP anchor: input calendar date or entire input prefix")
        else:
            parser.add_argument("--" + field.name.replace("_", "-"), type=positive_integer,
                                default=getattr(defaults, field.name),
                                help=f"{field.name.replace('_', ' ')} (default: {getattr(defaults, field.name)})")
    args = parser.parse_args(argv)
    try:
        indicator_settings = IndicatorSettings(**{field.name: getattr(args, field.name) for field in fields(defaults)})
        settings = TrendSettings(args.trend_tolerance, args.trend_lookback,
                                 args.min_touches, args.max_trendlines)
    except ValueError as exc:
        parser.error(str(exc))
    if args.gui:
        if args.show or args.until is not None:
            parser.error("--gui has its own chart and observed-bars control; omit --show and --until.")
        try:
            from swingpoints.gui import launch
            launch(args.input, args.window, args.basis, args.output, settings, indicator_settings)
        except (ImportError, RuntimeError) as exc:
            print(f"Desktop interface unavailable: {exc}\nUse the command-line mode to save charts instead.", file=sys.stderr)
            return 1
        return 0
    if args.input is None:
        parser.error("provide a CSV/JSON input path or use --gui")
    try:
        bars = load_prices(args.input)
        if args.until is not None:
            if args.until > len(bars):
                raise ValueError(f"--until exceeds the {len(bars)} available bars.")
            bars = bars[:args.until]
        import matplotlib
        if not args.show:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from swingpoints.plotting import draw_prices
        from swingpoints.output import export_results

        points = detect_swings(bars, args.window, args.basis)
        lines = detect_trendlines(bars, points, settings)
        selected = select_trendlines(lines, settings)
        fig = plt.figure(figsize=(14, 8))
        draw_prices(fig, bars, points, args.window, args.basis, args.input.name, lines, settings)
        output = export_results(args.output, args.input, bars, points, args.window, args.basis, fig, lines, settings, indicator_settings)
        print(f"Loaded {len(bars)} bars: {bars[0].timestamp} to {bars[-1].timestamp}")
        print(f"Swing highs: {sum(p.kind == 'high' for p in points)} | Swing lows: {sum(p.kind == 'low' for p in points)}")
        print(f"Trendlines: {len(lines)} accepted candidates | displayed: "
              f"{sum(line.kind == 'up' for line in selected)} up / {sum(line.kind == 'down' for line in selected)} down")
        print(f"Saved price/indicator charts, CSV/JSON swing, trendline and indicator tables, and summary to {output.resolve()}")
        if any(b.volume is None for b in bars):
            print("VWAP: unavailable from missing volume within each anchor period; other indicators are calculated.")
        if len(bars) < 2*args.window + 1:
            print("Not enough bars for this window; no confirmed swings yet.")
        if any((b.timestamp-a.timestamp).total_seconds() != 60 for a,b in zip(bars,bars[1:])):
            print("Note: some intervals are not one minute. No gaps were filled; the window counts bars.")
        if args.show:
            from swingpoints.indicators import calculate_indicators
            from swingpoints.indicator_plotting import draw_indicators
            dashboard = plt.figure(figsize=(14, 13))
            draw_indicators(dashboard, bars, calculate_indicators(bars, indicator_settings), args.input.name)
            plt.show()
            plt.close(dashboard)
        plt.close(fig)
        return 0
    except (DataError, ValueError, OSError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
