"""Streaming local-extrema detector: a pivot becomes known after a delay.

At completed bar t, evaluate i = t - window using only bars up to t. A strict
maximum/minimum over [i-window, i+window] is emitted at t, never at i. This is
retrospective pivot identification without giving earlier computations future
information. Once emitted, an event never changes.
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .data import Bar


@dataclass(frozen=True)
class SwingPoint:
    """Indices are zero-based internally; exported bar numbers are one-based."""

    # kind: Extremum type: "high" for a peak or "low" for a trough.
    kind: str
    # price: Pivot price: Close, or High/Low according to basis.
    price: float
    # pivot_index: Zero-based position of the pivot in the full observed bar sequence.
    pivot_index: int
    # pivot_time: Timestamp of the original peak or trough, before confirmation.
    pivot_time: datetime
    # confirmed_index: Zero-based bar position when the right-hand window completes.
    confirmed_index: int
    # confirmed_at: Timestamp when this swing first becomes available to analysis.
    confirmed_at: datetime
    # basis: Price selection: "close" for both kinds, or "high-low" for High/Low.
    basis: str

    def as_record(self) -> dict:
        """
        Convert this confirmed swing into a portable export record.

        Internal indices are zero-based; only exported bar numbers are increased by
        one. The original pivot time and the later confirmation time remain separate.

        Args:
            None.

        Result:
            dict: Kind, price, one-based pivot/confirmation bars, ISO timestamps,
                delay in bars and the selected price basis.

        Exception:
            No explicit exceptions for a SwingPoint containing valid field values.
        """
        return {
            "kind": self.kind,
            "price": self.price,
            "pivot_bar": self.pivot_index + 1,
            "pivot_time": self.pivot_time.isoformat(),
            "confirmed_bar": self.confirmed_index + 1,
            "confirmed_at": self.confirmed_at.isoformat(),
            "delay_bars": self.confirmed_index - self.pivot_index,
            "basis": self.basis,
        }


class SwingDetector:
    """Consume completed bars in chronological order with O(window) memory.

    basis='close' uses Close for both extrema, matching the PDF's illustrations.
    basis='high-low' uses High for peaks and Low for troughs. Strict comparisons
    exclude plateaus. An outside bar can be both kinds in high-low mode; no
    within-bar order is inferred. The window counts bars, not elapsed minutes.
    """

    def __init__(self, window: int = 2, basis: str = "close"):
        """
        Initialize a streaming detector with an empty rolling price window.

        The buffer holds at most 2 * window + 1 bars. Window size counts observations,
        including across time gaps and sessions, rather than elapsed minutes.

        Args:
            window (int): Number of neighbouring bars required on each side of a
                pivot. Must be at least 1; booleans are rejected. Default is 2.
            basis (str): 'close' for Close extrema, or 'high-low' for High peaks
                and Low troughs. Default is 'close'.

        Result:
            None: Initializes detector settings, its buffer and the running bar index.

        Exception:
            ValueError: If the window is invalid or the basis is unsupported.
        """
        if isinstance(window, bool) or not isinstance(window, int) or window < 1:
            raise ValueError("window must be an integer of at least 1.")
        if basis not in ("close", "high-low"):
            raise ValueError("basis must be 'close' or 'high-low'.")
        # window: Required neighbouring bars on EACH side; counts observations, not minutes.
        self.window = window
        # basis: Extremum source: "close" or "high-low".
        self.basis = basis
        # _bars: Rolling buffer of at most 2 * window + 1 completed bars, oldest first.
        self._bars = deque(maxlen=2 * window + 1)
        # _index: Zero-based position of the latest consumed bar; -1 before the first update.
        self._index = -1

    def update(self, bar: Bar) -> list[SwingPoint]:
        """
        Consume one completed bar and emit only swings newly confirmed at that bar.

        At index t, the candidate is t - window. Strict comparisons with all neighbours
        exclude equal-price plateaus. High-low mode can emit both a high and a low
        for an outside bar, without inferring their within-bar order. Confirmed events
        are never revised; the detector does not emit unconfirmed boundary points.

        Args:
            bar (Bar): A validated completed bar later than the previous input bar.

        Result:
            list[SwingPoint]: Zero, one or two newly confirmed events. Returns an
                empty list until the rolling window has enough observations.

        Exception:
            ValueError: If the new timestamp is not strictly later than the previous one.
        """
        if self._bars and bar.timestamp <= self._bars[-1].timestamp:
            raise ValueError("Bars must arrive in strictly increasing timestamp order.")
        self._bars.append(bar)
        self._index += 1
        if len(self._bars) < self._bars.maxlen:
            return []
        observed = list(self._bars)
        candidate = observed[self.window]
        neighbors = observed[:self.window] + observed[self.window + 1:]
        events = []
        for kind, field in (("high", "high"), ("low", "low")):
            field = "close" if self.basis == "close" else field
            value = getattr(candidate, field)
            other = [getattr(item, field) for item in neighbors]
            is_pivot = value > max(other) if kind == "high" else value < min(other)
            if is_pivot:
                events.append(SwingPoint(kind, value, self._index - self.window,
                                         candidate.timestamp, self._index,
                                         bar.timestamp, self.basis))
        return events


def detect_swings(bars: Iterable[Bar], window: int = 2, basis: str = "close") -> list[SwingPoint]:
    """
    Detect confirmed swings by replaying the supplied bars in time order.

    Uses the same update method as streaming detection. Only the supplied history
    is observed; no swing is forced at either boundary of that history.

    Args:
        bars (Iterable[Bar]): Validated bars in strictly increasing timestamp order.
        window (int): Required neighbours on each side of a pivot; default is 2.
        basis (str): 'close' or 'high-low'; default is 'close'.

    Result:
        list[SwingPoint]: Events in confirmation order. Empty or insufficient
            history produces no events when settings are valid.

    Exception:
        ValueError: If detector settings are invalid or timestamps are not increasing.
    """
    detector = SwingDetector(window, basis)
    return [event for bar in bars for event in detector.update(bar)]
