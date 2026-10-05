"""Causal Close-based alternatives. Events are frozen when confirmed.

Percentage and ATR reversal track alternating extrema. Local prominence uses a
completed symmetric context, not unrestricted full-history peak prominence.
"""
from dataclasses import dataclass, asdict
from .detector import SwingPoint as BaseSwingPoint
from math import isfinite, isclose
from .data import Bar


def positive(name, value, integer=False):
    """Reject booleans, nonfinite values and invalid positive settings."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
        raise ValueError(f'{name} must be finite and positive')
    if integer and (not isinstance(value, int)):
        raise ValueError(f'{name} must be a positive integer')


@dataclass(frozen=True)
class PercentageSettings:
    # reversal_percent: Required decline/rise from a running extreme, in percent.
    reversal_percent: float = 5.0

    def __post_init__(self):
        """Validate the percentage; 5 means five percent, not 0.05 percent."""
        positive('reversal_percent', self.reversal_percent)
        if self.reversal_percent >= 100:
            raise ValueError('reversal_percent must be below 100')


@dataclass(frozen=True)
class ATRSettings:
    # atr_period: Completed bars in the initial Wilder ATR seed.
    atr_period: int = 14
    # atr_multiplier: Required reversal in units of ATR frozen at the extreme.
    atr_multiplier: float = 2.0

    def __post_init__(self):
        """Validate warm-up length and reversal multiplier."""
        positive('atr_period', self.atr_period, True)
        positive('atr_multiplier', self.atr_multiplier)


@dataclass(frozen=True)
class ProminenceSettings:
    # radius: Completed observations on EACH side of the candidate pivot.
    radius: int = 5
    # min_prominence_percent: Local prominence divided by pivot Close, times 100.
    min_prominence_percent: float = 3.0
    # min_distance: Minimum index separation from the last accepted same-kind pivot.
    min_distance: int = 3

    def __post_init__(self):
        """Validate local context, prominence cutoff and past-only spacing."""
        positive('radius', self.radius, True)
        positive('min_prominence_percent', self.min_prominence_percent)
        positive('min_distance', self.min_distance, True)


@dataclass(frozen=True)
class SwingPoint(BaseSwingPoint):
    """Frozen event; indices are zero-based internally, one-based in exports."""
    basis: str = 'close'      # Fixed across all three comparison projects.
    method: str = ''          # Percentage, ATR or local prominence.
    threshold_price: float = 0.0  # Absolute reversal / required prominence.
    prominence_price: float | None = None  # Measured local prominence, if used.
    atr_at_pivot: float | None = None      # Frozen ATR, if used.

    def as_record(self):
        """Export explicit pivot and confirmation timing plus method evidence."""
        return dict(kind=self.kind, price=self.price, pivot_bar=self.pivot_index+1,
                    pivot_time=self.pivot_time.isoformat(), confirmed_bar=self.confirmed_index+1,
                    confirmed_at=self.confirmed_at.isoformat(), delay_bars=self.confirmed_index-self.pivot_index,
                    basis=self.basis, method=self.method, threshold_price=self.threshold_price,
                    prominence_price=self.prominence_price, atr_at_pivot=self.atr_at_pivot)


def atr_values(bars, period):
    """Wilder ATR; first TR=High-Low, seed=mean(first period TRs).

    Return None before warm-up. Subsequent ATR uses ((n-1)*previous+TR)/n.
    Only information through the current completed bar enters each value.
    """
    positive('period', period, True)
    result, total, previous = [], 0.0, None
    for i, bar in enumerate(bars):
        tr = bar.high-bar.low if i == 0 else max(bar.high-bar.low,
                   abs(bar.high-bars[i-1].close), abs(bar.low-bars[i-1].close))
        if i < period:
            total += tr
        if i == period-1:
            previous = total/period
        elif i >= period:
            previous = ((period-1)*previous+tr)/period
        result.append(previous)
    return result


def _event(bars, kind, pivot, current, method, threshold, prominence=None, atr=None):
    """Build an immutable event after the pivot's confirmation bar arrives."""
    return SwingPoint(kind, bars[pivot].close, pivot, bars[pivot].timestamp,
                      current, bars[current].timestamp, 'close', method, threshold, prominence, atr)


def _reached(distance, threshold):
    """Include exact threshold equality despite binary floating-point roundoff."""
    return distance >= threshold or isclose(distance, threshold, rel_tol=1e-12, abs_tol=0.0)


def _reversals(bars, settings):
    """Track extremes; equal extremes retain the first occurrence.

    During initialization track both extremes, then alternate high/low searches.
    Freeze an ATR threshold at its candidate extreme; only a STRICT new extreme
    updates it. After confirmation seed the opposite extreme at the current bar.
    One event per bar maximum; the unfinished final extreme is never exported.
    """
    using_atr = isinstance(settings, ATRSettings)
    method = 'atr' if using_atr else 'percentage'
    atr = atr_values(bars, settings.atr_period) if using_atr else [None]*len(bars)
    start = settings.atr_period-1 if using_atr else 0
    if start >= len(bars):
        return []
    def threshold(i):
        # Tiny price-relative floor prevents zero ATR causing zero-size reversals.
        return max(settings.atr_multiplier*atr[i], bars[i].close*1e-12) if using_atr else bars[i].close*settings.reversal_percent/100
    hi = lo = start
    hi_threshold = lo_threshold = threshold(start)
    direction, events = None, []
    for i in range(start+1, len(bars)):
        price = bars[i].close
        if direction is None:
            if price > bars[hi].close:
                hi, hi_threshold = i, threshold(i)
            if price < bars[lo].close:
                lo, lo_threshold = i, threshold(i)
            if i > lo and _reached(price-bars[lo].close, lo_threshold):
                events.append(_event(bars,'low',lo,i,method,lo_threshold,atr=atr[lo]))
                direction, hi, hi_threshold = 'up', i, threshold(i)
            elif i > hi and _reached(bars[hi].close-price, hi_threshold):
                events.append(_event(bars,'high',hi,i,method,hi_threshold,atr=atr[hi]))
                direction, lo, lo_threshold = 'down', i, threshold(i)
        elif direction == 'up':
            if price > bars[hi].close:
                hi, hi_threshold = i, threshold(i)
            elif i > hi and _reached(bars[hi].close-price, hi_threshold):
                events.append(_event(bars,'high',hi,i,method,hi_threshold,atr=atr[hi]))
                direction, lo, lo_threshold = 'down', i, threshold(i)
        else:
            if price < bars[lo].close:
                lo, lo_threshold = i, threshold(i)
            elif i > lo and _reached(price-bars[lo].close, lo_threshold):
                events.append(_event(bars,'low',lo,i,method,lo_threshold,atr=atr[lo]))
                direction, hi, hi_threshold = 'up', i, threshold(i)
    return events


def local_prominence(values, center):
    """Height above the higher side base, bounded by context or a higher value.

    Caller supplies a strict adjacent local maximum. Equal distant peaks do not
    stop the search. This matches SciPy's bounded prominence for non-plateau peaks.
    Apply to negated Close values to measure trough depth.
    """
    height = values[center]
    bases = []
    for step in (-1,1):
        minimum, j = height, center+step
        while 0 <= j < len(values) and values[j] <= height:
            minimum = min(minimum, values[j])
            j += step
        bases.append(minimum)
    return height-max(bases)


def _prominences(bars, settings):
    """Confirm at pivot+radius; reject adjacent plateaus and dense later events.

    The minimum-distance policy is first-accepted, separately for highs/lows.
    It never replaces an earlier confirmed pivot with a later larger peak.
    """
    r, events = settings.radius, []
    last = {'high': -10**18, 'low': -10**18}
    for t in range(2*r, len(bars)):
        pivot = t-r
        values = [b.close for b in bars[pivot-r:t+1]]
        for kind, sign in [('high',1),('low',-1)]:
            v = [sign*x for x in values]
            if not (v[r] > v[r-1] and v[r] > v[r+1]):
                continue
            prominence = local_prominence(v,r)
            threshold = bars[pivot].close*settings.min_prominence_percent/100
            if _reached(prominence, threshold) and pivot-last[kind] >= settings.min_distance:
                events.append(_event(bars,kind,pivot,t,'prominence',threshold,prominence))
                last[kind] = pivot
    return events


def detect_swings(bars, settings):
    """Return confirmed events from a chronological observed prefix.

    Args: bars: validated Bar list; settings: one of the three settings classes.
    Returns: immutable SwingPoint list, ordered by confirmation.
    Raises: ValueError for unordered input; TypeError for unsupported settings.
    """
    if any(b.timestamp <= a.timestamp for a,b in zip(bars,bars[1:])):
        raise ValueError('Bars must be in strictly increasing time order')
    if isinstance(settings, (PercentageSettings,ATRSettings)):
        return _reversals(bars,settings)
    if isinstance(settings, ProminenceSettings):
        return _prominences(bars,settings)
    raise TypeError('Unsupported swing settings')
