# Replace the earlier engine-comparison addition

The requested alternatives are Step 1–2 swing-point methods. The earlier
Backtesting.py engine comparison addressed a different task. This corrected
package contains the backtesting work and the percentage/ATR swing comparison.

Uploading a ZIP's extracted files does not delete files already on GitHub.
If the earlier engine-comparison addition was uploaded, remove only these
paths under `swingpoints_project` in the branch being corrected:

```
compare_engines.py
engine_comparison_plan.json
requirements-engines.txt
ENGINE_INTEGRATION.md
ENGINE_INTEGRATION_PR_DESCRIPTION.md
ENGINE_INTEGRATION_TEST_RESULTS.json
ENGINE_INTEGRATION_FILES.json
swingpoints/engine_adapters/
tests/test_engine_adapters.py
engine_comparison_results/
reports/Alternative_Engine_Integration_Report.docx
```

Keep the original application and all files from the separate backtesting
package, including `backtest.py`, `swingpoints/backtesting.py`,
`swingpoints/trading.py`, `data/backtest/` and `backtest_results/`.

Upload the corrected package at the repository root, keeping exactly one
`swingpoints_project` level. If the branch already has an open PR, committing
the corrections on the same branch updates that PR. Use
`SWING_COMPARISON_PR_DESCRIPTION.md` to explain the swing-method comparison.

For a single PR containing both parts, a suitable title is:

**Add backtesting and compare percentage and ATR swing methods**

Suggested body:

Adds chronological backtesting and a focused comparison of the existing
percentage and ATR swing methods against traditional TA. All three share the
same trendline, breakout, entry and exit rules. Includes 20-stock data,
P/L and cost analysis, comparison figures, reports and tests. All 156 tests
pass; 720 backtests and 720 swing-prefix checks pass. Neither alternative
improves aggregate base-cost P/L over TA in this experiment.
