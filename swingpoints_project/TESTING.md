# Validation: Steps 1–3

Run from `swingpoints_project`:

```bash
python -m unittest discover -s tests -v
```

## Executed results

The full suite passed **34 tests**: 15 existing Step 1–2 tests and 19 new Step 3
tests. Environment: Python 3.12.14, Matplotlib 3.10.8, noninteractive Agg rendering.
The suite uses standard-library unittest; no new test dependency is needed.

Existing tests still cover known swings, confirmation delays, all 374 swing
prefixes in both bases, invalid records, CSV/JSON equality and CLI exports.
New tests cover:

- Hand-calculated rising lows and falling highs, slope, confirmation and touches.
- Equal anchors, monotonic/flat prices and insufficient history.
- Crossings between anchors and during second-anchor confirmation delay.
- First-break timing and exclusion of touches only confirmed at/after the break.
- Exact tolerance boundaries, approximate touches and floating-point handling.
- Actual elapsed-time slopes across timestamp gaps.
- Different Close and High/Low crossing behavior.
- **All 374 historical prefixes in both bases**: full-run candidates, filtered
  by creation time with touch/break state truncated to the cutoff, equal a fresh
  prefix-only computation. This is stronger than checking the final chart alone.
- Future events and future-price changes cannot affect the earlier observed run.
- Settings validation, lookback limit, display filtering and overlap suppression.
- Chart dashed/solid segments and observed-history limits.
- Equivalent CSV/JSON trendline exports, six output files and empty output tables.
- Input protection for both newly introduced output filenames.
- Actual GUI refresh/export callbacks with mock widgets and real analysis:
  visible prefix, both tables and export of applied rather than edited settings.

No data-reader or Step 2 swing-detector source code was changed.
All Python functions retain Args, Result and Exception docstrings.

## Sample runs and visual inspection

These commands completed, and the resulting PNG charts were visually inspected:

```bash
python app.py data/data.csv --output examples/step3_close_window2
python app.py data/data.csv --basis high-low --window 5 --output examples/step3_high_low_window5
```

| Run | Bars | Highs | Lows | Accepted candidates | Displayed up/down |
| --- | ---: | ---: | ---: | ---: | --- |
| Close, window 2 | 374 | 49 | 52 | 152 | 3 / 3 |
| High/Low, window 5 | 374 | 18 | 22 | 51 | 3 / 3 |

Counts are descriptive outputs, not predictive accuracy scores.

## Remaining manual desktop checks

The environment has no graphical display. Mock callback tests and shared Agg
rendering passed, but the actual Tk window was not opened or manually clicked.
On the user's computer:

1. Run `python app.py --gui data/data.csv`.
2. Confirm the Close/High/Low chart and green/red lines are visible.
3. Switch between Confirmed swings and Displayed trendlines tables.
4. Change Min touches to 3 and click Apply / replay; check selected lines update.
5. Set Observed bars to 100, Apply, then Next bar; no event may refer to unseen bars.
6. Switch to high-low and Window 5; Apply and inspect the result.
7. Export and check six files. Edit a control without Apply, export again, and
   verify the stored settings still describe the displayed run.
8. Try invalid controls and confirm a readable error dialog appears.

Automated checks establish the specified arithmetic/timing and integration,
not a unique financial definition of a significant trend or future profitability.
