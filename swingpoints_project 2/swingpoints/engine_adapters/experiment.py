"""Reusable preparation, export and comparison logic for optional engines."""
import csv
from dataclasses import asdict
from datetime import date
import hashlib
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from ..breakouts import BreakoutSettings
from ..methods import create_method
from ..pipeline import analyze
from ..trendlines import TrendSettings
from .common import EngineSettings, validate_inputs


def digest(path):
    """Hash exact source bytes, not a rounded CSV representation."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_csv(path, records, fields=None):
    """Write full-precision audit records, including a header for empty ledgers."""
    records = list(records)
    if fields is None:
        fields = list(records[0]) if records else []
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({k:json.dumps(v) if isinstance(v,(tuple,list,dict)) else v for k,v in r.items()}
                         for r in records)


def validate_plan(plan):
    """Validate the fixed experiment before any result is inspected."""
    if not plan.get("symbols") or len(set(plan["symbols"])) != len(plan["symbols"]):
        raise ValueError("Use at least one unique symbol")
    for name in plan["symbols"]:
        if not name or not all(c.isalnum() or c in "_-" for c in name):
            raise ValueError("Unsafe symbol filename")
    minimum, repetitions = plan["minimum_warmup_bars"], plan["timing_repetitions"]
    for name, value, lowest in (("minimum_warmup_bars",minimum,0),("timing_repetitions",repetitions,1)):
        if isinstance(value,bool) or not isinstance(value,int) or value < lowest:
            raise ValueError(name+" must be an integer at least "+str(lowest))
    if not plan["periods"]:
        raise ValueError("At least one scored period is required")
    previous = None
    for p in plan["periods"]:
        start, end = date.fromisoformat(p["start"]), date.fromisoformat(p["end"])
        if start > end or (previous is not None and start <= previous):
            raise ValueError("Periods must be increasing and nonoverlapping")
        previous = end
    for values in (plan["periods"], plan["methods"], plan["cost_scenarios"]):
        names = [v["name"] for v in values]
        if not names or len(names) != len(set(names)):
            raise ValueError("Period/method/scenario names must be nonempty and unique")
    methods = [create_method(m["name"], **m.get("attributes", {})) for m in plan["methods"]]
    if any(m.basis != "close" for m in methods):
        raise ValueError("Trading comparison requires Close-based Step 4 events")
    trend = TrendSettings(**plan["trend_settings"])
    breakout = BreakoutSettings(**plan["breakout_settings"])
    scenarios = [(s["name"], EngineSettings(**plan["engine_settings"],
                                           **{k:v for k,v in s.items() if k != "name"}))
                 for s in plan["cost_scenarios"]]
    return methods, trend, breakout, scenarios


def prepare(bars, period, method, trend, breakout, minimum_warmup_bars):
    """Run existing Steps 1–4 on an observed prefix and exclude warm-up entries."""
    end, start_date = date.fromisoformat(period["end"]), date.fromisoformat(period["start"])
    prefix = [b for b in bars if b.timestamp.date() <= end]
    validate_inputs(prefix, [])
    start = next((i for i,b in enumerate(prefix) if b.timestamp.date() >= start_date), None)
    if start is None or start < minimum_warmup_bars:
        raise ValueError("Empty scored period or insufficient warm-up")
    result = analyze(prefix, method, trend, breakout)
    # Include later-failed events: the final failure label is unavailable at entry.
    events = [e for e in result.events if e.confirmation_index is not None and e.confirmation_index >= start]
    return prefix, start, events


def timed_run(engine, bars, events, settings, method, repetitions):
    """Median wall time for the complete adapter, excluding detection and I/O.

    The result must be deterministic across repetitions. Optional dependencies
    are loaded when the engine is constructed, outside this measured interval.
    """
    samples, last, checksum = [], None, None
    for _ in range(repetitions):
        start = perf_counter()
        result = engine.run(bars, events, settings, method)
        samples.append(perf_counter()-start)
        stamp = json.dumps((result.trades,result.equity), sort_keys=True, allow_nan=False)
        current = hashlib.sha256(stamp.encode()).hexdigest()
        if checksum is not None and checksum != current:
            raise AssertionError("Engine results changed between identical repetitions")
        checksum, last = current, result
    return last, dict(median_seconds=median(samples), minimum_seconds=min(samples),
                      repetitions=repetitions, samples_seconds=samples, result_sha256=checksum)


def prefix_check(bars, start, period, method, trend, breakout, engine, settings, full):
    """Rerun detection and execution at a midpoint; earlier results must persist."""
    count = start + max(1,(len(bars)-start)//2)
    shorter = bars[:count]
    analysis = analyze(shorter, method, trend, breakout)
    events = [e for e in analysis.events if e.confirmation_index is not None and e.confirmation_index >= start]
    partial = engine.run(shorter, events, settings, method.key)
    error = max(abs(a-b) for a,b in zip(partial.equity,full.equity[:count]))
    keys = lambda result: [(t["signal_index"],t["side"],t["entry_index"],t["entry_price"],t["stop_price"],t["target_price"])
                           for t in result.trades if t["entry_index"] < count]
    if error > 1e-7 or keys(partial) != keys(full):
        raise AssertionError("Future data changed earlier decisions/equity")
    return dict(engine=full.engine, period=period["name"], method=method.key,
                checked_prefix_bars=count, maximum_equity_error=error, passed=True)


def plot_comparison(output, summaries, comparisons, timings, curves):
    """Create reproducible grayscale figures from original-bar statistics."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    methods = list(dict.fromkeys(r["method"] for r in summaries))
    scenarios = list(dict.fromkeys(r["scenario"] for r in summaries))
    engines = list(dict.fromkeys(r["engine"] for r in summaries))
    fig, axes = plt.subplots(1,len(scenarios),figsize=(12,4),squeeze=False)
    for ax, scenario in zip(axes[0], scenarios):
        width=.7/len(engines)
        for j,engine in enumerate(engines):
            values=[sum(r["net_pnl"] for r in summaries if r["method"]==m and r["scenario"]==scenario and r["engine"]==engine)
                    for m in methods]
            ax.bar([i+(j-(len(engines)-1)/2)*width for i in range(len(methods))],values,width,
                   label=engine,color=str(.25+.4*j),edgecolor="black",linewidth=.5)
        ax.set_xticks(range(len(methods)),methods,fontsize=9)
        ax.set_title(scenario.replace("_"," "))
        ax.axhline(0,color="black",linewidth=.6)
        ax.set_ylabel("Sum of independent-block net P/L")
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output/"engine_pnl_comparison.png",dpi=170)
    plt.close(fig)

    fig, axes = plt.subplots(1,2,figsize=(11,4))
    if comparisons:
        gains=[sum(r["target_gap_gain"] for r in comparisons if r["method"]==m and r["scenario"]==scenarios[-1]) for m in methods]
        residual=[max([r["maximum_policy_adjusted_equity_difference"] for r in comparisons if r["method"]==m] or [0]) for m in methods]
        axes[0].bar(methods,gains,color=".5",edgecolor="black")
        axes[0].set_ylabel("P/L difference explained by target gaps")
        axes[0].set_title("Native fill-policy difference")
    for engine in engines:
        values=[1000*median([r["median_seconds"] for r in timings if r["engine"]==engine and r["method"]==m]) for m in methods]
        axes[1].plot(methods,values,"o-" if engine==engines[0] else "s--",color=".2" if engine==engines[0] else ".55",label=engine)
    axes[1].set_yscale("log")
    axes[1].set_ylabel("Median adapter time per run in milliseconds")
    axes[1].set_title("Same-machine timing excluding Steps 1–4")
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(output/"engine_differences_and_timing.png",dpi=170)
    plt.close(fig)

    if curves:
        from datetime import datetime
        scenario=scenarios[-1]
        periods=list(dict.fromkeys(k[0] for k in curves))
        fig,axes=plt.subplots(len(periods),1,figsize=(10,2.5*len(periods)),squeeze=False)
        # One TA portfolio view; detailed all-method curves remain in the export.
        chosen="ta" if "ta" in methods else methods[0]
        for ax,period in zip(axes[:,0],periods):
            for j,engine in enumerate(engines):
                rows=curves[(period,chosen,scenario,engine)]
                ax.plot([datetime.fromisoformat(x["timestamp"]) for x in rows],[x["net_pnl"] for x in rows],
                        label=engine,linestyle="-" if j==0 else "--",color=str(.15+.4*j))
            ax.axhline(0,color=".7",linewidth=.6)
            ax.set_title(period,loc="left")
            ax.set_ylabel("Net P/L")
        axes[0,0].legend()
        fig.suptitle(f"{chosen} | {scenario} | independently reset portfolios")
        fig.tight_layout(rect=(0,0,1,.97))
        fig.savefig(output/"engine_equity_comparison.png",dpi=170)
        plt.close(fig)
