# Suggested PR title

Add chronological parameter search and expanded stock backtests

# Suggested description

Implement the parameter-selection report on top of the existing unified Steps 1–6 application.

- Expand the historical sample from 20 to 60 stocks (75,540 daily OHLCV rows), with 20 stocks reserved from parameter selection.
- Add a seeded, two-stage search across TA, percentage reversal, ATR reversal and prominence: 192 trials covering swing sensitivity, trendline tolerance, breakout confirmation, stop distance and reward/risk.
- Freeze parameters before later-period evaluations; compare default and tuned settings, buy-and-hold and three cost scenarios.
- Include all trial logs, selected presets, backtest ledgers, four plots, data/code hashes and documented results.
- Add 11 tests; all 191 tests pass. Independently reconcile 2,400 test runs and 603,360 equity observations; verify selected-preset compatibility with the existing application and backtest CLI.

The final selected policy lost 46.94 input-currency units on the 20 reserved stocks, compared with a 164.96 loss for default TA. It did not beat buy-and-hold and did not consistently improve other test periods. Existing application and GUI defaults remain unchanged.
