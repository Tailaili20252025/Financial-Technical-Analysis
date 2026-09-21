"""Step 3: deterministic support/resistance lines from confirmed swing pairs.

No regression model is trained. Candidate geometry is fixed at creation. A
line can gain confirmed touches or become broken as completed bars arrive.
Replay must always pass only the observed prefix of prices and swing events.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from .data import Bar
from .detector import SwingPoint


@dataclass(frozen=True)
class TrendSettings:
    """Explicit project choices, not universal financial definitions."""

    # tolerance_percent: Allowed price deviation as percent of the FIRST anchor price; 0.5 means 0.5%.
    tolerance_percent: float = 0.5
    # lookback: Maximum number of earlier same-kind swings tried for each second anchor.
    lookback: int = 20
    # min_touches: Minimum confirmed touches for display selection, not candidate creation.
    min_touches: int = 2
    # max_per_direction: Maximum selected chart lines separately for up and down directions.
    max_per_direction: int = 3

    def __post_init__(self):
        """Validate settings before any detection or export.

        Args:
            None; dataclass fields contain the supplied settings.
        Result:
            None: Valid settings are retained unchanged.
        Exception:
            ValueError: For nonfinite/out-of-range tolerance or invalid integers.
        """
        if (isinstance(self.tolerance_percent, bool)
                or not isinstance(self.tolerance_percent, (int, float))
                or not isfinite(self.tolerance_percent)
                or not 0 <= self.tolerance_percent < 100):
            raise ValueError("Trend tolerance must be finite and between 0 (inclusive) and 100 percent (exclusive).")
        for name, minimum in (("lookback", 1), ("min_touches", 2), ("max_per_direction", 1)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"{name} must be an integer of at least {minimum}.")


@dataclass(frozen=True)
class TrendLine:
    """One observed candidate; indices are zero-based and slope is price/minute."""

    # kind: Direction: "up" for rising support or "down" for falling resistance.
    kind: str
    # first: Earlier confirmed swing anchor; defines the line origin and tolerance scale.
    first: SwingPoint
    # second: Later anchor; its confirmation bar is the line creation time.
    second: SwingPoint
    # slope: Fixed price change per elapsed minute, including overnight/session gaps.
    slope: float
    # tolerance: Absolute price tolerance: first.price * tolerance_percent / 100.
    tolerance: float
    # touches: Distinct same-kind swings within tolerance, confirmed before any first break.
    touches: tuple[SwingPoint, ...]
    # broken_index: Zero-based first breach bar after creation; None if unbroken so far.
    broken_index: int | None
    # observed_end: Zero-based final bar of this analysis prefix; not a future projection.
    observed_end: int

    @property
    def line_id(self) -> str:
        """Return a stable ID for this direction and anchor pair.

        Args:
            None.
        Result:
            str: Direction followed by one-based anchor bar numbers.
        Exception:
            None for valid stored fields.
        """
        return f"{self.kind}-{self.first.pivot_index + 1}-{self.second.pivot_index + 1}"

    def value_at(self, timestamp) -> float:
        """Evaluate the fixed line using elapsed minutes from its first anchor.

        Args:
            timestamp (datetime): Time with timezone semantics matching the input.
        Result:
            float: Geometrical line value, not a model prediction.
        Exception:
            TypeError: If timestamps have incompatible timezone semantics.
        """
        minutes = (timestamp - self.first.pivot_time).total_seconds() / 60
        return self.first.price + self.slope * minutes

    def as_record(self, bars: list[Bar], displayed: bool = False) -> dict:
        """Export geometry, confirmation timing, touches and break status.

        Args:
            bars (list[Bar]): The observed history used for this result.
            displayed (bool): Whether chart selection includes this line.
        Result:
            dict: Portable record with one-based indices and ISO timestamps.
        Exception:
            IndexError: If bars does not cover the stored indices.
        """
        created = self.second.confirmed_index
        end = self.broken_index if self.broken_index is not None else self.observed_end
        return {
            "line_id": self.line_id, "direction": self.kind, "basis": self.first.basis,
            "anchor1_bar": self.first.pivot_index + 1,
            "anchor1_time": self.first.pivot_time.isoformat(), "anchor1_price": self.first.price,
            "anchor2_bar": self.second.pivot_index + 1,
            "anchor2_time": self.second.pivot_time.isoformat(), "anchor2_price": self.second.price,
            "created_bar": created + 1, "created_at": bars[created].timestamp.isoformat(),
            "slope_per_minute": self.slope, "tolerance_price": self.tolerance,
            "touch_count": len(self.touches),
            "touch_bars": [p.pivot_index + 1 for p in self.touches],
            "touch_confirmed_bars": [p.confirmed_index + 1 for p in self.touches],
            "status": "broken" if self.broken_index is not None else "active",
            "broken_bar": None if self.broken_index is None else self.broken_index + 1,
            "broken_at": None if self.broken_index is None else bars[self.broken_index].timestamp.isoformat(),
            "end_bar": end + 1, "end_time": bars[end].timestamp.isoformat(),
            "displayed": displayed,
        }


def detect_trendlines(bars: list[Bar], points: list[SwingPoint],
                      settings: TrendSettings | None = None) -> list[TrendLine]:
    """Find rising support and falling resistance from confirmed same-kind pairs.

    Try each second anchor against the previous lookback same-kind swings. Reject
    flat/wrong-direction pairs and any line already crossed before or at creation.
    Use Close for close swings, Low for support and High for resistance otherwise.
    Stop at the first later crossing beyond a fixed absolute tolerance. Touches
    count only distinct same-kind swings confirmed before that break. The minimum
    touch setting filters display, not candidate history.

    Args:
        bars (list[Bar]): Validated completed bars in strictly increasing time order.
        points (list[SwingPoint]): Events from detect_swings on this history; events
            confirmed after the cutoff are ignored defensively.
        settings (TrendSettings or None): Candidate and display configuration.
    Result:
        list[TrendLine]: All accepted candidates, including subsequently broken lines.
            Empty or insufficient history returns an empty list.
    Exception:
        ValueError: If timestamps are unordered or available events do not match bars.
    """
    settings = settings or TrendSettings()
    if any(b.timestamp <= a.timestamp for a, b in zip(bars, bars[1:])):
        raise ValueError("Trendline bars must be in strictly increasing time order.")
    available = [p for p in points if p.confirmed_index < len(bars)]
    seen = set()
    for p in available:
        if (not 0 <= p.pivot_index < p.confirmed_index < len(bars)
                or p.kind not in ("high", "low") or p.basis not in ("close", "high-low")
                or p.pivot_time != bars[p.pivot_index].timestamp
                or p.confirmed_at != bars[p.confirmed_index].timestamp):
            raise ValueError("Swing events must match the observed bars and confirmation times.")
        field = "close" if p.basis == "close" else p.kind
        if p.price != getattr(bars[p.pivot_index], field) or (p.kind, p.pivot_index) in seen:
            raise ValueError("Swing price mismatch or duplicate swing event.")
        seen.add((p.kind, p.pivot_index))
    if len({p.basis for p in available}) > 1:
        raise ValueError("Use one swing basis per trendline analysis.")
    lines = []
    for pivot_kind, direction in (("low", "up"), ("high", "down")):
        swings = sorted((p for p in available if p.kind == pivot_kind), key=lambda p: p.pivot_index)
        if any(b.confirmed_index <= a.confirmed_index for a, b in zip(swings, swings[1:])):
            raise ValueError("Same-kind confirmations must follow pivot order.")
        for j, second in enumerate(swings):
            for first in swings[max(0, j-settings.lookback):j]:
                change = second.price - first.price
                if (direction == "up" and change <= 0) or (direction == "down" and change >= 0):
                    continue
                slope = change / ((second.pivot_time-first.pivot_time).total_seconds()/60)
                tolerance = first.price * settings.tolerance_percent / 100
                # A tiny numerical allowance avoids floating-point false crossings.
                epsilon = max(1.0, abs(first.price), abs(second.price)) * 1e-12
                field = "close" if first.basis == "close" else pivot_kind
                broken = None
                for i in range(first.pivot_index, len(bars)):
                    expected = first.price + slope * ((bars[i].timestamp-first.pivot_time).total_seconds()/60)
                    actual = getattr(bars[i], field)
                    breach = expected-actual if direction == "up" else actual-expected
                    if breach > tolerance + epsilon:
                        broken = i
                        break
                if broken is not None and broken <= second.confirmed_index:
                    continue
                touches = tuple(p for p in swings if p.pivot_index >= first.pivot_index
                                and (broken is None or p.confirmed_index < broken)
                                and abs(p.price - (first.price+slope*((p.pivot_time-first.pivot_time).total_seconds()/60)))
                                <= tolerance + epsilon)
                lines.append(TrendLine(direction, first, second, slope, tolerance, touches,
                                       broken, len(bars)-1))
    return lines


def select_trendlines(lines: list[TrendLine], settings: TrendSettings | None = None) -> list[TrendLine]:
    """Select a small, deterministic set for the current historical chart.

    Rank by more confirmed touches, longer anchor time span, then newer creation.
    Suppress lines sharing at least two touching pivots with an already selected
    line of the same direction. This display-only choice may change with new data;
    exported candidate records retain the full history.

    Args:
        lines (list[TrendLine]): Candidates computed for one observed prefix.
        settings (TrendSettings or None): Minimum touches and per-direction plot cap.
    Result:
        list[TrendLine]: At most max_per_direction lines for each direction.
    Exception:
        None for valid candidate objects and settings.
    """
    settings = settings or TrendSettings()
    chosen = []
    for kind in ("up", "down"):
        candidates = [line for line in lines if line.kind == kind and len(line.touches) >= settings.min_touches]
        candidates.sort(key=lambda line: (len(line.touches),
                        (line.second.pivot_time-line.first.pivot_time).total_seconds(),
                        line.second.confirmed_index, line.first.pivot_index), reverse=True)
        selected = []
        for line in candidates:
            indices = {p.pivot_index for p in line.touches}
            if any(len(indices & {p.pivot_index for p in other.touches}) >= 2 for other in selected):
                continue
            selected.append(line)
            if len(selected) == settings.max_per_direction:
                break
        chosen.extend(selected)
    return chosen
