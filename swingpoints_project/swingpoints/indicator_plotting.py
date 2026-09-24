"""A separate indicator dashboard preserves the existing Steps 1-3 price figure."""
from __future__ import annotations
import math
import matplotlib.dates as mdates


def draw_indicators(figure, bars, result, title=''):
    """Draw price overlays and five aligned oscillator/volatility panels.

    Args:
        figure: Matplotlib Figure to clear and redraw (CLI or Tk canvas).
        bars: Nonempty observed bars matching the IndicatorResult.
        result: Calculated aligned indicator series and settings.
        title: Input name shown above the dashboard.
    Returns:
        Figure: The supplied figure, with unavailable values left as gaps.
    """
    if not bars:
        raise ValueError('Cannot plot indicators without bars.')
    result.records(bars)  # Check alignment before plotting.
    figure.clear()
    axes = figure.subplots(6, 1, sharex=True, gridspec_kw={'height_ratios': [2.2, 1, 1.2, 1, 1, 1]})
    times = [b.timestamp for b in bars]
    settings, series = result.settings, result.series
    colors = ['#202020', '#a56714', '#306f71', '#795694']
    axes[0].plot(times, [b.close for b in bars], label='Close', color=colors[0], linewidth=1)
    for key, label, color in [('sma', f'SMA {settings.sma_period}', colors[1]),
                              ('ema', f'EMA {settings.ema_period}', colors[2]),
                              ('vwap', f'VWAP ({settings.vwap_reset})', colors[3])]:
        if any(v is not None for v in series[key]):
            axes[0].plot(times, [math.nan if v is None else v for v in series[key]], label=label, color=color, linewidth=1)
    notes = []
    if 'missing_volume' in result.vwap_status:
        notes.append('VWAP unavailable where volume is missing (no substitute used).')
    if all(v is None for v in series['vwap']) and 'missing_volume' not in result.vwap_status:
        notes.append('VWAP unavailable: cumulative volume is zero.')
    if notes:
        axes[0].text(.01, .02, ' '.join(notes), transform=axes[0].transAxes, fontsize=9,
                     bbox={'facecolor': 'white', 'alpha': .85, 'edgecolor': 'none'})
    axes[0].set_ylabel('Price')
    axes[0].legend(loc='upper left', ncol=4, fontsize=9)
    panels = [('rsi', f'RSI {settings.rsi_period}'), ('macd', f'MACD {settings.macd_fast}/{settings.macd_slow}/{settings.macd_signal}'),
              ('atr', f'ATR {settings.atr_period}'), ('roc', f'ROC {settings.roc_period} (%)'), ('cci', f'CCI {settings.cci_period}')]
    for ax, (key, label) in zip(axes[1:], panels):
        ax.plot(times, [math.nan if x is None else x for x in series[key]], color='#306f71', linewidth=1, label=label)
        ax.set_ylabel(label, fontsize=9)
        if all(x is None for x in series[key]):
            ax.text(.5, .5, 'Insufficient history', transform=ax.transAxes, ha='center')
    axes[1].set_ylim(0, 100)
    for level in [30, 70]:
        axes[1].axhline(level, color='gray', linestyle='--', linewidth=.7)
    axes[2].plot(times, [math.nan if x is None else x for x in series['macd_signal']], color='#a56714', label='Signal', linewidth=1)
    numeric_times = mdates.date2num(times)
    gaps = sorted(b-a for a, b in zip(numeric_times, numeric_times[1:]) if b > a)
    width = .8*gaps[len(gaps)//2] if gaps else .0005
    axes[2].bar(times, [math.nan if x is None else x for x in series['macd_histogram']], width=width,
                color='#aab6b3', label='Histogram')
    axes[2].legend(loc='upper left', ncol=3, fontsize=8)
    for ax in (axes[2], axes[4], axes[5]):
        ax.axhline(0, color='gray', linewidth=.6)
    for level in [-100, 100]:
        axes[5].axhline(level, color='gray', linestyle='--', linewidth=.7)
    for ax in axes:
        ax.grid(alpha=.18)
        ax.spines[['right', 'top']].set_visible(False)
    locator = mdates.AutoDateLocator()
    axes[-1].xaxis.set_major_locator(locator)
    axes[-1].xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    axes[-1].set_xlabel('Input timestamps | periods count observed bars')
    figure.suptitle(f'{title} | Technical indicators | {len(bars)} observed bars', fontsize=14)
    figure.text(.09, .013, 'Indicators use completed bars only. Warm-up values are gaps; Step 1-3 swings and trendlines remain in prices.png.', fontsize=9)
    figure.subplots_adjust(left=.09, right=.98, top=.94, bottom=.06, hspace=.16)
    return figure
