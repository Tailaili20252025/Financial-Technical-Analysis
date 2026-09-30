# Step 4 — Breakout, Breakdown and False Breaks

This update is based on the **Unified Swing Methods** version (four swing strategies,
shared trendlines and eight indicators). It implements the Close-based first version
proposed in the supplied **Breakdown Point Report.docx**. It does not replace Steps 1–3.

## Run

From `swingpoints_project`, with the existing Python environment activated:

```bash
python app.py data/data.csv --output new_data_output/step4_data
python app.py data/TSLA_ready.csv --method ta --output new_data_output/step4_TSLA
python app.py data/data.csv --gui
```

All four methods (`ta`, `percentage`, `atr`, `prominence`) use the same Step 4 rules.
To compare all four on TSLA:

```bash
python run_methods.py data/TSLA_ready.csv --output new_data_output/step4_comparison
```

To change counts or replay an observed prefix:

```bash
python app.py data/data.csv --until 200 --break-confirmation-bars 3 --break-observation-bars 7 --output new_data_output/step4_custom
```

`--trend-tolerance 0.5` remains the shared Step 3/4 buffer setting: 0.5% of the FIRST
anchor price, fixed for that line. Changing it also changes Step 3 candidates.
`--break-confirmation-bars` and `--break-observation-bars` default to 2 and 5.
Both must be positive integers, and confirmation cannot exceed observation + 1.
Counts mean observed completed bars, not clock minutes or calendar days.

## Exact rules

Write L(t) for `TrendLine.value_at(timestamp)` and B for the line's fixed absolute
tolerance. L(t) uses elapsed time including gaps; it is geometry, not a predicted price.

| Event | Rule |
| --- | --- |
| Breakout candidate | First Close greater than L(t) + B for falling resistance. |
| Breakdown candidate | First Close less than L(t) − B for rising support. |
| Time confirmation | First run of N consecutive closes beyond the same directional threshold, starting no earlier than the candidate. |
| False breakout | A following Close less than L(t) − B within W bars after the candidate. |
| False breakdown | A following Close greater than L(t) + B within W bars after the candidate. |

Detection begins on the bar AFTER the second anchor is confirmed. The candidate
counts as the first close toward confirmation, but not as a follow-up bar. The
observation window is candidate + 1 through candidate + W, inclusive. A close
inside the tolerance band resets the consecutive-close count without creating a
failure. Equality is not a crossing; the Step 3 floating-point allowance is retained.

Keep one first-break event per line ID. After failure, later crossings of that line
do not create additional events. The original slope and anchors never change.
The scanner continues checking the original line through the follow-up window even
though its Step 3 solid segment stops at the first break.

## Confirmation and outcome are separate

`confirmation_status` is `pending`, `confirmed`, or `not_confirmed`.
`outcome` is `pending`, `false_breakout`, `false_breakdown`, or
`no_failure_within_window`. A confirmed event can later become false. A full window
without failure may also end without time confirmation if closes stayed in the band.
Neither result establishes predictive accuracy or guarantees continuation.

The report's example has line values 100.0, 99.9, 99.8; buffer 0.5; and closes
100.8, 100.9, 99.1. These produce candidate, confirmation and false breakout on three
successive bars. The false label appears only when the third close is observed.

Incomplete follow-up remains pending, even if confirmation already occurred. A
failure can become known before the full window has elapsed. Summary failure rates
nevertheless include **only candidates with all W follow-up bars observed**, as the
report specifies. `deadline_bar` may refer to a not-yet-observed bar; `deadline_at`
remains null until that bar is actually observed. No future timestamps are inferred.

## Output and GUI

Each run now writes **12 files**. The original nine output files remain; new files are:

| File | Content |
| --- | --- |
| `breakouts.csv` | One event per trendline, suitable for Excel; header retained when empty. |
| `breakouts.json` | The same records with nulls and booleans preserved. |
| `breakouts.png` | Separate breakout and breakdown panels; candidate circles, confirmation +, false-break x. |

`run_summary.json` adds a `breakouts` section with settings, direction counts,
confirmation counts, outcomes, full-window sample size and failure rate.
Bar numbers in exported records are **one-based**. Candidate, confirmation,
failure and outcome-availability times are stored separately. Join `line_id` to
`trendlines.json` to inspect the original anchors and slope.

`prices.png` remains the original Steps 1–3 figure. `breakouts.png` includes all
line events, grouping coincident markers for readability. Its grey dashed guides
show only the Step 3 display subset; the scanner never filters events by that subset.
Counts are per line: one price bar can break several lines, so they are not counts
of independent trades. No-failure outcomes are in the table; there is no invented
future-success marker.

In the GUI, load a file and choose **Close** basis. Use **Step 4 settings** to edit
the counts, **Apply / replay** or **Next bar** to change the observed prefix, and
**Breakout chart** to open the Step 4 figure. The **Step 4: all line events** tab
shows all records. **Export visible results** exports the last successful snapshot,
including its applied Step 4 settings, regardless of later unapplied control edits.
Existing Tkinter installation instructions still apply; no new dependency is needed.

## Scope and implementation

This first implementation intentionally supports **Close-based lines only**.
High/Low mode still runs Steps 1–3 and indicators but exports an empty Step 4 table
and explicit `not_supported_high_low` status. A wick-only crossing is not a candidate.
Separate wick-rejection records, ATR breakout buffers, volume confirmation and
retest filters are research extensions, not enabled features in this update.
Using the ATR swing method does not change the Step 4 buffer into an ATR buffer.

- `breakouts.py`: immutable settings/events, all-line scan, lifecycle and summary.
- `breakout_plotting.py`: dedicated chart with availability-time markers.
- `pipeline.py`: runs Step 4 immediately after shared trendline detection.
- `app.py`, `gui.py`: controls, snapshot handling and display.
- `output.py`: three new outputs and summary metadata.
- `run_methods.py`: shared Step 4 parameters and per-method comparison statistics.

```python
from swingpoints.breakouts import BreakoutSettings
from swingpoints.methods import create_method
from swingpoints.pipeline import run_analysis

result = run_analysis(
    "data/data.csv", "new_data_output/step4",
    method=create_method("ta", window=2, basis="close"),
    breakout_settings=BreakoutSettings(confirmation_bars=2, observation_bars=5),
)
print(len(result.events))
```

The functional scanner and pipeline replay only the supplied observed prefix.
The implementation scans fixed candidate geometry without reranking eligibility
using future touches. Existing trendline construction/selection is unchanged.

## 中文上传与使用说明

这份更新针对已经整合好的 unified 版本，只补充 Step 4。解压交付包后，把
`changes_only` 里面的内容上传到仓库根目录；不要把外层 `changes_only` 文件夹上传。
不需要删除文件，也不需要再次上传之前 indicators 或 alternative methods 的完整包。

如果使用新分支：从已经有 unified 的分支创建 Step 4 分支，再提交这些文件。
PR 的 base 选已经包含 unified 的目标分支，compare 选你的 Step 4 分支。

查看结果：原始数据在 `examples/step4_data`；TSLA 四种方法在
`examples/step4_tsla/001_ta`、`002_percentage`、`003_atr`、`004_prominence`。
先打开 `breakouts.png` 看图，再用 `breakouts.csv` 查看每条趋势线对应的具体时间。
假突破可能出现在确认以后；不足五根后续 bar 时仍保留 pending，不能当作成功。

## Validation

Run `python -m unittest discover -s tests -v` from the project directory.
See `STEP4_TEST_RESULTS.txt` and `STEP4_RESULTS.md` for the delivered run.
Tests include the report example in both directions, equality/numerical allowance,
wick-only movement, neutral streak resets, deadline boundaries, incomplete windows,
creation timing, timestamp gaps, CSV/JSON exports, GUI snapshot preservation and
causal replay for all four methods. The existing 14 legacy swing/trendline reference
cases remain in the suite. GUI callbacks use mock widgets; a native macOS window
was not visually tested in this environment.
