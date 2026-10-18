# Compare Step 1–2 swing alternatives with traditional TA

Connect the existing percentage-reversal and ATR-reversal strategies to a
reproducible comparison through the shared trendline, breakout and trade stages.

- Reuse the SwingMethod interface and the same Steps 3–6 settings and execution engine.
- Compare swing counts, confirmation delay, detector runtime and net P/L on
  25,180 daily records across 20 stocks and three cost scenarios.
- Add a configurable CLI, paired comparison tables, figures and an analysis report.

Validation: all 156 tests pass with the backtesting additions applied. The 720
backtests pass independent accounting audits; 720 swing-prefix checks pass.

Results: the alternatives produce fewer, later-confirmed swings. Neither
improves aggregate base-cost P/L over TA; all three lose money at base costs.

The algorithms were already present in main. This PR adds their focused
integration comparison and verification. It depends on the separate backtesting
additions; the corrected combined package includes those files as well.
