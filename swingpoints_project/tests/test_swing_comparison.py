"""Integration checks for two swing alternatives under common later-stage rules."""
import csv
import json
import math
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from swingpoints.data import Bar
from swingpoints.detector import SwingPoint
from swingpoints.methods import create_method
from swingpoints.swing_comparison import (SwingComparisonSettings, audit_swing_prefixes,
    measure_detection, pair_pnl, require_methods, summarize_methods)


def bars(values):
    return [Bar(datetime(2020, 1, 1)+timedelta(days=i), value+1, value-1, value, value)
            for i, value in enumerate(values)]


class SwingComparisonTests(unittest.TestCase):
    def test_requires_ta_and_two_named_swing_alternatives(self):
        require_methods([create_method(k) for k in ("ta", "percentage", "atr")])
        for keys in (("ta", "percentage"), ("ta", "atr", "prominence"), ("ta", "atr", "atr")):
            with self.assertRaises(ValueError):
                require_methods([create_method(k) for k in keys])

    def test_metrics_use_confirmation_not_pivot_date(self):
        history = bars([100, 110, 108, 106.7, 100, 103])
        metrics, points = measure_detection(history, create_method("percentage", reversal_percent=3), 3,
                                             SwingComparisonSettings(1, 5))
        self.assertEqual([(p.kind, p.pivot_index, p.confirmed_index) for p in points],
                         [("low", 0, 1), ("high", 1, 3), ("low", 4, 5)])
        self.assertEqual(metrics["confirmed_swings"], 2)
        self.assertEqual(metrics["mean_delay_bars"], 1.5)

    def test_empty_swings_have_undefined_delay(self):
        metrics, _ = measure_detection(bars([100]*20), create_method("ta"), 5)
        self.assertEqual(metrics["confirmed_swings"], 0)
        self.assertIsNone(metrics["mean_delay_bars"])

    def test_all_selected_methods_keep_observed_prefix_events(self):
        history = bars([100+8*math.sin(i*.6) for i in range(60)])
        for key in ("ta", "percentage", "atr"):
            checks = audit_swing_prefixes(history, create_method(key), [12, 25, 47, 60])
            self.assertEqual(len(checks), 4)
            self.assertTrue(all(r["passed"] for r in checks))

    def test_prefix_audit_rejects_revised_confirmed_point(self):
        history = bars([100, 103, 99, 102])
        class RepaintingMethod:
            key = "bad"
            def detect(self, bb):
                return [SwingPoint("low", bb[0].close+len(bb), 0, bb[0].timestamp,
                                   1, bb[1].timestamp, "close")]
        with self.assertRaises(AssertionError):
            audit_swing_prefixes(history, RepaintingMethod(), [3])

    def test_pairs_by_stock_period_and_cost(self):
        rows = [dict(symbol=s, period="p", scenario="base", method=m, net_pnl=v)
                for s, values in (("A", [3, -1, 6]), ("B", [-8, -2, -10]))
                for m, v in zip(("ta", "percentage", "atr"), values)]
        paired = pair_pnl(list(reversed(rows)))
        self.assertEqual({(r["symbol"], r["alternative"]): r["difference"] for r in paired},
                         {("A", "percentage"): -4, ("A", "atr"): 3,
                          ("B", "percentage"): 6, ("B", "atr"): -2})

    def test_pairs_reject_missing_duplicate_and_nonfinite_arms(self):
        rows = [dict(symbol="A", period="p", scenario="base", method=k, net_pnl=1)
                for k in ("ta", "percentage", "atr")]
        for invalid in (rows[:2], rows+[rows[0]], rows[:2]+[dict(rows[2], net_pnl=float("nan"))]):
            with self.assertRaises(ValueError):
                pair_pnl(invalid)

    def test_measurement_settings_reject_invalid_counts(self):
        for value in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                SwingComparisonSettings(timing_repetitions=value)

    def test_combined_steps_export_three_methods_without_external_broker(self):
        try:
            from compare_swing_methods import run
            import backtest
        except ModuleNotFoundError:
            self.skipTest("Apply the separate backtesting additions to test Steps 5-6")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/"data").mkdir()
            with (root/"data/TEST.csv").open("w", newline="") as f:
                w = csv.writer(f); w.writerow(["timestamp", "Open", "High", "Low", "Close"])
                for i, b in enumerate(bars([100+i*.05+7*math.sin(i*.45) for i in range(100)])):
                    w.writerow([b.timestamp.isoformat(), b.open, b.high, b.low, b.close])
            source = Path(__file__).resolve().parents[1]/"swing_comparison_plan.json"
            plan = json.loads(source.read_text())
            plan.update(data_dir="data", symbols=["TEST"], prefix_audit_symbols=["TEST"],
                        minimum_warmup_bars=20,
                        periods=[dict(name="test", start="2020-02-01", end="2020-04-09")])
            path = root/"plan.json"; path.write_text(json.dumps(plan))
            output = root/"result"
            totals = run(path, output, SwingComparisonSettings(1, 40))
            self.assertEqual(len(totals), 9)
            self.assertEqual({r["method"] for r in totals}, {"ta", "percentage", "atr"})
            meta = json.loads((output/"comparison_experiment.json").read_text())
            self.assertEqual(meta["status"], "completed")
            self.assertEqual(meta["backtest_runs"], 9)
            self.assertEqual(meta["paired_comparisons"], 6)
            self.assertEqual(meta["swing_prefix_checks"], 9)
            self.assertTrue((output/"swing_and_trendline_comparison.png").is_file())
            self.assertTrue(json.loads((output/"backtest/validation.json").read_text())["passed"])


if __name__ == "__main__":
    unittest.main()
