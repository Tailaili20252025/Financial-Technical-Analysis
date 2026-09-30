"""Step 4 chart: both directions with markers at their actual availability times."""
import matplotlib.dates as mdates
from .breakouts import BreakoutSettings
from .trendlines import select_trendlines


def draw_breakouts(fig, bars, events, lines, source="Price data", settings=None,
                   trend_settings=None, basis="close"):
    """Draw all events; group coincident markers without dropping exported records.

    Args: fig: Matplotlib figure; bars: observed prefix; events/lines: same snapshot.
    settings: BreakoutSettings; trend_settings: display selection only; basis: swing basis.
    Returns: None. Selected line guides extend only through known follow-up bars;
    no outcome is drawn at the earlier candidate timestamp.
    """
    settings = settings or BreakoutSettings()
    fig.clear()
    axes = fig.subplots(2, 1, sharex=True)
    times = [b.timestamp for b in bars]
    selected = {line.line_id for line in select_trendlines(lines, trend_settings)}
    lookup = {line.line_id: line for line in lines}
    for ax, direction, kind in zip(axes, ("breakout", "breakdown"), ("down", "up")):
        subset = [e for e in events if e.direction == direction]
        ax.plot(times, [b.close for b in bars], color="#334155", linewidth=1, label="Close")
        guide_label = False
        for event in subset:
            if event.line_id not in selected:
                continue
            line = lookup[event.line_id]
            end = min(event.deadline_index, len(bars)-1)
            start = line.second.confirmed_index
            ax.plot([times[start], times[end]], [line.value_at(times[start]), line.value_at(times[end])],
                    color="#8c8c8c", linestyle="--", linewidth=.9,
                    label="Selected line: fixed geometry" if not guide_label else None)
            guide_label = True
        styles = [("candidate_index", "o", "#a65e00", "Candidate", True),
                  ("confirmation_index", "+", "#087f5b", "Time confirmed", False),
                  ("failure_index", "x", "#c92a2a", "False break known", False)]
        for attr, marker, color, label, hollow in styles:
            indices = sorted({getattr(e, attr) for e in subset if getattr(e, attr) is not None})
            if indices:
                kwargs = {"facecolors": "none", "edgecolors": color} if hollow else {"color": color}
                ax.scatter([times[i] for i in indices], [bars[i].close for i in indices],
                           marker=marker, s=40, linewidths=1.3, zorder=5, label=label, **kwargs)
        ax.set_title(f"{direction.title()} | {len(subset)} line events | "
                     f"{sum(e.failure_index is not None for e in subset)} false | "
                     f"{sum(e.outcome == 'pending' for e in subset)} pending", loc="left", fontsize=10)
        ax.set_ylabel("Close (input units)")
        ax.grid(alpha=.18)
        ax.spines[['top', 'right']].set_visible(False)
        ax.legend(loc="upper left", fontsize=8, ncol=2)
        if basis != "close":
            ax.text(.5, .5, "Step 4 requires Close-based swings/trendlines.\nHigh/Low Step 1-3 results are unchanged.",
                    transform=ax.transAxes, ha="center", bbox={"facecolor":"white", "alpha":.9, "edgecolor":"none"})
        elif not subset:
            ax.text(.02, .05, "No qualifying candidates in the observed prefix.", transform=ax.transAxes, fontsize=9)
    locator = mdates.AutoDateLocator(minticks=4, maxticks=8, tz=times[0].tzinfo)
    axes[-1].xaxis.set_major_locator(locator)
    axes[-1].xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator, tz=times[0].tzinfo))
    axes[-1].set_xlabel("Observed timestamps (input timezone)")
    fig.suptitle(f"{source} | Step 4: Breakout / Breakdown\n"
                 f"{settings.confirmation_bars} consecutive closes; {settings.observation_bars} follow-up bars; fixed Step 3 buffer", fontsize=13)
    fig.text(.07, .022, "All line events are included; coincident markers are grouped. Dashed guides show only the Step 3 display subset.\n"
             "Confirmation and failure are plotted when known. Pending = incomplete follow-up. No future continuation is implied.", fontsize=8)
    fig.subplots_adjust(left=.07, right=.98, bottom=.12, top=.88, hspace=.24)
