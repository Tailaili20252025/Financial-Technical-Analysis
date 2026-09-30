"""Step 4: causal Close-based first breaks and finite-window false-break labels.

Geometry and tolerance belong to Step 3 and are never refitted here. All accepted
Close-based lines are scanned, independently of the final chart ranking.
"""
from dataclasses import dataclass, asdict
from .data import Bar
from .trendlines import TrendLine


@dataclass(frozen=True)
class BreakoutSettings:
    """Project choices from Breakdown Point Report; counts refer to observed bars."""
    confirmation_bars: int = 2  # Consecutive directional closes, candidate included.
    observation_bars: int = 5  # Follow-up bars AFTER the candidate, deadline inclusive.

    def __post_init__(self):
        """Reject nonpositive/noninteger counts and unattainable confirmation lengths."""
        for name in ("confirmation_bars", "observation_bars"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.confirmation_bars > self.observation_bars + 1:
            raise ValueError("confirmation_bars cannot exceed observation_bars + 1")


@dataclass(frozen=True)
class BreakoutEvent:
    """One first-break event per line; indices are zero-based internally."""
    line_id: str  # Stable Step 3 direction/anchor identifier.
    direction: str  # breakout: above falling resistance; breakdown: below rising support.
    created_index: int  # Second anchor confirmation; candidate must occur later.
    candidate_index: int  # First qualifying Close beyond the directional threshold.
    price: float  # Actual Close at candidate, not the line's geometric value.
    line_value: float  # Frozen original line evaluated at candidate timestamp.
    buffer: float  # Absolute Step 3 tolerance, fixed using first anchor price.
    confirmation_index: int | None  # First qualifying consecutive run's last bar.
    failure_index: int | None  # First opposite-side breach inside the follow-up window.
    deadline_index: int  # Candidate + observation_bars; may lie beyond known history.
    outcome: str  # pending, false_breakout/false_breakdown, no_failure_within_window.
    outcome_index: int | None  # When outcome first became knowable; None while pending.
    observed_index: int  # Last supplied bar; snapshot cutoff, not a future projection.

    @property
    def confirmation_status(self):
        """Keep time confirmation separate from the finite-window outcome."""
        if self.confirmation_index is not None:
            return "confirmed"
        return "pending" if self.outcome == "pending" else "not_confirmed"

    def as_record(self, bars):
        """Export one-based bar numbers and only timestamps observed at the cutoff."""
        def time(index):
            return bars[index].timestamp.isoformat() if index is not None and index <= self.observed_index else None
        return {
            "line_id": self.line_id, "direction": self.direction, "basis": "close",
            "created_bar": self.created_index + 1, "created_at": time(self.created_index),
            "candidate_bar": self.candidate_index + 1, "candidate_at": time(self.candidate_index),
            "price": self.price, "line_value": self.line_value, "buffer": self.buffer,
            "confirmation_status": self.confirmation_status,
            "confirmation_bar": None if self.confirmation_index is None else self.confirmation_index + 1,
            "confirmed_at": time(self.confirmation_index),
            "confirmation_delay_bars": None if self.confirmation_index is None else self.confirmation_index-self.candidate_index,
            "failure_bar": None if self.failure_index is None else self.failure_index + 1,
            "failed_at": time(self.failure_index),
            "deadline_bar": self.deadline_index + 1, "deadline_at": time(self.deadline_index),
            "outcome": self.outcome,
            "outcome_bar": None if self.outcome_index is None else self.outcome_index + 1,
            "outcome_at": time(self.outcome_index),
            "followup_bars_observed": min(self.deadline_index, self.observed_index)-self.candidate_index,
            "full_window_observed": self.deadline_index <= self.observed_index,
            "observed_through_bar": self.observed_index + 1, "observed_through_at": time(self.observed_index),
        }


BREAKOUT_FIELDS = [
    "line_id", "direction", "basis", "created_bar", "created_at", "candidate_bar", "candidate_at",
    "price", "line_value", "buffer", "confirmation_status", "confirmation_bar", "confirmed_at",
    "confirmation_delay_bars", "failure_bar", "failed_at", "deadline_bar", "deadline_at", "outcome",
    "outcome_bar", "outcome_at", "followup_bars_observed", "full_window_observed",
    "observed_through_bar", "observed_through_at",
]


def detect_breakouts(bars: list[Bar], lines: list[TrendLine],
                     settings: BreakoutSettings | None = None) -> list[BreakoutEvent]:
    """Scan every eligible Close line, starting AFTER its second anchor confirmation.

    Args:
        bars: Validated chronological observed prefix (never future bars).
        lines: All Step 3 candidates for that prefix, not select_trendlines output.
        settings: Consecutive-close and follow-up counts; defaults to 2 and 5.
    Returns:
        Candidate-time-sorted events; High/Low lines are intentionally skipped.
        Later return can invalidate a confirmed break without erasing confirmation.
    Raises:
        ValueError: For unordered bars or duplicate line IDs.

    Equality and floating point noise do not cross a threshold. A neutral close
    resets the confirmation streak. Failure ends monitoring, and a new attempt
    on the same line does not create another event. An unfinished window remains
    pending even after confirmation. The deadline bar can confirm or fail.
    """
    settings = settings or BreakoutSettings()
    if any(b.timestamp <= a.timestamp for a, b in zip(bars, bars[1:])):
        raise ValueError("Breakout bars must be in strictly increasing time order")
    seen, events = set(), []
    for line in lines:
        if line.line_id in seen:
            raise ValueError("Duplicate trendline ID")
        seen.add(line.line_id)
        created = line.second.confirmed_index
        if line.first.basis != "close" or line.second.basis != "close" or created >= len(bars)-1:
            continue
        epsilon = max(1.0, abs(line.first.price), abs(line.second.price))*1e-12
        sign = 1 if line.kind == "down" else -1
        direction = "breakout" if sign == 1 else "breakdown"
        candidate = confirmed = failed = None
        streak = 0
        for i in range(created + 1, len(bars)):
            difference = sign*(bars[i].close-line.value_at(bars[i].timestamp))
            beyond = difference > line.tolerance + epsilon
            if candidate is None:
                if not beyond:
                    continue
                candidate = i
                deadline = i + settings.observation_bars
            if i > deadline:
                break
            if i > candidate and difference < -line.tolerance - epsilon:
                failed = i
                break
            streak = streak + 1 if beyond else 0
            if confirmed is None and streak >= settings.confirmation_bars:
                confirmed = i
        if candidate is None:
            continue
        if failed is not None:
            outcome, known = "false_" + direction, failed
        elif deadline < len(bars):
            outcome, known = "no_failure_within_window", deadline
        else:
            outcome, known = "pending", None
        events.append(BreakoutEvent(line.line_id, direction, created, candidate,
                      bars[candidate].close, line.value_at(bars[candidate].timestamp),
                      line.tolerance, confirmed, failed, deadline, outcome, known, len(bars)-1))
    return sorted(events, key=lambda e: (e.candidate_index, e.line_id))


def breakout_summary(events, settings=None, basis="close"):
    """Summarize line events; failure rate uses only fully observed follow-up windows."""
    settings = settings or BreakoutSettings()
    mature = [e for e in events if e.deadline_index <= e.observed_index]
    confirmed = [e for e in events if e.confirmation_index is not None]
    failures = sum(e.failure_index is not None for e in mature)
    return {
        "status": "enabled" if basis == "close" else "not_supported_high_low",
        "settings": asdict(settings), "basis": "close", "buffer_rule": "Step 3 fixed absolute first-anchor tolerance",
        "scope": "All accepted Close trendlines; one first-break event per line ID",
        "candidate_events": len(events), "breakouts": sum(e.direction == "breakout" for e in events),
        "breakdowns": sum(e.direction == "breakdown" for e in events),
        "confirmed": len(confirmed), "confirmation_pending": sum(e.confirmation_status == "pending" for e in events),
        "not_confirmed": sum(e.confirmation_status == "not_confirmed" for e in events),
        "false_breakouts": sum(e.outcome == "false_breakout" for e in events),
        "false_breakdowns": sum(e.outcome == "false_breakdown" for e in events),
        "pending": sum(e.outcome == "pending" for e in events),
        "no_failure_within_window": sum(e.outcome == "no_failure_within_window" for e in events),
        "fully_observed_candidates": len(mature), "failures_in_fully_observed_candidates": failures,
        "failure_rate_full_windows": failures/len(mature) if mature else None,
        "mean_confirmation_delay_bars": sum(e.confirmation_index-e.candidate_index for e in confirmed)/len(confirmed) if confirmed else None,
        "interpretation": "Confirmed can later fail. No failure within the window is not proof of future continuation. Counts are per line, not independent trades.",
    }
