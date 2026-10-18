"""Small adapter contract, input validation and independent accounting checks."""
from dataclasses import dataclass, field
from decimal import Decimal
from math import isclose, isfinite
from typing import Protocol


@dataclass(frozen=True)
class EngineSettings:
    """Common comparison settings, deliberately limited to matched capabilities.

    Prices and P/L use input units. No slippage, spread or short borrow is charged
    in this experiment; fee_per_order applies at both entry and exit. Unsupported
    options are rejected by construction instead of silently being ignored.
    """
    initial_equity: float = 10000.0  # Separate initial account value per stock/block.
    quantity: int = 1  # Absolute whole shares; not a fraction of account equity.
    allow_short: bool = True  # Permit breakdown signals to open short positions.
    atr_period: int = 14  # Wilder ATR history known at the signal Close.
    atr_stop_multiple: float = 2.0  # Fixed risk distance = this value times signal ATR.
    reward_risk_multiple: float = 2.0  # Fixed target distance as a multiple of risk.
    fee_per_order: float = 0.0  # Fixed commission per filled entry or exit order.

    def __post_init__(self):
        """Reject nonfinite settings and quantities with incompatible semantics."""
        for name in ("quantity", "atr_period"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, int) or v < 1:
                raise ValueError(name + " must be a positive integer")
        if not isinstance(self.allow_short, bool):
            raise ValueError("allow_short must be boolean")
        for name in ("initial_equity", "atr_stop_multiple", "reward_risk_multiple", "fee_per_order"):
            v = getattr(self, name)
            if (isinstance(v, bool) or not isinstance(v, (float, int)) or not isfinite(v)
                    or v < 0 or (name != "fee_per_order" and v == 0)):
                raise ValueError(name + " must be finite and positive (fees may be zero)")


@dataclass
class EngineResult:
    """Normalized records; prices/equity must come from the chosen engine."""
    engine: str  # Stable registry key.
    trades: list[dict]  # Closed and open trades, in entry order, using original indices.
    equity: list[float]  # One mark at each ORIGINAL bar Close, including warm-up.
    decisions: list[dict] = field(default_factory=list)  # Accepted/skipped signal audit.
    warnings: list[str] = field(default_factory=list)  # Captured third-party warnings.

    def summary(self, settings, start_index=0):
        """Report net marked P/L and closed-trade statistics over scored bars."""
        closed = [t for t in self.trades if t["exit_index"] is not None]
        opened = [t for t in self.trades if t["exit_index"] is None]
        realised = sum(t["net_pnl"] for t in closed)
        unrealised = sum(t["net_pnl"] for t in opened)
        wins = sum(t["net_pnl"] > 0 for t in closed)
        gain = sum(max(t["net_pnl"], 0) for t in closed)
        loss = -sum(min(t["net_pnl"], 0) for t in closed)
        return dict(engine=self.engine, filled_trades=len(self.trades), closed_trades=len(closed),
                    open_trades=len(opened), winning_trades=wins, realised_net_pnl=realised,
                    unrealised_net_pnl=unrealised, net_pnl=self.equity[-1]-settings.initial_equity,
                    final_equity=self.equity[-1], return_percent=100*(self.equity[-1]/settings.initial_equity-1),
                    max_drawdown_percent=maximum_drawdown(self.equity[start_index:], settings.initial_equity),
                    win_rate_percent=100*wins/len(closed) if closed else None,
                    profit_factor=gain/loss if loss else None,
                    fees=sum(t["fees"] for t in self.trades))


class ExecutionEngine(Protocol):
    """Adapter interface; implementations must own their order and equity state."""
    def run(self, bars, events, settings: EngineSettings, method="ta") -> EngineResult:
        """Replay a single instrument through the observed cutoff."""
        ...


def maximum_drawdown(values, initial):
    """Return the largest percentage fall from starting equity or a later peak."""
    peak, drawdown = initial, 0.0
    for value in values:
        peak = max(peak, value)
        drawdown = max(drawdown, 100*(peak-value)/peak)
    return drawdown


def validate_inputs(bars, events):
    """Validate observed OHLC bars and causal confirmation fields for both engines.

    Outcome/failure labels are not used for entry selection. Bars must include
    Open; never substitute the Close or impute a missing opening price.
    """
    if not bars:
        raise ValueError("At least one observed bar is required")
    for i, bar in enumerate(bars):
        values = (bar.open, bar.high, bar.low, bar.close)
        if any(v is None or not isfinite(v) or v <= 0 for v in values):
            raise ValueError("Comparison requires finite positive Open/High/Low/Close")
        if not bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high:
            raise ValueError("Inconsistent OHLC range")
        if i and bar.timestamp <= bars[i-1].timestamp:
            raise ValueError("Bars must have strictly increasing timestamps")
    seen = set()
    for event in events:
        if event.line_id in seen:
            raise ValueError("Duplicate Step 4 line ID")
        seen.add(event.line_id)
        if event.direction not in ("breakout", "breakdown"):
            raise ValueError("Unknown breakout direction")
        if not 0 <= event.created_index < event.candidate_index < len(bars):
            raise ValueError("Invalid event creation/candidate index")
        if event.confirmation_index is not None and not event.candidate_index <= event.confirmation_index < len(bars):
            raise ValueError("Confirmation is outside observed history")


def audit_accounting(bars, result, settings, start_index=0):
    """Reconstruct every original Close equity independently with Decimal.

    This checks each engine's returned fills and fees against its equity, not
    whether daily OHLC reveals the actual market's intrabar order of execution.
    """
    if len(result.equity) != len(bars):
        raise AssertionError("An engine omitted original Close equity rows")
    d = lambda x: Decimal(str(x))
    max_error = Decimal(0)
    previous_exit = -1
    for t in result.trades:
        if t["signal_index"] < start_index or t["entry_index"] != t["signal_index"]+1:
            raise AssertionError("Warm-up entry or wrong next-Open timing")
        if previous_exit is None or t["entry_index"] <= previous_exit:
            raise AssertionError("Overlapping positions")
        previous_exit = t["exit_index"]
        if not isclose(t["entry_price"], bars[t["entry_index"]].open, abs_tol=1e-9):
            raise AssertionError("Entry was not filled at next observed Open")
        expected_fee = settings.fee_per_order*(1+(t["exit_index"] is not None))
        if not isclose(t["fees"], expected_fee, abs_tol=1e-8):
            raise AssertionError("Wrong order commission")
    for i, bar in enumerate(bars):
        value = d(settings.initial_equity)
        for t in result.trades:
            if i < t["entry_index"]:
                continue
            closed = t["exit_index"] is not None and t["exit_index"] <= i
            mark = t["exit_price"] if closed else bar.close
            sign = 1 if t["side"] == "long" else -1
            value += sign*d(t["quantity"])*(d(mark)-d(t["entry_price"]))
            value -= d(settings.fee_per_order)*(2 if closed else 1)
        error = abs(value-d(result.equity[i]))
        max_error = max(error, max_error)
        if error > Decimal("0.000001"):
            raise AssertionError(f"{result.engine} equity mismatch at original bar {i}: {error}")
    total = d(settings.initial_equity) + sum((d(t["net_pnl"]) for t in result.trades), Decimal(0))
    if abs(total-d(result.equity[-1])) > Decimal("0.000001"):
        raise AssertionError("Final realised plus open P/L does not reconcile")
    return dict(engine=result.engine, checked_bars=len(bars), checked_trades=len(result.trades),
                maximum_error=float(max_error), passed=True)


def reconcile(reference, alternative, bars, tolerance=1e-7):
    """Explain native limit price improvement without changing either result.

    Only same-signal, same-entry/exit-time target fills improved to an observed
    opening gap qualify. Everything else is an explicit unexplained difference.
    Policy-adjusted equity is diagnostic only; it never drives future orders.
    """
    key = lambda t: (t["signal_index"], t["side"], tuple(t["line_ids"]))
    refs, alts = {key(t): t for t in reference.trades}, {key(t): t for t in alternative.trades}
    issues, gaps = [], []
    for k in sorted(refs.keys() | alts.keys()):
        r, a = refs.get(k), alts.get(k)
        if r is None or a is None:
            issues.append(dict(signal_index=k[0], side=k[1], reason="entry_set_differs"))
            continue
        for f in ("entry_index", "exit_index", "quantity"):
            if r[f] != a[f]:
                issues.append(dict(signal_index=k[0], side=k[1], reason=f+"_differs"))
        for f in ("entry_price", "stop_price", "target_price", "fees"):
            if not isclose(r[f], a[f], rel_tol=0, abs_tol=tolerance):
                issues.append(dict(signal_index=k[0], side=k[1], reason=f+"_differs"))
        if r["exit_index"] is None or a["exit_index"] is None:
            continue
        delta = a["net_pnl"]-r["net_pnl"]
        if abs(delta) <= tolerance:
            continue
        sign = 1 if r["side"] == "long" else -1
        index = r["exit_index"]
        improved_gap = (index == a["exit_index"] and delta > 0
                        and isclose(r["exit_price"], r["target_price"], abs_tol=tolerance, rel_tol=0)
                        and sign*(bars[index].open-r["target_price"]) > 0
                        and isclose(a["exit_price"], bars[index].open, abs_tol=tolerance, rel_tol=0))
        if improved_gap:
            gaps.append(dict(signal_index=k[0], side=k[1], exit_index=index,
                             target=r["target_price"], opening_price=bars[index].open,
                             reference_fill=r["exit_price"], alternative_fill=a["exit_price"],
                             gain=delta, quantity=r["quantity"]))
        else:
            issues.append(dict(signal_index=k[0], side=k[1], reason="unexplained_pnl", delta=delta))
    differences = [a-r for r,a in zip(reference.equity, alternative.equity)]
    residual = max((abs(delta-sum(g["gain"] for g in gaps if g["exit_index"] <= i))
                    for i,delta in enumerate(differences)), default=0.0)
    if residual > tolerance:
        issues.append(dict(reason="equity_difference_not_explained_by_target_gaps", maximum_error=residual))
    return dict(matched_entry_keys=len(refs.keys() & alts.keys()),
                reference_trades=len(refs), alternative_trades=len(alts),
                raw_pnl_difference=alternative.equity[-1]-reference.equity[-1],
                target_gap_gain=sum(g["gain"] for g in gaps), target_gap_count=len(gaps),
                maximum_policy_adjusted_equity_difference=residual,
                reconciled=not issues, unexplained=issues, target_gaps=gaps)
