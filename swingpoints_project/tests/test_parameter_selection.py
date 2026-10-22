"""Selection boundaries, scoring, deterministic search and end-to-end exports."""
import copy
import csv
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from optimize_parameters import load_cohort, run
from run_selected_parameters import run as run_selected
from swingpoints.backtesting import validate_plan as validate_backtest_plan
from swingpoints.data import Bar
from swingpoints.parameter_selection import (canonical, check_config, choose_best, config_id,
    default_config, evaluate_job, init_worker, joint_candidates, make_config,
    score_blocks, swing_candidates, validate_plan)

ROOT = Path(__file__).resolve().parents[1]


def plan():
    """Small predeclared experiment for orchestration tests, not research results."""
    value = json.loads((ROOT / "parameter_search_plan.json").read_text())
    value.update(development_symbols=["DEV"], heldout_symbols=["HOLD"], data_dir="data",
                 minimum_warmup_bars=10, joint_trials_per_method=2, prefix_audit_symbols=["DEV", "HOLD"])
    value["swing_grids"] = {"ta": {"attribute": "window", "values": [2, 3]},
                             "percentage": {"attribute": "reversal_percent", "values": [2, 5]}}
    value["rounds"] = [dict(name="tiny", validation=[dict(name="m"+str(m), start=f"2020-{m:02d}-01",
                      end=f"2020-{m:02d}-{30 if m==4 else 31}") for m in (3, 4, 5)],
                      test=dict(name="test", start="2020-06-01", end="2020-06-30"))]
    value["constraints"] = dict(minimum_blocks=3, minimum_closed_trades=1,
                               minimum_closed_per_block=1, maximum_drawdown_percent=5)
    value["cost_scenarios"] = {"base": value["cost_scenarios"]["base"]}
    return value


def bars(future_multiplier=1):
    """Deterministic oscillations with bounded OHLC and no missing sessions."""
    values = []
    for i in range(200):
        time = datetime(2020, 1, 1)+timedelta(days=i)
        close = 100 + i*.05 + 7*math.sin(i*.64) + 2*math.sin(i*.17)
        if time.month >= 6: close *= future_multiplier
        values.append(Bar(time, close+2, close-2, close, close-.1, 1000))
    return values


def write_data(root, future_multiplier=1, hold_multiplier=1):
    """Write fixture histories and verifiable manifests in the normal schema."""
    directory = root / "data"
    directory.mkdir(exist_ok=True)
    records = []
    for symbol in ("DEV", "HOLD"):
        path = directory / (symbol+".csv")
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
            multiplier = hold_multiplier if symbol == "HOLD" else 1
            for b in bars(future_multiplier):
                writer.writerow([b.timestamp.isoformat(), b.open*multiplier, b.high*multiplier,
                                 b.low*multiplier, b.close*multiplier, b.volume])
        records.append(dict(symbol=symbol, rows=200, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    manifest = dict(files=records)
    (directory / "source_manifest.json").write_text(json.dumps(manifest))
    return manifest


class ParameterSelectionTests(unittest.TestCase):
    def test_reference_plan_and_budget(self):
        value = json.loads((ROOT / "parameter_search_plan.json").read_text())
        validate_plan(value)
        self.assertEqual((len(value["development_symbols"]), len(value["heldout_symbols"])), (40, 20))
        initial = [c for m in value["swing_grids"] for c in swing_candidates(value, m)]
        self.assertEqual(len(initial), 16)
        joint = [c for m in value["swing_grids"] for c in joint_candidates(value, m, default_config(value, m),
                  0, {config_id(c) for c in initial})]
        self.assertEqual(len({config_id(c) for c in initial+joint}), 96)

    def test_grid_and_joint_search_reproducible_unique_and_seeded(self):
        value = plan()
        parent = swing_candidates(value, "ta")[1]
        a = joint_candidates(value, "ta", parent, 0, set())
        self.assertEqual(a, joint_candidates(value, "ta", parent, 0, set()))
        value["seed"] += 1
        self.assertNotEqual(a, joint_candidates(value, "ta", parent, 0, set()))
        self.assertTrue(all(c["method"]["attributes"]["window"] == 3 for c in a))

    def test_hash_covers_effective_settings_not_dictionary_order(self):
        config = make_config("ta")
        self.assertEqual(config_id(config), config_id(dict(reversed(list(config.items())))))
        changed = copy.deepcopy(config)
        changed["breakout"]["confirmation_bars"] += 1
        self.assertNotEqual(config_id(config), config_id(changed))
        self.assertEqual(check_config(config), config)

    def test_manual_score_and_constraints(self):
        blocks = [dict(account_return_percent=r, net_pnl=r*100, closed_trades=20,
                       max_drawdown_percent=dd) for r, dd in ((1, 2), (-.5, 3), (2, 4))]
        limits = dict(minimum_blocks=3, minimum_closed_trades=50, minimum_closed_per_block=10,
                      maximum_drawdown_percent=5)
        score = score_blocks(blocks, limits)
        self.assertEqual((score["median_return_percent"], score["aggregate_net_pnl"], score["closed_trades"]), (1, 250, 60))
        self.assertTrue(score["eligible"])
        blocks[0].update(closed_trades=0, max_drawdown_percent=6)
        score = score_blocks(blocks, limits)
        self.assertFalse(score["eligible"])
        self.assertEqual(set(score["constraint_failures"]), {"too_few_closed_trades", "too_few_closed_in_a_block", "drawdown_limit"})

    def test_ranking_excludes_failed_ineligible_and_breaks_ties(self):
        base = dict(status="completed", eligible=True, median_return_percent=1,
                    worst_drawdown_percent=2, aggregate_net_pnl=3, config_id="b")
        candidates = [base, {**base, "config_id": "a"}, {**base, "config_id": "c", "eligible": False, "median_return_percent": 100},
                      {**base, "config_id": "d", "status": "failed", "median_return_percent": 100}]
        self.assertEqual(choose_best(candidates)["config_id"], "a")
        self.assertIsNone(choose_best(candidates[2:]))
        self.assertEqual(choose_best(candidates[2:], False)["config_id"], "c")

    def test_overlap_holdout_timing_and_unknown_keys_rejected(self):
        for mutation in (lambda p: p["heldout_symbols"].append("DEV"),
                         lambda p: p["rounds"][0]["test"].update(start="2020-05-31"),
                         lambda p: p["rounds"][0]["validation"][1].update(start="2020-03-31"),
                         lambda p: p["trade_settings"].update(entry_timing="confirmation_close"),
                         lambda p: p["joint_space"].update(quantity=[1, 100]),
                         lambda p: p["swing_grids"]["ta"].update(values=[2, 2])):
            value = plan()
            mutation(value)
            with self.assertRaises((ValueError, TypeError)): validate_plan(value)

    def test_validation_unchanged_by_later_prices(self):
        value = plan()
        configs = swing_candidates(value, "ta")
        period = value["rounds"][0]["validation"][-1]
        task = ("DEV", period, configs, "base", value["cost_scenarios"]["base"], 10, False, False)
        init_worker({"DEV": bars()})
        before = evaluate_job(task)
        init_worker({"DEV": bars(4)})
        after = evaluate_job(task)
        self.assertEqual(before, after)
        self.assertTrue(all(i["status"] == "completed" for i in before))

    def test_failed_worker_result_is_logged_not_dropped(self):
        value = plan()
        init_worker({})
        output = evaluate_job(("MISSING", value["rounds"][0]["test"], [default_config(value, "ta")],
                               "base", value["cost_scenarios"]["base"], 10, False, False))
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["status"], "failed")
        self.assertIn("KeyError", output[0]["error"])

    def test_manifest_modification_and_calendar_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = write_data(root)
            path = root / "data/DEV.csv"
            path.write_text(path.read_text()+"\n")
            with self.assertRaises(ValueError): load_cohort(root / "data", ["DEV"], manifest)
            manifest = write_data(root)
            path = root / "data/HOLD.csv"
            lines = path.read_text().splitlines(True)
            path.write_text("".join(lines[:1]+lines[2:]))
            manifest["files"][1]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(ValueError): load_cohort(root / "data", ["DEV", "HOLD"], manifest)

    def test_preset_tampering_and_overwrite_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = make_config("ta")
            preset = dict(version=1, config=config, config_id="wrong", costs={})
            path = root / "preset.json"
            path.write_text(json.dumps(preset))
            with self.assertRaises(ValueError): run_selected("unused.csv", path, root / "output")

    def test_end_to_end_freeze_exports_and_future_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_data(root)
            path = root / "plan.json"
            path.write_text(json.dumps(plan()))
            # Plot formatting is visually checked on the full research run.
            with patch("optimize_parameters.plot_results"):
                first, summaries = run(path, root / "first", workers=1)
                # Neither changed test prices nor changed held-out stock prices may alter selection.
                write_data(root, future_multiplier=1.4, hold_multiplier=1.8)
                second, _ = run(path, root / "second", workers=2)
            self.assertEqual(first, second)
            self.assertEqual((root / "first/trials.jsonl").read_text(), (root / "second/trials.jsonl").read_text())
            self.assertEqual(len(summaries), 8)  # 4 arms x 2 cohorts x 1 cost.
            self.assertEqual(len((root / "first/trials.jsonl").read_text().splitlines()), 8)
            replay = json.loads((root / "first/selected_backtest_plan.json").read_text())
            validate_backtest_plan(replay)
            audit = json.loads((root / "first/validation.json").read_text())
            self.assertTrue(audit["passed"])
            self.assertGreater(audit["audited_equity_rows"], 0)
            self.assertTrue(all(a["passed"] for a in audit["prefix_audits"]))
            self.assertEqual(json.loads((root / "first/experiment.json").read_text())["status"], "completed")
            with self.assertRaises(ValueError): run(path, root / "first")


if __name__ == "__main__":
    unittest.main()
