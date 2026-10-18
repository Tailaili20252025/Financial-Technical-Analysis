# Integrate Backtesting.py and compare execution performance

Adds an optional Backtesting.py adapter that independently executes the existing
four swing methods' confirmed breakout signals. Includes a separate CLI,
configuration, trade/equity exports, comparison figures and a results report.

- Compare both engines on 25,180 daily records across 20 stocks and four periods.
- Match next-Open entries, ATR exits, position sizing and commission scenarios.
- Reconcile native target-gap fill differences and measure adapter runtime.
- Keep all additions separate from the earlier backtesting PR; no existing files
  are modified and there are no overlapping added paths.

**Validation:** All 177 tests pass after both PRs are applied, including 30 new
tests. All 640 paired cases reconcile; 32 real-data prefix checks pass.

**Results:** Raw P/L differences are explained by favourable target-gap fills.
The application adapter is faster in this measurement. Changing the execution
engine does not establish a new profitable strategy.

**Dependency:** The full comparison uses `trading.py` and `data/backtest/` from
the earlier backtesting PR. The alternative alone runs on `data/data.csv` before
that PR is merged. Install `requirements-engines.txt` for the optional framework.
