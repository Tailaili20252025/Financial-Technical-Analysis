"""Compare Step 1-2 strategies while reusing the application's later stages.

The percentage and ATR strategies already live in methods.py. This module adds
measurement and paired comparisons; it does not implement another trade engine.
"""
from dataclasses import dataclass
from math import isfinite
from statistics import median
from time import perf_counter_ns

METHOD_KEYS = ("ta", "percentage", "atr")


@dataclass(frozen=True)
class SwingComparisonSettings:
    """Measurement attributes, separate from each method's detection settings."""
    timing_repetitions: int = 3  # Replays of an identical observed prefix.
    preview_bars: int = 160  # Last observed bars displayed in the example figure.

    def __post_init__(self):
        """Reject invalid counts before starting the experiment."""
        for name in ("timing_repetitions", "preview_bars"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(name + " must be a positive integer")


def require_methods(methods):
    """Require the traditional baseline and the two selected swing alternatives."""
    keys = [method.key for method in methods]
    if len(keys) != 3 or set(keys) != set(METHOD_KEYS):
        raise ValueError("Use exactly ta, percentage and atr once each")
    if any(method.basis != "close" for method in methods):
        raise ValueError("Use Close basis for all three strategies")


def point_signature(points):
    """Capture every exported field, including pivot-time ATR and thresholds."""
    return [point.as_record() for point in points]


def measure_detection(bars, method, start_index, settings=None):
    """Measure detector time and events becoming available in the test block.

    A pivot in warm-up is counted if its confirmation occurs during the test.
    Delay is confirmation index minus pivot index, in observed bars. No event
    means an undefined mean delay (None), not a fabricated zero-bar delay.
    """
    settings = settings or SwingComparisonSettings()
    if isinstance(start_index, bool) or not isinstance(start_index, int) or not 0 <= start_index < len(bars):
        raise ValueError("start_index must select an observed test bar")
    timings, expected, final = [], None, []
    for _ in range(settings.timing_repetitions):
        begin = perf_counter_ns()
        final = method.detect(bars)
        timings.append((perf_counter_ns() - begin) / 1e6)
        signature = point_signature(final)
        if expected is not None and signature != expected:
            raise AssertionError("Detector changed on an identical replay")
        expected = signature
    observed = [p for p in final if p.confirmed_index >= start_index]
    delays = [p.confirmed_index - p.pivot_index for p in observed]
    return dict(method=method.key, test_bars=len(bars)-start_index,
                swing_highs=sum(p.kind == "high" for p in observed),
                swing_lows=sum(p.kind == "low" for p in observed),
                confirmed_swings=len(observed), delay_sum_bars=sum(delays),
                mean_delay_bars=sum(delays)/len(delays) if delays else None,
                median_delay_bars=median(delays) if delays else None,
                detector_median_ms=median(timings), detector_runs_ms=timings), final


def audit_swing_prefixes(bars, method, cutoffs):
    """Verify that later prices do not revise previously confirmed swings."""
    full = method.detect(bars)
    records = []
    for cutoff in sorted(set(cutoffs)):
        if isinstance(cutoff, bool) or not isinstance(cutoff, int) or not 1 <= cutoff <= len(bars):
            raise ValueError("cutoff must be an observed prefix length")
        shorter = method.detect(bars[:cutoff])
        expected = [p for p in full if p.confirmed_index < cutoff]
        if point_signature(shorter) != point_signature(expected):
            raise AssertionError("Confirmed swings changed after extending history")
        records.append(dict(method=method.key, cutoff_bars=cutoff,
                            confirmed_swings=len(shorter), passed=True))
    return records


def pair_pnl(rows):
    """Pair alternative-minus-TA P/L by identical stock, dates and costs.

    Missing or duplicated arms are errors. Comparisons never pair observations
    merely because they happen to occupy the same CSV row number.
    """
    groups = {}
    for row in rows:
        method = row["method"]
        if method not in METHOD_KEYS:
            raise ValueError("Unexpected method in comparison: " + method)
        key = tuple(row[field] for field in ("symbol", "period", "scenario"))
        group = groups.setdefault(key, {})
        if method in group:
            raise ValueError("Duplicate stock-period-cost-method result")
        value = float(row["net_pnl"])
        if not isfinite(value):
            raise ValueError("P/L must be finite")
        group[method] = value
    pairs = []
    for (symbol, period, scenario), group in sorted(groups.items()):
        if set(group) != set(METHOD_KEYS):
            raise ValueError("Each comparison needs all three methods")
        for method in METHOD_KEYS[1:]:
            delta = group[method] - group["ta"]
            pairs.append(dict(symbol=symbol, period=period, scenario=scenario,
                              alternative=method, ta_net_pnl=group["ta"],
                              alternative_net_pnl=group[method], difference=delta,
                              beats_ta=delta > 1e-8))
    return pairs


def summarize_methods(rows, detection, portfolios):
    """Aggregate reset-block P/L and event-weighted confirmation delay.

    Sum P/L is not a compounded return. Drawdown is the worst of the separately
    calculated block-portfolio drawdowns, not a sum/average of drawdowns.
    """
    pairs = pair_pnl(rows)
    result = []
    scenarios = list(dict.fromkeys(row["scenario"] for row in rows))
    for scenario in scenarios:
        for method in METHOD_KEYS:
            selected = [r for r in rows if r["scenario"] == scenario and r["method"] == method]
            metrics = [r for r in detection if r["method"] == method]
            portfolio = [r for r in portfolios if r["scenario"] == scenario and r["method"] == method]
            if not selected or not metrics or not portfolio:
                raise ValueError("Missing evaluation data")
            count = sum(int(r["confirmed_swings"]) for r in metrics)
            closed = sum(int(r["closed_trades"]) for r in selected)
            wins = sum(int(r["winning_trades"]) for r in selected)
            relevant = [r for r in pairs if r["scenario"] == scenario and r["alternative"] == method]
            total = lambda key: sum(float(r[key]) for r in selected)
            result.append(dict(
                method=method, scenario=scenario, stock_blocks=len(selected),
                confirmed_swings=count,
                mean_delay_bars=sum(r["delay_sum_bars"] for r in metrics)/count if count else None,
                detector_median_ms=median(r["detector_median_ms"] for r in metrics),
                filled_trades=int(total("filled_trades")), closed_trades=closed,
                win_rate_percent=100*wins/closed if closed else None,
                realized_net_pnl=total("realized_net_pnl"),
                unrealized_net_pnl=total("unrealized_net_pnl"), net_pnl=total("net_pnl"),
                buy_hold_net_pnl=total("buy_hold_net_pnl"),
                excess_pnl_vs_buy_hold=total("excess_pnl_vs_buy_hold"),
                positive_stock_blocks=sum(float(r["net_pnl"]) > 0 for r in selected),
                stock_blocks_beating_ta=sum(r["beats_ta"] for r in relevant) if relevant else None,
                worst_block_portfolio_drawdown_percent=max(float(r["max_drawdown_percent"]) for r in portfolio)))
    return result


def plot_swings(output, blocks, preview_bars):
    """Plot shared Close data, each strategy's pivots, delays and selected lines."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    for ax, block in zip(axes, blocks):
        bars, analysis = block.bars, block.analysis
        start = max(block.start_index, len(bars) - preview_bars)
        ax.plot([b.timestamp for b in bars[start:]], [b.close for b in bars[start:]],
                color="0.25", linewidth=1, label="Close")
        for kind, marker in (("high", "v"), ("low", "^")):
            points = [p for p in analysis.points if p.pivot_index >= start]
            group = [p for p in points if p.kind == kind]
            ax.scatter([p.pivot_time for p in group], [p.price for p in group],
                       marker=marker, facecolors="white", edgecolors="black", s=24,
                       label="Swing " + kind, zorder=3)
        for point in points:
            ax.plot([point.pivot_time, point.confirmed_at], [point.price, point.price],
                    color="0.6", linewidth=.7, linestyle=":")
        ax.scatter([p.confirmed_at for p in points], [p.price for p in points],
                   marker="x", color="0.45", s=16, label="Confirmation at pivot price")
        labelled = set()
        for line in analysis.selected:
            begin = max(start, line.second.confirmed_index)
            end = line.broken_index if line.broken_index is not None else len(bars)-1
            if end < begin:
                continue
            label = "Rising support" if line.kind == "up" else "Falling resistance"
            ax.plot([bars[begin].timestamp, bars[end].timestamp],
                    [line.value_at(bars[begin].timestamp), line.value_at(bars[end].timestamp)],
                    linestyle="--" if line.kind == "up" else "-.", color="black", linewidth=1.1,
                    label=label if label not in labelled else None)
            labelled.add(label)
        ax.set_title(analysis.method.label, loc="left")
        ax.set_ylabel("Price")
        ax.grid(alpha=.15)
        ax.legend(loc="best", fontsize=7, ncol=3)
    axes[-1].set_xlabel("Observed date")
    fig.suptitle("Same prices and Step 3 candidate rules | different Step 2 swing definitions")
    fig.tight_layout(rect=(0, .035, 1, .96))
    fig.text(.07, .012, "Pivots become available at the x marks. Trendlines show the cutoff display subset, not historical trade selection.", fontsize=9)
    fig.savefig(output, dpi=160)
    plt.close(fig)


def plot_detection(output, totals):
    """Display confirmed-event count, event-weighted delay and detector time."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = [r for r in totals if r["scenario"] == totals[0]["scenario"]]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    labels = [r["method"] for r in rows]
    for ax, field, title in zip(axes, ("confirmed_swings", "mean_delay_bars", "detector_median_ms"),
                                ("Confirmed swings", "Mean delay in bars", "Median detector time in ms")):
        ax.bar(labels, [r[field] or 0 for r in rows], color=["0.3", "0.55", "0.8"], edgecolor="black")
        ax.set_title(title)
        ax.grid(axis="y", alpha=.15)
    fig.tight_layout()
    fig.savefig(output, dpi=160)
    plt.close(fig)
