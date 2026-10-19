## Summary

Extend the unified application's confirmed Step 4 line events into simulated
trade entries and fixed stop-loss/take-profit exits, with realised and unrealised
profit/loss displayed in CLI output, Tkinter tables and Matplotlib charts.

- Breakout → Buy/long; breakdown → Sell/short. Default fills use the confirmation
  Close as the supplied slides' idealised assumption; optional next-Open execution
  follows the report. Both retain separate candidate, confirmation and fill timing.
- Freeze ATR-based stops and reward/risk targets at entry. Model gap stops,
  conservative stop-first ambiguous bars, fees, slippage and configurable borrow costs.
- Share one trading engine across all four swing strategies. Preserve Steps 1–4
  and the eight existing indicators. Add no dependencies.
- Add trade/equity charts, trade and entry-decision tables, GUI settings, replay-safe
  snapshots and eight new output files, plus trading metadata in run_summary.json.
- Include results on unchanged data/data.csv, method comparisons and the complete
  test log. See STEP56_RESULTS.md for measured results and STEP56.md for assumptions.

## Validation

Run `python -m unittest discover -s tests -v` from `swingpoints_project`.
Tests cover signed P/L, fixed levels, costs, gaps, execution timing, final-bar
signals, duplicate/conflicting confirmations, warm-up, open-position marking,
export protection and historical-prefix consistency across the four methods.
Existing swing, trendline, breakout and indicator tests remain in the suite.

GUI callbacks are tested with mock widgets; interactive desktop rendering remains
a local check with `python app.py data/data.csv --gui`.

## Interpretation

These are historical simulations, not live orders or evidence of future returns.
Default same-Close fills and zero costs are explicitly recorded. No end-of-data
exit is invented, and later false-break outcomes do not erase earlier fills.
