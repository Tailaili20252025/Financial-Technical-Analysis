# Step 1–2 alternatives: percentage and ATR reversal

This addition compares the two swing-point alternatives from the earlier report
with traditional TA. It uses the application's existing execution engine.

## What already existed and what this adds

The supplied main already contains `PercentageReversalMethod`,
`ATRReversalMethod` and `ProminenceMethod` in `swingpoints/methods.py`, with their
algorithms in `swingpoints/alternative_algorithms.py`. CLI and GUI use that same
registry. Those algorithms are reused, not copied or replaced.

This addition supplies `compare_swing_methods.py`, a focused configuration,
`swingpoints/swing_comparison.py`, integration tests, diagnostics, paired P/L
comparisons, figures and a report. The selected alternatives are percentage and
ATR reversal. Prominence remains available in the main application.

The common workflow is: load OHLC data → choose the swing strategy → construct
and validate trendline candidates → confirm breakouts/breakdowns → execute
trades → calculate realized and unrealized P/L. Only the swing strategy changes
between comparison arms. All candidate lines feed the shared Step 4 rules;
the small display subset is never used to select historical trades.

## Run

Apply this addition and the earlier backtesting package to the supplied main.
The corrected combined ZIP already contains both additions. Use the existing
virtual environment in `swingpoints_project`:

```bash
python -m pip install -r requirements.txt
python compare_swing_methods.py --output swing_method_results/my_run
python -m unittest discover -s tests -v
```

No optional backtesting framework dependency is required. Choose an empty output
folder for each run. Edit the `methods[].attributes` values in
`swing_comparison_plan.json` to try different thresholds while preserving the
same common trading rules. These map directly to `TASettings`,
`PercentageSettings` and `ATRSettings` class attributes.

Existing single-data commands also work:

```bash
python app.py data/data.csv --method percentage --reversal-percent 5 --output output/percentage
python app.py data/data.csv --method atr --swing-atr-period 14 --atr-multiplier 2 --output output/atr
python app.py --gui
```

In the existing GUI, choose `percentage` or `atr` in **Swing method** and edit
its attributes under **Method settings**. The supplied main's GUI displays
Steps 1–4; the complete Steps 1–6 comparison and trade accounting run through
the new command and the backtesting module. This addition does not add GUI
trade controls.

## Rules and units

- TA: a strict Close maximum/minimum over two observed bars on either side;
  the event becomes known two bars after its pivot.
- Percentage: a 5% opposite Close move confirms the running extreme. An
  unfinished final extreme is not emitted. The threshold is relative to the
  pivot price, not a 5-unit price move.
- ATR: use a 14-bar Wilder Average True Range and a reversal of two times the
  ATR frozen at the candidate extreme. Only a strictly new extreme refreshes
  this threshold. A later volatility spike cannot retroactively change it.
- Step 3: shared candidate construction/validation, 0.5% tolerance and a
  lookback of 20 same-kind swings. This is not regression or an ML trendline.
- Step 4: two consecutive closes for confirmation and five bars of observation.
- Steps 5–6: next-Open entry, one share, long/short, 10,000 initial units per
  stock/block; fixed stop distance of two signal-time ATR(14), target at 2R.
  Here R is the entry-to-stop distance. The trading ATR and the swing ATR are
  separate settings, although their default periods happen to be equal.

The 20 stocks contain 25,180 daily records from February 2013 to February 2018.
Test blocks are 2014, 2015, 2016 and January 2017 to 7 February 2018. Preceding
history warms the detector and indicators; accounts start flat each block.
Parameters are fixed, not fitted to test outcomes. This is a historical
comparison, not an untouched final holdout or proof of live profitability.

Costs are zero, base (5 bps adverse slippage per fill, 0.10 per order, 3% annual
short borrow), and stress (10 bps, 0.50, 6%). One basis point is 0.01%.
Open positions are marked at cutoff rather than force-liquidated.

## Outputs and interpretation

`swing_method_results/research_run/` contains the completed experiment:

- `method_totals.csv`: P/L, trade counts, weighted swing delay and detector time.
- `paired_pnl_vs_ta.csv`: alternative-minus-TA differences for matching stock,
  test block and cost scenario (480 pairs).
- `detection_metrics.csv` and `confirmed_swings.csv`: confirmation counts,
  pivot/availability times and reversal-threshold evidence.
- `swing_prefix_checks.json`: 720 checks that later data do not revise already
  confirmed swings, including checks of ATR and threshold metadata.
- `swing_and_trendline_comparison.png`: the same AAPL observations plotted for
  all three methods. X marks show confirmation time at the pivot's price;
  displayed lines are the final-cutoff subset, not historical trade selectors.
- `detection_comparison.png`: event count, confirmation delay and detector time.
- `backtest/`: 720 backtest records, trade/equity ledgers, cost and equity
  figures, arithmetic audits and 12 trade-prefix checks.

At base costs, total marked P/L across the independent blocks is −61.62 for TA,
−227.31 for percentage and −317.65 for ATR, in input price units. The matching
one-share buy-and-hold sum is +2,267.94. These totals are not compounded returns.
Percentage and ATR produce 635 and 1,149 confirmed swings versus TA's 5,748,
with average delays of 10.17, 6.14 and 2.00 observed bars respectively.

The alternatives are sparser and their detector implementations ran faster in
this environment. That does not improve the base-cost aggregate P/L. At stress
costs they lose less than TA, but all three remain negative. The code functions
correctly; these fixed strategies have not established a profitable advantage.
One-share sizing leaves most capital idle, making account drawdowns small.

## Validation and merge scope

All 156 tests pass after combining main, backtesting and this addition: 147
existing/backtesting tests plus nine new comparison tests. All 720 arithmetic
audits pass (maximum equity error below 0.00000001 units), and all 720 new runs
exactly match the earlier backtest for their corresponding settings.

All delivered files are additions relative to the supplied main. The
alternatives-only ZIP has no path overlap with the 44-file backtesting package.
The corrected combined ZIP contains both. No Backtesting.py adapter is needed.
If the earlier engine comparison was uploaded, follow
`REPLACE_ENGINE_COMPARISON.md` to remove those unrelated files.
