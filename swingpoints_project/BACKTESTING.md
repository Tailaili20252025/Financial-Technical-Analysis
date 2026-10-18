# Historical backtesting

This addition evaluates the existing four swing methods through the shared
trendline and breakout stages, then simulates entries, exits and net P/L. The
supplied repository snapshot contained Steps 1–4 but no `trading.py`; this package
therefore also includes the previously delivered Step 5–6 engine as a dependency.
The existing application files and GUI are not replaced. The new entry point is
`backtest.py`; it imports the existing `pipeline.analyze()` service.

## Run on macOS or Linux

Open Terminal in `swingpoints_project`, the folder containing `app.py`.
Use Python 3.10 or newer; the verification environment used Python 3.12.14.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python backtest.py --plan backtest_plan.json --output backtest_results/my_run
```

If `.venv` already exists with the dependencies installed, activation and the last
command are enough. On macOS, view the result charts with:

```bash
open backtest_results/my_run/equity_comparison.png
open backtest_results/my_run/cost_comparison.png
```

The included results are in `backtest_results/research_run`. Use a new output
folder for each experiment. Existing nonempty folders are refused unless you
explicitly supply `--overwrite`. The runner does not require Tkinter or a display.

On Windows, use `py -m venv .venv`, then invoke `.\.venv\Scripts\python.exe`
in place of `python` in the install, test and backtest commands.

## Data and reproducibility

Twenty ready-to-run CSVs are included under `data/backtest`. They contain 25,180
daily records: 1,259 per stock from 2013-02-08 to 2018-02-07. The original
`data/data.csv` is untouched.

Symbols selected before running the strategy were AAPL, MSFT, AMZN, GOOGL, JPM,
BAC, XOM, CVX, JNJ, PFE, PG, KO, WMT, HD, GE, BA, CAT, MMM, DIS and VZ. They offer
several sectors, but are not a random sample or a point-in-time index universe.

Source: [Cam Nugent, S&P 500 stock data on Kaggle](https://www.kaggle.com/datasets/camnugent/sandp500),
published as CC0 Public Domain. The archive's `getSandP.py` identifies IEX as its
upstream source. The downloaded combined file has 619,040 rows and 505 symbols.
The experiment uses only the selected 20 stocks, not the entire source universe.

The adapter verifies the frozen source SHA256 and splits `Name` into one file per
stock. It renames `date` to `timestamp` and preserves OHLCV values. It rejects
invalid prices, missing required values and duplicate dates; nothing is imputed.

```text
timestamp,open,high,low,close,volume
```

`data/backtest/source_manifest.json` records source URLs, licensing, preparation,
date ranges, counts and hashes. Normalized files are checked against this manifest
when running. Recreate the exact sample with:

```bash
python prepare_backtest_data.py
```

Or supply a locally downloaded copy of the publisher's combined CSV:

```bash
python prepare_backtest_data.py --source-csv /path/to/all_stocks_5yr.csv
```

If the publisher changes that snapshot, the checksum deliberately fails. Review
and version the new source before changing the pin. The bundled sample works
without another download or a Kaggle account.

## Experiment design

`backtest_plan.json` declares the complete matrix before metrics are calculated.
Edit its method attributes, periods, stocks or cost scenarios to create a new
experiment. Save a separate plan and use `--plan path/to/plan.json`. Its `data_dir`
is relative to that plan. Each selected symbol needs its own compatible CSV and
the evaluated stock calendars must match; missing sessions are not forward filled.

- Four nonoverlapping blocks: 2014, 2015, 2016, and 2017-01-01–2018-02-07.
- Each block starts flat with 10,000 units of capital per stock, or 200,000 across
  the 20 accounts. No profits, positions or queued orders carry across blocks.
- All earlier observations are available for indicator and trendline warm-up.
  At least 200 bars are required; the earliest block has 226.
- Only events confirmed inside a block may enter; a warm-up candidate can confirm
  inside the block. An already confirmed warm-up signal cannot open a new trade.
- Four fixed methods, 20 stocks, four blocks and three cost scenarios give 960
  simulations. The three cost cases reuse the same signals; they are sensitivity
  tests, not 960 independent market samples.
- No parameters were optimized. This is fixed-rule chronological evaluation with
  expanding prior context, not a trained-model walk-forward optimization.

| Method | Swing settings |
| --- | --- |
| Traditional TA | Close basis, 2 completed neighbours on each side |
| Percentage reversal | 5% reversal of Close |
| ATR reversal | Wilder ATR(14), reversal of 2 ATR frozen at the pivot |
| Local prominence | Radius 5, minimum prominence 3%, same-kind spacing 3 |

All methods reuse the existing candidate trendline construction and validation:
0.5% tolerance, 20 previous same-kind swings, minimum 2 touches. Display ranking
does not select trades: all eligible candidate-line events feed Step 4.
Breakouts require 2 consecutive closes; false-break observation lasts 5 bars.

The trade engine uses one share per position, one position per stock, no leverage,
and allows long and short trades. A confirmation at Close queues the next observed
Open. ATR(14) at confirmation fixes a stop 2 ATR from the entry fill and a target
twice that risk distance. Stop and target do not trail. If both levels occur inside
one daily bar, stop-first is used. A known opening gap is processed first: adverse
stop gaps fill at the Open; favourable target gaps receive only the limit price.
Targets have no additional adverse slippage. A last-bar signal stays unfilled.

The EMA entry filter and exits on false/opposite signals are off in this fixed
comparison. ATR is used for risk; other indicators remain available in the main
application but are not automatically extra buy/sell rules. A later false-break
label never retrospectively deletes an earlier entry.

| Cost case | Adverse market-fill slippage | Fee per order | Annual short borrow |
| --- | --- | --- | --- |
| Zero | 0 basis points | 0.00 | 0% |
| Base | 5 basis points (0.05%) | 0.10 | 3% |
| Stress | 10 basis points (0.10%) | 0.50 | 6% |

These are sensitivity assumptions, not broker quotations. Borrow is charged on
entry notional over elapsed calendar time using actual days / 365. Slippage is
already included in fill prices; it is not deducted a second time. Costs can
alter fills and later position availability, so scenario differences are not
always equal to the sum of explicit charges.

## Accounting and benchmarks

Closed net P/L = direction × quantity × (exit fill − entry fill) − fees − borrow.
Direction is +1 for a long and −1 for a short. Open P/L substitutes the final
Close for the exit price and includes only fees/borrow incurred so far.

Final equity = initial capital + realized net P/L + open net P/L.
Account return (%) = 100 × net P/L / initial capital.
Maximum drawdown is the largest percentage decline from starting capital or a
later closing-equity high. It does not measure unobserved intraday drawdown.
Profit factor divides total positive closed net P/L by absolute negative closed
net P/L; it is blank when no losses occur. Win rate uses closed trades only.

Buy-and-hold buys one share of each stock at its block's first Open, applies the
same entry slippage/fee, and marks the final Close. Both arms leave remaining cash
idle and do not force a terminal sale, so no imaginary exit commission is charged.
Cash earns zero interest. These are price-only, pre-tax results; dividends and
payments in lieu on shorts are excluded. Buy-and-hold is a same-quantity reference,
not an exposure-matched hedge or a fully invested portfolio.

The small account return/drawdown figures reflect one-share sizing against large
idle capital. Share-price levels also create unequal stock exposure. Do not infer
low strategy risk or capital efficiency from those small percentages.

## Output files

| File | Meaning |
| --- | --- |
| `summary.csv` | 960 stock/method/block/cost rows with P/L, return, drawdown and benchmark |
| `portfolio_summary.csv` | 48 aggregates of 20 separate stock accounts |
| `portfolio_equity.csv` | Closing equity of those aggregates; drawdown uses summed paths |
| `trades.csv` | Every filled trade, timing, stop/target, fees, borrow and P/L |
| `signals.csv.gz` | Compressed entry decisions, including skipped and unfilled signals |
| `equity_by_run.csv.gz` | All 247,920 evaluated closing-equity rows, compressed |
| `equity_comparison.png` | Separate P/L curves for each block and same-quantity buy-and-hold |
| `cost_comparison.png` | Cost sensitivity summed across independent blocks |
| `applied_plan.json`, `experiment.json` | Frozen configuration, environment, input/code/output hashes |
| `validation.json` | Independent Decimal P/L reconciliation and prefix replay checks |

`.gz` files are standard gzip-compressed CSVs, readable with Python's `gzip.open`,
or decompressible with common archive utilities. Summaries use full precision;
the report rounds currency values to two decimals.

## Verified results and interpretation

At base costs, the sum of the four independently reset blocks is −61.62 for TA,
−227.31 for percentage reversal, −317.65 for ATR reversal, and −265.60 for
prominence. The comparable buy-and-hold sum is +2,267.94; cash is zero. These sums
are diagnostic totals across separate experiments, not a compounded multi-year
account. Per-block results and realized/open components are in the CSVs.

TA totals +234.39 at zero costs but −1,049.01 at stress costs. All four methods
have a negative base-cost sum. The implementation passes its accounting and
causality checks; this sample does not establish a profitable trading edge.

The full application suite passed 147 tests, including 34 added tests. The large
run passed 960 independent Decimal reconstructions of every evaluated equity row
(247,920 rows) and 16 midpoint prefix checks across all four methods on AAPL.
The greatest equity difference was below 0.000000000003 price units. These checks
validate arithmetic and tested timing invariance; they are not execution-quality
or statistically significant profitability tests.

This old static dataset has selection/survivorship bias, no independent corporate
action audit, and no modern market regimes after February 2018. Daily OHLC cannot
recover within-bar price order, executable spreads, liquidity or short availability.
The original small sample used a different bar frequency, so this run tests daily
bars rather than proving equivalent intraday behaviour. Further evaluation should
use a newer point-in-time universe with explicit adjustment/dividend conventions,
and reserve a genuinely untouched period for any subsequent parameter choices.

## Pull request upload

The changes-only archive is relative to the root of the supplied repository and
contains a single `swingpoints_project` folder. On the desired GitHub branch, open
the repository root, select Add file → Upload files, and drag that folder in.
Do not upload it from inside `swingpoints_project`, which would nest the folder.
Check that paths begin with `swingpoints_project/backtest.py` and
`swingpoints_project/swingpoints/backtesting.py`, then commit and open the PR.

## References

1. Cam Nugent. S&P 500 stock data. Kaggle. https://www.kaggle.com/datasets/camnugent/sandp500
2. Backtrader. Order Management and Execution, market orders. https://www.backtrader.com/docu/order-creation-execution/order-creation-execution/
3. SEC Office of Investor Education and Advocacy. Investor Bulletin: Performance Claims. https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-47

The runner does not depend on or claim result equivalence with Backtrader; its
documentation supports the next-observed-Open timing convention. The existing
project engine supplies the actual calculations.
