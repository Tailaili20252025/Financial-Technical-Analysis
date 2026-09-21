# Step 3: identify and plot trendlines

This milestone extends the existing CSV/JSON reader and confirmed-swing detector.
It is deterministic technical analysis: no machine-learning model is trained and
no future price is predicted. The supplied illustration defines rising lines
through swing lows and falling lines through swing highs, but does not specify
numerical thresholds or how to choose among competing lines. The rules below
make those implementation choices explicit and reproducible.

## Run

Use the existing project Python environment. Open a terminal in
`swingpoints_project`, the directory containing `app.py`.

```bash
python app.py data/data.csv --output output/step3
python app.py data/data.json --output output/step3_json
python app.py --gui data/data.csv
```

No additional dependencies are required. Python 3.10+ is recommended, as in the
existing README. The new module defers annotation evaluation and does not add a
new runtime dependency. Validation used Python 3.12.14 and Matplotlib 3.10.8.

```bash
# Fewer, wider-window swing points
python app.py data/data.csv --window 5 --basis high-low --output output/step3_wicks

# Require at least three confirmed touching swings for display
python app.py data/data.csv --min-touches 3 --output output/step3_three_touches

# Observe only the first 100 chronologically sorted bars
python app.py data/data.csv --until 100 --output output/step3_replay
```

## Exact detection rules

1. Read, validate and sort the input exactly as in Steps 1–2. Work only with the
   visible prefix when using `--until` or GUI replay.
2. Use the Step 2 swing events. A window of `k` requires `k` neighbours on each
   side; a pivot at `i` becomes available at completed bar `i+k`. A wider window
   is our operational way of selecting more prominent local swings. There is
   no separate amplitude-based definition of “significant”.
3. At each newly confirmed low, try pairing it with each of the previous 20
   confirmed lows. Keep only strictly higher second lows (uptrend support).
   Do the symmetric operation for strictly lower second highs (downtrend
   resistance). Equal prices define horizontal levels, outside this step.
4. Two anchors define a fixed straight line. If `t` is elapsed minutes from the
   first anchor, `m = (p2-p1)/(t2-t1)` and `L(t) = p1 + m*(t-t1)`.
   Geometry uses actual elapsed time, including gaps, to agree with the chart's
   timestamp axis. Swing windows and lookback still count observations/events.
5. Set an absolute tolerance `epsilon = p1 * tolerance_percent / 100`.
   The default is 0.5% of the first anchor price, held fixed for that candidate.
   A tiny floating-point allowance of `max(1, abs(p1), abs(p2))*1e-12` is also
   applied. These are project settings, not values estimated from the data.
6. Check every observed bar from the first anchor. Reject an uptrend candidate
   if its test price is below `L(t)-epsilon` before or at line creation. Reject
   a downtrend candidate if its test price exceeds `L(t)+epsilon` in that
   interval. This includes the interval between anchors and the second swing's
   confirmation delay. A pair that slopes correctly is not enough by itself.
7. The line is created only at the second anchor's confirmation time. After
   creation, the first crossing beyond that same tolerance marks it `broken`.
   Its drawing stops at that bar; it never becomes active again. A later valid
   anchor pair can create another candidate. A line with no observed break is
   `active` only as of the supplied cutoff.
8. Count distinct same-kind swing points at or after the first anchor with
   `abs(swing_price-L(pivot_time)) <= epsilon`. Only confirmed swings count.
   If a line breaks, a touch must have been confirmed strictly before the break.
   Both anchor points count as touches; a third touch provides an extra check.

The test price is Close in `--basis close`, Low for rising support in
`--basis high-low`, and High for falling resistance in `--basis high-low`.
No within-bar sequence is inferred when a bar has both types of swing.

## Display selection and chart interpretation

All accepted candidates are exported, including lines subsequently broken.
To prevent a cluttered chart, the display selects a small subset:

- Require at least `min_touches` confirmed touches (default 2).
- Rank by more touches, longer elapsed time between anchors, more recent second
  confirmation, and finally more recent first pivot, in that order.
- Within each direction, suppress a candidate sharing two or more touch pivots
  with an already selected line. This is an explicit display heuristic for
  overlapping candidates, not a new detection rule.
- Keep at most `max_per_direction` lines of each direction (default 3).

This is a historical chart, so displayed lines can be broken. They are not
necessarily the newest currently active lines. More touches are a descriptive
ranking, not a probability, forecast score or guarantee of future behavior.

Green = rising support; red = falling resistance. Dashed segments connect the
historical first anchor to the time when the line becomes available. Diamonds
mark line creation. Solid segments show the line's subsequent observed lifetime.
Large X marks show its first break. The smaller swing-confirmation x marks from
Step 2 remain. Lines never extend beyond the last observed timestamp.

The selected subset and touch counts can change as more data becomes known.
Geometry and creation time of an existing candidate remain fixed. To inspect
what was knowable at an earlier time, rerun that prefix; do not use a later
full-history ranking as an earlier-time signal.

## Settings

| CLI option | GUI control | Default | Meaning |
| --- | --- | ---: | --- |
| `--window` | Window | 2 | Neighbours on each side required for a swing |
| `--basis` | Swing basis | close | Close extrema, or High peaks / Low troughs |
| `--trend-tolerance` | Trend tolerance (%) | 0.5 | Percent of the first anchor price; 0 <= value < 100 |
| `--trend-lookback` | Anchor lookback | 20 | Previous same-kind swings tried for each second anchor; >= 1 |
| `--min-touches` | Min touches | 2 | Minimum confirmed touches for chart selection; >= 2 |
| `--max-trendlines` | Max lines / direction | 3 | Per-direction chart cap; >= 1 |

Click **Apply / replay** after editing GUI controls. **Displayed trendlines**
shows the same selected lines as the chart. The **Confirmed swings** tab retains
the original table. Export uses the last applied run, not unapplied control edits.

## Output and architecture

Each run writes six files: `prices.png`, `swing_points.csv`, `swing_points.json`,
`trendlines.csv`, `trendlines.json`, and `run_summary.json`. Both trendline tables
contain the full accepted candidate list. Filter `displayed` to recover the
chart selection. CSV stores touch-index lists as JSON strings. Exported bar
numbers are one-based; internal indices are zero-based. Empty results still
produce a CSV header, an empty JSON array, a chart and summary.

Each trendline record includes its ID, direction, basis, two anchor times/prices,
creation time, slope in price units per elapsed minute, tolerance, confirmed
touch bars and confirmation bars, active/broken status, break time, end time
and displayed flag. The summary includes all settings and candidate/display
counts. A blank/null break time means no break has yet been observed.

| File | Responsibility |
| --- | --- |
| `swingpoints/trendlines.py` | Settings, candidate geometry, timing, break/touch evaluation and chart selection |
| `app.py` | CLI options and Step 1 → Step 2 → Step 3 → draw/export flow |
| `swingpoints/gui.py` | Controls, replay, two tables and export of the applied run |
| `swingpoints/plotting.py` | Shared rendering of prices, swings and selected lines |
| `swingpoints/output.py` | Six-file export and reproducibility metadata |
| `swingpoints/__init__.py` | Exposes the new public types and functions |
| `tests/test_trendlines.py` | New Step 3 tests; the old test suite is unchanged |

The reader and Step 2 detector are unchanged. Existing functions retain their
triple-quoted documentation; new functions document Args, Result and Exception.

## Walk-through

Suppose confirmed swing lows occur at 10:00 (100), 10:02 (102), and 10:04 (104).
The first pair gives slope `(102-100)/2 = 1` price unit per minute. At 10:04 the
line value is 104, so the third low is another touch once it is confirmed. If
`window=1`, the line is first available at 10:03 and the third touch at 10:05.
Intermediate observed prices must also respect the support tolerance. With the
default 0.5% setting the tolerance is 0.5; at 10:06 the line is 106, so a Close
strictly below 105.5 breaks this Close-based line. A Close of 105.5 is within
allowed tolerance. Falling highs of 110, 108 and 106 work symmetrically.

## Reproducible supplied-data results

| Example directory | Bars | Swing highs/lows | Accepted line candidates | Displayed up/down |
| --- | ---: | --- | ---: | --- |
| `examples/step3_close_window2` | 374 | 49 / 52 | 152 | 3 / 3 |
| `examples/step3_high_low_window5` | 374 | 18 / 22 | 51 | 3 / 3 |

Different windows, tolerances and rankings can produce different valid charts.
This program is not intended to reproduce the instructor's manually chosen
anchor points exactly. It does not implement later multi-candle breakout
confirmation or price-prediction steps. The first-crossing rule here only ends
an existing geometrical line.

The batch implementation scans observed bars for each candidate pair. Its
worst-case work is approximately O(N * S * K), with N bars, S swings and K
lookback swings, plus touch counting. It is appropriate for this 374-row
prototype; large multi-year intraday datasets would need incremental indexing.
