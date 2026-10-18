"""Chronological backtests around the application's shared analysis services.

Each test block starts flat. Earlier bars warm up indicators and line detection,
but only confirmations inside the block can open positions. Final open positions
are marked, not force-liquidated. No parameter fitting or future line ranking is
performed by this module.
"""
from dataclasses import asdict, dataclass, replace
from datetime import date
from decimal import Decimal
from math import isclose

from .breakouts import BreakoutSettings
from .methods import create_method
from .pipeline import analyze
from .trading import TradeSettings, simulate_trades
from .trendlines import TrendSettings


@dataclass(frozen=True)
class TestPeriod:
    """Inclusive calendar boundaries for one independently funded test block."""
    name: str  # Stable ID in exported run keys; no separators are allowed.
    start: str  # ISO date; first available session on or after this date is used.
    end: str  # ISO date; final available session on or before this date is used.

    def __post_init__(self):
        """Validate boundaries before a test consumes historical data."""
        if not self.name or not all(c.isalnum() or c in "_-" for c in self.name):
            raise ValueError("Period name must contain only letters, numbers, '_' or '-'")
        if date.fromisoformat(self.start) > date.fromisoformat(self.end):
            raise ValueError("Period start must precede end")


@dataclass
class PreparedBlock:
    """One causal Steps 1-4 replay, reusable across trading-cost scenarios."""
    period: TestPeriod  # Requested evaluation dates.
    bars: list  # History through the test cutoff; excludes every later bar.
    start_index: int  # First evaluated bar; earlier bars are warm-up only.
    analysis: object  # Existing AnalysisResult with ALL candidate lines/events.
    events: list  # Confirmed events eligible to open a trade in this block.


def prepare_block(bars, period, method, trend_settings=None, breakout_settings=None,
                  minimum_warmup_bars=200):
    """Replay through a cutoff and forbid entries from warm-up confirmations.

    Returns:
        PreparedBlock retaining original indices for causal ATR calculation.
    Raises:
        ValueError: Invalid OHLC history, insufficient warm-up or empty period.
    """
    if isinstance(minimum_warmup_bars, bool) or not isinstance(minimum_warmup_bars, int) or minimum_warmup_bars < 0:
        raise ValueError("minimum_warmup_bars must be a nonnegative integer")
    prefix = [b for b in bars if b.timestamp.date() <= date.fromisoformat(period.end)]
    if not prefix:
        raise ValueError("No observations before test end")
    # Reuse the trade engine's strict OHLC/time validation without opening trades.
    simulate_trades(prefix, [], TradeSettings(enabled=False))
    if any(b.open is None for b in prefix):
        raise ValueError("Backtesting requires Open prices for next-session execution")
    start = next((i for i, b in enumerate(prefix) if b.timestamp.date() >= date.fromisoformat(period.start)), None)
    if start is None:
        raise ValueError("No observations inside test period")
    if start < minimum_warmup_bars:
        raise ValueError(f"Need {minimum_warmup_bars} warm-up bars; found {start}")
    if method.basis != "close":
        raise ValueError("Step 4 and the trade backtest currently require basis='close'")
    analysis = analyze(prefix, method, trend_settings, breakout_settings)
    events = eligible_events(analysis.events, start)
    return PreparedBlock(period, prefix, start, analysis, events)


def eligible_events(events, start_index):
    """Retain confirmations in the block, including ones that later fail.

    A warm-up candidate may confirm inside the block. An already confirmed
    warm-up event cannot produce a new test entry. Future failure is not a filter.
    """
    return [e for e in events if e.confirmation_index is not None and e.confirmation_index >= start_index]


def buy_and_hold(bars, settings):
    """Buy the same quantity at first test Open and mark each test Close.

    Entry commission and adverse buy slippage apply. There is no exit order and
    therefore no exit fee. Dividends and interest are excluded from both arms.
    Raises ValueError if this unlevered position cannot be funded.
    """
    if not bars or bars[0].open is None:
        raise ValueError("Buy-and-hold needs a first Open")
    entry = bars[0].open * (1 + settings.slippage_bps / 10000)
    if entry * settings.quantity + settings.fee_per_order > settings.initial_equity:
        raise ValueError("Buy-and-hold quantity exceeds initial capital")
    return [dict(timestamp=b.timestamp.isoformat(),
                 equity=settings.initial_equity + settings.quantity * (b.close-entry) - settings.fee_per_order)
            for b in bars]


def maximum_drawdown(values, initial):
    """Largest percentage fall from starting capital or a later equity high."""
    peak, largest = initial, 0.0
    for value in values:
        peak = max(peak, value)
        largest = max(largest, 100 * (peak-value) / peak)
    return largest


def simulate_block(block, settings, symbol, scenario):
    """Simulate a prepared block and return its ledger, equity and exact metrics."""
    if settings.entry_timing != "next_open" or not settings.enabled:
        raise ValueError("Backtest requires enabled next_open execution")
    result = simulate_trades(block.bars, block.events, settings, block.analysis.method.key,
                             block.analysis.method.basis)
    if result.status != "enabled":
        raise ValueError("Backtest unavailable: " + result.status)
    equity = result.equity[block.start_index:]
    benchmark = buy_and_hold(block.bars[block.start_index:], settings)
    closed = [t for t in result.trades if t.exit_index is not None]
    wins = sum(t.net_pnl > 0 for t in closed)
    gross_profits = sum(max(t.net_pnl, 0) for t in closed)
    gross_losses = -sum(min(t.net_pnl, 0) for t in closed)
    basic = result.summary()
    net = basic["realized_net_pnl"] + basic["unrealized_net_pnl"]
    bh_net = benchmark[-1]["equity"] - settings.initial_equity
    summary = dict(
        run_id=f"{symbol}:{block.period.name}:{block.analysis.method.key}:{scenario}",
        symbol=symbol, period=block.period.name, method=block.analysis.method.key, scenario=scenario,
        requested_start=block.period.start, requested_end=block.period.end,
        first_date=block.bars[block.start_index].timestamp.date().isoformat(),
        last_date=block.bars[-1].timestamp.date().isoformat(),
        warmup_bars=block.start_index, test_bars=len(equity),
        initial_equity=settings.initial_equity, quantity=settings.quantity,
        slippage_bps=settings.slippage_bps, fee_per_order=settings.fee_per_order,
        short_borrow_rate_percent=settings.short_borrow_rate_percent,
        filled_trades=len(result.trades), closed_trades=len(closed), open_trades=len(result.trades)-len(closed),
        long_trades=basic["long_trades"], short_trades=basic["short_trades"], winning_trades=wins,
        realized_net_pnl=basic["realized_net_pnl"], unrealized_net_pnl=basic["unrealized_net_pnl"],
        net_pnl=net, final_equity=equity[-1]["equity"],
        account_return_percent=100*net/settings.initial_equity,
        win_rate_percent=100*wins/len(closed) if closed else None,
        profit_factor=gross_profits/gross_losses if gross_losses else None,
        gross_winning_pnl=gross_profits, absolute_losing_pnl=gross_losses,
        max_drawdown_percent=maximum_drawdown([e["equity"] for e in equity], settings.initial_equity),
        explicit_costs=sum(t.total_costs for t in result.trades),
        ambiguous_exits=basic["ambiguous_exits"], pending_entries=basic["pending_entries"],
        skipped_entries=sum(basic["skipped_entries"].values()),
        buy_hold_net_pnl=bh_net, buy_hold_return_percent=100*bh_net/settings.initial_equity,
        buy_hold_max_drawdown_percent=maximum_drawdown([r["equity"] for r in benchmark], settings.initial_equity),
        excess_pnl_vs_buy_hold=net-bh_net, cash_net_pnl=0.0,
        bars_with_position_at_close=sum(e["open_trade_id"] is not None for e in equity),
    )
    return result, summary, equity, benchmark


def audit_result(bars, start_index, result, summary):
    """Independently reconstruct each closing equity with Decimal arithmetic.

    Recomputes borrow from timestamps, not the engine's accumulated borrow field.
    Fails on timing leakage or a discrepancy above 0.000001 input-currency units.
    This validates bookkeeping, not the realism of fills or source adjustments.
    """
    d = lambda value: Decimal(str(value))
    settings = result.settings
    initial = d(settings.initial_equity)
    maximum_error = Decimal(0)
    for t in result.trades:
        if t.signal_index < start_index or t.entry_index != t.signal_index + 1:
            raise AssertionError("Warm-up entry or same-close execution detected")
        if t.exit_index is not None and t.exit_index < t.entry_index:
            raise AssertionError("Exit before entry")
    for i in range(start_index, len(bars)):
        expected = initial
        for t in result.trades:
            if t.entry_index > i:
                continue
            closed = t.exit_index is not None and t.exit_index <= i
            end_index = t.exit_index if closed else i
            price = t.exit_price if closed else bars[i].close
            elapsed = d((bars[end_index].timestamp-bars[t.entry_index].timestamp).total_seconds())
            borrow = (d(t.quantity)*d(t.entry_price)*d(settings.short_borrow_rate_percent)/100
                      *elapsed/d(365*24*3600)) if t.side == "short" else Decimal(0)
            fees = d(t.entry_fee) + (d(t.exit_fee) if closed else Decimal(0))
            expected += d(t.sign)*d(t.quantity)*(d(price)-d(t.entry_price))-fees-borrow
        error = abs(expected-d(result.equity[i]["equity"]))
        maximum_error = max(maximum_error, error)
        if error > Decimal("0.000001"):
            raise AssertionError(f"Independent equity audit failed at bar {i+1}: {error}")
    components = summary["realized_net_pnl"] + summary["unrealized_net_pnl"]
    if not isclose(summary["final_equity"]-settings.initial_equity, components, abs_tol=1e-8):
        raise AssertionError("Final P/L does not reconcile")
    return dict(run_id=summary["run_id"], checked_bars=len(bars)-start_index,
                checked_trades=len(result.trades), maximum_equity_error=float(maximum_error), passed=True)


def audit_prefix(block, settings, result):
    """Repeat detection on a shorter real-data prefix and compare earlier equity.

    Final open-trade marks and later event outcomes may change, but prices, fills
    and equity already observed at the midpoint must not change.
    """
    end = block.start_index + max(1, (len(block.bars)-block.start_index)//2)
    bars = block.bars[:end]
    analysis = analyze(bars, block.analysis.method, block.analysis.trend_settings,
                       block.analysis.breakout_settings)
    events = eligible_events(analysis.events, block.start_index)
    shorter = simulate_trades(bars, events, settings, block.analysis.method.key)
    def signatures(items):
        return sorted((e.line_id, e.direction, e.created_index, e.candidate_index, e.confirmation_index)
                      for e in items if e.confirmation_index is not None and e.confirmation_index < end)
    if signatures(events) != signatures(block.events):
        raise AssertionError("Confirmed events changed with future bars")
    for a, b in zip(shorter.equity, result.equity):
        if a["timestamp"] != b["timestamp"] or not isclose(a["equity"], b["equity"], abs_tol=1e-8):
            raise AssertionError("Historical equity changed with future bars")
    return dict(period=block.period.name, method=block.analysis.method.key,
                cutoff=bars[-1].timestamp.isoformat(), checked_bars=end-block.start_index, passed=True)


def aggregate_portfolio(summaries, equity_by_symbol, benchmark_by_symbol):
    """Add independently funded stock accounts with aligned observed calendars.

    The result is one method/scenario/block portfolio. Drawdown is calculated on
    the sum of equity paths, never averaged from individual stock drawdowns.
    """
    if not summaries:
        raise ValueError("Cannot aggregate an empty portfolio")
    identities = {(s["period"], s["method"], s["scenario"]) for s in summaries}
    if len(identities) != 1 or len({s["symbol"] for s in summaries}) != len(summaries):
        raise ValueError("Aggregate one period/method/scenario with unique symbols")
    dates = [r["timestamp"] for r in next(iter(equity_by_symbol.values()))]
    for s in summaries:
        symbol = s["symbol"]
        if ([r["timestamp"] for r in equity_by_symbol[symbol]] != dates or
                [r["timestamp"] for r in benchmark_by_symbol[symbol]] != dates):
            raise ValueError("Portfolio calendars differ; do not silently fill prices")
    initial = sum(s["initial_equity"] for s in summaries)
    curves = []
    for i, timestamp in enumerate(dates):
        e = sum(equity_by_symbol[s["symbol"]][i]["equity"] for s in summaries)
        b = sum(benchmark_by_symbol[s["symbol"]][i]["equity"] for s in summaries)
        curves.append(dict(timestamp=timestamp, equity=e, net_pnl=e-initial,
                           buy_hold_equity=b, buy_hold_net_pnl=b-initial, cash_equity=initial))
    period, method, scenario = next(iter(identities))
    additive = ["filled_trades", "closed_trades", "open_trades", "winning_trades", "long_trades", "short_trades",
                "realized_net_pnl", "unrealized_net_pnl", "net_pnl", "explicit_costs", "ambiguous_exits",
                "pending_entries", "gross_winning_pnl", "absolute_losing_pnl", "buy_hold_net_pnl"]
    totals = {k: sum(s[k] for s in summaries) for k in additive}
    closed = totals["closed_trades"]
    totals.update(period=period, method=method, scenario=scenario, stocks=len(summaries),
                  initial_equity=initial, final_equity=curves[-1]["equity"],
                  first_date=summaries[0]["first_date"], last_date=summaries[0]["last_date"],
                  account_return_percent=100*totals["net_pnl"]/initial,
                  buy_hold_return_percent=100*totals["buy_hold_net_pnl"]/initial,
                  excess_pnl_vs_buy_hold=totals["net_pnl"]-totals["buy_hold_net_pnl"],
                  win_rate_percent=100*totals["winning_trades"]/closed if closed else None,
                  profit_factor=totals["gross_winning_pnl"]/totals["absolute_losing_pnl"] if totals["absolute_losing_pnl"] else None,
                  max_drawdown_percent=maximum_drawdown([r["equity"] for r in curves], initial),
                  buy_hold_max_drawdown_percent=maximum_drawdown([r["buy_hold_equity"] for r in curves], initial),
                  profitable_stocks=sum(s["net_pnl"] > 0 for s in summaries),
                  stocks_beating_buy_hold=sum(s["net_pnl"] > s["buy_hold_net_pnl"] for s in summaries))
    return totals, curves


def validate_plan(plan):
    """Fail early on unsupported, overlapping or ambiguous experiment settings."""
    required = {"data_dir", "symbols", "periods", "minimum_warmup_bars", "methods", "trend_settings",
                "breakout_settings", "trade_settings", "cost_scenarios", "prefix_audit_symbols"}
    if set(plan) != required:
        raise ValueError(f"Plan fields must be {sorted(required)}")
    for key in ("symbols", "periods", "methods", "cost_scenarios"):
        if not plan[key]:
            raise ValueError(f"{key} cannot be empty")
    symbols = plan["symbols"]
    if len(set(symbols)) != len(symbols) or any(not isinstance(s, str) or not s or
            not all(c.isalnum() or c in "._-" for c in s) or s in (".", "..") for s in symbols):
        raise ValueError("Symbols must be unique safe filenames")
    if not set(plan["prefix_audit_symbols"]) <= set(symbols):
        raise ValueError("Prefix-audit symbols must belong to the experiment")
    periods = [TestPeriod(**p) for p in plan["periods"]]
    if len({p.name for p in periods}) != len(periods):
        raise ValueError("Duplicate period name")
    for earlier, later in zip(periods, periods[1:]):
        if earlier.end >= later.start:
            raise ValueError("Periods must be chronological and nonoverlapping")
    warm = plan["minimum_warmup_bars"]
    if isinstance(warm, bool) or not isinstance(warm, int) or warm < 0:
        raise ValueError("minimum_warmup_bars must be a nonnegative integer")
    methods = [create_method(m["name"], **m["attributes"]) for m in plan["methods"]]
    if len({m.key for m in methods}) != len(methods) or any(m.basis != "close" for m in methods):
        raise ValueError("Use each method once, with Close basis")
    trend, breakout = TrendSettings(**plan["trend_settings"]), BreakoutSettings(**plan["breakout_settings"])
    scenarios = []
    cost_keys = {"name", "slippage_bps", "fee_per_order", "short_borrow_rate_percent"}
    for scenario in plan["cost_scenarios"]:
        if set(scenario) != cost_keys or not scenario["name"] or not all(c.isalnum() or c in "_-" for c in scenario["name"]):
            raise ValueError("Invalid cost scenario")
        settings = TradeSettings(**{**plan["trade_settings"], **{k: v for k, v in scenario.items() if k != "name"}})
        if settings.entry_timing != "next_open" or not settings.enabled:
            raise ValueError("Use enabled next_open trading for this backtest")
        scenarios.append((scenario["name"], settings))
    if len({name for name, _ in scenarios}) != len(scenarios):
        raise ValueError("Duplicate scenario name")
    return periods, methods, trend, breakout, scenarios
