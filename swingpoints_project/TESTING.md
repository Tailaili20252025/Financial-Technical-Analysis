# Current validation: Steps 1–6

The complete suite passed **137 tests** on Python 3.12.14 / Matplotlib 3.10.8,
including 24 new Step 5–6 tests and the existing 113 tests. See
`STEP56_TEST_RESULTS.txt` for the complete run and `STEP56_RESULTS.md` for data
results. New trading formula/timing tests are in `tests/test_trading.py`.
Existing export assertions now cover 20 files; GUI fixtures include the applied
trading snapshot. New GUI callbacks are exercised with mock widgets and actual
analysis; a local graphical display is still required for a desktop window check.

```bash
python -m unittest discover -s tests -v
python app.py data/data.csv --gui
```

For manual verification: open the trade and equity charts, double-click a trade
row, change the entry timing and apply it, replay a shorter prefix, then export.
Confirm that `trades.csv/json` and the displayed snapshot agree. Input data and
Steps 1–4 algorithms remain unchanged. No additional dependency was added.

The sections below preserve earlier milestone validation records; their smaller
file counts/test totals describe those older versions.

## Step 4 validation

The Step 4 test suite added `tests/test_breakouts.py`. Existing export assertions
include the three new Step 4 files (12 total); GUI tests verify applied settings
and event snapshots. See `STEP4_TEST_RESULTS.txt` and `STEP4_RESULTS.md`.

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


## Indicator extension tests

`tests/test_indicators.py` adds formula fixtures, all 374 observed-prefix checks,
volume handling, warm-up alignment and CLI/export integration. Existing GUI mock
tests now also check indicator rows and export of the applied parameter snapshot.
Run the same `python -m unittest discover -s tests -v` command. The indicator milestone
log is `INDICATOR_TEST_RESULTS.txt`; earlier test totals in this document describe
the original Steps 1–3 version.


## Unified strategy regression

Run `python -m unittest discover -s tests -v`: 95 tests passed in that earlier delivery.
See UNIFIED_METHODS.md and UNIFIED_TEST_RESULTS.txt for baseline provenance,
algorithm-equivalence tests, parameter validation, causal replay and GUI callback
coverage. Desktop rendering on macOS remains a manual check.
