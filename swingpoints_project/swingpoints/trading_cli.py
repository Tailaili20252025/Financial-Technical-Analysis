"""One shared command-line mapping for application and method comparisons."""
from .trading import TradeSettings


def add_trade_arguments(parser):
    """Add Step 5–6 controls to an argparse parser without duplicating defaults."""
    group = parser.add_argument_group("Steps 5–6: simulated entries, fixed stops/targets and P/L")
    defaults = TradeSettings()
    group.add_argument("--no-trades", action="store_true", help="disable trade simulation")
    group.add_argument("--entry-timing", choices=["confirmation_close", "next_open"], default=defaults.entry_timing,
                       help="confirmation_close follows slides (idealised); next_open follows report execution timing")
    group.add_argument("--long-only", action="store_true", help="disable Sell-to-open short trades")
    for name in ("quantity", "initial_equity", "atr_stop_multiple", "reward_risk_multiple",
                 "slippage_bps", "fee_per_order", "short_borrow_rate_percent"):
        group.add_argument("--"+name.replace("_", "-"), type=float, default=getattr(defaults, name))
    group.add_argument("--trade-atr-period", type=int, default=defaults.atr_period,
                       help="ATR bars for trade stops, separate from indicator/swing settings")
    group.add_argument("--trade-ema-period", type=int, default=defaults.ema_period)
    group.add_argument("--trade-ema-filter", action="store_true", help="require Close above/below EMA for long/short")
    group.add_argument("--exit-on-false-break", action="store_true", help="optional next-Open exit after primary-line failure")
    group.add_argument("--exit-on-opposite", action="store_true", help="optional next-Open exit after an opposite confirmation")


def trade_settings_from_args(args):
    """Return validated attributes from either parser; bad settings raise ValueError."""
    return TradeSettings(enabled=not args.no_trades, entry_timing=args.entry_timing, allow_short=not args.long_only,
                         quantity=args.quantity, initial_equity=args.initial_equity, atr_period=args.trade_atr_period,
                         atr_stop_multiple=args.atr_stop_multiple, reward_risk_multiple=args.reward_risk_multiple,
                         slippage_bps=args.slippage_bps, fee_per_order=args.fee_per_order,
                         short_borrow_rate_percent=args.short_borrow_rate_percent,
                         ema_filter=args.trade_ema_filter, ema_period=args.trade_ema_period,
                         exit_on_false_break=args.exit_on_false_break, exit_on_opposite=args.exit_on_opposite)
