"""Thin reference adapter. No copy of the existing trading algorithm lives here."""
from dataclasses import asdict
from .common import EngineResult, validate_inputs


class ApplicationEngine:
    """Call the application's actual Step 5–6 module when it is installed."""
    def __init__(self):
        """Fail clearly if the separate Step 5–6/backtesting PR is not merged."""
        try:
            from ..trading import TradeSettings, simulate_trades
        except ModuleNotFoundError as exc:
            if exc.name != "swingpoints.trading":
                raise
            raise RuntimeError("Reference comparison needs swingpoints/trading.py. Merge the Step 5–6 "
                               "or Backtesting_Changes_Only PR first, or run --engines backtesting_py.") from exc
        self.settings_type = TradeSettings
        self.simulator = simulate_trades

    def run(self, bars, events, settings, method="ta"):
        """Reuse the native simulator and normalize its independently filled trades."""
        events = list(events)
        validate_inputs(bars, events)
        cfg = self.settings_type(**asdict(settings), entry_timing="next_open")
        native = self.simulator(bars, events, cfg, method=method, basis="close")
        trades = [dict(signal_index=t.signal_index, entry_index=t.entry_index,
                       exit_index=t.exit_index, side=t.side, line_ids=list(t.line_ids),
                       entry_price=t.entry_price, exit_price=t.exit_price, quantity=t.quantity,
                       stop_price=t.stop_price, target_price=t.target_price, fees=t.total_costs,
                       net_pnl=t.unrealized_pnl if t.exit_index is None else t.net_pnl,
                       exit_reason=t.exit_reason) for t in native.trades]
        return EngineResult("application", trades, [r["equity"] for r in native.equity], native.signals)
