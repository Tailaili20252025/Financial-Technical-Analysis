"""Shared chart used by both desktop and command-line interfaces."""

import matplotlib.dates as mdates
from matplotlib.figure import Figure

from .data import Bar
from .detector import SwingPoint
from .trendlines import detect_trendlines, select_trendlines


def draw_prices(fig: Figure, bars: list[Bar], points: list[SwingPoint], window: int,
                basis: str, source: str = "Price data", lines=None, settings=None) -> None:
    """
    Draw prices, swings and ranked uptrend/downtrend lines for the observed history.

    Triangles indicate original pivot locations. Crosses indicate confirmation
    times at the pivot price, not the confirmation bar price. The shaded right
    edge marks bars with insufficient later context for confirmation. The caller
    must provide events matching the visible history; this function does not filter
    out events beyond a replay cutoff.

    Args:
        fig (Figure): Existing Matplotlib figure to clear and redraw.
        bars (list[Bar]): Nonempty chronological sequence of observed bars.
        points (list[SwingPoint]): Swings confirmed within the observed history.
        window (int): Detector window, used in the title and right-edge shading.
        basis (str): Detector price basis to display in the title.
        source (str): Descriptive chart title prefix; default is 'Price data'.
        lines (list[TrendLine] or None): Candidates for this prefix; None computes them.
        settings (TrendSettings or None): Detection/display rules; None uses defaults.

    Result:
        None: Modifies the supplied figure without saving it or opening a window.

    Exception:
        IndexError: If bars is empty.
        ValueError: If automatic trend detection receives inconsistent events or times.
        Matplotlib rendering errors propagate to the caller.
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
    if lines is None:
        lines = detect_trendlines(bars, points, settings)
    selected_lines = select_trendlines(lines, settings)
    for line in selected_lines:
        color = "#079447" if line.kind == "up" else "#e32929"
        start, created = line.first.pivot_index, line.second.confirmed_index
        end = line.broken_index if line.broken_index is not None else line.observed_end
        label = f"{line.kind.title()} {line.line_id.split('-', 1)[1]}: {len(line.touches)} touches"
        # Historical anchor segment is dashed: this line was not available yet.
        ax.plot([times[start], times[created]],
                [line.value_at(times[start]), line.value_at(times[created])],
                color=color, linestyle="--", linewidth=1.8, alpha=.8)
        ax.plot([times[created], times[end]],
                [line.value_at(times[created]), line.value_at(times[end])],
                color=color, linewidth=2.1, label=label, zorder=3)
        ax.scatter([times[created]], [line.value_at(times[created])],
                   marker="D", s=26, color=color, zorder=6)
        if line.broken_index is not None:
            ax.scatter([times[end]], [line.value_at(times[end])],
                       marker="X", s=44, color=color, zorder=6)
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
    if not selected_lines:
        ax.text(.01, .02, "No trendlines meet the current rules.", transform=ax.transAxes,
                fontsize=9, color="#475569")
    fig.text(.075, .025, "Triangles: swing pivots; small x: swing confirmation. Green: rising support; red: falling resistance.\n"
             "Dashed: before line creation; diamond: line creation; solid: observed lifetime; large X: first break. No future extension.",
             fontsize=8.5, color="#475569")
    fig.subplots_adjust(left=.075, right=.975, bottom=.15, top=.87)
