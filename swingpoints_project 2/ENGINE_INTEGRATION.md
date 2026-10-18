# Independent execution engine comparison

This addition integrates **Backtesting.py 0.6.5**, the first independent-check
alternative recommended in the backtesting research report. The existing four
swing methods, shared trendlines and Step 4 confirmation rules still generate
signals. Backtesting.py owns its own orders, fills, positions and account equity.
The application's `trading.py` remains the reference implementation.

## Separate PR and merge compatibility

Every file in this package is new relative to the supplied
`Financial-Technical-Analysis-main (1).zip`. It changes no existing app, GUI,
indicator, swing, trendline or breakout file. Its paths do not overlap the
earlier `Backtesting_Changes_Only.zip`, so either PR can be merged first.

There are two runtime dependencies for the full comparison:

- `swingpoints/trading.py`: the Step 5–6 engine, included in the earlier
  backtesting package because the supplied main snapshot did not contain it.
- `data/backtest/`: the same 20 prepared stock files and source manifest from
  that backtesting package. Data are reused, not duplicated here.

If the integration PR is merged first, the alternative alone can already run
on the original `data/data.csv`. Comparative runs become available after both
PRs are merged. Missing dependencies produce an actionable message; the program
never substitutes a fabricated reference engine or missing Open prices.

## Install and run on macOS

Open Terminal in `swingpoints_project` and use Python 3.10 or later:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-engines.txt
```

If no environment exists yet, first run `python3 -m venv .venv`, then activate it.
The optional requirements file leaves the original requirements unchanged.

Alternative only, using the original project data, before the other PR merges:

```bash
python compare_engines.py --input data/data.csv --engines backtesting_py --output engine_comparison_results/original_data
```

After both PRs are merged, compare both engines on the same original data:

```bash
python compare_engines.py --input data/data.csv --output engine_comparison_results/original_data_comparison
```

Repeat the large-data experiment included in this delivery:

```bash
python compare_engines.py --plan engine_comparison_plan.json --output engine_comparison_results/my_run
open engine_comparison_results/my_run/engine_pnl_comparison.png
open engine_comparison_results/my_run/engine_equity_comparison.png
```

Use a fresh output directory; `--overwrite` is required to replace an existing
run. The full plan uses three repetitions for timing. `--repetitions 1` runs it
once per configuration. The precomputed outputs are in
`engine_comparison_results/research_run/`.

## How the adapter works

`get_engine(name)` returns objects with the same `run(bars, events, settings,
method)` interface. `ApplicationEngine` calls the existing trading simulator.
`BacktestingPyEngine` converts original bars into a pandas DataFrame and wraps
confirmed events in a `Strategy` subclass. Both return `EngineResult`, a common
trade ledger and one equity value per original bar Close.

An adapter translates interfaces so the rest of the application can call an
alternative implementation without duplicating Step 1–4 algorithms. This is the
Adapter pattern with a shared execution-engine protocol. The optional framework
is imported lazily, so the existing GUI works without installing it.

The framework adapter uses **two synthetic phases per original candle**:

1. Open phase: all four synthetic prices equal the current Open. The previous
   Close's pending signal and its already-known ATR determine whether an entry
   can be funded and where the fixed brackets belong.
2. Range/Close phase: Backtesting.py fills the market order at that same original
   Open and processes the original High/Low range through native bracket orders.
   The strategy then receives the new completed Close's confirmed signals.

This represents execution order, not new ticks or twice as much market data.
No original High/Low/Close is exposed in the Open-phase row. Existing protective
orders encounter opening gaps before the later range. No broker internals are
patched. Public strategy/order APIs and the documented `_strategy` and
`_equity_curve` result entries are used. Framework synthetic-frequency Sharpe,
annualization and holding-duration statistics are deliberately not reported.

## Matched experiment and explicit differences

The fixed plan reuses the earlier dataset, symbols, date blocks and class
attributes. It scores 2014, 2015, 2016 and January 2017–7 February 2018, with
earlier observations used only for signal/indicator warm-up. Every stock/block
starts flat with 10,000 input units and trades one whole share. Blocks reset
independently; their summed P/L is not a compounded portfolio return.

Each engine uses confirmed Close signals, next observed Open entries, fixed
2 × ATR(14) stop distance, a 2:1 reward/risk target, and one position at a time.
Opposing simultaneous signals are skipped. New signals while occupied do not
reverse the position. A later false-break label cannot cancel an earlier entry.
Open positions are marked at the cutoff Close with no invented liquidation.

The comparison has **zero** and **fees_only** scenarios. Fees are 0 or 0.10 per
filled entry/exit. Both sides use zero spread, slippage and short-borrow charges.
This isolates execution/accounting behavior; it is not the previous backtest's
5-basis-point/3%-borrow base scenario. Unsupported cost options fail instead of
being silently dropped. The old full-cost backtesting runner remains available.

Both engines use stop-first when the unknown intrabar path reaches both levels.
One intentional difference remains: at a favourable opening gap through the
profit target, the application fills at the target while Backtesting.py uses the
better Open. Raw results preserve this difference. The reconciliation subtracts
only individually verified gap gains in a separate **diagnostic** calculation;
it does not alter framework orders, fees, equity or future decisions.

Execution-engine replacement does not create new predictive signals. Agreement
checks the accounting and execution of shared signals; it cannot independently
validate the swing, trendline, breakout or ATR calculations used by both.

## Outputs

| File | Meaning |
|---|---|
| `summary.csv` | Net marked P/L, realized/open components, trades and drawdown for each engine/run |
| `comparisons.csv` | Matched entry counts, raw P/L difference, explained gap gain and unexplained differences |
| `target_gap_differences.csv` | Every verified target-gap fill difference, with symbol/date/prices |
| `trades.csv` | Both independently filled ledgers, including final open positions |
| `equity_by_run.csv.gz` | Original-bar closing equity; gzip-compressed CSV |
| `portfolio_summary.csv` | Twenty-account totals per method, period, scenario and engine |
| `portfolio_equity.csv` | Daily total equity for the same independent portfolios |
| `confirmed_events.csv` | Shared eligible Step 4 events, not final future failure labels |
| `decisions.json.gz` | Accepted/skipped signal decisions from each engine |
| `timing.csv` | Repeated wall-clock samples and median adapter runtime |
| `validation.json` | Decimal accounting reconciliation and actual-data midpoint-prefix checks |
| `experiment.json` | Applied design, versions, source/code hashes and captured framework warnings |
| `applied_plan.json` | Exact settings frozen for this run |
| `engine_pnl_comparison.png` | Raw engine P/L comparison |
| `engine_differences_and_timing.png` | Explained gap differences and adapter runtime |
| `engine_equity_comparison.png` | TA portfolio equity comparison across the independent blocks |

Trade indices in these research CSVs are **zero-based original bar indices**;
`original_bar` in the equity CSV is one-based. These are not the synthetic phase
indices used internally by the external framework.

## Tests and interpretation

```bash
python -m unittest discover -s tests -p 'test_engine_adapters.py' -v
python -m unittest discover -s tests -v
```

The focused suite checks hand-calculated long/short P/L, entry-bar protection,
opening gaps, stop-first ambiguity, commissions, unfunded entries, occupied
signals, missing Open, final pending signals and future-data invariance. On main
without `trading.py`, only the two reference-specific tests are skipped. Without
the optional dependency, framework tests are explicitly skipped, not passed.

The full experiment independently reconstructs every returned closing-equity
value from each ledger using Decimal arithmetic. Repeated timings must produce
identical trades and equity. AAPL midpoint replays regenerate Steps 1–4 from
shortened input and check that earlier equity/entry decisions do not change.
Unexplained comparison differences give the CLI a nonzero exit status.

Timing is the median of three same-process, same-machine **adapter** runs,
including data conversion and framework result statistics but excluding imports,
Steps 1–4 detection, export and plotting. It is not an engine-only benchmark or
a universal speed claim. No parallel CPU workload was used during measurement.

The archival dataset is selected, not point-in-time, and ends in 2018. Dividends,
liquidity, taxes, true intrabar paths and stock-borrow availability are not
modelled. Neither engine agreement nor favourable simulated P/L establishes
live profitability. Read `reports/Alternative_Engine_Integration_Report.docx`
for the measured results and conclusion.

## GitHub upload

Create a separate integration branch from main. At the repository root, choose
Add file → Upload files and upload the extracted `swingpoints_project` folder
from this changes-only ZIP. Verify that paths begin with a single
`swingpoints_project/`. Use `ENGINE_INTEGRATION_PR_DESCRIPTION.md` as the PR text.
Do not upload the ZIP itself as the source code.

## Sources

- Backtesting.py public API: https://kernc.github.io/backtesting.py/doc/backtesting/backtesting.html
- Backtesting.py 0.6.5 distribution and source: https://pypi.org/project/backtesting/0.6.5/
- Dataset publisher: https://www.kaggle.com/datasets/camnugent/sandp500
- Earlier project report: Backtesting Approaches for the SwingPoints Application,
  section 5, alternative frameworks and integration.
