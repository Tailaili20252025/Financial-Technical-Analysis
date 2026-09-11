"""Shared chart used by both desktop and command-line interfaces."""

import matplotlib.dates as mdates
from matplotlib.figure import Figure

from .data import Bar
from .detector import SwingPoint


def draw_prices(fig: Figure, bars: list[Bar], points: list[SwingPoint], window: int,
                basis: str, source: str = "Price data") -> None:
    """Plot only an observed prefix; markers distinguish pivot and availability.

    Triangle = original pivot location; x = time it became known, placed at
    the pivot's price (not the price of that confirmation bar).
    """
    fig.clear()
    ax = fig.add_subplot(111)
    times = [bar.timestamp for bar in bars]
    ax.plot(times, [b.high for b in bars], color="#c3a169", linewidth=.9, alpha=.8, label="High")
    ax.plot(times, [b.low for b in bars], color="#94a3b8", linewidth=.9, alpha=.9, label="Low")
    ax.plot(times, [b.close for b in bars], color="#2458a6", linewidth=1.35, label="Close")
    ax.fill_between(times, [b.low for b in bars], [b.high for b in bars], color="#dfe7ef", alpha=.3)
    confirmation_label_added = False
    for kind, marker, color in (("high", "v", "#c43142"), ("low", "^", "#147d66")):
        selected = [point for point in points if point.kind == kind]
        if not selected:
            continue
        ax.scatter([p.pivot_time for p in selected], [p.price for p in selected],
                   marker=marker, color=color, s=46, zorder=5, label=f"Swing {kind} (pivot)")
        ax.scatter([p.confirmed_at for p in selected], [p.price for p in selected],
                   marker="x", color=color, s=18, linewidths=.8, alpha=.65, zorder=4,
                   label=None if confirmation_label_added else "Confirmation time (at pivot price)")
        confirmation_label_added = True
    # Explain edge regions: no complete left context / no completed right context.
    if len(bars) > 1:
        ax.axvspan(times[max(0, len(times) - window)], times[-1], color="#eab308", alpha=.09)
    ax.set_title(f"{source} | Close, High and Low\n"
                 f"{len(bars)} observed bars | basis: {basis} | window: {window} | "
                 f"{sum(p.kind == 'high' for p in points)} highs / {sum(p.kind == 'low' for p in points)} lows",
                 loc="left", fontsize=12, pad=13)
    ax.set_xlabel("Timestamp (input timezone; no timezone assumed for naive timestamps)")
    ax.set_ylabel("Price (input units)")
    locator = mdates.AutoDateLocator(minticks=4, maxticks=9, tz=times[0].tzinfo)
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator, tz=times[0].tzinfo))
    ax.grid(alpha=.18)
    ax.spines[['top', 'right']].set_visible(False)
    ax.legend(loc="best", fontsize=8, ncol=3)
    fig.text(.07, .025, "Triangles mark past pivots; x marks when they became known. "
             "The latest bars cannot yet be confirmed as pivots.", fontsize=9, color="#475569")
    fig.subplots_adjust(left=.075, right=.975, bottom=.15, top=.87)
