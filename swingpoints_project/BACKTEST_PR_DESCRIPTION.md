# Add chronological backtesting and audited net P/L comparisons

Adds a backtest runner using the existing four swing methods, shared trendline
and breakout detection, and the previously delivered Step 5–6 trading engine
(missing from the supplied snapshot). Includes 25,180 daily records across 20
stocks, a reproducible source adapter, configurable test periods/costs, trade and
equity exports, and comparisons with same-quantity buy-and-hold and cash.

Validation: all 147 tests passed; 960 simulations passed independent P/L
reconciliation across 247,920 equity rows, plus 16 real-data prefix checks.

Results: all four methods have negative summed net P/L across the independent
test blocks at base costs. The report documents costs, open positions, source
limitations and the distinction between correct software and a profitable strategy.
