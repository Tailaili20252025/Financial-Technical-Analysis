# Verification record

## Automated execution

Environment: Python 3.12.14, Matplotlib 3.10.8, headless rendering (Agg).
Command: `python -m unittest discover -s tests -v`.
Result: **15 tests passed**.

Coverage includes:

1. Known price sequence with hand-checked high/low prices and confirmation bars.
2. Window 2 does not identify a pivot until both later bars have arrived.
3. Every prefix of the supplied 374-row dataset agrees with events available
   by its cutoff, for both Close and High/Low detection (748 prefix comparisons).
4. Changing future bars cannot alter previously emitted events.
5. Constant, monotonic and tied-peak cases return no strict extrema.
6. Short inputs return no swings without a crash.
7. Outside-bar ambiguity is retained explicitly in High/Low mode.
8. Invalid detector settings and nonchronological streaming input are rejected.
9. Supplied CSV and generated JSON load into identical 374 bars.
10. ISO timestamps, JSON wrapper, case-insensitive fields and sorting work.
11. Empty data, duplicate times, bad numbers/dates, OHLC violations and mixed
    timezone conventions are rejected.
12. BOM/semicolon CSV works; duplicate column names are rejected.
13. CLI reads both formats and exports equivalent causal results at cutoff 100.
14. Invalid CLI window/cutoff gives a useful error without a traceback.
15. Export paths cannot overwrite the source input.

Full CLI runs were also executed for Close/window 2, High-Low/window 5, and
Close/window 2/cutoff 100. Their PNG charts and CSV/JSON results are in `examples/`.
Rendered charts were visually checked for line/marker visibility and layout.

## Desktop checks to perform on a computer with a display

The current execution environment has no display, so these checks are not
claimed as completed:

- Run `python app.py --gui data/data.csv`; verify the chart and table appear.
- Open the JSON file; verify the same point counts under the same settings.
- Set observed bars to 100 and apply; verify the table has 25 total swings.
- Advance one bar; check only currently available events appear.
- Change window/basis, apply and verify chart/table refresh together.
- Try invalid window or observed-bar values; verify a readable error.
- Export results; compare the image and table with the currently displayed run.
- Cancel file/folder selection; verify the current view stays intact.

No model fitting or forecasting results are claimed: this task implements
descriptive Steps 1-2 only.
