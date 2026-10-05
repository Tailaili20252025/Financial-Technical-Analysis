# Step 4 example results

All runs use the existing default swing parameters, shared trendline tolerance
0.5% of the first anchor price, two consecutive closes for confirmation, and five
observed follow-up bars. These are rule-based descriptive results, not predictions.

| Dataset / method | Bars | Candidate line events | Confirmed | False | Pending | Failure rate (full windows only) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original data / TA | 374 | 141 | 114 | 43 | 2 | 30.94% |
| TSLA / TA | 639 | 239 | 195 | 85 | 0 | 35.56% |
| TSLA / Percentage | 639 | 93 | 68 | 40 | 0 | 43.01% |
| TSLA / ATR | 639 | 22 | 11 | 11 | 0 | 50.00% |
| TSLA / Prominence | 639 | 83 | 60 | 34 | 0 | 40.96% |

Confirmed and false columns overlap: a confirmed event can later fail. Pending
refers to the outcome, not necessarily time confirmation. Counts are per line,
so simultaneous events need not be independent. Method failure rates should not
be treated as accuracy rankings: the methods construct different candidate sets.

Original data has 139 fully observed windows: 43 failed and 96 had no failure
within five follow-up bars. Two more candidates remain pending. The 114 time-
confirmed events are a separate count. Original data has no volume, so the
existing VWAP missing-volume behaviour remains unchanged.

Files are in `examples/step4_data/` and `examples/step4_tsla/001_ta/` through
`004_prominence/`. Each folder contains twelve outputs. Start with `breakouts.png`,
then inspect `breakouts.csv` or `breakouts.json` for the exact availability times.
`examples/step4_tsla/comparison.csv` adds Step 4 counts and settings to the existing
swing comparison. Its comparison.png still compares swing counts/delays.

Regression verification: for all five runs, prices.png, swing_points.csv/json,
trendlines.csv/json, indicators.csv/json/png match the previous unified outputs
byte for byte. The summary preserves every previous field and adds `breakouts`.
The datasets, all four swing algorithms, trendline algorithm, indicators and
Steps 1–3 plotting module are unchanged.

The supplied report proposed GOOG and Tech reruns as well. This delivery uses
only the datasets bundled in unified (data.csv and TSLA_ready.csv); it does not
claim new GOOG or Tech runs.
