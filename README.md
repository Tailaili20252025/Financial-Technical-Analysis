# Financial-Technical-Analysis

A documented Python implementation of **Steps 1 and 2** in the supplied
*Model Steps Complete.pdf*: read prices, plot Close/High/Low, and identify and
display local swing highs and lows. Includes CSV and JSON examples, a desktop
interface, a command-line interface, automated tests, and sample results.



## 1. Install and run

Use **Python 3.10 or later**; this project was tested with Python 3.12.14 and
Matplotlib 3.10.8. Open a terminal in the extracted `swingpoints_project` folder.

On macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py data/data.csv
```

On Windows PowerShell (activation is not necessary):

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py data/data.csv
```

The default command saves four files in `output/`:

| File | Content |
| --- | --- |
| `prices.png` | Close, High and Low lines with swing and confirmation markers |
| `swing_points.csv` | Swing results suitable for Excel or later Python work |
| `swing_points.json` | The same results in machine-readable JSON |
| `run_summary.json` | Input hash, observed range, settings and swing counts |

Opening `output/prices.png` requires no Python graphical display. Re-running
with the same output folder replaces those four results; use a different folder
to keep multiple runs. The original input is never intentionally overwritten.

## 2. Desktop interface

```bash
python app.py --gui data/data.csv
```

Or `python app.py --gui` to start with a file picker. The interface provides:

- **Open CSV / JSON**: choose an input file.
- **Window**: number of bars on each side of the candidate pivot; initially 2.
- **Swing basis**: `close` or `high-low`.
- **Observed bars**: historical cutoff. Enter 100, then select **Apply / replay**
  to show only the first 100 bars and swings confirmed by that point.
- **Next bar**: reveal one more observed bar, then recompute the same prefix.
- **Export visible results**: save exactly the currently plotted run. Apply any
  changed settings first. Exports use the plotted settings, not unapplied edits.
- A chart toolbar for zooming/panning and a table of pivot/confirmation times.

Tkinter is optional for the command-line workflow. Test your Python's Tk
installation with `python -m tkinter`. If it is unavailable, use a Python
installation built with Tk, or use the CLI to save PNG charts. The desktop
interface requires a local graphical display.

**Validation limitation:** this build environment had no display, so desktop
controls were not interactively verified. The shared loading, detection,
plotting and export workflow was tested through the CLI. A manual desktop
checklist is in `TESTING.md`.

## 3. Command-line examples

```bash
# Equivalent input using JSON
python app.py data/data.json --output output/json

# Find peaks on High and troughs on Low with a wider neighborhood
python app.py data/data.csv --basis high-low --window 5 --output output/high_low

# Replay only the first 100 observed bars
python app.py data/data.csv --until 100 --output output/replay_100

# Display a Matplotlib window as well as saving files (requires a display)
python app.py data/data.csv --show

# See all options
python app.py --help
```

`--until N` means the first N rows **after chronological sorting**, not a row
number in an unsorted source file. `--gui` uses its own observed-bars control.

## 4. Input formats

Required fields are `timestamp`, `high`, `low`, and `close`. `open` is optional
and checked when present. Other fields, such as volume, are ignored in this
milestone. Column names are case-insensitive. Supply one instrument per file.

CSV:

```csv
timestamp,open,high,low,close
19/05/23 9:16,344.2,361.7,333.35,347.1
19/05/23 9:17,352.5,362.5,343.7,358.85
```

JSON:

```json
[
  {"timestamp": "2023-05-19T09:16:00", "open": 344.2, "high": 361.7, "low": 333.35, "close": 347.1},
  {"timestamp": "2023-05-19T09:17:00", "open": 352.5, "high": 362.5, "low": 343.7, "close": 358.85}
]
```

JSON also accepts `{"data": [...]}`. JSON Lines and column-oriented JSON are
not supported. CSV accepts comma, semicolon or tab separators, with decimal
points in numbers. Dates accept ISO 8601, or day-first `DD/MM/YY HH:MM` and
`DD/MM/YYYY HH:MM` (optionally with seconds). No timezone is invented when the
file supplies none. Do not mix timestamps with and without timezone offsets.

The reader sorts data, rejects duplicate timestamps, missing/invalid required
fields, nonfinite or nonpositive prices, and inconsistent OHLC values. It does
not fill gaps or resample. Windows count bars and can cross session boundaries;
for separate-session analysis, provide each session separately. Non-one-minute
intervals are reported, not assumed to be data errors or market closures.

The supplied sample was checked: **374 rows, 2023-05-19 09:16 through 15:29**,
all consecutive one-minute timestamps, no duplicates or inconsistent OHLC rows.
`data/data.json` was generated directly from `data/data.csv` and contains the
same observations, not additional data.

## 5. Exact swing logic and the no-future-data requirement

The PDF illustrates local extrema on Close without prescribing a numerical
threshold or neighborhood. This implementation makes that choice explicit and
configurable: default `window = 2`, `basis = close`. Its markers need not exactly
match the PDF's manually selected significant points.

For window `k`, candidate `i` is a swing high if its price is **strictly greater**
than all `k` neighbors on its left and all `k` neighbors on its right. It is a
swing low if it is **strictly smaller** than all those neighbors.

At current completed bar `t`, the program evaluates candidate `i = t - k`.
The rightmost bar required is therefore `i + k = t`, which has already arrived.
The detector uses a rolling buffer of `2*k + 1` observed bars, never the unknown
future. A pivot is identified retrospectively and becomes available only at
its confirmation time. This is not a claim that a reversal can be known at the
instant the turning point occurs.

Example with `k = 1` and Close values `[100, 102, 101, 105, 103]`:

| Pivot bar | Type | Price | First known at bar |
| --- | --- | --- | --- |
| 2 | High | 102 | 3 |
| 3 | Low | 101 | 4 |
| 4 | High | 105 | 5 |

Before bar 3 arrives, the high at bar 2 is **not available**. The triangle on a
historical chart marks the original pivot; the small `x` marks confirmation time
at that same pivot price, not the price at the later bar. The table explicitly
separates `pivot_time` and `confirmed_at`. Any later model must join events by
`confirmed_at`, never backfill them into the original pivot row.

Rules and edge cases:

- `close`: compare Close for both highs and lows, as in the PDF's charts.
- `high-low`: compare High for peaks and Low for troughs.
- The first `k` bars lack left context; the final `k` bars lack sufficient right
  context. Neither edge is forced into a swing.
- Equal prices/plateaus do not qualify as strict extrema.
- With fewer than `2*k + 1` bars, plot prices and return an empty swing table.
- In High/Low mode an outside bar can be both a high and a low. Both are retained;
  OHLC data do not reveal the order of movements inside that minute.
- Consecutive same-type swings are not merged and alternating swings are not
  forced. This is local-extrema detection, not a ZigZag algorithm.
- Earlier discussion included an additional prior-swing breakout confirmation
  rule. That rule is **not part of the supplied PDF's Steps 1-2** and is not
  implemented here. Here “confirmed” means the local-extremum window completed.

Using the full file for a historical display is different from giving earlier
predictions access to all of it. `--until` and GUI replay restrict computations
and display to the observed prefix; automated prefix tests enforce this rule.

## 6. Code architecture and how to read it

| File | Purpose |
| --- | --- |
| `app.py` | Parses commands and runs loading, detection, plotting and export |
| `swingpoints/data.py` | Defines a price bar; reads and validates CSV/JSON |
| `swingpoints/detector.py` | Defines swing events and the streaming algorithm |
| `swingpoints/plotting.py` | Draws price lines, pivots and confirmation times |
| `swingpoints/output.py` | Writes charts, swing tables and metadata |
| `swingpoints/gui.py` | Desktop controls and historical replay |
| `tests/test_system.py` | Arithmetic, timing, input and integration tests |

Read `app.py` first, then `data.py`, then `detector.py`. The essential flow is:

```python
from swingpoints import load_prices, detect_swings

bars = load_prices("data/data.csv")
points = detect_swings(bars, window=2, basis="close")
for point in points:
    print(point.as_record())
```

To use the detector on arriving completed bars:

```python
from swingpoints import SwingDetector

detector = SwingDetector(window=2, basis="close")
for completed_bar in bars:
    newly_confirmed = detector.update(completed_bar)
    # These events become available NOW, at completed_bar.timestamp.
```

This milestone contains deterministic analysis, not machine learning or price
prediction. Trendlines, breakout rules, trading decisions and later model steps
are outside the requested implementation.

## 7. Tests and included results

```bash
python -m unittest discover -s tests -v
```

The suite uses standard-library `unittest`; no pytest install is required.
It checks known extrema and delays, flat/monotonic/tied prices, short sequences,
outside bars, validation errors, JSON/CSV equivalence, source protection and
end-to-end exports. It also compares every historical prefix against only the
events available by that cutoff for both detection bases.

Reproducible sample runs are included in `examples/`:

| Run | Bars | Highs | Lows |
| --- | ---: | ---: | ---: |
| `close_window2` | 374 | 49 | 52 |
| `high_low_window5` | 374 | 18 | 22 |
| `replay_100` (Close, window 2) | 100 | 13 | 12 |

These are descriptive counts, not performance scores. See `TESTING.md` for the
executed validation and the remaining manual desktop checks.

## 8. Git commit included in the download

No external repository was supplied. The code is committed in a new local Git
repository. The download includes `swingpoints.bundle`, a portable copy of that
repository and commit history. To restore it after unzipping:

```bash
git clone swingpoints.bundle swingpoints_committed
cd swingpoints_committed
git log -1 --oneline
git status
```

The extracted source itself can be run immediately; restoring the bundle is
only needed to inspect or continue the Git history. No GitHub push was made.
