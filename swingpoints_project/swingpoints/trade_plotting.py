"""Step 5 entry markers, Step 6 fixed price zones and marked account value."""
import matplotlib.dates as mdates
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


def _time_axis(axis):
    """Apply compact timestamps without assuming an exchange timezone."""
    locator = mdates.AutoDateLocator(minticks=4, maxticks=9)
    axis.xaxis.set_major_locator(locator)
    axis.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    axis.set_xlabel("Observed bar timestamp (input timezone)")
    axis.grid(alpha=.18)


def draw_trades(figure, bars, trading, title="", lines=None, selected_trade_id=None):
    """Draw the price history plus slide-style entry/stop/target zones.

    Args:
        figure: Reusable Matplotlib Figure; cleared before drawing.
        bars: Exactly the observed prefix used by the TradingResult.
        trading: Shared Steps 5–6 snapshot, including realised and open P/L.
        title: Input filename or short chart title.
        lines: Optional Step 3 candidates; only source lines of shown trades appear.
        selected_trade_id: Focus on one trade; None displays all filled trades.
    Returns:
        None. No chart element projects past the observed cutoff or a trade's exit.
    """
    figure.clear()
    axis = figure.add_subplot(111)
    x = [b.timestamp for b in bars]
    axis.plot(x, [b.close for b in bars], color="#304a64", linewidth=1.4, label="Close", zorder=2)
    axis.fill_between(x, [b.low for b in bars], [b.high for b in bars], color="#64748b", alpha=.10)
    selected = [t for t in trading.trades if selected_trade_id is None or t.trade_id == selected_trade_id]
    by_id = {line.line_id: line for line in lines or []}
    for trade in selected:
        end = trade.exit_index if trade.exit_index is not None else len(bars)-1
        start_time, end_time = x[trade.entry_index], x[end]
        for y, color, style in ((trade.stop_price, "#c63030", "-"), (trade.entry_price, "#2580a0", "--"),
                                (trade.target_price, "#168044", "-")):
            axis.plot([start_time, end_time], [y, y], color=color, linestyle=style, linewidth=1.4, zorder=3)
        axis.fill_between([start_time, end_time], trade.entry_price, trade.stop_price, color="#dc2626", alpha=.08)
        axis.fill_between([start_time, end_time], trade.entry_price, trade.target_price, color="#16a34a", alpha=.08)
        color = "#168044" if trade.side == "long" else "#c63030"
        axis.scatter([x[trade.signal_index]], [trade.signal_price], marker="o", s=70,
                     facecolors="none", edgecolors="black", linewidths=1, zorder=6)
        axis.scatter([start_time], [trade.entry_price], marker="^" if trade.side == "long" else "v",
                     color=color, s=65, zorder=7)
        pnl = trade.net_pnl if trade.exit_index is not None else trade.unrealized_pnl
        tag = "net" if trade.exit_index is not None else "open"
        # Trade labels are sparse and offset; the table retains exact levels/results.
        axis.annotate(f"{trade.trade_id} {'Buy' if trade.side == 'long' else 'Sell'}",
                      (start_time, trade.entry_price), xytext=(3, 12 if trade.side == "long" else -20),
                      textcoords="offset points", fontsize=8, color=color)
        if trade.exit_index is not None:
            axis.scatter([end_time], [trade.exit_price], marker="X", color="#111111", s=50, zorder=7)
            axis.plot([start_time, end_time], [trade.entry_price, trade.exit_price], color="#777777", linewidth=.8, alpha=.6)
        if selected_trade_id is not None or len(selected) <= 3:
            y = trade.exit_price if trade.exit_price is not None else bars[-1].close
            reason = trade.exit_reason or "open at cutoff"
            axis.annotate(f"{tag} {pnl:+.2f}\n{reason}", (end_time, y), xytext=(4, -28), textcoords="offset points", fontsize=8)
        if selected_trade_id is not None:
            for value, label, level_color in ((trade.stop_price, "Stop", "#c63030"),
                                              (trade.entry_price, "Entry", "#2580a0"),
                                              (trade.target_price, "Target", "#168044")):
                axis.annotate(f"{label} {value:.4f}", (end_time, value), xytext=(6, 4), textcoords="offset points",
                              color=level_color, fontsize=9)
        line = by_id.get(trade.line_ids[0])
        if line is not None:
            indices = range(line.second.confirmed_index, trade.signal_index+1)
            axis.plot([x[i] for i in indices], [line.value_at(x[i]) for i in indices],
                      color="#168044" if line.kind == "up" else "#c63030", linestyle=":", alpha=.7, linewidth=1)
    stats = trading.summary()
    mode = "confirmation Close (idealised)" if trading.settings.entry_timing == "confirmation_close" else "next Open"
    axis.set_title(f"{title} | Steps 5–6: trade entries and fixed exits\n"
                   f"{stats['closed_trades']} closed / {stats['open_trades']} open | "
                   f"realised net {stats['realized_net_pnl']:+.2f} | open net {stats['unrealized_net_pnl']:+.2f} | {mode}", loc="left", fontsize=12)
    if not selected:
        axis.text(.5, .5, "No filled trades in this prefix\n"+trading.status.replace("_", " "),
                  transform=axis.transAxes, ha="center", va="center", bbox=dict(facecolor="white", alpha=.9, edgecolor=".8"))
    handles = [Line2D([], [], color="#304a64", label="Close"),
               Line2D([], [], marker="o", color="none", markeredgecolor="black", label="Confirmation"),
               Line2D([], [], marker="^", color="#168044", linestyle="none", label="Buy / long entry"),
               Line2D([], [], marker="v", color="#c63030", linestyle="none", label="Sell / short entry"),
               Line2D([], [], marker="X", color="black", linestyle="none", label="Exit"),
               Line2D([], [], color="#2580a0", linestyle="--", label="Entry price"),
               Patch(facecolor="#dc2626", alpha=.15, label="Stop-loss zone"),
               Patch(facecolor="#16a34a", alpha=.15, label="Take-profit zone")]
    axis.legend(handles=handles, loc="best", fontsize=8, ncol=4)
    axis.set_ylabel("Price (input units)")
    _time_axis(axis)
    figure.text(.075, .025, "Fixed levels start at entry and end at exit/cutoff. Close entries cannot use earlier High/Low of that bar.\n"
                "Sell opens a short. Green zone is below entry for a short, above for a long. Exact prices/reasons: trades.csv.", fontsize=8, color="#333333")
    figure.tight_layout(rect=(0, .075, 1, .98))


def draw_equity(figure, bars, trading, title=""):
    """Draw net account equity and realised/open P/L on the observed prefix."""
    figure.clear()
    axes = figure.subplots(3, 1, sharex=True, gridspec_kw={"height_ratios": [2, 1, 1]})
    x = [b.timestamp for b in bars]
    rows = trading.equity
    axes[0].plot(x, [r["equity"] for r in rows], color="#243c55", label="Net account equity")
    axes[0].axhline(trading.settings.initial_equity, color=".55", linestyle="--", linewidth=.8, label="Initial equity")
    axes[0].set_ylabel("Account units")
    axes[0].set_title(f"{title} | Step 6: marked equity and profit/loss\n{trading.status.replace('_', ' ')}; costs included", loc="left", fontsize=12)
    axes[1].plot(x, [r["realized_net_pnl"] for r in rows], label="Realised net P/L", color="#168044")
    axes[1].plot(x, [r["unrealized_net_pnl"] for r in rows], label="Open net P/L", color="#8b613b")
    axes[1].axhline(0, color=".55", linewidth=.7)
    axes[1].set_ylabel("P/L")
    axes[2].fill_between(x, [r["drawdown_percent"] for r in rows], color="#a63838", alpha=.25)
    axes[2].set_ylabel("Drawdown (%)")
    for ax in axes:
        ax.grid(alpha=.18)
    axes[0].legend(loc="best", fontsize=8)
    axes[1].legend(loc="best", fontsize=8)
    _time_axis(axes[2])
    figure.text(.075, .02, "Equity = initial equity + realised net P/L + open net P/L. Open positions are marked at Close, not forcibly sold.\n"
                "Drawdown uses observed Close marks; intrabar account extremes and broker margin rules are not modelled.", fontsize=8)
    figure.tight_layout(rect=(0, .07, 1, 1))
