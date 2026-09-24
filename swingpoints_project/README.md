## Added: SMA, EMA, RSI, MACD, ATR, VWAP, ROC and CCI

This incremental update keeps the existing Steps 1–3. Run the same command to also
produce `indicators.png` and `indicators.csv/json`. Original `data.csv` has no
volume, so VWAP is explicitly unavailable for this input. See [INDICATORS.md](INDICATORS.md)
for settings, formulas, results and GUI instructions. Each run now saves nine files;
older examples below remain historical Step 1–3 examples.

# SwingPoints project

A documented Python implementation of **Steps 1, 2 and 3** in the supplied
*Model Steps Complete.pdf*: read prices, plot Close/High/Low, and identify and
display local swing highs/lows and rising/falling trendlines. Includes CSV and JSON examples, a desktop
interface, a command-line interface, automated tests, and sample results.

Start with `QUICKSTART_ZH.md` if you prefer the beginner instructions in Chinese.

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

The default command saves six files in `output/`:

| File | Content |
| --- | --- |
| `prices.png` | Close, High and Low lines with swings and selected trendlines |
| `swing_points.csv` | Swing results suitable for Excel or later Python work |
| `swing_points.json` | The same results in machine-readable JSON |
| `trendlines.csv` | All accepted trendlines, touch counts, timing and displayed flag |
| `trendlines.json` | The same trendline records in JSON |
| `run_summary.json` | Input hash, observed range, settings, swing and trendline counts |

Opening `output/prices.png` requires no Python graphical display. Re-running
with the same output folder replaces those six results; use a different folder
to keep multiple runs. The original input is never intentionally overwritten.

## 2. GUI - Tkinter usage and install

Tkinter supplies the desktop window, controls and file dialogs. Matplotlib draws
inside it through `FigureCanvasTkAgg`. The GUI runs the same Steps 1–3 as the CLI:
load and validate data, detect confirmed swings, then calculate and plot trendlines.

### Install and check Tkinter

Use the Python environment created in Section 1. Tkinter requires Python's Tk
support and a local graphical desktop; it is not installed by `requirements.txt`.
Do not use `pip install tkinter` as a repair command.

On macOS, open Terminal in `swingpoints_project` and run:

```bash
source .venv/bin/activate
python --version
python -m tkinter
```

A small demonstration window confirms that Tk is working. Close it before launching
the application. If `_tkinter` or `tkinter` is missing, install a Python distribution
with Tcl/Tk support. The python.org macOS installer includes it. Verify the new
interpreter with `python3 -m tkinter` before creating a fresh environment:

```bash
# Run outside the old virtual environment, using the verified Python interpreter.
python3 -m venv .venv-tk
source .venv-tk/bin/activate
python -m pip install -r requirements.txt
python -m tkinter
```

Creating another venv with the same Tk-less interpreter will not repair Tk.
On Windows, use a full Python installation with Tcl/Tk support and test with
`.\.venv\Scripts\python.exe -m tkinter`. On Linux, install your distribution's
Tkinter package for the Python interpreter you use, then repeat the check.

Official references: [Python Tkinter documentation](https://docs.python.org/3/library/tkinter.html)
and [Python on macOS with Tcl/Tk](https://www.python.org/download/mac/tcltk/).

### Launch the application

From `swingpoints_project`, with the environment active:

```bash
# Open the example data immediately.
python app.py --gui data/data.csv

# Or open an empty window, then click Open CSV / JSON.
python app.py --gui
```

Windows PowerShell without activation:

```powershell
.\.venv\Scripts\python.exe app.py --gui data/data.csv
```

The terminal remains occupied until the GUI window is closed.

### Controls and settings

| Control | Meaning and use |
| --- | --- |
| Open CSV / JSON | Select and validate a file; a successful load analyses all its bars. |
| Window | Neighbours required on each side of a pivot; default 2. At least `2 * window + 1` observed bars are needed for the first possible swing. |
| Swing basis | `close` uses Close for peaks and troughs; `high-low` uses High for peaks and Low for troughs. |
| Observed bars | Number of bars to analyse from the beginning of the sorted data, between 1 and the loaded count. |
| Apply / replay | Validate current controls and recalculate the selected historical prefix. |
| Next bar | Increase the observed count by one and recalculate with the current settings; stops at the last loaded bar. |
| Trend tolerance (%) | Allowed deviation as a percentage of the first anchor price; default 0.5 means 0.5%, not 50%. |
| Anchor lookback | Number of earlier same-kind swing anchors considered per later anchor; default 20. |
| Min touches | Minimum confirmed touches for a line to be eligible for display; default 2. |
| Max lines / direction | Display cap for each direction separately; default 3 up and 3 down. |
| Export visible results | Select an existing destination folder and save the last successfully displayed analysis. |

For replay, enter a smaller observed count, click **Apply / replay**, then click
**Next bar**. Opening a file initially shows all bars, so reduce this count first.
With `window=2`, a pivot becomes confirmed two observations after it occurs.

The chart toolbar provides navigation, pan, zoom and figure saving. The **Confirmed
swings** tab lists pivot and confirmation times; **Displayed trendlines** lists
selected lines and break status. Export writes the six files in Section 1;
trendline CSV/JSON includes all accepted candidates and a `displayed` flag.

Click **Apply / replay** after editing settings and before exporting. Export uses
the last successful plot snapshot, not unapplied control edits. Choose a separate
folder for each dataset to avoid replacing a previous run's six output files.
See [STEP3.md](STEP3.md) for the full trendline rules.

### How gui.py connects the controls

`launch()` creates `tk.Tk()`, builds `SwingApp`, optionally loads the input, then
starts `root.mainloop()`. Buttons bind callbacks using `command=self.refresh`
(without parentheses). `StringVar` connects text fields to Python values;
`refresh()` reads and validates those values before analysing data. `canvas.draw()`
redraws the plot; the two `Treeview` widgets display the result tables.

Attributes are documented beside their first assignment. For example, `self.cutoff`
is a bar count, while `self.current_run` stores the last successful export snapshot.
The current callbacks run synchronously on the Tk thread; large datasets can make
the interface temporarily unresponsive. Background processing is not implemented.

### Troubleshooting and a short manual check

- `python: command not found`: activate the virtual environment first.
- `can't open file app.py`: change into the folder containing `app.py`.
- `No module named matplotlib`: run `python -m pip install -r requirements.txt`
  in the same environment used to launch the GUI.
- `No module named _tkinter`: use the Tk-enabled interpreter described above.
- `no display name` / Tk cannot open a display: run on a local desktop, or use
  `python app.py data/data.csv` to produce a PNG without the GUI.
- No swings or lines: check the observed count and settings; insufficient history
  or no qualifying price pattern can legitimately produce an empty result.

Manual check: open the sample CSV; apply 100 observed bars; advance to 101; change
basis and apply; inspect both result tabs; export to a new folder and verify the
six files. This checks actual window interaction, which automated CLI tests alone
cannot establish. The development environment did not provide an interactive
Tk desktop; see [TESTING.md](TESTING.md) for the existing test checklist.

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
| `swingpoints/trendlines.py` | Defines, validates and ranks rising/falling trendlines |
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
prediction. Step 3 trendlines are implemented with explicit timing and tolerance rules.
Later breakout-confirmation and prediction steps remain outside this milestone.
See [STEP3.md](STEP3.md) for the algorithm and [TESTING.md](TESTING.md) for validation.

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

## 8. Step 3 source and branch history

This code extends the uploaded `Add-Step3` branch snapshot, which already includes
function documentation from `Add-Function-Notation`. Upload the update files to
`Add-Step3` and open a PR against the appropriate base described in the delivery guide.

The existing `swingpoints.bundle` and older example/output folders are retained
as historical Step 1–2 artifacts. They do **not** contain this Step 3 revision.
Use the current source files and `examples/step3_*` for this milestone.
