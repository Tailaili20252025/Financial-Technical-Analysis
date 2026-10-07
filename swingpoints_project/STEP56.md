# Steps 5–6: trade entry, fixed exits and profit/loss

This is an incremental extension of the supplied unified application. The four
swing strategies still share candidate trendlines (Step 3) and confirmed breakout
events (Step 4). `trading.py` consumes those events for all four methods. The
original datasets, swing algorithms, trendline rules, breakout rules and eight
indicators are retained.

## 1. Rules from the two slides

| Confirmed Step 4 event | Entry | Stop-loss level | Take-profit level |
| --- | --- | --- | --- |
| Breakout above falling resistance | **Buy / open long** | Below entry | Above entry |
| Breakdown below rising support | **Sell / open short** | Above entry | Below entry |

Sell in this application means **opening a short position**, not selling an
existing holding. A later decline earns money for a short. Only one position is
held at a time, so confirming several overlapping lines does not multiply trades.

The default `confirmation_close` mode models the slide's entry at time **t** as a
fill at the **confirmation bar's Close**. This is an idealised historical fill,
not a guarantee of execution at a price already used to observe confirmation.
The candidate crossing may be earlier than t: with two-bar confirmation, it is
the second qualifying close that permits entry. It is never the trendline's
geometrical price or the first candidate Close.

The report's `next_open` execution convention is also available: decide at the
confirmation Close and fill at the next observed bar's Open. A signal on the last
bar then stays queued with no invented fill. `entry_phase` and `exit_phase`
distinguish Open, Close and intrabar fills; timestamps identify input bars.

The report proposed long-only and optional early exits. To follow the slides,
this delivery enables **both Buy and Sell** by default and exits on **stop/target**.
`--long-only`, `--exit-on-false-break` and `--exit-on-opposite` expose those report
choices explicitly. Optional signal exits execute at the next Open and do not
automatically reverse the position.

## 2. Choosing and freezing the two exit prices

The slides specify where the levels sit, but do not give their numerical distance.
The report supplies the implementation: reuse Wilder ATR to scale the stop.

| Symbol / attribute | Definition | Default |
| --- | --- | --- |
| E | Actual entry fill price, after any configured slippage | From data |
| A / `atr_period` | ATR available at the confirmation Close | 14 observed bars |
| k / `atr_stop_multiple` | Stop-distance multiplier | 2 |
| R = k × A | Planned risk per unit, in input price units | Calculated |
| m / `reward_risk_multiple` | Target distance divided by stop distance | 2 |
| q / `quantity` | Fixed units/shares per trade | 1 |
| `initial_equity` | Starting account value in the same currency/units | 10,000 |

Long: **stop = E − R; target = E + mR**.
Short: **stop = E + R; target = E − mR**.

ATR uses True Range = max(High − Low, |High − previous Close|,
|Low − previous Close|). The first bar uses High − Low. The first 14 ranges seed
an arithmetic mean; subsequent values use Wilder smoothing. A, stop and target
are frozen for each trade. Later swings do not move them. Missing/nonpositive ATR,
nonpositive computed levels or insufficient equity cause a documented skip.
The 2× ATR stop and 2:1 reward/risk are starting parameters, not optimized values.

## 3. Bar processing and causality

1. At the new bar's Open, execute any queued exit and then a queued entry.
2. Check existing protection. A long stops when Low reaches the stop; a short
   stops when High reaches it. The target conditions reverse those comparisons.
3. If Open gaps beyond a stop, use Open as the stop fill. For a target reached at
   Open, use the target price conservatively. If neither level was passed at Open
   and High/Low touch both in the same bar, choose **stop first** and set
   `ambiguous_exit=true`: OHLC does not reveal the intrabar sequence.
4. At Close, process newly confirmed signals and optional false/opposite exits.
   A Close entry cannot use the same bar's earlier High/Low to claim an exit.
   An Open entry can use its own bar's later High/Low.
5. Mark any remaining open position at Close and append an equity row.

Entries do not consult an event's eventual `outcome`. A trade can enter and later
become associated with a false break; it remains in the history. With the optional
false-break exit enabled, only the failure time of the primary line queues an exit.
The default ignores that label for exiting and retains the pictured fixed levels.

Same-time, same-direction confirmations become one decision retaining all source
line IDs. The earliest-created line, then lexical line ID, supplies the primary
reference. Opposing signals when flat are skipped; signals while a position is
open are logged as `position_open`. Previously skipped signals are not retried.
Only all accepted **Close** trendlines supply trades; chart ranking is not a trade
filter. High/Low basis reports `not_supported_high_low`, as Step 4 already does.

Open is required on every supplied bar for gap execution. Missing Open produces
`unavailable_missing_open` for the trade module; Steps 1–4 still run. No Open is
substituted with Close. A replay cutoff recalculates only the observed prefix.

## 4. Profit/loss and account value

Let X be the exit fill and d be +1 for a long or −1 for a short.

- Gross realised P/L = **d × q × (X − E)**.
- Net realised P/L = gross realised P/L − entry fee − exit fee − borrow charges.
- Open gross P/L = **d × q × (latest Close − E)**.
- Open net P/L subtracts costs already incurred, without an unfilled exit fee.
- Equity = initial equity + closed net P/L + open net P/L.
- Closed-trade return (%) = 100 × net realised P/L ÷ (q × E).
- Win rate (%) = 100 × profitable closed trades ÷ all closed trades; no closed
  trades means unavailable, not zero accuracy.
- Drawdown (%) = 100 × (highest marked equity so far − current equity) ÷ highest
  marked equity so far. The peak includes starting equity. Maximum drawdown uses
  bar-Close marks, not unobserved intrabar equity extremes.

Example: Sell 10 units at E=500, A=10, k=2 gives stop 520 and target 460. At the
target, gross profit is 10×(500−460)=400. Two commissions of 5 leave net profit
390. At the stop, gross loss is 200 and net loss is 210, absent slippage/gaps.
This arithmetic fixture is tested independently of the supplied dataset.

`slippage_bps` applies once to market entries, stop fills and optional signal exits:
buy fill = reference × (1+s/10,000); sell fill = reference × (1−s/10,000). A target
uses its fixed limit, so no adverse target slippage is added. Commission is a fixed
`fee_per_order`. Short borrow is charged on entry notional using the configured
annual percentage and elapsed timestamp intervals / 365 days; this is a declared
approximation, not an exchange/broker billing model. Zero values assume zero cost.

Entry notional plus its fee must fit available account equity, on both sides.
Short-sale proceeds are not added as profit. There is no leverage, margin-call
model, liquidity model or live order submission. Positions still open at cutoff
remain open; no artificial last-bar liquidation is used.

## 5. Run it

From the `swingpoints_project` directory, with the existing virtual environment active:

```bash
python app.py data/data.csv --output output
python app.py data/data.csv --gui
```

Compare the report's next-Open fill with the slide fill:

```bash
python app.py data/data.csv --entry-timing next_open --output examples/step56_next_open
```

Change class attributes through CLI flags; trade ATR/EMA are independent of the
swing ATR and indicator-dashboard periods:

```bash
python app.py data/data.csv --quantity 2 --trade-atr-period 14 --atr-stop-multiple 1.5 --reward-risk-multiple 2 --slippage-bps 5 --fee-per-order 0.1 --output my_trade_test
python app.py data/data.csv --entry-timing next_open --exit-on-false-break --exit-on-opposite --output report_rules
python run_methods.py data/data.csv --output examples/step56_methods
```

`run_methods.py` accepts the same trade flags for every strategy. Existing method
parameter sweeps remain available; hold trading settings constant for comparisons.
Use `--no-trades` to disable the simulation and keep the other stages.

Python API:

```python
from swingpoints.data import load_prices
from swingpoints.methods import create_method
from swingpoints.pipeline import analyze
from swingpoints.trading import TradeSettings

settings = TradeSettings(entry_timing="next_open", quantity=1,
                         atr_period=14, atr_stop_multiple=2, reward_risk_multiple=2)
result = analyze(load_prices("data/data.csv"), create_method("ta"), trade_settings=settings)
print(result.trading.summary())
```

## 6. GUI and files

**Step 5–6 settings** changes attributes and recalculates the visible prefix.
**Trade chart** shows Buy/Sell markers and red stop/green target areas, matching
the slides. **Equity / P&L** shows marked account value, realised/open P/L and
drawdown. The **Steps 5–6: trades** tab lists exact levels, prices and outcomes;
double-click a trade row for its individual chart. **Entry decisions** explains
skipped or waiting signals. Both tables scroll horizontally.

**Observed bars → Apply / replay → Next bar** works for all stages. New chart
windows are snapshots; reopen them after replay to see the new cutoff. **Export
visible results** uses the applied snapshot even if a control was edited later.
Tk still requires a desktop and working `python -m tkinter`; there is no new pip
dependency. See README's Tkinter section for the existing installation steps.

Every normal run writes 20 files. The original 12 are retained, plus:

| New file | Contents |
| --- | --- |
| `trades.csv`, `trades.json` | Filled positions; source lines, signal/fill times, fixed levels, fees and realised/open P/L |
| `trades.png` | All filled trades on the price chart, with stop/target zones |
| `equity.csv`, `equity.json` | One account mark and drawdown per observed bar |
| `equity.png` | Account equity, realised/open P/L and drawdown |
| `trade_signals.csv`, `trade_signals.json` | Grouped confirmations, fill/queue status and reasons for skips |

`run_summary.json` now contains `trading`, including all applied settings,
execution assumptions, win rate, drawdown and pending-entry count. CSV blanks and
JSON null represent unavailable values. Bar numbers are one-based in all exports.

## 7. Evidence and limits

`STEP56_RESULTS.md` records runs on the original 374-row `data/data.csv`, with
unchanged input bytes. `STEP56_TEST_RESULTS.txt` records the complete test suite.
Tests check both entry modes, both directions, gaps, same-bar ambiguity, costs,
capital, warm-up, duplicates, optional exits, open positions, exported values and
prefix consistency across all four swing methods. Tk callbacks are tested with
mock widgets and real analysis; this environment has no desktop display for an
interactive Mac window test.

The two supplied slides determine entry direction and the relative exit levels.
The supplied *Trade Entry and Profit or Loss* report supplies the ATR, timing and
accounting conventions, with the default-mode differences stated above. ATR's
volatility interpretation is consistent with
[Fidelity's ATR guide](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr).
The numerical settings are project choices. One historical session and idealised
fills establish neither predictive accuracy nor future profitability.
