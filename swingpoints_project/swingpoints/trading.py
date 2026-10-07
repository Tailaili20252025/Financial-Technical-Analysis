"""Steps 5–6: chronological, single-position trade simulation from Step 4 events.

The slide mode fills at the confirmation Close (an idealised assumption). The
report mode queues entry for the next observed Open. Neither uses later failure
labels to reject an earlier signal. Stops/targets are fixed at entry; their first
eligible bar is after a Close fill or the same bar as an Open fill.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite

from .data import Bar
from .indicators import atr, ema


@dataclass(frozen=True)
class TradeSettings:
    """Editable strategy attributes; amounts use the input prices' currency/units."""
    enabled: bool = True  # False preserves Steps 1–4 and produces empty trade outputs.
    entry_timing: str = "confirmation_close"  # Slide assumption, or 'next_open'.
    allow_short: bool = True  # Slide Sell means open a short; False is long-only.
    quantity: float = 1.0  # Fixed positive units/shares per trade, not risk percentage.
    initial_equity: float = 10000.0  # Starting account value; no added short-sale cash.
    atr_period: int = 14  # Observed bars for Wilder ATR used only for trade stops.
    atr_stop_multiple: float = 2.0  # R = this multiple * ATR known at signal Close.
    reward_risk_multiple: float = 2.0  # Target distance = this multiple * R.
    slippage_bps: float = 0.0  # Adverse market-fill adjustment; 1 bp = 0.01%.
    fee_per_order: float = 0.0  # Fixed commission at each entry and each exit.
    short_borrow_rate_percent: float = 0.0  # Annual rate on entry notional, actual/365.
    ema_filter: bool = False  # Optional: long above EMA, short below EMA at signal.
    ema_period: int = 20  # Independent trade-filter period; warmed up before entry.
    exit_on_false_break: bool = False  # Optional report rule: next Open after failure.
    exit_on_opposite: bool = False  # Optional report rule; closes, never auto-reverses.

    def __post_init__(self):
        """Reject invalid configuration before a simulation writes any output."""
        for name in ("enabled", "allow_short", "ema_filter", "exit_on_false_break", "exit_on_opposite"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean")
        if self.entry_timing not in ("confirmation_close", "next_open"):
            raise ValueError("entry_timing must be confirmation_close or next_open")
        for name in ("atr_period", "ema_period"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        positive = ("quantity", "initial_equity", "atr_stop_multiple", "reward_risk_multiple")
        for name in (*positive, "slippage_bps", "fee_per_order", "short_borrow_rate_percent"):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value)
                    or value < 0 or (name in positive and value == 0)):
                raise ValueError(f"{name} must be finite and {'positive' if name in positive else 'nonnegative'}")
        if self.slippage_bps >= 10000:
            raise ValueError("slippage_bps must be below 10000")


@dataclass
class Trade:
    """One filled position; all indices are zero-based, exports use one-based bars."""
    trade_id: str  # Sequential stable ID in this method's chronological simulation.
    method: str  # Swing-method key, e.g. ta, percentage, atr or prominence.
    side: str  # 'long' for Buy, 'short' for Sell-to-open.
    line_ids: tuple[str, ...]  # Same-direction lines confirming together, primary first.
    candidate_index: int  # Candidate bar of the stable primary line.
    signal_index: int  # Confirmation Close when the entry decision became available.
    signal_price: float  # Actual confirmation Close, not the candidate or line price.
    entry_index: int  # Filled bar, distinct from signal in next_open mode.
    entry_phase: str  # 'close' or 'open'; timestamps identify bars, not intrabar seconds.
    entry_price: float  # Fill after adverse slippage.
    quantity: float  # Fixed number of units/shares.
    atr_at_signal: float  # Frozen ATR from the signal Close, never later prices.
    stop_price: float  # Fixed protective trigger (above a short / below a long).
    target_price: float  # Fixed favourable limit (below a short / above a long).
    entry_fee: float  # Commission charged at the fill.
    exit_index: int | None = None  # None while position remains open at cutoff.
    exit_phase: str | None = None  # open, intrabar, or None; intrabar order is assumed.
    exit_price: float | None = None  # Actual modelled exit fill; not a projected value.
    exit_reason: str | None = None  # take_profit, stop_loss, stop_gap, or optional signal exit.
    exit_fee: float = 0.0  # Zero until closed.
    borrow_cost: float = 0.0  # Accumulated elapsed-time short charge to exit/cutoff.
    ambiguous_exit: bool = False  # Both levels touched within a bar; stop-first chosen.
    mark_index: int | None = None  # Latest observed Close for an open position.
    mark_price: float | None = None  # Latest mark; no invented end-of-data liquidation.
    exit_signal_index: int | None = None  # Optional false/opposite Close that queues exit.
    pending_exit_reason: str | None = None  # Unfilled next-Open exit, if cutoff ends first.

    @property
    def sign(self):
        """Return +1 for a long, -1 for a short, for shared P/L arithmetic."""
        return 1 if self.side == "long" else -1

    @property
    def total_costs(self):
        """Return paid/incurred costs; slippage is already in the fill prices."""
        return self.entry_fee + self.exit_fee + self.borrow_cost

    @property
    def net_pnl(self):
        """Return realised net P/L for a closed trade, otherwise None."""
        if self.exit_price is None:
            return None
        return self.sign * self.quantity * (self.exit_price-self.entry_price) - self.total_costs

    @property
    def unrealized_pnl(self):
        """Return open net-to-date P/L, without charging an unfilled exit fee."""
        if self.exit_index is not None or self.mark_price is None:
            return None
        return self.sign * self.quantity * (self.mark_price-self.entry_price) - self.total_costs

    def as_record(self, bars):
        """Export timing, frozen levels and separate realised/unrealised amounts."""
        def time(index):
            """Resolve an observed bar timestamp; no future time is invented."""
            return None if index is None else bars[index].timestamp.isoformat()
        gross = None if self.exit_price is None else self.sign*self.quantity*(self.exit_price-self.entry_price)
        open_gross = (None if self.unrealized_pnl is None else self.unrealized_pnl+self.total_costs)
        return dict(
            trade_id=self.trade_id, method=self.method, side=self.side,
            action="BUY" if self.side == "long" else "SELL", status="open" if self.exit_index is None else "closed",
            primary_line_id=self.line_ids[0], line_ids=list(self.line_ids),
            candidate_bar=self.candidate_index+1, candidate_at=time(self.candidate_index),
            confirmation_bar=self.signal_index+1, confirmed_at=time(self.signal_index), signal_price=self.signal_price,
            entry_bar=self.entry_index+1, entry_at=time(self.entry_index), entry_phase=self.entry_phase,
            entry_price=self.entry_price, quantity=self.quantity, atr_at_signal=self.atr_at_signal,
            stop_price=self.stop_price, target_price=self.target_price,
            risk_per_unit=abs(self.entry_price-self.stop_price),
            planned_risk=self.quantity*abs(self.entry_price-self.stop_price),
            planned_reward=self.quantity*abs(self.target_price-self.entry_price),
            exit_bar=None if self.exit_index is None else self.exit_index+1, exit_at=time(self.exit_index),
            exit_phase=self.exit_phase, exit_price=self.exit_price, exit_reason=self.exit_reason,
            ambiguous_exit=self.ambiguous_exit, entry_fee=self.entry_fee, exit_fee=self.exit_fee,
            borrow_cost=self.borrow_cost, total_costs=self.total_costs,
            gross_pnl=gross, net_pnl=self.net_pnl,
            return_percent=None if self.net_pnl is None else 100*self.net_pnl/(self.quantity*self.entry_price),
            unrealized_gross_pnl=open_gross, unrealized_net_pnl=self.unrealized_pnl,
            marked_bar=None if self.mark_index is None else self.mark_index+1, marked_at=time(self.mark_index),
            mark_price=self.mark_price, exit_signal_bar=None if self.exit_signal_index is None else self.exit_signal_index+1,
            pending_exit_reason=self.pending_exit_reason)


TRADE_FIELDS = [
    "trade_id", "method", "side", "action", "status", "primary_line_id", "line_ids", "candidate_bar", "candidate_at",
    "confirmation_bar", "confirmed_at", "signal_price", "entry_bar", "entry_at", "entry_phase", "entry_price",
    "quantity", "atr_at_signal", "stop_price", "target_price", "risk_per_unit", "planned_risk", "planned_reward",
    "exit_bar", "exit_at", "exit_phase", "exit_price", "exit_reason", "ambiguous_exit", "entry_fee", "exit_fee",
    "borrow_cost", "total_costs", "gross_pnl", "net_pnl", "return_percent", "unrealized_gross_pnl",
    "unrealized_net_pnl", "marked_bar", "marked_at", "mark_price", "exit_signal_bar", "pending_exit_reason"]
SIGNAL_FIELDS = ["confirmation_bar", "confirmed_at", "side", "line_ids", "status", "reason", "trade_id", "fill_bar"]
EQUITY_FIELDS = ["bar", "timestamp", "close", "realized_net_pnl", "unrealized_net_pnl", "equity", "drawdown_percent", "open_trade_id"]


@dataclass
class TradingResult:
    """Pure calculation result used unchanged by CLI, GUI and export services."""
    settings: TradeSettings  # Exact applied settings, also exported for reproducibility.
    status: str = "enabled"  # disabled / not_supported_high_low / unavailable_missing_open.
    trades: list[Trade] = field(default_factory=list)  # Filled positions only.
    signals: list[dict] = field(default_factory=list)  # Deduplicated entry decisions and skip reasons.
    equity: list[dict] = field(default_factory=list)  # One mark-to-market row per observed bar.

    def summary(self):
        """Calculate account statistics; no-trade win rate remains undefined."""
        closed = [t for t in self.trades if t.exit_index is not None]
        skipped = {}
        for row in self.signals:
            if row["status"] == "skipped":
                skipped[row["reason"]] = skipped.get(row["reason"], 0)+1
        realized = sum(t.net_pnl for t in closed)
        unrealized = sum(t.unrealized_pnl for t in self.trades if t.exit_index is None)
        return dict(status=self.status, settings=asdict(self.settings), trades=len(self.trades),
                    closed_trades=len(closed), open_trades=len(self.trades)-len(closed),
                    long_trades=sum(t.side == "long" for t in self.trades),
                    short_trades=sum(t.side == "short" for t in self.trades),
                    realized_net_pnl=realized, unrealized_net_pnl=unrealized,
                    final_equity=self.settings.initial_equity+realized+unrealized,
                    account_return_percent=100*(realized+unrealized)/self.settings.initial_equity,
                    win_rate_percent=100*sum(t.net_pnl > 0 for t in closed)/len(closed) if closed else None,
                    max_drawdown_percent=max((r["drawdown_percent"] for r in self.equity), default=0),
                    ambiguous_exits=sum(t.ambiguous_exit for t in closed),
                    pending_entries=sum(r["status"] == "queued" for r in self.signals), skipped_entries=skipped,
                    entry_assumption=("Idealised confirmation-Close fill; not a guaranteed executable price. Protection begins on the next bar."
                                      if self.settings.entry_timing == "confirmation_close" else
                                      "Signal at confirmation Close; fill at next observed Open. No Open means no fill."),
                    exit_assumption="Fixed ATR stop and reward/risk target. Gap stop at Open; target at limit. Both intrabar levels: stop first.",
                    timestamp_convention="Timestamps identify input bars; entry_phase/exit_phase distinguish Open, Close and unknown intrabar time.",
                    capital_rule="One position, fixed quantity; entry notional plus entry fee must fit available equity; no leverage.",
                    costs_assumption="Configured commission/slippage; short borrow charged on entry notional by elapsed time using actual/365. Zero rates assume zero cost.",
                    interpretation="Historical simulation, not live order execution. An open position is marked at the cutoff, not forcibly closed.")


def simulate_trades(bars: list[Bar], events, settings=None, method="ta", basis="close") -> TradingResult:
    """Replay confirmed Step 4 events into trades and account P/L.

    Args:
        bars: Validated chronological observed prefix, with Open for gap handling.
        events: All Step 4 line events for this prefix; final outcomes are not entry filters.
        settings: TradeSettings; default follows the two supplied slides.
        method: Swing-method name for provenance; no method-specific trade rules.
        basis: Step 4 currently supports Close-based trendlines only.
    Returns:
        TradingResult including empty/disabled results, audit decisions and equity.
    Raises:
        ValueError: Inconsistent bars/events, or nonfinite arithmetic.

    Same-close/same-direction signals are one decision. Opposing signals when
    flat are skipped. One occupied position blocks additional entries. Optional
    false/opposite exits use the NEXT Open and never reverse automatically.
    """
    settings = settings or TradeSettings()
    result = TradingResult(settings)
    for i, bar in enumerate(bars):
        values = (bar.low, bar.high, bar.close) + (() if bar.open is None else (bar.open,))
        if any(not isfinite(v) or v <= 0 for v in values) or not bar.low <= bar.close <= bar.high:
            raise ValueError("Trading requires finite positive Low <= Close <= High")
        if bar.open is not None and not bar.low <= bar.open <= bar.high:
            raise ValueError("Trading requires Low <= Open <= High")
        if i and bar.timestamp <= bars[i-1].timestamp:
            raise ValueError("Trading bars must be chronological without duplicates")
    if not settings.enabled:
        result.status = "disabled"
    elif basis != "close":
        result.status = "not_supported_high_low"
    elif any(b.open is None for b in bars):
        result.status = "unavailable_missing_open"
    if result.status != "enabled":
        result.equity = [dict(bar=i+1, timestamp=b.timestamp.isoformat(), close=b.close, realized_net_pnl=0.0,
                            unrealized_net_pnl=0.0, equity=settings.initial_equity, drawdown_percent=0.0,
                            open_trade_id=None) for i, b in enumerate(bars)]
        return result
    events = list(events)
    by_signal, failures, seen = {}, {}, set()
    for event in events:
        if event.line_id in seen:
            raise ValueError("Duplicate Step 4 line ID")
        seen.add(event.line_id)
        if event.direction not in ("breakout", "breakdown"):
            raise ValueError("Unknown Step 4 direction")
        if not 0 <= event.created_index < event.candidate_index < len(bars):
            raise ValueError("Event candidate/creation is outside the observed prefix")
        if event.confirmation_index is not None:
            if not event.candidate_index <= event.confirmation_index < len(bars):
                raise ValueError("Event confirmation is outside the observed prefix")
            by_signal.setdefault(event.confirmation_index, []).append(event)
        if event.failure_index is not None:
            if not event.candidate_index < event.failure_index < len(bars):
                raise ValueError("Event failure is outside the observed prefix")
            if event.confirmation_index is not None and event.failure_index <= event.confirmation_index:
                raise ValueError("A failed event cannot later confirm")
            failures[event.line_id] = event.failure_index
    atr_values = atr(bars, settings.atr_period)
    ema_values = ema([b.close for b in bars], settings.ema_period) if settings.ema_filter else []
    position = pending_entry = None
    realized, peak = 0.0, settings.initial_equity

    def market_price(price, buy):
        """Apply adverse slippage once; target limit fills bypass this function."""
        return price*(1+(1 if buy else -1)*settings.slippage_bps/10000)

    def open_trade(i, signal_index, group, decision, phase):
        """Validate levels and capital at fill time, then create a fixed-level trade."""
        side = "long" if group[0].direction == "breakout" else "short"
        sign = 1 if side == "long" else -1
        price = market_price(bars[i].close if phase == "close" else bars[i].open, side == "long")
        risk = settings.atr_stop_multiple*atr_values[signal_index]
        stop, target = price-sign*risk, price+sign*settings.reward_risk_multiple*risk
        amounts = (price, risk, stop, target, settings.quantity*price)
        reason = ("invalid_price_levels" if any(not isfinite(v) or v <= 0 for v in amounts) else
                  "insufficient_equity" if settings.quantity*price+settings.fee_per_order > settings.initial_equity+realized else None)
        if reason:
            decision.update(status="skipped", reason=reason)
            return None
        trade = Trade(f"T{len(result.trades)+1:04d}", method, side, tuple(e.line_id for e in group),
                      group[0].candidate_index, signal_index, bars[signal_index].close, i, phase, price,
                      settings.quantity, atr_values[signal_index], stop, target, settings.fee_per_order)
        result.trades.append(trade)
        decision.update(status="filled", reason="confirmed", trade_id=trade.trade_id, fill_bar=i+1)
        return trade

    def close_trade(i, reference, reason, phase, ambiguous=False, limit=False):
        """Record an actual model fill and realise costs; no forced cutoff exit."""
        nonlocal position, realized
        trade = position
        trade.exit_index, trade.exit_phase = i, phase
        trade.exit_price = reference if limit else market_price(reference, trade.side == "short")
        trade.exit_reason, trade.ambiguous_exit = reason, ambiguous
        trade.exit_fee = settings.fee_per_order
        trade.mark_index = trade.mark_price = None
        trade.pending_exit_reason = None
        realized += trade.net_pnl
        position = None

    for i, bar in enumerate(bars):
        if position is not None and position.side == "short" and i > position.entry_index:
            elapsed = (bar.timestamp-bars[i-1].timestamp).total_seconds()
            position.borrow_cost += (position.quantity*position.entry_price*settings.short_borrow_rate_percent/100
                                     *elapsed/(365*24*60*60))
        if position is not None and position.pending_exit_reason:
            close_trade(i, bar.open, position.pending_exit_reason, "open")
        if pending_entry is not None:
            signal_index, group, decision = pending_entry
            position = open_trade(i, signal_index, group, decision, "open")
            pending_entry = None
        # Only prices occurring after the fill can trigger protection.
        if position is not None:
            t = position
            stop_gap = bar.open <= t.stop_price if t.side == "long" else bar.open >= t.stop_price
            target_gap = bar.open >= t.target_price if t.side == "long" else bar.open <= t.target_price
            stop_hit = bar.low <= t.stop_price if t.side == "long" else bar.high >= t.stop_price
            target_hit = bar.high >= t.target_price if t.side == "long" else bar.low <= t.target_price
            if stop_gap:
                close_trade(i, bar.open, "stop_gap", "open")
            elif target_gap:
                close_trade(i, t.target_price, "take_profit", "open", limit=True)
            elif stop_hit:
                close_trade(i, t.stop_price, "stop_loss", "intrabar", ambiguous=target_hit)
            elif target_hit:
                close_trade(i, t.target_price, "take_profit", "intrabar", limit=True)
        group = sorted(by_signal.get(i, []), key=lambda e: (e.created_index, e.line_id))
        directions = {e.direction for e in group}
        if position is not None:
            if settings.exit_on_false_break and failures.get(position.line_ids[0]) == i:
                position.pending_exit_reason = "false_break"
                position.exit_signal_index = i
            elif settings.exit_on_opposite and ("breakdown" if position.side == "long" else "breakout") in directions:
                position.pending_exit_reason = "opposite_signal"
                position.exit_signal_index = i
        if group:
            side = "mixed" if len(directions) > 1 else "long" if group[0].direction == "breakout" else "short"
            decision = dict(confirmation_bar=i+1, confirmed_at=bar.timestamp.isoformat(), side=side,
                            line_ids=[e.line_id for e in group], status="queued", reason="awaiting_next_open",
                            trade_id=None, fill_bar=None)
            result.signals.append(decision)
            reason = ("position_open" if position is not None else "opposing_signals" if side == "mixed" else
                      "short_disabled" if side == "short" and not settings.allow_short else
                      "atr_unavailable" if atr_values[i] is None or atr_values[i] <= 0 else None)
            if reason is None and settings.ema_filter:
                reason = ("ema_unavailable" if ema_values[i] is None else
                          "ema_filter" if (bar.close <= ema_values[i] if side == "long" else bar.close >= ema_values[i]) else None)
            if reason:
                decision.update(status="skipped", reason=reason)
            elif settings.entry_timing == "confirmation_close":
                position = open_trade(i, i, group, decision, "close")
            else:
                pending_entry = (i, group, decision)
        unrealized = 0.0
        if position is not None:
            position.mark_index, position.mark_price = i, bar.close
            unrealized = position.unrealized_pnl
        value = settings.initial_equity+realized+unrealized
        if not isfinite(value):
            raise ValueError("Trade arithmetic overflow; check input magnitudes/settings")
        peak = max(peak, value)
        result.equity.append(dict(bar=i+1, timestamp=bar.timestamp.isoformat(), close=bar.close,
                                 realized_net_pnl=realized, unrealized_net_pnl=unrealized, equity=value,
                                 drawdown_percent=100*(peak-value)/peak,
                                 open_trade_id=None if position is None else position.trade_id))
    return result
