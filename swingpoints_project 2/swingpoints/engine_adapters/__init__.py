"""Optional execution engines sharing the application's Steps 1–4 signals.

Importing this package does not import Backtesting.py or require trading.py.
Use get_engine() to select an implementation through the same run interface.
"""
from .common import EngineSettings, EngineResult


def get_engine(name):
    """Construct an engine lazily; keep optional dependencies out of the GUI."""
    if name == "application":
        from .native import ApplicationEngine
        return ApplicationEngine()
    if name == "backtesting_py":
        from .framework import BacktestingPyEngine
        return BacktestingPyEngine()
    raise ValueError("Unknown engine: " + str(name))


__all__ = ["EngineSettings", "EngineResult", "get_engine"]
