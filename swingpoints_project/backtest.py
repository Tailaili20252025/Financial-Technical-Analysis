"""Run reproducible chronological backtests using the existing analysis engine.

python backtest.py --plan backtest_plan.json --output backtest_results/my_run
The plan controls methods, class attributes, dates, symbols and trading costs.
"""
import argparse
import csv
import gzip
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from swingpoints.backtesting import (aggregate_portfolio, audit_prefix, audit_result,
                                    prepare_block, simulate_block, validate_plan)
from swingpoints.data import load_prices
from swingpoints.trading import EQUITY_FIELDS, SIGNAL_FIELDS, TRADE_FIELDS

ROOT = Path(__file__).resolve().parent


def write_csv(path, records):
    """Write a consistent schema, preserving full precision for audit."""
    if not records:
        raise ValueError("Cannot infer an empty CSV schema")
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, list(records[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def serialized(record):
    """Encode list-valued audit fields as JSON inside CSV cells."""
    return {k: json.dumps(v, separators=(",", ":")) if isinstance(v, (list, tuple, dict)) else v
            for k, v in record.items()}


def plot_results(output, summaries, curves):
    """Draw black/gray comparison figures without needing a GUI or display."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from datetime import datetime
    methods = list(dict.fromkeys(s["method"] for s in summaries))
    periods = list(dict.fromkeys(s["period"] for s in summaries))
    scenarios = list(dict.fromkeys(s["scenario"] for s in summaries))
    base = "base" if "base" in scenarios else scenarios[0]
    styles = ["-", "--", "-.", ":"]
    fig, axes = plt.subplots(len(periods), 1, figsize=(10, 2.8*len(periods)), squeeze=False)
    for ax, period in zip(axes[:, 0], periods):
        last = None
        for index, method in enumerate(methods):
            rows = curves[(period, method, base)]
            times = [datetime.fromisoformat(r["timestamp"]) for r in rows]
            ax.plot(times, [r["net_pnl"] for r in rows], label=method,
                    color=str(.12+.12*(index % 4)), linestyle=styles[index % 4], linewidth=1.5)
            last = rows
        ax.plot(times, [r["buy_hold_net_pnl"] for r in last], label="buy and hold", color="0.6", linewidth=2)
        ax.axhline(0, color="0.8", linewidth=.6)
        ax.set_title(period.replace("_", " "), loc="left")
        ax.set_ylabel("Net marked P/L")
        ax.grid(alpha=.15)
    axes[0, 0].legend(ncol=3, fontsize=9)
    fig.suptitle(f"{base.capitalize()} costs | independent test blocks | same quantity benchmark", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, .98))
    fig.savefig(output / "equity_comparison.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    width = .8/len(scenarios)
    for j, scenario in enumerate(scenarios):
        values = [sum(s["net_pnl"] for s in summaries if s["scenario"] == scenario and s["method"] == m) for m in methods]
        x = [i + (j-(len(scenarios)-1)/2)*width for i in range(len(methods))]
        ax.bar(x, values, width, label=scenario, color=str(.25+.5*j/max(1, len(scenarios)-1)), edgecolor="black", linewidth=.4)
    ax.set_xticks(range(len(methods)), methods)
    ax.set_ylabel("Sum of block net marked P/L")
    ax.set_title("Cost sensitivity across independently reset blocks")
    ax.axhline(0, color="black", linewidth=.6)
    ax.legend()
    ax.grid(axis="y", alpha=.15)
    fig.tight_layout()
    fig.savefig(output / "cost_comparison.png", dpi=160)
    plt.close(fig)


def run(plan_path, output, overwrite=False):
    """Execute the declared matrix, reconcile ledgers and export reproducibility data."""
    plan_path, output = Path(plan_path).resolve(), Path(output).resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    periods, methods, trend, breakout, scenarios = validate_plan(plan)
    if output.exists() and any(output.iterdir()) and not overwrite:
        raise ValueError("Output directory is not empty. Choose another folder or pass --overwrite.")
    data_dir = (plan_path.parent / plan["data_dir"]).resolve()
    manifest_path = data_dir / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    expected_hashes = {r["symbol"]: r["sha256"] for r in manifest["files"]} if manifest else {}
    source_files, data = [], {}
    for symbol in plan["symbols"]:
        path = data_dir / (symbol+".csv")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if symbol in expected_hashes and digest != expected_hashes[symbol]:
            raise ValueError("Source manifest hash mismatch: " + symbol)
        data[symbol] = load_prices(path)
        source_files.append(dict(symbol=symbol, sha256=digest, rows=len(data[symbol]),
                                 first_date=data[symbol][0].timestamp.date().isoformat(),
                                 last_date=data[symbol][-1].timestamp.date().isoformat()))
    output.mkdir(parents=True, exist_ok=True)
    code_files = sorted((ROOT / "swingpoints").glob("*.py")) + [Path(__file__).resolve()]
    metadata = dict(status="running", started_utc=datetime.now(timezone.utc).isoformat(),
                    python=sys.version, platform=platform.platform(),
                    plan=plan, plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                    input_files=source_files, source_manifest=manifest,
                    code_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in code_files},
                    design="Fixed parameters; nonoverlapping chronological test blocks; independent flat resets",
                    accounting="One fixed-quantity position per stock; separate funded stock accounts; mark open positions at cutoff",
                    currency="Input price units (archival US equity prices); no FX conversion or inflation adjustment")
    metadata_path = output / "experiment.json"
    metadata_path.write_text(json.dumps(metadata, indent=2)+"\n")
    # Freeze a full configuration before inspecting any performance result.
    (output / "applied_plan.json").write_text(json.dumps(plan, indent=2)+"\n")
    summaries, audits, prefixes, portfolios, curves = [], [], [], [], {}
    try:
        with (output / "trades.csv").open("w", newline="", encoding="utf-8") as tf, \
                gzip.open(output / "equity_by_run.csv.gz", "wt", newline="", encoding="utf-8") as ef, \
                gzip.open(output / "signals.csv.gz", "wt", newline="", encoding="utf-8") as sf:
            tw = csv.DictWriter(tf, ["run_id", *TRADE_FIELDS], lineterminator="\n")
            ew = csv.DictWriter(ef, ["run_id", *EQUITY_FIELDS], lineterminator="\n")
            sw = csv.DictWriter(sf, ["run_id", *SIGNAL_FIELDS], lineterminator="\n")
            for writer in (tw, ew, sw):
                writer.writeheader()
            for period in periods:
                for method in methods:
                    grouped = {name: ([], {}, {}) for name, _ in scenarios}
                    for symbol in plan["symbols"]:
                        block = prepare_block(data[symbol], period, method, trend, breakout, plan["minimum_warmup_bars"])
                        for scenario, settings in scenarios:
                            result, summary, equity, bh = simulate_block(block, settings, symbol, scenario)
                            audits.append(audit_result(block.bars, block.start_index, result, summary))
                            if symbol in plan["prefix_audit_symbols"] and scenario == scenarios[0][0]:
                                prefixes.append(dict(symbol=symbol, **audit_prefix(block, settings, result)))
                            summaries.append(summary)
                            run_id = summary["run_id"]
                            for trade in result.trades:
                                tw.writerow(serialized(dict(run_id=run_id, **trade.as_record(block.bars))))
                            ew.writerows(dict(run_id=run_id, **r) for r in equity)
                            sw.writerows(serialized(dict(run_id=run_id, **r)) for r in result.signals)
                            gs, ge, gb = grouped[scenario]
                            gs.append(summary)
                            ge[symbol], gb[symbol] = equity, bh
                    for scenario, (gs, ge, gb) in grouped.items():
                        total, curve = aggregate_portfolio(gs, ge, gb)
                        portfolios.append(total)
                        curves[(period.name, method.key, scenario)] = curve
                    print(f"Completed {period.name} / {method.key}: {len(plan['symbols'])} stocks x {len(scenarios)} costs", flush=True)
        write_csv(output / "summary.csv", summaries)
        write_csv(output / "portfolio_summary.csv", portfolios)
        write_csv(output / "portfolio_equity.csv", [dict(period=p, method=m, scenario=s, **r)
                  for (p, m, s), rows in curves.items() for r in rows])
        validation = dict(passed=True, audited_runs=len(audits),
                          audited_equity_rows=sum(a["checked_bars"] for a in audits),
                          audited_trades=sum(a["checked_trades"] for a in audits),
                          maximum_equity_error=max(a["maximum_equity_error"] for a in audits),
                          prefix_audits=prefixes, arithmetic_audits=audits,
                          scope="Independent Decimal ledger/equity reconstruction and selected real-data prefix checks; not proof of market realism")
        (output / "validation.json").write_text(json.dumps(validation, indent=2)+"\n")
        plot_results(output, portfolios, curves)
        metadata.update(status="completed", completed_utc=datetime.now(timezone.utc).isoformat(),
                        simulations=len(summaries), unique_input_rows=sum(len(v) for v in data.values()),
                        output_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                       for p in sorted(output.iterdir()) if p.is_file() and p.name != "experiment.json"})
        metadata_path.write_text(json.dumps(metadata, indent=2)+"\n")
    except Exception as error:
        metadata.update(status="failed", error=str(error))
        metadata_path.write_text(json.dumps(metadata, indent=2)+"\n")
        raise
    return portfolios


def main():
    """Provide one terminal entry point; running the GUI is unnecessary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT / "backtest_plan.json")
    parser.add_argument("--output", type=Path, default=ROOT / "backtest_results" / "latest")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    run(args.plan, args.output, args.overwrite)
    print("Results:", args.output.resolve())


if __name__ == "__main__":
    main()
