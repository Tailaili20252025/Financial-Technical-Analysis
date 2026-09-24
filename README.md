## Added: SMA, EMA, RSI, MACD, ATR, VWAP, ROC and CCI

This incremental update keeps the existing Steps 1–3. Run the same command to also
produce `indicators.png` and `indicators.csv/json`. Original `data.csv` has no
volume, so VWAP is explicitly unavailable for this input. See [swingpoints_project/INDICATORS.md](swingpoints_project/INDICATORS.md)
for settings, formulas, results and GUI instructions. Each run now saves nine files;
older examples below remain historical Step 1–3 examples.

# Financial Technical Analysis

Python application implementing Steps 1–3: read CSV/JSON stock prices, plot
Close/High/Low, identify confirmed swing points, and identify/plot rising support
and falling resistance trendlines.

- [Install and run](swingpoints_project/README.md)
- [Step 3 rules, formulas, settings and examples](swingpoints_project/STEP3.md)
- [中文运行与算法说明](swingpoints_project/STEP3_ZH.md)
- [Validation and tests](swingpoints_project/TESTING.md)

Run all commands from `swingpoints_project`, the folder containing `app.py`.
This milestone performs deterministic analysis; it does not train a prediction model.
