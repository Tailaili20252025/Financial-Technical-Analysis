"""Causal, aligned technical indicators. Warm-up/undefined values are None.

Periods count observed completed bars. No filling, look-ahead or price adjustment
is performed. These series supplement the existing swing/trendline algorithms.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import math
from .data import Bar


@dataclass(frozen=True)
class IndicatorSettings:
    """Validated indicator attributes shared by CLI, GUI and exports."""
    sma_period: int = 20  # Number of Close observations in the simple mean.
    ema_period: int = 20  # SMA seed length; subsequent alpha is 2/(period+1).
    rsi_period: int = 14  # Number of Close changes for Wilder gain/loss smoothing.
    macd_fast: int = 12  # Fast Close EMA period; must be below macd_slow.
    macd_slow: int = 26  # Slow Close EMA period.
    macd_signal: int = 9  # SMA-seeded EMA of valid MACD values.
    atr_period: int = 14  # Wilder smoothing period of true range.
    roc_period: int = 12  # Observed-bar distance to the reference Close.
    cci_period: int = 20  # Typical-price window and mean absolute deviation.
    vwap_reset: str = "session"  # 'session': input calendar-date reset; 'cumulative': full prefix.

    def __post_init__(self):
        """Reject invalid periods and unsupported VWAP anchors before analysis."""
        for field in fields(self):
            if field.name != 'vwap_reset':
                _period(getattr(self, field.name))
        if self.macd_fast >= self.macd_slow:
            raise ValueError('MACD fast period must be smaller than slow period.')
        if self.vwap_reset not in ('session', 'cumulative'):
            raise ValueError('VWAP reset must be session or cumulative.')


@dataclass(frozen=True)
class IndicatorResult:
    """One aligned result bundle, independent of plotting and file writing."""
    settings: IndicatorSettings  # Exact parameter snapshot for this run.
    series: dict[str, list[float | None]]  # Same-length series keyed by indicator name.
    vwap_status: list[str]  # Per-bar reason: ok, missing_volume, or zero_cumulative_volume.

    def records(self, bars: list[Bar]) -> list[dict]:
        """Return timestamped rows, preserving warm-up values as None."""
        if any(len(v) != len(bars) for v in self.series.values()) or len(self.vwap_status) != len(bars):
            raise ValueError('Indicator rows must align with the supplied bars.')
        return [dict(bar=i+1, timestamp=b.timestamp.isoformat(), close=b.close,
                     **{k: v[i] for k, v in self.series.items()}, vwap_status=self.vwap_status[i])
                for i, b in enumerate(bars)]

    def metadata(self) -> dict:
        """Describe availability, conventions and final-bar values, without NaN."""
        missing = self.vwap_status.count('missing_volume')
        warnings = []
        if missing:
            warnings.append('VWAP unavailable after missing volume within its anchor period; no substitute volume is used.')
        return dict(settings=asdict(self.settings),
                    valid_counts={k: sum(x is not None for x in v) for k, v in self.series.items()},
                    latest={k: v[-1] if v else None for k, v in self.series.items()},
                    vwap_status_counts={s: self.vwap_status.count(s) for s in sorted(set(self.vwap_status))},
                    warnings=warnings,
                    timing='Available at the current completed bar; all windows use past/current observations only.',
                    warmup='Unavailable values are JSON null / CSV blank; no backward filling.',
                    ema_seed='SMA of first period values; alpha=2/(period+1).',
                    rsi='Wilder smoothing; flat gain/loss yields 50; gain-only 100, loss-only 0.',
                    atr='First true range is High-Low; SMA seed then Wilder smoothing.',
                    cci='Typical price HLC3; 0.015 scaling; mean absolute deviation; flat window yields 0.',
                    vwap='HLC3 weighted by actual volume; session means input calendar date, not an exchange calendar.')


def _period(period: int) -> None:
    """Require a strictly positive integer period, rejecting booleans."""
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise ValueError('Indicator periods must be positive integers.')


def _values(values) -> list[float]:
    """Copy finite numeric inputs; undefined source values are not imputed."""
    result = []
    for x in values:
        if isinstance(x, bool):
            raise ValueError('Indicator input must be finite numeric values.')
        try:
            number = float(x)
        except (TypeError, ValueError):
            raise ValueError('Indicator input must be finite numeric values.') from None
        if not math.isfinite(number):
            raise ValueError('Indicator input must be finite numeric values.')
        result.append(number)
    return result


def sma(values, period: int) -> list[float | None]:
    """Return trailing simple means; first value exists at zero-based period-1."""
    _period(period)
    values = _values(values)
    return [None if i+1 < period else math.fsum(values[i-period+1:i+1])/period
            for i in range(len(values))]


def _smooth(values, period: int, alpha: float) -> list[float | None]:
    """Seed an exponential recursion with a complete arithmetic-mean window."""
    out = [None]*len(values)
    if len(values) >= period:
        previous = math.fsum(values[:period])/period
        out[period-1] = previous
        for i in range(period, len(values)):
            previous += alpha*(values[i]-previous)
            out[i] = previous
    return out


def ema(values, period: int) -> list[float | None]:
    """Return SMA-seeded EMA with alpha 2/(period+1); retain warm-up alignment."""
    _period(period)
    return _smooth(_values(values), period, 2/(period+1))


def rsi(values, period: int) -> list[float | None]:
    """Return Wilder RSI from period changes (requires period+1 prices).

    Zero average loss with a gain returns 100, zero gain with a loss returns 0;
    when both are zero the neutral convention is 50.
    """
    _period(period)
    values = _values(values)
    changes = [b-a for a, b in zip(values, values[1:])]
    gains = _smooth([max(x, 0) for x in changes], period, 1/period)
    losses = _smooth([max(-x, 0) for x in changes], period, 1/period)
    out = [None]*len(values)
    for i, (gain, loss) in enumerate(zip(gains, losses), start=1):
        if gain is not None:
            out[i] = 50.0 if gain == loss == 0 else 100.0*gain/(gain+loss)
    return out


def macd(values, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[list, list, list]:
    """Return aligned fast-minus-slow EMA, signal EMA and MACD-minus-signal.

    The signal EMA starts from the first signal valid MACD observations.
    """
    for period in (fast, slow, signal):
        _period(period)
    if fast >= slow:
        raise ValueError('MACD fast period must be smaller than slow period.')
    values = _values(values)
    f, s = ema(values, fast), ema(values, slow)
    line = [None if b is None else a-b for a, b in zip(f, s)]
    signal_line = [None]*min(slow-1, len(values)) + ema(line[slow-1:], signal)
    histogram = [None if b is None else a-b for a, b in zip(line, signal_line)]
    return line, signal_line, histogram


def atr(bars: list[Bar], period: int = 14) -> list[float | None]:
    """Return Wilder ATR; first TR is High-Low and later TR includes Close gaps."""
    _period(period)
    ranges = [b.high-b.low if i == 0 else max(b.high-b.low,
              abs(b.high-bars[i-1].close), abs(b.low-bars[i-1].close)) for i, b in enumerate(bars)]
    return _smooth(_values(ranges), period, 1/period)


def vwap(bars: list[Bar], reset: str = 'session') -> tuple[list, list[str]]:
    """Return actual-volume weighted HLC3 and an availability status per bar.

    Missing volume invalidates the current and remaining bars of that anchor.
    Zero volume contributes no weight. Until positive weight exists return None.
    Session resets follow dates as represented in the input timestamps.
    """
    if reset not in ('session', 'cumulative'):
        raise ValueError('VWAP reset must be session or cumulative.')
    out, statuses = [], []
    total_weight = weighted = 0.0
    invalid = False
    last_date = None
    for b in bars:
        date = b.timestamp.date()
        if reset == 'session' and date != last_date:
            total_weight = weighted = 0.0
            invalid = False
        last_date = date
        if b.volume is None:
            invalid = True
        else:
            volume = _values([b.volume])[0]
            if volume < 0:
                raise ValueError('Volume must be nonnegative.')
            total_weight += volume
            weighted += ((b.high+b.low+b.close)/3)*volume
        status = 'missing_volume' if invalid else 'zero_cumulative_volume' if total_weight == 0 else 'ok'
        statuses.append(status)
        out.append(weighted/total_weight if status == 'ok' else None)
    return out, statuses


def roc(values, period: int = 12) -> list[float | None]:
    """Return percent change against period bars ago; zero denominator is None."""
    _period(period)
    values = _values(values)
    return [None if i < period or values[i-period] == 0 else
            100*(values[i]/values[i-period]-1) for i in range(len(values))]


def cci(bars: list[Bar], period: int = 20) -> list[float | None]:
    """Return (HLC3-mean)/(0.015*mean absolute deviation); flat window gives 0."""
    _period(period)
    typical = _values([(b.high+b.low+b.close)/3 for b in bars])
    means = sma(typical, period)
    out = [None]*len(bars)
    for i in range(period-1, len(bars)):
        deviation = math.fsum(abs(x-means[i]) for x in typical[i-period+1:i+1])/period
        out[i] = (typical[i]-means[i])/(0.015*deviation) if deviation else 0.0
    return out


def calculate_indicators(bars: list[Bar], settings: IndicatorSettings | None = None) -> IndicatorResult:
    """Calculate all eight indicators on a validated chronological observed prefix.

    Args:
        bars: Completed bars, normally returned by load_prices; empty input is valid.
        settings: Immutable periods/anchor; None selects documented defaults.
    Returns:
        IndicatorResult: Ten numeric columns (MACD includes signal/histogram).
    Raises:
        ValueError: Invalid price, timestamp ordering, volume or settings.
    """
    settings = settings or IndicatorSettings()
    for i, b in enumerate(bars):
        h, l, c = _values([b.high, b.low, b.close])
        if l <= 0 or not l <= c <= h:
            raise ValueError('Require positive Low <= Close <= High.')
        if i and b.timestamp <= bars[i-1].timestamp:
            raise ValueError('Indicator bars must have strictly increasing timestamps.')
    close = [b.close for b in bars]
    line, signal, histogram = macd(close, settings.macd_fast, settings.macd_slow, settings.macd_signal)
    weighted, status = vwap(bars, settings.vwap_reset)
    series = dict(sma=sma(close, settings.sma_period), ema=ema(close, settings.ema_period),
                  rsi=rsi(close, settings.rsi_period), macd=line, macd_signal=signal,
                  macd_histogram=histogram, atr=atr(bars, settings.atr_period), vwap=weighted,
                  roc=roc(close, settings.roc_period), cci=cci(bars, settings.cci_period))
    if any(x is not None and not math.isfinite(x) for v in series.values() for x in v):
        raise ValueError('Indicator arithmetic overflow: check input magnitudes.')
    return IndicatorResult(settings, series, status)
