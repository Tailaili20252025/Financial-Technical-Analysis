"""Select parameters on earlier blocks, freeze them, then run later backtests.

python optimize_parameters.py --plan parameter_search_plan.json --output parameter_results/my_run --workers 4
No application defaults are changed. Existing output folders are never overwritten.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from contextlib import nullcontext
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import platform
import sys

from backtest import serialized, write_csv
from swingpoints.data import load_prices
from swingpoints.parameter_selection import (aggregate_items, canonical, choose_best, config_id,
    default_config, evaluate_job, init_worker, joint_candidates, score_blocks,
    swing_candidates, validate_plan)

ROOT = Path(__file__).resolve().parent


def save_json(path, value):
    """Write complete JSON atomically, avoiding a misleading partial selection."""
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    temporary.replace(path)


def sha(path):
    """SHA256 of the exact file bytes used by this experiment."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_cohort(data_dir, symbols, manifest):
    """Read a declared cohort, verify source hashes and forbid calendar filling."""
    expected = {r["symbol"]: r for r in manifest["files"]}
    data, records, calendar = {}, [], None
    for symbol in symbols:
        path = data_dir / (symbol+".csv")
        digest = sha(path)
        if symbol not in expected or digest != expected[symbol]["sha256"]:
            raise ValueError("Source manifest hash mismatch: " + symbol)
        bars = load_prices(path)
        dates = [b.timestamp.isoformat() for b in bars]
        if calendar is not None and dates != calendar:
            raise ValueError("Different observed calendars; no implicit filling: " + symbol)
        calendar = dates
        data[symbol] = bars
        records.append(dict(symbol=symbol, sha256=digest, rows=len(bars), first_date=dates[0], last_date=dates[-1]))
    return data, records


def evaluate(configs, periods, symbols, scenario, plan, pool, detail=False):
    """Yield portfolio groups one block at a time, bounding memory consumption."""
    configs = list({config_id(c): c for c in configs}.values())
    for period in periods:
        tasks = [(s, period, configs, scenario, plan["cost_scenarios"][scenario],
                  plan["minimum_warmup_bars"], detail, s in plan["prefix_audit_symbols"]) for s in symbols]
        responses = map(evaluate_job, tasks) if pool is None else pool.map(evaluate_job, tasks, chunksize=1)
        groups = {config_id(c): [] for c in configs}
        for response in responses:
            for item in response:
                groups[item["config_id"]].append(item)
        for identity, items in groups.items():
            errors = [x for x in items if x["status"] != "completed"]
            if len(items) != len(symbols):
                raise AssertionError("Incomplete experiment matrix")
            if errors:
                yield identity, period["name"], None, None, items, errors
            else:
                total, curve = aggregate_items(items)
                yield identity, period["name"], total, curve, items, []


class CsvLog:
    """Append rows with one stable schema; gzip keeps trial stock metrics compact."""
    def __init__(self, path):
        self.handle = gzip.open(path, "wt", newline="", encoding="utf-8") if str(path).endswith(".gz") else Path(path).open("w", newline="", encoding="utf-8")
        self.writer = None

    def write(self, rows):
        for row in rows:
            if self.writer is None:
                self.writer = csv.DictWriter(self.handle, list(row), lineterminator="\n")
                self.writer.writeheader()
            self.writer.writerow(serialized(row))
        self.handle.flush()

    def close(self):
        self.handle.close()


def search_phase(configs, stage, round_row, plan, pool, output, stock_log, block_log):
    """Score every declared trial; incomplete/failed trials cannot win."""
    blocks = {config_id(c): [] for c in configs}
    errors = {config_id(c): [] for c in configs}
    for identity, period, total, _, items, failed in evaluate(configs, round_row["validation"],
            plan["development_symbols"], plan["selection_scenario"], plan, pool):
        errors[identity].extend(failed)
        if total is not None:
            blocks[identity].append(total)
            block_log.write([dict(round=round_row["name"], stage=stage, **total)])
        stock_log.write([dict(round=round_row["name"], stage=stage, **x["summary"])
                         for x in items if x["status"] == "completed"])
    trials = []
    for config in configs:
        identity = config_id(config)
        row = dict(round=round_row["name"], stage=stage, method=config["method"]["name"],
                   config_id=identity, config=config, status="failed" if errors[identity] else "completed",
                   errors=errors[identity], eligible=False, constraint_failures=[],
                   median_return_percent=None, aggregate_net_pnl=None, worst_drawdown_percent=None,
                   closed_trades=None, positive_blocks=None, validation_blocks=len(blocks[identity]))
        if not errors[identity]:
            if len(blocks[identity]) != len(round_row["validation"]):
                raise AssertionError("Trial lacks a declared validation block")
            row.update(score_blocks(blocks[identity], plan["constraints"]))
        trials.append(row)
    with (output / "trials.jsonl").open("a", encoding="utf-8") as handle:
        for trial in trials:
            handle.write(json.dumps(trial, allow_nan=False)+"\n")
    print(f"Selected-data replay complete: {round_row['name']} / {stage} / {len(trials)} trials", flush=True)
    return trials


def select_round(round_index, row, plan, pool, output, stock_log, block_log):
    """Two-stage fixed-budget search, using only this round's validation dates."""
    initial = [c for method in plan["swing_grids"] for c in swing_candidates(plan, method)]
    trials = search_phase(initial, "swing_grid", row, plan, pool, output, stock_log, block_log)
    parents, joint = {}, []
    for method in plan["swing_grids"]:
        method_trials = [t for t in trials if t["method"] == method]
        parent = choose_best(method_trials) or choose_best(method_trials, require_eligible=False)
        if parent is None:
            raise RuntimeError("All Stage 1 configurations failed for " + method)
        parents[method] = dict(config_id=parent["config_id"], eligible=parent["eligible"])
        joint.extend(joint_candidates(plan, method, parent["config"], round_index,
                                      {t["config_id"] for t in trials}))
    trials.extend(search_phase(joint, "joint_random", row, plan, pool, output, stock_log, block_log))
    winner = choose_best(trials)
    per_method = {}
    for method in plan["swing_grids"]:
        best = choose_best([t for t in trials if t["method"] == method])
        per_method[method] = dict(qualified=best is not None,
                                 config=best["config"] if best else default_config(plan, method),
                                 score=best["median_return_percent"] if best else None)
    selection = dict(round=row["name"], validation=row["validation"], test=row["test"],
                     frozen_before_outer_evaluation=True, stage1_parents=parents,
                     qualified=winner is not None,
                     selected_config=winner["config"] if winner else default_config(plan, "ta"),
                     selected_score=winner["median_return_percent"] if winner else None,
                     per_method=per_method, trials=len(trials), eligible_trials=sum(t["eligible"] for t in trials),
                     reason="Highest eligible median net validation return; ties use drawdown, aggregate P/L, then ID" if winner else "No eligible trial; use unchanged TA baseline, not a fitted winner")
    save_json(output / f"selection_{row['name']}.json", selection)
    return selection, trials


def evaluate_outer(selection, cohort, data, plan, pool, logs, audit_records, prefix_records):
    """Assess frozen candidates and unchanged baselines; never feeds selection."""
    arms = {f"default_{m}": default_config(plan, m) for m in plan["swing_grids"]}
    arms.update({f"tuned_{m}": r["config"] for m, r in selection["per_method"].items()})
    selected_id = config_id(selection["selected_config"])
    rows, curves = [], []
    for scenario in plan["cost_scenarios"]:
        for identity, _, total, curve, items, errors in evaluate(list(arms.values()), [selection["test"]],
                list(data), scenario, plan, pool, detail=True):
            if errors:
                raise RuntimeError("Frozen test failed: " + canonical(errors))
            common = dict(round=selection["round"], cohort=cohort, scenario=scenario, config_id=identity)
            for item in items:
                audit_records.append(dict(**common, **{k: v for k, v in item["audit"].items() if k not in common}))
                if "prefix_audit" in item:
                    prefix_records.append(dict(**common, symbol=item["summary"]["symbol"], **item["prefix_audit"]))
            for arm, config in arms.items():
                if config_id(config) != identity:
                    continue
                label = dict(round=selection["round"], cohort=cohort, arm=arm,
                             selected_by_validation=arm.startswith("tuned_") and identity == selected_id,
                             qualified=selection["per_method"][config["method"]["name"]]["qualified"] if arm.startswith("tuned_") else True)
                rows.append(dict(**label, **total))
                curves.extend(dict(**label, scenario=scenario, **r) for r in curve)
                for item in items:
                    logs["stocks"].write([dict(**label, **item["summary"])])
                    logs["trades"].write([dict(**label, scenario=scenario, symbol=item["summary"]["symbol"],
                                                config_id=identity, **t) for t in item["trades"]])
        print(f"Frozen test complete: {selection['round']} / {cohort} / {scenario}", flush=True)
    return rows, curves


def export_replay_plan(output, data_dir, plan, selection):
    """Allow the existing backtest.py and application to consume the winner."""
    config = selection["selected_config"]
    replay = dict(data_dir=os.path.relpath(data_dir, output), symbols=plan["heldout_symbols"],
                  periods=[selection["test"]], minimum_warmup_bars=plan["minimum_warmup_bars"],
                  methods=[config["method"]], trend_settings=config["trend"], breakout_settings=config["breakout"],
                  trade_settings=config["trade"],
                  cost_scenarios=[dict(name=n, **v) for n, v in plan["cost_scenarios"].items()],
                  prefix_audit_symbols=[s for s in plan["prefix_audit_symbols"] if s in plan["heldout_symbols"]])
    save_json(output / "selected_backtest_plan.json", replay)
    save_json(output / "selected_application.json", dict(version=1, config=config,
              config_id=config_id(config), costs=plan["cost_scenarios"][plan["selection_scenario"]],
              selection_round=selection["round"], validation_end=selection["validation"][-1]["end"],
              qualified=selection["qualified"], note="A validation-selected preset, not a profitability guarantee; application defaults are unchanged"))


def plot_results(output, trials, summaries, curves, selection_scenario="base"):
    """Draw publication-friendly figures from exported numbers, not estimates."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {"ta": "#222222", "percentage": "#777777", "atr": "#9b5a18", "prominence": "#126d61"}
    fig, axes = plt.subplots(1, len({t['round'] for t in trials}), figsize=(12, 4.5), squeeze=False)
    for ax, name in zip(axes[0], dict.fromkeys(t["round"] for t in trials)):
        subset = [t for t in trials if t["round"] == name]
        for method in dict.fromkeys(t["method"] for t in subset):
            for eligible, marker in ((True, "o"), (False, "x")):
                points = [(i+1, t["median_return_percent"]) for i, t in enumerate(subset)
                          if t["method"] == method and t["status"] == "completed" and t["eligible"] == eligible]
                if points:
                    ax.scatter(*zip(*points), s=24, marker=marker, color=colors[method],
                               label=method + (" (ineligible)" if not eligible else ""))
        initial_count = sum(t["stage"] == "swing_grid" for t in subset)
        ax.axvline(initial_count+.5, color="gray", linestyle="--", linewidth=.8)
        ax.axhline(0, color="black", linewidth=.6)
        ax.set(title=name+": validation only", xlabel="Trial order; dashed divider ends swing grid", ylabel="Median block net return (%)")
        ax.grid(alpha=.15)
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output / "validation_search.png", dpi=180)
    plt.close(fig)
    groups = list(dict.fromkeys((s["round"], s["cohort"]) for s in summaries))
    fig, axes = plt.subplots(1, len(groups), figsize=(15, 4.8), squeeze=False)
    methods = list(dict.fromkeys(s["method"] for s in summaries))
    for ax, group in zip(axes[0], groups):
        subset = [s for s in summaries if (s["round"], s["cohort"]) == group and s["scenario"] == selection_scenario]
        for offset, prefix, color in ((-.18, "default_", "#bbbbbb"), (.18, "tuned_", "#333333")):
            values = [next(s["net_pnl"] for s in subset if s["arm"] == prefix+m) for m in methods]
            ax.bar([i+offset for i in range(len(methods))], values, .36, color=color, label=prefix[:-1])
        ax.axhline(0, color="black", linewidth=.6)
        ax.set_xticks(range(len(methods)), methods, rotation=20)
        ax.set(title=" / ".join(group), ylabel="Net marked P/L (input currency units)")
        ax.legend(fontsize=8)
        ax.grid(axis="y", alpha=.15)
    fig.suptitle(f"Frozen test: each method's selected settings versus its unchanged baseline ({selection_scenario} costs)")
    fig.tight_layout()
    fig.savefig(output / "test_parameter_comparison.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(len(groups), 1, figsize=(11, 3.1*len(groups)), squeeze=False)
    for ax, group in zip(axes[:, 0], groups):
        subset = [s for s in summaries if (s["round"], s["cohort"]) == group and s["scenario"] == selection_scenario]
        selected = next(s for s in subset if s["selected_by_validation"])
        for arm, style, label in ((selected["arm"], "-", "Selected policy: " + selected["method"]),
                                  ("default_ta", "--", "Unchanged TA")):
            path = [r for r in curves if (r["round"], r["cohort"], r["scenario"], r["arm"]) == (*group, selection_scenario, arm)]
            ax.plot([r["timestamp"][:10] for r in path], [r["net_pnl"] for r in path], style, color="black", label=label, linewidth=1.4)
        ax.plot([r["timestamp"][:10] for r in path], [r["buy_hold_net_pnl"] for r in path], color="gray", linestyle=":", label="Buy-and-hold, same one share per stock")
        ax.set_xticks(range(0, len(path), max(1, len(path)//6)), [r["timestamp"][:10] for r in path[::max(1,len(path)//6)]])
        ax.axhline(0, color="black", linewidth=.5)
        ax.set(title=" / ".join(group)+" — independent flat reset", ylabel="Net marked P/L")
        ax.legend(fontsize=8, loc="upper left")
        ax.grid(alpha=.15)
    fig.tight_layout()
    fig.savefig(output / "selected_test_equity.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, len(groups), figsize=(14, 4.5), squeeze=False)
    for ax, group in zip(axes[0], groups):
        subset = [s for s in summaries if (s["round"], s["cohort"]) == group and s["selected_by_validation"]]
        ax.bar([s["scenario"] for s in subset], [s["net_pnl"] for s in subset], color=["#cccccc", "#777777", "#222222"][:len(subset)])
        ax.axhline(0, color="black", linewidth=.6)
        ax.set(title=" / ".join(group), ylabel="Selected policy net marked P/L")
        ax.grid(axis="y", alpha=.15)
    fig.suptitle("Same frozen settings re-simulated under different trading costs")
    fig.tight_layout()
    fig.savefig(output / "selected_cost_sensitivity.png", dpi=180)
    plt.close(fig)


def run(plan_path, output, workers=4):
    """Execute the complete predeclared experiment; leave audit files on failure."""
    plan_path, output = Path(plan_path).resolve(), Path(output).resolve()
    plan = validate_plan(json.loads(plan_path.read_text(encoding="utf-8")))
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise ValueError("workers must be a positive integer")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory is not empty; choose a new folder to preserve prior results")
    data_dir = (plan_path.parent / plan["data_dir"]).resolve()
    manifest = json.loads((data_dir / "source_manifest.json").read_text(encoding="utf-8"))
    data, inputs = load_cohort(data_dir, plan["development_symbols"], manifest)
    output.mkdir(parents=True, exist_ok=True)
    save_json(output / "applied_plan.json", plan)
    code = sorted((ROOT / "swingpoints").glob("*.py")) + [ROOT / name for name in
            ("optimize_parameters.py", "prepare_parameter_data.py", "run_selected_parameters.py",
             "backtest.py", "prepare_backtest_data.py")]
    metadata = dict(status="running", started_utc=datetime.now(timezone.utc).isoformat(),
                    plan_sha256=sha(plan_path), python=sys.version, platform=platform.platform(), workers=workers,
                    input_files=inputs, source_manifest=manifest,
                    code_sha256={str(p.relative_to(ROOT)): sha(p) for p in code},
                    design="Two-stage inner validation; frozen yearly outer tests; final stock cohort excluded from selection",
                    accounting="Independent 10,000-unit accounts by default; one share per trade; next-Open entry; marked end positions, no forced liquidation")
    save_json(output / "experiment.json", metadata)
    logs = {"validation_stocks": CsvLog(output / "validation_by_stock.csv.gz"),
            "validation_blocks": CsvLog(output / "validation_blocks.csv"),
            "stocks": CsvLog(output / "test_by_stock.csv"), "trades": CsvLog(output / "test_trades.csv")}
    trials, selections, summaries, curves, audits, prefixes = [], [], [], [], [], []
    def make_pool(cohort):
        if workers == 1:
            init_worker(cohort)
            return nullcontext(None)
        return ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
                                   initializer=init_worker, initargs=(cohort,))
    try:
        with make_pool(data) as pool:
            for index, row in enumerate(plan["rounds"]):
                selection, searched = select_round(index, row, plan, pool, output,
                                                   logs["validation_stocks"], logs["validation_blocks"])
                selections.append(selection)
                trials.extend(searched)
            # All parameter decisions are written before ANY outer-test scoring.
            save_json(output / "frozen_selections.json", selections)
            for selection in selections:
                rows, paths = evaluate_outer(selection, "development", data, plan, pool, logs, audits, prefixes)
                summaries.extend(rows)
                curves.extend(paths)
        # Only now load price histories belonging to the held-out stock cohort.
        holdout, held_inputs = load_cohort(data_dir, plan["heldout_symbols"], manifest)
        metadata["input_files"].extend(held_inputs)
        with make_pool(holdout) as pool:
            rows, paths = evaluate_outer(selections[-1], "heldout", holdout, plan, pool, logs, audits, prefixes)
            summaries.extend(rows)
            curves.extend(paths)
        write_csv(output / "trial_summary.csv", [serialized(t) for t in trials])
        write_csv(output / "test_portfolios.csv", summaries)
        write_csv(output / "test_portfolio_equity.csv", curves)
        save_json(output / "validation.json", dict(passed=True, audited_runs=len(audits),
                  audited_equity_rows=sum(a["checked_bars"] for a in audits), audited_trades=sum(a["checked_trades"] for a in audits),
                  maximum_equity_error=max(a["maximum_equity_error"] for a in audits),
                  arithmetic_audits=audits, prefix_audits=prefixes,
                  scope="Independent Decimal reconstruction of every outer evaluation; selected-symbol real-data prefix invariance; not a guarantee of realistic fills"))
        export_replay_plan(output, data_dir, plan, selections[-1])
        plot_results(output, trials, summaries, curves, plan["selection_scenario"])
        for log in logs.values(): log.close()
        metadata.update(status="completed", completed_utc=datetime.now(timezone.utc).isoformat(),
                        trials=len(trials), failed_trials=sum(t["status"] != "completed" for t in trials),
                        evaluated_portfolios=len(summaries), unique_input_rows=sum(r["rows"] for r in metadata["input_files"]),
                        output_sha256={p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file() and p.name != "experiment.json"})
        save_json(output / "experiment.json", metadata)
    except Exception as error:
        for log in logs.values(): log.close()
        metadata.update(status="failed", error=f"{type(error).__name__}: {error}")
        save_json(output / "experiment.json", metadata)
        raise
    return selections, summaries


def main():
    """Terminal interface; multiprocessing is optional and changes no results."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT / "parameter_search_plan.json")
    parser.add_argument("--output", type=Path, default=ROOT / "parameter_results" / "latest")
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args()
    run(args.plan, args.output, args.workers)
    print("Results:", args.output.resolve())


if __name__ == "__main__":
    main()
