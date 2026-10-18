"""Compare the application with Backtesting.py without modifying app.py or GUI.

python compare_engines.py --plan engine_comparison_plan.json --output engine_comparison_results/my_run
python compare_engines.py --input data/data.csv --engines backtesting_py
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import sys
from time import perf_counter

# Disable third-party progress bars, not broker execution or statistics.
os.environ.setdefault("TQDM_DISABLE", "1")
from swingpoints.data import load_prices
from swingpoints.engine_adapters import get_engine
from swingpoints.engine_adapters.common import audit_accounting, maximum_drawdown, reconcile
from swingpoints.engine_adapters.experiment import (digest, plot_comparison, prefix_check,
                                                    prepare, timed_run, validate_plan, write_csv)

ROOT=Path(__file__).resolve().parent


def run(plan_path, output, engines=("application","backtesting_py"), source=None,
        repetitions=None, overwrite=False):
    """Run matched settings, audit both accounts and export every difference.

    Large-data comparisons reuse data/backtest from the separate backtesting PR.
    A single existing CSV can also be used before that PR is merged. Request only
    backtesting_py when the original main lacks the Step 5–6 trading module.
    """
    plan_path, output=Path(plan_path).resolve(),Path(output).resolve()
    plan=json.loads(plan_path.read_text(encoding="utf-8"))
    if repetitions is not None:
        plan["timing_repetitions"]=repetitions
    engines=list(engines)
    if not engines or len(set(engines))!=len(engines):
        raise ValueError("Select unique engines")
    if output.exists() and any(output.iterdir()) and not overwrite:
        raise ValueError("Output exists. Choose a fresh folder or use --overwrite.")
    data, source_files={},[]
    if source is not None:
        path=Path(source).resolve()
        bars=load_prices(path)
        plan["symbols"]=["input"]
        plan["periods"]=[dict(name="input",start=bars[0].timestamp.date().isoformat(),end=bars[-1].timestamp.date().isoformat())]
        plan["minimum_warmup_bars"]=0
        plan["prefix_audit_symbols"]=[]
        data["input"]=bars
        paths={"input":path}
    else:
        data_dir=(plan_path.parent/plan["data_dir"]).resolve()
        paths={s:data_dir/(s+".csv") for s in plan["symbols"]}
        if any(not path.is_file() for path in paths.values()):
            raise ValueError("Comparison data missing. Merge the backtesting PR for data/backtest, "
                             "or pass --input data/data.csv.")
    methods,trend,breakout,scenarios=validate_plan(plan)
    adapters={name:get_engine(name) for name in engines}
    source_manifest=None
    if source is None:
        manifest_path=next(iter(paths.values())).parent/"source_manifest.json"
        if manifest_path.exists():
            source_manifest=json.loads(manifest_path.read_text())
    expected={r["symbol"]:r["sha256"] for r in source_manifest["files"]} if source_manifest else {}
    for symbol,path in paths.items():
        sha=digest(path)
        if symbol in expected and sha!=expected[symbol]:
            raise ValueError("Source checksum mismatch: "+symbol)
        data.setdefault(symbol,load_prices(path))
        source_files.append(dict(symbol=symbol,sha256=sha,rows=len(data[symbol]),
                                 first=data[symbol][0].timestamp.isoformat(),last=data[symbol][-1].timestamp.isoformat()))
    output.mkdir(parents=True,exist_ok=True)
    metadata=dict(status="running",started_utc=datetime.now(timezone.utc).isoformat(),
                  python=sys.version,platform=platform.platform(),engines=engines,
                  packages={name:version(name) for name in ("backtesting","pandas","numpy","bokeh")}
                  if "backtesting_py" in engines else {},plan=plan,input_files=source_files,
                  source_manifest=source_manifest,unique_input_rows=sum(len(v) for v in data.values()),
                  engine_contract="Next original Open, original Close marks, integer quantity, one position, no forced cutoff exit",
                  cost_contract="Zero spread/slippage/borrow. Zero or fixed per-order fees. Not the previous base-cost scenario.",
                  target_difference="Application uses limit price; Backtesting.py permits favourable gap improvement.",
                  independence="Shared Steps 1–4 events and ATR values; order execution/accounting is independent.",
                  code_sha256={str(p.relative_to(ROOT)):digest(p) for p in sorted((ROOT/"swingpoints").rglob("*.py"))},
                  runner_sha256=digest(Path(__file__)),timing_scope="Median repeated adapter wall time, excludes Steps 1–4, imports and file I/O")
    (output/"applied_plan.json").write_text(json.dumps(plan,indent=2)+"\n")
    meta_path=output/"experiment.json"
    meta_path.write_text(json.dumps(metadata,indent=2)+"\n")
    summaries,comparisons,timings,ledgers,audits,prefixes,decisions,signal_rows=[],[],[],[],[],[],[],[]
    trade_differences,portfolio_rows,curves=[],[],{}
    warnings_by_engine={name:set() for name in engines}
    total_started=perf_counter()
    with gzip.open(output/"equity_by_run.csv.gz","wt",encoding="utf-8",newline="") as equity_file:
        import csv
        writer=csv.DictWriter(equity_file,["run_id","engine","original_bar","timestamp","equity"],lineterminator="\n")
        writer.writeheader()
        for period in plan["periods"]:
            for method in methods:
                grouped={(scenario,engine):[] for scenario,_ in scenarios for engine in engines}
                for symbol in plan["symbols"]:
                    prepare_started=perf_counter()
                    bars,start,events=prepare(data[symbol],period,method,trend,breakout,plan["minimum_warmup_bars"])
                    preparation_seconds=perf_counter()-prepare_started
                    case=dict(symbol=symbol,period=period["name"],method=method.key)
                    for e in events:
                        signal_rows.append(dict(**case,line_id=e.line_id,direction=e.direction,
                                                created_index=e.created_index,candidate_index=e.candidate_index,
                                                confirmation_index=e.confirmation_index))
                    for scenario,settings in scenarios:
                        key=dict(**case,scenario=scenario)
                        run_id=":".join(key.values())
                        results={}
                        for name,engine in adapters.items():
                            result,timing=timed_run(engine,bars,events,settings,method.key,plan["timing_repetitions"])
                            results[name]=result
                            summary=dict(run_id=run_id,**key,**result.summary(settings,start),
                                         scored_bars=len(bars)-start,warmup_bars=start,
                                         initial_equity=settings.initial_equity,quantity=settings.quantity,
                                         fee_per_order=settings.fee_per_order)
                            summaries.append(summary)
                            timings.append(dict(run_id=run_id,**key,engine=name,preparation_seconds=preparation_seconds,**timing))
                            audits.append(dict(run_id=run_id,**audit_accounting(bars,result,settings,start)))
                            warnings_by_engine[name].update(result.warnings)
                            for t in result.trades:
                                ledgers.append(dict(run_id=run_id,**key,engine=name,**t))
                            for decision in result.decisions:
                                decisions.append(dict(run_id=run_id,engine=name,decision=decision))
                            rows=[dict(timestamp=b.timestamp.isoformat(),equity=value)
                                  for b,value in zip(bars[start:],result.equity[start:])]
                            grouped[(scenario,name)].append(rows)
                            writer.writerows(dict(run_id=run_id,engine=name,original_bar=i+1,
                                                  timestamp=bars[i].timestamp.isoformat(),equity=result.equity[i])
                                             for i in range(start,len(bars)))
                            if (symbol in plan.get("prefix_audit_symbols",[]) and scenario==scenarios[0][0]):
                                prefixes.append(dict(symbol=symbol,**prefix_check(bars,start,period,method,trend,breakout,
                                                                                 engine,settings,result)))
                        if len(results)==2:
                            reconciliation=reconcile(results["application"],results["backtesting_py"],bars)
                            gaps=reconciliation.pop("target_gaps")
                            comparisons.append(dict(run_id=run_id,**key,**reconciliation))
                            trade_differences.extend(dict(run_id=run_id,**key,exit_at=bars[g["exit_index"]].timestamp.isoformat(),**g)
                                                     for g in gaps)
                for (scenario,name),stock_curves in grouped.items():
                    dates=[r["timestamp"] for r in stock_curves[0]]
                    if any([r["timestamp"] for r in curve]!=dates for curve in stock_curves):
                        raise ValueError("Stock calendars differ; refusing to fill missing prices")
                    settings=dict(scenarios)[scenario]
                    initial=settings.initial_equity*len(stock_curves)
                    rows=[dict(timestamp=t,equity=sum(curve[i]["equity"] for curve in stock_curves))
                          for i,t in enumerate(dates)]
                    for r in rows: r["net_pnl"]=r["equity"]-initial
                    curves[(period["name"],method.key,scenario,name)]=rows
                    group=[s for s in summaries if s["period"]==period["name"] and s["method"]==method.key and s["scenario"]==scenario and s["engine"]==name]
                    portfolio_rows.append(dict(period=period["name"],method=method.key,scenario=scenario,engine=name,
                                               initial_equity=initial,net_pnl=rows[-1]["net_pnl"],
                                               filled_trades=sum(s["filled_trades"] for s in group),
                                               closed_trades=sum(s["closed_trades"] for s in group),
                                               open_trades=sum(s["open_trades"] for s in group),
                                               max_drawdown_percent=maximum_drawdown([r["equity"] for r in rows],initial)))
                print(f"Completed {period['name']} / {method.key}",flush=True)
    for filename,rows in (("summary.csv",summaries),("comparisons.csv",comparisons),("timing.csv",timings),
                          ("trades.csv",ledgers),("target_gap_differences.csv",trade_differences),
                          ("portfolio_summary.csv",portfolio_rows),("confirmed_events.csv",signal_rows)):
        write_csv(output/filename,rows)
    write_csv(output/"portfolio_equity.csv",[dict(period=p,method=m,scenario=s,engine=e,**r)
                                            for (p,m,s,e),rows in curves.items() for r in rows])
    with gzip.open(output/"decisions.json.gz","wt",encoding="utf-8") as f:
        json.dump(decisions,f)
    validation=dict(accounting_audits=audits,prefix_audits=prefixes,
                    all_accounting_passed=all(x["passed"] for x in audits),
                    all_comparisons_reconciled=all(x["reconciled"] for x in comparisons) if comparisons else None,
                    matched_cases=len(comparisons),audit_runs=len(audits),
                    maximum_accounting_error=max(x["maximum_error"] for x in audits),
                    maximum_policy_adjusted_equity_error=max((x["maximum_policy_adjusted_equity_difference"] for x in comparisons),default=None))
    (output/"validation.json").write_text(json.dumps(validation,indent=2)+"\n")
    plot_comparison(output,summaries,comparisons,timings,curves)
    metadata.update(status="completed",completed_utc=datetime.now(timezone.utc).isoformat(),
                    wall_seconds=perf_counter()-total_started,engine_runs=len(summaries),matched_cases=len(comparisons),
                    warnings={k:sorted(v) for k,v in warnings_by_engine.items()},
                    output_sha256={p.name:digest(p) for p in sorted(output.iterdir()) if p.is_file() and p!=meta_path})
    meta_path.write_text(json.dumps(metadata,indent=2)+"\n")
    return validation


def main():
    """Expose optional engines without changing any existing application's command."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan",type=Path,default=ROOT/"engine_comparison_plan.json")
    parser.add_argument("--output",type=Path,default=ROOT/"engine_comparison_results/latest")
    parser.add_argument("--input",type=Path,help="Use one existing CSV/JSON instead of the large-data plan")
    parser.add_argument("--engines",nargs="+",choices=["application","backtesting_py"],default=["application","backtesting_py"])
    parser.add_argument("--repetitions",type=int,help="Override repeat count for adapter timing")
    parser.add_argument("--overwrite",action="store_true")
    args=parser.parse_args()
    try:
        validation=run(args.plan,args.output,args.engines,args.input,args.repetitions,args.overwrite)
    except (ValueError,RuntimeError,FileNotFoundError) as exc:
        parser.exit(2,str(exc)+"\n")
    print("Results:",args.output.resolve())
    if validation["all_comparisons_reconciled"] is False:
        parser.exit(1,"Unexplained differences exported; inspect comparisons.csv before accepting results.\n")


if __name__=="__main__":
    main()
