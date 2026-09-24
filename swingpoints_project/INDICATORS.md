# Technical indicators — incremental extension

The existing technical-analysis Steps 1–3 continue to load prices, confirm window-based swings, and construct/validate trendlines. Indicators are calculated alongside that pipeline. No alternative swing method is introduced, and indicator values do not alter pivot or trendline selection.

## Run

From `swingpoints_project`, with the existing environment activated:

```bash
python app.py data/data.csv
python app.py data/data.csv --sma-period 10 --ema-period 10 --rsi-period 7 --output output/custom
python app.py data/data.csv --macd-fast 8 --macd-slow 21 --macd-signal 5
python app.py data/data.csv --gui
python -m unittest discover -s tests -v
```

Use Python 3.10+ and the unchanged `requirements.txt`. First-time setup on macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

All defaults are documented class attributes in `swingpoints/indicators.py`, under `IndicatorSettings`. CLI flags override them. `--until N` calculates both the original analysis and indicators using only the first N observed bars. No later bars are used to seed earlier indicators.

## Formulas and conventions

Here n is a number of observed completed bars, C is Close and TP = (High + Low + Close) / 3. Warm-up entries stay unavailable (CSV blank / JSON null), rather than zero or backward-filled values.

| Indicator | Default | Calculation | First available bar (1-based) |
| --- | --- | --- | --- |
| SMA | 20 | Arithmetic mean of the latest n Close values | 20 |
| EMA | 20 | Seed with the first n-value SMA; then previous EMA + 2/(n+1) × (Close − previous EMA) | 20 |
| RSI | 14 | 100 × smoothed gain / (smoothed gain + smoothed loss); seed from n Close changes, then Wilder smoothing with alpha 1/n | 15 |
| MACD | 12, 26, 9 | Independently seeded EMA(12) − EMA(26); signal is EMA(9) of valid MACD values; histogram is MACD − signal | MACD 26; signal/histogram 34 |
| ATR | 14 | True range = max(High−Low, abs(High−previous Close), abs(Low−previous Close)); first TR = High−Low. SMA seed then Wilder smoothing | 14 |
| VWAP | Calendar-date anchor | Cumulative(TP × actual Volume) / cumulative Volume within the anchor | First positive cumulative volume, provided none is missing |
| ROC | 12 | 100 × (current Close / Close n bars earlier − 1) | 13 |
| CCI | 20 | (TP − trailing mean TP) / (0.015 × mean absolute deviation from that same mean) | 20 |

SMA/EMA/MACD/ATR/VWAP use the input price units; ROC is a percentage; RSI and CCI are dimensionless. For one-minute input, period 20 is 20 observed bars, not necessarily 20 elapsed minutes when gaps exist. ATR smoothing crosses session boundaries and includes overnight gaps. Indicators other than VWAP do not reset daily.

RSI returns 100 for gains without losses, 0 for losses without gains, and 50 when both averages are zero. CCI returns 0 for a constant window. ROC returns null if its reference value is zero (the price loader itself requires positive prices). EMA initialization differs between software packages; SMA seeding is explicit here, including separate MACD fast/slow seeds and a signal seed using only valid MACD values.

## VWAP and the supplied data

**The original data/data.csv has timestamp, open, high, low and close, but no volume column.** Its 374 VWAP entries therefore remain null/blank with `vwap_status=missing_volume`. The plot and run summary state this. The code implements VWAP; the supplied dataset cannot support a numerical VWAP result. No synthetic or equal-weight volume has been added.

The loader now accepts an optional case-insensitive `volume` field in CSV/JSON. It accepts finite nonnegative values, including zero; absent, blank and JSON null values mean missing. Negative, boolean, nonnumeric and infinite volume are rejected. If a volume is missing inside an anchor, VWAP is unavailable from that bar through the rest of that anchor; earlier valid rows remain unchanged. This avoids silently underweighting an incomplete session.

`--vwap-reset session` resets on the calendar date represented by each input timestamp. It does not infer an exchange, trading calendar, overnight session or timezone. Use consistently localized timestamps for this convention. `--vwap-reset cumulative` accumulates across the complete observed prefix. With a mid-session input, VWAP starts at the first supplied bar; it cannot reconstruct earlier trades. A new session can recover from a previous session's missing volume. Zero cumulative volume is separately labelled `zero_cumulative_volume`.

## Application integration

The existing `prices.png` chart stays unchanged. New output files are:

- `indicators.png`: Close with SMA/EMA/available VWAP, plus RSI, MACD/signal/histogram, ATR, ROC and CCI panels.
- `indicators.csv`: One row per observed bar, with bar number, timestamp, Close, ten numeric columns and VWAP status.
- `indicators.json`: The same records with actual null values.

`run_summary.json` gains an `indicators` section containing parameters, valid-value counts, latest values, warnings and calculation conventions. Existing summary fields and swing/trendline exports keep their meanings. A full run now writes nine files. Existing destinations are overwritten just as before; select another `--output` to keep multiple runs.

In the GUI, use **Indicator settings** to edit periods and VWAP anchor, **Apply / replay** or **Next bar** to refresh, the **Indicators** table tab for per-bar values, and **Indicator chart** for a separate dashboard window. The latter shows a snapshot of the last successful run. Reopen it after a replay step to view updated results. **Export visible results** exports the applied snapshot, including its indicator settings, even if controls have since been edited.

Tkinter remains optional for CLI use. Run `python -m tkinter` to check desktop support. If unavailable, use a Python installation with Tcl/Tk support and recreate its virtual environment; tkinter is not installed through pip. No new third-party dependency is added. GUI replay/export callbacks were tested with mock widgets, but an interactive desktop session was not available for visual GUI testing.

## Results on the original data

The complete 374-row input runs from 2023-05-19 09:16 through 15:29. Default Steps 1–3 still yield 49 highs, 52 lows and 152 accepted trendline candidates, with three uptrend and three downtrend lines displayed. The original CSV/JSON swing and trendline exports and prices.png match a fresh run of the unmodified ZIP byte-for-byte.

Final-bar indicator values (display rounded; exports retain floating-point precision):

| Output | Final value | Valid rows |
| --- | ---: | ---: |
| SMA | 260.965000 | 355 |
| EMA | 266.814793 | 355 |
| RSI | 35.916168 | 360 |
| MACD | -11.509603 | 349 |
| MACD_SIGNAL | -13.952831 | 341 |
| MACD_HISTOGRAM | 2.443228 | 341 |
| ATR | 9.438971 | 361 |
| VWAP | Unavailable: no volume | 0 |
| ROC | -2.303446 | 362 |
| CCI | -53.193555 | 355 |

These are descriptive computations on the supplied price series, not a prediction-accuracy test. Plot reference lines are visual aids, not automatic transaction rules.

## Verification and references

Tests cover hand-calculated examples for all eight indicators, warm-up positions, flat prices, price gaps, MACD alignment, zero/missing volume, anchor resets, malformed input, CLI parameter overrides, CSV/JSON export, historical-prefix consistency and GUI applied-snapshot behavior. The original algorithm tests remain; their file-count and mock-GUI expectations were updated for the new outputs. See `INDICATOR_TEST_RESULTS.txt` for the complete run and `INDICATOR_VALIDATION.json` for baseline comparisons.

Formula references (retrieved 23 September 2026; implementation conventions are specified above):

- EMA and its SMA initialization: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/ema
- RSI: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/rsi
- MACD: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/macd
- ATR: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr
- CCI: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/cci
- VWAP calculation and anchors: https://www.tradingview.com/support/solutions/43000502018-volume-weighted-average-price-vwap/
