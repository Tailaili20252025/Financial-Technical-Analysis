# Parameter selection for SwingPoints

This addition implements the parameter-selection research using the existing unified application. It adds a reproducible, bounded search, more historical stock data, later-period evaluations, plots and an optional application preset. Steps 1–6, the four swing algorithms, indicators and the Tkinter interface retain their existing implementations and defaults.

The delivered results are in [parameter_results/reference/RESULTS.md](parameter_results/reference/RESULTS.md). **The search ran successfully, but the selected parameters did not consistently improve later-period profit. They are research presets, not replacement defaults.**

## Run it

Open a terminal in your existing `swingpoints_project` folder. Use the same Python environment as the application; no additional packages are required beyond `requirements.txt`.

```bash
source .venv/bin/activate
python optimize_parameters.py --plan parameter_search_plan.json --output parameter_results/my_search --workers 4
```

If an environment has not been created yet:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Use `--workers 1` if parallel processes are inconvenient. The selection is deterministic for the same plan, input files and code, regardless of worker count. Existing output folders must be empty; choose another name to keep earlier results. Runtime depends on the machine; the supplied full run took about two minutes in the verification environment.

To reproduce the selected final policy with the **existing** backtest entry point:

```bash
python backtest.py --plan parameter_results/reference/selected_backtest_plan.json --output backtest_results/selected_replay
```

To apply the preset to the regular application and export its Steps 1–6 figures, indicators and trade outputs:

```bash
python run_selected_parameters.py data/data.csv --preset parameter_results/reference/selected_application.json --output output/selected_demo
```

This last command is an application demonstration on `data.csv`, not a new out-of-sample test. The supplied search uses daily equity histories; its settings are not validated for the original minute-frequency example. The wrapper refuses to overwrite an existing result folder and copies the applied preset into the new output.

The existing GUI still opens with `python app.py --gui`. Optimization is a separate terminal experiment; it does not add an optimizer button or silently load its settings into the GUI. The selected class attributes are recorded explicitly in `selected_application.json` and can be entered into the existing controls.

## Data added

The new `data/parameter_search/` folder contains **60 stocks × 1,259 daily observations = 75,540 rows**, covering 8 February 2013 to 7 February 2018. It preserves the previous 20 stocks and adds 40 histories: **50,360 additional rows**. The original `data.csv` and `data/backtest/` are untouched.

Forty stocks form the development cohort. Twenty additional stocks are excluded from parameter selection and used only for the final 2017 comparison. The lists were fixed using coverage and sector variety before calculating search performance. They are in the plan and source manifest. All selected stocks have the same observed session calendar; no prices or missing sessions are filled.

The source is Cam Nugent's archived S&P 500 dataset on Kaggle, with IEX identified in its original download script. The archive is pinned by the SHA256 of `all_stocks_5yr.csv`:

`6aea253cd19de60b568143991aaf1fa482456565c389205658d236e595e716cf`

Only the date column name and file organization change: `date` becomes `timestamp`, and `Name` is split into separate stock files. Open, high, low, close and volume values are preserved. The source manifest records each normalized file hash, row count, dates, exclusions and limitations. To rebuild the already-included data:

```bash
python prepare_parameter_data.py --source-zip /path/to/sandp500.zip
```

Alternatively use `--source-csv /path/to/all_stocks_5yr.csv`, or omit both to download the pinned snapshot. A changed source hash fails explicitly. This expands stock coverage, **not the date range**. The static constituent sample has survivorship and selection limitations; corporate-action treatment, delisting returns, dividends and short availability are not independently reconstructed.

## Search design

The implementation uses a small swing grid followed by seeded random sampling of joint execution parameters. This avoids an exhaustive grid while keeping the budget and every trial inspectable. It is a search for the best **tested validation configuration**, not a proof of a global optimum. No ML model is trained.

### Stage 1: swing sensitivity

| Existing method | Class attribute varied | Values | Other swing settings |
| --- | --- | --- | --- |
| Traditional TA | `TASettings.window` | 2, 3, 5, 8 | Close basis |
| Percentage reversal | `PercentageSettings.reversal_percent` | 2, 3, 5, 8 | Values are percentages |
| ATR reversal | `ATRSettings.atr_multiplier` | 1, 1.5, 2, 3 | ATR period 14 |
| Local prominence | `ProminenceSettings.min_prominence_percent` | 1, 2, 3, 5 | Radius 5; minimum distance 3 |

There are 16 initial configurations, four per method. Each uses the existing common Step 3 candidate-construction/validation algorithm, Step 4 breakout detection and Steps 5–6 trade engine. Trend and trading settings stay at the backtest defaults in this stage.

### Stage 2: joint parameters

Retain the best eligible Stage 1 swing setting for each method. If a method has no eligible Stage 1 setting, its best completed setting is an explicitly recorded exploration seed; it still has to pass the final constraints to qualify.

| Class attribute | Meaning | Values |
| --- | --- | --- |
| `TrendSettings.tolerance_percent` | Price band as a percentage of the trendline's first anchor price | 0.25, 0.5, 1 |
| `BreakoutSettings.confirmation_bars` | Consecutive closes beyond the directional threshold, candidate included | 1, 2, 3 |
| `TradeSettings.atr_stop_multiple` | Initial stop distance in units of ATR known at the signal | 1, 1.5, 2, 3 |
| `TradeSettings.reward_risk_multiple` | Target distance divided by the initial stop distance | 1, 1.5, 2, 3 |

For each method, sample 20 distinct joint configurations without replacement from the 144 combinations, excluding configurations already evaluated in Stage 1. The declared seed is `20261022`; a stable seed derived from the round and method makes ordering reproducible. That gives **96 trials per round and 192 in the two-round experiment**. Prominence has the same 24-trial budget as the other methods.

Lookback stays at 20, observation window at 5, trade ATR period at 14, quantity at one share, and capital at 10,000 units per stock. Long and short entries remain enabled. EMA filtering and optional false/opposite-break exits remain disabled. SMA, EMA, RSI, MACD, ATR, VWAP, ROC and CCI calculations are unchanged. Display-only minimum touches and line-count settings are not optimization variables. This bounded implementation does not search every range listed in the research report.

### Chronological selection and evaluation

| Round | Inner validation used to select parameters | Frozen outer evaluation |
| --- | --- | --- |
| `wf2016` | Four half-years: 2014 H1 through 2015 H2, 40 stocks | Calendar 2016, same 40 stocks |
| `wf2017` | Six half-years: 2014 H1 through 2016 H2, 40 stocks | Calendar 2017, same 40 stocks; then 20 reserved stocks |

Every validation and test block begins flat with fresh capital. All earlier observations warm up detection and indicators, with at least 200 bars required. Only confirmations inside the evaluated block can open positions; a final-bar confirmation stays pending because the next Open is unknown. Price history is cut at each block's end. Positions still open at that cutoff are marked to its Close, not closed using later prices or silently liquidated.

All selections are saved to disk before any outer-test performance is evaluated. The held-out cohort is loaded by the optimizer only after these decisions are frozen. Its earlier history is permitted for indicator warm-up during evaluation, not for parameter selection. The 2016 outer period becomes earlier validation history for the next scheduled round, as in an expanding walk-forward procedure. There is no random shuffling of bars.

These same historical years have appeared in earlier project work. Consequently the evaluation is procedurally separated within this run but remains **exploratory historical research**, not a pristine future-market validation. Repeatedly changing the plan after seeing its test results would invalidate that separation.

### Objective and eligibility

For each stock, net marked profit/loss is realized net P/L plus unrealized net P/L at the cutoff. Slippage is embedded in fills; commissions and short borrow are deducted. For a block with M stocks and starting capital E per stock:

`block return (%) = 100 × sum(stock net marked P/L) / (M × E)`

The selection score is the **median block return** across the equal-length half-year validation blocks. It is not annualized. Before ranking, require at least three blocks, at least 50 closed trades in total, at least 10 closed trades in every block, and no block portfolio drawdown above 5%. Drawdown is the largest percentage decline of summed portfolio equity from its prior peak, including starting capital. These thresholds were fixed before the search.

Ties use lower worst-block drawdown, then higher summed block P/L, then a stable configuration ID. Failed trials are recorded and excluded. A method without any eligible trial explicitly falls back to its default; if none qualify globally, the policy falls back to default TA. Eligibility establishes sufficient observations and a risk bound; it **does not require or imply positive profit**. The 5% limit is relatively loose when only one share is traded per 10,000-unit account.

### Execution and costs

Signals are acted on at the next observed Open. Existing fixed ATR stops, fixed targets, gap handling and conservative stop-first treatment when both levels are touched in one bar are retained. Borrow uses elapsed calendar time. Each stock has its own funded account and at most one open position. Buy-and-hold buys the same one share at the first test Open and marks it at the final Close, with matching entry costs and no invented exit fee.

| Scenario | Market-fill slippage | Fee per order | Annual short-borrow rate |
| --- | ---: | ---: | ---: |
| Zero | 0 basis points | 0 | 0% |
| Base — selection objective | 5 basis points | 0.10 | 3% |
| Stress | 10 basis points | 0.50 | 6% |

One basis point equals 0.01%. Stress results re-run the trade engine; costs are not simply subtracted from a previously fixed total. The existing target-limit fill assumptions still apply. Idle capital earns no interest; there is no dividend, tax, FX, market-impact or short-locate model. Equal shares do not mean equal dollar exposure, and the buy-and-hold benchmark is not a fully invested portfolio.

## Code and output map

| File | Responsibility |
| --- | --- |
| `parameter_search_plan.json` | Cohorts, periods, class-attribute ranges, seed, trial budget, constraints and costs |
| `swingpoints/parameter_selection.py` | Validated configurations, trial generation, robust ranking, reusable stock/block evaluation |
| `optimize_parameters.py` | Two-stage search, frozen tests, exports, accounting audits and plots |
| `prepare_parameter_data.py` | Reproducible extraction and validation of the expanded dataset |
| `run_selected_parameters.py` | Apply the saved preset through the normal shared application pipeline |
| `tests/test_parameter_selection.py` | Scoring, temporal isolation, held-out isolation, deterministic execution, manifest and export checks |

Within `parameter_results/reference/`:

| Output | How to use it |
| --- | --- |
| `RESULTS.md` | Interpretation of the actual search, figures and later tests |
| `applied_plan.json`, `experiment.json` | Frozen design, input/code hashes, source provenance and completion status |
| `trials.jsonl`, `trial_summary.csv` | All 192 configurations, scores, constraints, stages and failures |
| `validation_blocks.csv`, `validation_by_stock.csv.gz` | Every validation portfolio and stock metric; failed trials stay in the trial log |
| `selection_wf2016.json`, `selection_wf2017.json`, `frozen_selections.json` | Stage 1 parents, per-method winners and global policy, frozen before testing |
| `test_portfolios.csv`, `test_by_stock.csv`, `test_trades.csv` | Later-period performance and detailed trades for each arm and cost scenario |
| `test_portfolio_equity.csv` | Daily portfolio paths used in the figures |
| `validation.json` | Independent arithmetic and prefix-invariance audit results |
| `selected_backtest_plan.json` | Final selected policy in the existing `backtest.py` format |
| `selected_application.json` | Final selected class attributes for the normal application wrapper |
| Four PNG figures | Search scores, test comparisons, equity paths and cost sensitivity |

The selection wrapper caches identical detection settings only within one stock/block job, so changing swing attributes, trendline tolerance or confirmation invalidates the cache. Stop/target changes reuse Steps 1–4 events but rerun trade simulation. Workers never rank trials; the coordinator sorts and selects deterministically. No precomputed outer-test result is used to generate candidates.

## Verification and limitations

Run `python -m unittest discover -s tests -v`. New tests check manually calculated scores, eligibility, ties, duplicate prevention, seed reproducibility, disjoint cohorts, chronological boundaries, source hashes, explicit failures, exported plans and overwrite protection. An end-to-end test changes future evaluation prices and held-out stock prices, runs with one and two workers, and confirms that validation trials and selected configurations remain identical.

Every real outer stock/configuration/cost evaluation has its ledger independently rebuilt with Decimal arithmetic. Selected stocks also replay shorter prefixes to verify that adding later bars does not change already-observed confirmations or equity. This checks accounting and causality; it does not certify realistic execution or statistical significance.

The first stage can discard swing settings that would work better with a different second-stage combination. The random sample covers only part of the joint grid. There is no claim of a global optimum, no nested ML training, and no implemented probability-of-backtest-overfitting or deflated-Sharpe test. The result should guide a separately predeclared future experiment, not justify more tuning on the same final test.

## Sources

1. Cam Nugent, *S&P 500 stock data*, archived public OHLCV data and original download code. https://www.kaggle.com/datasets/camnugent/sandp500
2. Bergstra, J. and Bengio, Y. (2012), *Random Search for Hyper-Parameter Optimization*, JMLR 13, 281–305. Supports the use of a fixed random-search budget; it does not establish profitability of financial strategies. https://jmlr.org/papers/v13/bergstra12a.html
3. scikit-learn, *Cross-validation: evaluating estimator performance*. Temporal ordering and separating tuning from assessment inform this wrapper; it does not depend on scikit-learn. https://scikit-learn.org/stable/modules/cross_validation.html
4. scikit-learn, *Nested versus non-nested cross-validation*. Motivation for separate selection and evaluation, implemented here with chronological blocks rather than random folds. https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html
