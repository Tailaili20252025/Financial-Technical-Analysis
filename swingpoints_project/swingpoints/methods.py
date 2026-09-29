"""Polymorphic swing strategies and adapters for the existing algorithms.

One registry serves CLI, GUI and experiments. Core algorithms have no UI or I/O.
All detect() calls are stateless replays of the supplied observed prefix.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from .detector import SwingDetector, SwingPoint, detect_swings
from .alternative_algorithms import (
    PercentageSettings, ATRSettings, ProminenceSettings,
    detect_swings as detect_alternative,
)


@dataclass(frozen=True)
class TASettings:
    """Traditional symmetric-window extrema settings."""
    window: int = 2  # Required completed neighbours on each side.
    basis: str = "close"  # Close or separate High/Low extrema.

    def __post_init__(self):
        """Reuse the established detector's settings validation."""
        SwingDetector(self.window, self.basis)


class SwingMethod(ABC):
    """Strategy contract: return confirmed SwingPoint objects for observed bars."""
    key = ""
    label = ""
    settings_type = None
    timing_rule = ""

    def __init__(self, settings=None):
        """Store a validated immutable settings object of this strategy's type."""
        if settings is None:
            settings = self.settings_type()
        if not isinstance(settings, self.settings_type):
            raise TypeError(f"{self.key} requires {self.settings_type.__name__}")
        self._settings = settings  # Algorithm parameters; exposed read-only below.

    @property
    def settings(self):
        """Return immutable algorithm parameters."""
        return self._settings

    @property
    def basis(self):
        """Return the price series consumed by this method."""
        return "close"

    @property
    def context_radius(self):
        """Return fixed right-context length, or zero for variable-delay reversal."""
        return 0

    @abstractmethod
    def detect(self, bars) -> list[SwingPoint]:
        """Detect only events confirmed within this chronological observed prefix."""
        raise NotImplementedError

    def metadata(self):
        """Describe settings and availability semantics for reproducible exports."""
        return {"method": self.key, "label": self.label,
                "settings": asdict(self.settings), "timing_rule": self.timing_rule}


class TraditionalTAMethod(SwingMethod):
    """Adapter around the unchanged traditional detect_swings function."""
    key, label = "ta", "Traditional TA"
    settings_type = TASettings
    timing_rule = "At completed bar t, test pivot t-window using only bars <= t."

    @property
    def basis(self):
        return self.settings.basis

    @property
    def context_radius(self):
        return self.settings.window

    def detect(self, bars):
        """Replay the original strict local-extrema detector."""
        return detect_swings(bars, self.settings.window, self.settings.basis)


class AlternativeMethod(SwingMethod):
    """Adapter translating the old alternative API to the common detect contract."""
    def detect(self, bars):
        """Call the shared alternative engine with this strategy's settings."""
        return detect_alternative(list(bars), self.settings)


class PercentageReversalMethod(AlternativeMethod):
    """Confirm alternating Close extremes after a fixed percentage reversal."""
    key, label = "percentage", "Percentage reversal"
    settings_type = PercentageSettings
    timing_rule = "Confirm a running Close extreme when the opposite move reaches its percentage threshold; delay varies."


class ATRReversalMethod(AlternativeMethod):
    """Confirm reversals using Wilder ATR frozen at the running extreme."""
    key, label = "atr", "ATR reversal"
    settings_type = ATRSettings
    timing_rule = "After ATR warm-up, confirm on a reversal of ATR-at-pivot times multiplier; delay varies."


class ProminenceMethod(AlternativeMethod):
    """Confirm peaks/troughs in bounded context with a prominence threshold."""
    key, label = "prominence", "Local prominence"
    settings_type = ProminenceSettings
    timing_rule = "Confirm at pivot+radius using bounded local prominence and first-accepted same-kind spacing."

    @property
    def context_radius(self):
        return self.settings.radius


# METHODS: Public name -> constructor; adding a strategy needs no pipeline branch.
METHODS = {cls.key: cls for cls in (
    TraditionalTAMethod, PercentageReversalMethod, ATRReversalMethod, ProminenceMethod)}


def create_method(name="ta", **attributes):
    """Create a strategy from dataclass attributes; reject unknown names/fields."""
    if name not in METHODS:
        raise ValueError(f"Unknown method {name!r}; choose {', '.join(METHODS)}")
    cls = METHODS[name]
    return cls(cls.settings_type(**attributes))
