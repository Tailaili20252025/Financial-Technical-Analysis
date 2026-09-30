"""Shared Step 1-4 analysis used by CLI, GUI and comparison experiments."""
from dataclasses import dataclass, field
from .breakouts import BreakoutSettings, detect_breakouts
from pathlib import Path
from .data import load_prices
from .methods import SwingMethod, TraditionalTAMethod
from .trendlines import TrendSettings, detect_trendlines, select_trendlines
from .indicators import IndicatorSettings


@dataclass(frozen=True)
class AnalysisResult:
    """A single observed-prefix result, independent of UI and output directory."""
    bars: list  # Completed bars available at this run's cutoff.
    points: list  # Confirmed swings produced by the selected strategy.
    lines: list  # All accepted candidate trendlines (including later breaks).
    method: SwingMethod  # Strategy with validated settings for this snapshot.
    trend_settings: TrendSettings  # Shared candidate construction/validation rules.

    events: list = field(default_factory=list)  # Step 4 events for all eligible lines.
    breakout_settings: BreakoutSettings = field(default_factory=BreakoutSettings)  # Applied lifecycle rules.

    @property
    def selected(self):
        """Return the display subset; complete candidate history stays in lines."""
        return select_trendlines(self.lines, self.trend_settings)


def analyze(bars, method=None, trend_settings=None, breakout_settings=None):
    """Run one strategy followed by the common candidate trendline algorithm.

    Args: bars: chronological observed prefix; method: SwingMethod instance.
    breakout_settings: Step 4 consecutive-close and follow-up rules.
    Returns: AnalysisResult; no files are read/written and no GUI is required.
    Raises: ValueError for empty history; TypeError for a non-strategy method.
    """
    method = method if method is not None else TraditionalTAMethod()
    if not isinstance(method, SwingMethod):
        raise TypeError("method must implement SwingMethod")
    bars = list(bars)
    if not bars:
        raise ValueError("Analysis requires at least one observed bar")
    settings = trend_settings or TrendSettings()
    points = method.detect(bars)
    lines = detect_trendlines(bars, points, settings)
    breakout_settings = breakout_settings or BreakoutSettings()
    events = detect_breakouts(bars, lines, breakout_settings)
    return AnalysisResult(bars, points, lines, method, settings, events, breakout_settings)


def run_analysis(source, output, method=None, trend_settings=None, indicator_settings=None, until=None, breakout_settings=None):
    """Load, analyze, draw and export one method using the same application services.

    Existing result files in output are replaced. A cutoff counts sorted bars.
    """
    from matplotlib.figure import Figure
    from .plotting import draw_prices
    from .output import export_results
    bars = load_prices(source)
    if until is not None:
        if isinstance(until, bool) or not isinstance(until, int) or not 1 <= until <= len(bars):
            raise ValueError(f"until must be between 1 and {len(bars)}")
        bars = bars[:until]
    result = analyze(bars, method, trend_settings, breakout_settings)
    method = result.method
    figure = Figure(figsize=(14, 8))
    draw_prices(figure, bars, result.points, method.context_radius, method.basis,
                Path(source).name, result.lines, result.trend_settings, method=method)
    export_results(output, source, bars, result.points, method.context_radius, method.basis,
                   figure, result.lines, result.trend_settings, indicator_settings, method=method,
                   breakout_settings=result.breakout_settings, events=result.events)
    figure.clear()
    return result
