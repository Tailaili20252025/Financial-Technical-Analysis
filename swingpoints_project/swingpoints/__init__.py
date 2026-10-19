"""Price analysis, confirmed patterns and simulated trades (Steps 1–6)."""

from .data import Bar, DataError, load_prices
from .detector import SwingDetector, SwingPoint, detect_swings

__all__ = ["Bar", "DataError", "load_prices", "SwingDetector", "SwingPoint", "detect_swings"]

from .trendlines import TrendLine, TrendSettings, detect_trendlines, select_trendlines

__all__ += ["TrendLine", "TrendSettings", "detect_trendlines", "select_trendlines"]

from .trading import Trade, TradeSettings, TradingResult, simulate_trades

__all__ += ["Trade", "TradeSettings", "TradingResult", "simulate_trades"]
