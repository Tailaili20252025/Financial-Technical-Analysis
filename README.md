## Steps 5–6: trade entries and profit/loss

The unified application now runs **Steps 1–6** for all four swing methods.
Confirmed breakout → Buy/long; confirmed breakdown → Sell/short. Fixed ATR stops
and reward/risk targets, trade/equity charts and tables are shared across methods.
Default confirmation-Close fills follow the supplied slides as an idealised model;
`--entry-timing next_open` selects the report's execution convention.

See [Step 5–6 rules and settings](swingpoints_project/STEP56.md),
[Chinese instructions](swingpoints_project/STEP56_ZH.md) and
[results on the original data](swingpoints_project/STEP56_RESULTS.md).
Normal runs write **20 files**. Earlier milestone notes below are historical.

```bash
# Run from swingpoints_project, with the virtual environment active.
python app.py data/data.csv --output output
python app.py data/data.csv --gui
```

## Step 4 update: Breakout and False Breakout

Close-based Step 4 now runs after the shared trendline stage for all four methods.
The Step 4 milestone wrote 12 files, including `breakouts.csv/json` and `breakouts.png`.
See [Step 4 rules, commands and GUI instructions](swingpoints_project/STEP4.md). Earlier nine-file descriptions
and saved unified examples below describe the pre-Step-4 version.

> **Unified swing strategies:** Traditional TA, percentage reversal, ATR reversal
> and local prominence now share one application. See
> [the guide](swingpoints_project/UNIFIED_METHODS.md) and
> [tested comparisons](swingpoints_project/examples/unified_tsla/comparison.csv).

## Added: SMA, EMA, RSI, MACD, ATR, VWAP, ROC and CCI

This incremental update keeps the existing Steps 1–3. Run the same command to also
produce `indicators.png` and `indicators.csv/json`. Original `data.csv` has no
volume, so VWAP is explicitly unavailable for this input. See [swingpoints_project/INDICATORS.md](swingpoints_project/INDICATORS.md)
for settings, formulas, results and GUI instructions. The indicator-only milestone saved nine files;
older examples below remain historical Step 1–3 examples.

# Financial Technical Analysis

Python application implementing Steps 1–6: read CSV/JSON stock prices, plot
Close/High/Low, identify confirmed swing points, and identify/plot rising support
and falling resistance trendlines, confirmed breakouts, simulated entries,
fixed exits and profit/loss.

- [Install and run](swingpoints_project/README.md)
- [Step 3 rules, formulas, settings and examples](swingpoints_project/STEP3.md)
- [中文运行与算法说明](swingpoints_project/STEP3_ZH.md)
- [Validation and tests](swingpoints_project/TESTING.md)

Run all commands from `swingpoints_project`, the folder containing `app.py`.
This milestone performs deterministic analysis; it does not train a prediction model.
