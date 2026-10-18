"""Public-API Backtesting.py adapter with causal Open/Close phase expansion.

An Open-only synthetic row reveals only the current Open. The next row exposes
the completed original OHLC range. A decision made at the previous Close may
submit a market entry with fixed brackets during the Open phase; Backtesting.py
then fills it at the same original Open and evaluates its SL/TP in the range row.
This is an ordering device, NOT inferred ticks or extra market observations.
No private broker method is patched and no native simulator trades are replayed.
"""
from dataclasses import dataclass
from importlib.metadata import version
import warnings

from ..indicators import atr
from .common import EngineResult, validate_inputs


@dataclass(frozen=True)
class OrderTag:
    """Provenance and frozen exits passed through Backtesting.py's public tag API."""
    signal_index: int  # Original confirmation bar; only this bar's ATR is used.
    line_ids: tuple  # Deterministically sorted same-direction confirming lines.
    stop: float  # Fixed absolute stop trigger from the actual opening price.
    target: float  # Fixed absolute profit-target trigger.


def phase_frame(bars):
    """Return two rows per real bar, without leaking its range into the Open row.

    RangeIndex is intentional: phase indices are not timestamps or independent
    bars. Only original closing equity is exported; synthetic annualized Sharpe,
    duration and framework benchmark statistics must never be reported.
    """
    import pandas as pd
    records = []
    for i, b in enumerate(bars):
        records.append(dict(Open=b.open, High=b.open, Low=b.open, Close=b.open,
                            Volume=0.0, original_index=i, phase=0))
        records.append(dict(Open=b.open, High=b.high, Low=b.low, Close=b.close,
                            Volume=float("nan") if b.volume is None else b.volume,
                            original_index=i, phase=1))
    return pd.DataFrame.from_records(records)


class BacktestingPyEngine:
    """Independent broker simulation using Backtesting.py 0.6.5."""
    def __init__(self):
        """Load optional dependencies only when the alternative is requested."""
        try:
            from backtesting import Backtest, Strategy
        except ImportError as exc:
            raise RuntimeError("Install the optional engine: python -m pip install -r requirements-engines.txt") from exc
        if version("backtesting") != "0.6.5":
            raise RuntimeError("This adapter is validated against backtesting==0.6.5; install requirements-engines.txt")
        self.backtest_type, self.strategy_type = Backtest, Strategy

    def run(self, bars, events, settings, method="ta"):
        """Fill Step 4 decisions independently, leaving cutoff positions open.

        Settings match next-Open, whole-share, single-position trading. Native
        limit improvement at a favourable gap is retained and reported; it is
        not silently rewritten to the application's conservative target fill.
        """
        events = list(events)
        validate_inputs(bars, events)
        by_signal = {}
        for event in events:
            if event.confirmation_index is not None:
                by_signal.setdefault(event.confirmation_index, []).append(event)
        for group in by_signal.values():
            group.sort(key=lambda e: (e.created_index, e.line_id))
        atr_values = atr(bars, settings.atr_period)
        frame = phase_frame(bars)
        decisions, submitted = [], []

        class ConfirmedEventStrategy(self.strategy_type):
            """Translate observed decisions to orders; the framework owns fills."""
            def init(self):
                """Start flat with no future order queued."""
                self.pending = None

            def next(self):
                """Reveal an Open, submit eligible brackets, then process Close signals."""
                i, phase = int(self.data.original_index[-1]), int(self.data.phase[-1])
                if phase == 0:
                    if self.pending is None:
                        return
                    signal, group, decision = self.pending
                    self.pending = None
                    side = 1 if group[0].direction == "breakout" else -1
                    price = float(self.data.Open[-1])
                    risk = settings.atr_stop_multiple*atr_values[signal]
                    stop, target = price-side*risk, price+side*settings.reward_risk_multiple*risk
                    from math import isfinite
                    if any(not isfinite(v) or v <= 0 for v in (price, risk, stop, target)):
                        decision.update(status="skipped", reason="invalid_price_levels")
                        return
                    if price*settings.quantity+settings.fee_per_order > self.equity:
                        decision.update(status="skipped", reason="insufficient_equity")
                        return
                    tag = OrderTag(signal, tuple(e.line_id for e in group), stop, target)
                    order = (self.buy if side == 1 else self.sell)(size=settings.quantity,
                                                               sl=stop, tp=target, tag=tag)
                    submitted.append((tag, decision, order))
                    decision.update(status="submitted", reason="eligible_next_open")
                    return
                group = by_signal.get(i, [])
                if not group:
                    return
                directions = {e.direction for e in group}
                side = "mixed" if len(directions) > 1 else "long" if group[0].direction == "breakout" else "short"
                decision = dict(signal_index=i, side=side, line_ids=[e.line_id for e in group],
                                status="queued", reason="awaiting_next_open")
                decisions.append(decision)
                reason = ("position_open" if self.position else "opposing_signals" if side == "mixed" else
                          "short_disabled" if side == "short" and not settings.allow_short else
                          "atr_unavailable" if atr_values[i] is None or atr_values[i] <= 0 else None)
                if reason:
                    decision.update(status="skipped", reason=reason)
                else:
                    self.pending = (i, group, decision)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            bt = self.backtest_type(frame, ConfirmedEventStrategy, cash=settings.initial_equity,
                                    spread=0.0, commission=(settings.fee_per_order, 0.0),
                                    margin=1.0, trade_on_close=False, hedging=False,
                                    exclusive_orders=False, finalize_trades=False)
            stats = bt.run()
        # These underscore result keys are the documented Backtest.run result,
        # not broker internals. Strategy.trades/closed_trades are public APIs.
        strategy = stats["_strategy"]
        filled = list(strategy.closed_trades) + list(strategy.trades)
        trades = []
        tags = set()
        for t in sorted(filled, key=lambda t: t.entry_bar):
            tag = t.tag
            tags.add(tag)
            exited = t.exit_bar is not None
            entry, exit_index = t.entry_bar//2, None if not exited else t.exit_bar//2
            # Closed Trade.pl includes both commissions; open Trade.pl excludes
            # the already-debited entry commission, so report it explicitly.
            net = float(t.pl) if exited else float(t.pl)-settings.fee_per_order
            trades.append(dict(signal_index=tag.signal_index, entry_index=entry, exit_index=exit_index,
                               side="long" if t.is_long else "short", line_ids=list(tag.line_ids),
                               entry_price=float(t.entry_price), exit_price=None if not exited else float(t.exit_price),
                               quantity=abs(t.size), stop_price=tag.stop, target_price=tag.target,
                               fees=settings.fee_per_order*(2 if exited else 1), net_pnl=net,
                               exit_reason=None if not exited else "framework_bracket"))
        for tag, decision, order in submitted:
            decision.update(status="filled" if tag in tags else "skipped",
                            reason="confirmed" if tag in tags else "framework_rejected_order")
        equity = [float(x) for x in stats["_equity_curve"]["Equity"].iloc[1::2]]
        return EngineResult("backtesting_py", trades, equity, decisions,
                            sorted({str(w.message) for w in caught}))
