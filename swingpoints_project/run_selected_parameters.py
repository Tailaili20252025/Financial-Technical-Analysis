"""Apply a validation-selected preset to the normal Steps 1–6 application.

python run_selected_parameters.py data/data.csv --preset parameter_results/reference/selected_application.json --output output/selected
This is a retrospective application run, not an additional unseen backtest.
"""
import argparse
import json
from pathlib import Path

from swingpoints.breakouts import BreakoutSettings
from swingpoints.methods import create_method
from swingpoints.parameter_selection import check_config, config_id
from swingpoints.pipeline import run_analysis
from swingpoints.trading import TradeSettings
from swingpoints.trendlines import TrendSettings


def run(source, preset, output, until=None):
    """Validate the saved settings and export the usual figures and ledgers."""
    settings = json.loads(Path(preset).read_text(encoding="utf-8"))
    if settings.get("version") != 1:
        raise ValueError("Unsupported selected-preset version")
    config = check_config(settings["config"])
    if config_id(config) != settings["config_id"]:
        raise ValueError("Preset parameters do not match their saved configuration hash")
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty output folder; existing analysis results are preserved")
    result = run_analysis(source, output,
                          method=create_method(config["method"]["name"], **config["method"]["attributes"]),
                          trend_settings=TrendSettings(**config["trend"]),
                          breakout_settings=BreakoutSettings(**config["breakout"]),
                          trade_settings=TradeSettings(**{**config["trade"], **settings["costs"]}), until=until)
    (output / "selected_parameters.json").write_text(json.dumps(settings, indent=2)+"\n", encoding="utf-8")
    return result


def main():
    """Run without Tkinter, using the same shared pipeline as CLI and GUI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--preset", type=Path, default=Path(__file__).resolve().parent / "parameter_results/reference/selected_application.json")
    parser.add_argument("--output", type=Path, default=Path("output/selected_parameters"))
    parser.add_argument("--until", type=int)
    args = parser.parse_args()
    run(args.source, args.preset, args.output, args.until)
    print("Analysis results:", args.output.resolve())


if __name__ == "__main__":
    main()
