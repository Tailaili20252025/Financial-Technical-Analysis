"""Independent accounting, time boundaries, source conversion and CLI checks."""
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from prepare_backtest_data import prepare
from swingpoints.backtesting import (PreparedBlock, TestPeriod, aggregate_portfolio, audit_prefix,
    audit_result, buy_and_hold, eligible_events, maximum_drawdown, prepare_block, simulate_block, validate_plan)
from swingpoints.breakouts import BreakoutEvent
from swingpoints.data import Bar, load_prices
from swingpoints.methods import create_method
from swingpoints.pipeline import analyze
from swingpoints.trading import TradeSettings

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    """Seven flat daily bars; a confirmation on day four fills on day five."""
    bars = [Bar(datetime(2020, 1, 1)+timedelta(days=i), 101, 99, 100, 100, 1000) for i in range(7)]
    event = BreakoutEvent("L1", "breakout", 1, 2, 100, 99, .5, 3, None, 7, "pending", None, 6)
    analysis = analyze(bars, create_method())
    block = PreparedBlock(TestPeriod("tiny", "2020-01-04", "2020-01-07"), bars, 3, analysis, [event])
    settings = TradeSettings(entry_timing="next_open", atr_period=1, atr_stop_multiple=1)
    return block, settings


class BacktestTests(unittest.TestCase):
    def test_future_bars_removed_and_warmup_required(self):
        bars = fixture()[0].bars
        period = TestPeriod("p", "2020-01-04", "2020-01-06")
        block = prepare_block(bars, period, create_method(), minimum_warmup_bars=3)
        self.assertEqual((block.start_index, len(block.bars)), (3, 6))
        with self.assertRaises(ValueError):
            prepare_block(bars, period, create_method(), minimum_warmup_bars=4)

    def test_only_new_confirmations_enter_but_later_failure_is_retained(self):
        event = fixture()[0].events[0]
        later_false = replace(event, line_id="false", confirmation_index=4, failure_index=5)
        candidates = [event, later_false, replace(event, line_id="none", confirmation_index=None)]
        self.assertEqual(eligible_events(candidates, 4), [later_false])

    def test_flat_reset_and_no_final_liquidation(self):
        block, settings = fixture()
        result, summary, equity, _ = simulate_block(block, replace(settings, fee_per_order=.5), "X", "base")
        self.assertEqual(result.trades[0].entry_index, 4)
        self.assertEqual((summary["realized_net_pnl"], summary["unrealized_net_pnl"]), (0, -.5))
        self.assertEqual(summary["net_pnl"], -.5)
        self.assertIsNone(summary["win_rate_percent"])
        self.assertEqual(equity[0]["equity"], 10000)
        self.assertIsNone(result.trades[0].exit_index)
        self.assertTrue(audit_result(block.bars, block.start_index, result, summary)["passed"])

    def test_final_confirmation_remains_pending(self):
        block, settings = fixture()
        block.events = [replace(block.events[0], confirmation_index=6)]
        result, summary, *_ = simulate_block(block, settings, "X", "zero")
        self.assertEqual(summary["filled_trades"], 0)
        self.assertEqual(summary["pending_entries"], 1)

    def test_next_open_prices_and_stop_first_with_costs(self):
        block, settings = fixture()
        block.bars[4] = replace(block.bars[4], open=110, high=120, low=100, close=110)
        result, summary, *_ = simulate_block(block, replace(settings, fee_per_order=.25), "X", "base")
        trade = result.trades[0]
        # ATR at confirmation = 2, unaffected by tomorrow's large range.
        self.assertEqual((trade.entry_price, trade.stop_price, trade.target_price), (110, 108, 114))
        self.assertEqual((trade.exit_price, trade.net_pnl), (108, -2.5))
        self.assertTrue(trade.ambiguous_exit)
        self.assertTrue(audit_result(block.bars, block.start_index, result, summary)["passed"])

    def test_borrow_reconstructed_from_calendar_days(self):
        block, settings = fixture()
        block.events = [replace(block.events[0], direction="breakdown")]
        result, summary, *_ = simulate_block(block, replace(settings, short_borrow_rate_percent=36.5), "X", "base")
        # 100 notional x 36.5% x 2/365 = 0.20, with no price movement.
        self.assertAlmostEqual(summary["net_pnl"], -.2)
        self.assertTrue(audit_result(block.bars, block.start_index, result, summary)["passed"])

    def test_audit_rejects_corrupted_equity(self):
        block, settings = fixture()
        result, summary, *_ = simulate_block(block, settings, "X", "zero")
        result.equity[4]["equity"] += .01
        with self.assertRaises(AssertionError): audit_result(block.bars, block.start_index, result, summary)

    def test_buy_hold_exact_cost_example_and_capital(self):
        bars = fixture()[0].bars
        bars[-1] = replace(bars[-1], close=102, high=103)
        settings = TradeSettings(quantity=2, slippage_bps=10, fee_per_order=.5)
        result = buy_and_hold(bars, settings)
        self.assertAlmostEqual(result[-1]["equity"], 10003.3)
        with self.assertRaises(ValueError): buy_and_hold(bars, replace(settings, initial_equity=100))

    def test_drawdown_includes_initial_capital(self):
        self.assertEqual(maximum_drawdown([95, 110, 88], 100), 20)

    def test_aggregate_drawdown_is_not_average_of_stock_drawdowns(self):
        block, settings = fixture()
        _, summary, *_ = simulate_block(block, settings, "A", "zero")
        a = {**summary, "initial_equity": 100, "symbol": "A"}
        b = {**a, "symbol": "B"}
        curves = {"A": [{"timestamp": "1", "equity": 110}, {"timestamp": "2", "equity": 90}],
                  "B": [{"timestamp": "1", "equity": 90}, {"timestamp": "2", "equity": 110}]}
        total, _ = aggregate_portfolio([a, b], curves, curves)
        self.assertEqual(total["max_drawdown_percent"], 0)
        curves["B"][1]["timestamp"] = "3"
        with self.assertRaises(ValueError): aggregate_portfolio([a, b], curves, curves)

    def test_invalid_plan_overlap_and_same_close(self):
        plan = json.loads((ROOT / "backtest_plan.json").read_text())
        validate_plan(plan)
        plan["periods"][1]["start"] = "2014-12-31"
        with self.assertRaises(ValueError): validate_plan(plan)
        plan["periods"][1]["start"] = "2015-01-01"
        plan["trade_settings"]["entry_timing"] = "confirmation_close"
        with self.assertRaises(ValueError): validate_plan(plan)

    def test_missing_open_and_high_low_are_rejected(self):
        block, _ = fixture()
        for bars, method in (([replace(b, open=None) for b in block.bars], create_method()),
                             (block.bars, create_method("ta", basis="high-low"))):
            with self.assertRaises(ValueError): prepare_block(bars, block.period, method, minimum_warmup_bars=0)

    def test_prefix_causality_on_original_app_data_all_methods(self):
        bars = load_prices(ROOT / "data" / "data.csv")
        # Original sample has minute bars: use a direct block to test the same engine.
        for name in ("ta", "percentage", "atr", "prominence"):
            analysis = analyze(bars, create_method(name))
            block = PreparedBlock(TestPeriod("prefix", bars[0].timestamp.date().isoformat(),
                                             bars[-1].timestamp.date().isoformat()), bars, 30,
                                  analysis, eligible_events(analysis.events, 30))
            settings = TradeSettings(entry_timing="next_open")
            result, summary, *_ = simulate_block(block, settings, "sample", "zero")
            self.assertTrue(audit_prefix(block, settings, result)["passed"])
            self.assertTrue(audit_result(bars, 30, result, summary)["passed"])


class DataAndCLITests(unittest.TestCase):
    def test_conversion_preserves_ohlcv_and_source_identity(self):
        raw = b"date,open,high,low,close,volume,Name\n2020-01-02,100,102,99,101,400,X\n2020-01-03,101,104,100,103,500,X\n"
        with tempfile.TemporaryDirectory() as folder:
            with patch("prepare_backtest_data.SOURCE_SHA256", hashlib.sha256(raw).hexdigest()):
                manifest = prepare(raw, folder, ["X"])
            bars = load_prices(Path(folder)/"X.csv")
            self.assertEqual((len(bars), bars[1].open, bars[1].close, bars[1].volume), (2, 101, 103, 500))
            self.assertEqual(manifest["selected_rows"], 2)
            with self.assertRaises(ValueError): prepare(raw+b"\n", folder, ["X"])

    def test_invalid_source_ohlc_is_not_imputed(self):
        raw = b"date,open,high,low,close,volume,Name\n2020-01-02,100,98,99,101,400,X\n"
        with tempfile.TemporaryDirectory() as folder, patch("prepare_backtest_data.SOURCE_SHA256", hashlib.sha256(raw).hexdigest()):
            with self.assertRaises(ValueError): prepare(raw, folder, ["X"])

    def test_cli_exports_and_refuses_accidental_overwrite(self):
        plan = json.loads((ROOT / "backtest_plan.json").read_text())
        plan.update(symbols=["X"], prefix_audit_symbols=[], minimum_warmup_bars=0, data_dir="data")
        plan["periods"] = [dict(name="tiny", start="2020-01-01", end="2020-01-07")]
        plan["methods"] = plan["methods"][:1]
        plan["cost_scenarios"] = plan["cost_scenarios"][:1]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/"data").mkdir()
            with (root/"data/X.csv").open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["timestamp", "open", "high", "low", "close", "volume"])
                w.writerows([b.timestamp.isoformat(), b.open, b.high, b.low, b.close, b.volume] for b in fixture()[0].bars)
            (root/"plan.json").write_text(json.dumps(plan))
            command = [sys.executable, str(ROOT/"backtest.py"), "--plan", str(root/"plan.json"), "--output", str(root/"result")]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            metadata = json.loads((root/"result/experiment.json").read_text())
            self.assertEqual((metadata["status"], metadata["simulations"]), ("completed", 1))
            self.assertTrue((root/"result/equity_comparison.png").exists())
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
