"""Independent numeric fixtures and causal execution checks for the new adapter."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("TQDM_DISABLE","1")
from swingpoints.data import Bar
from swingpoints.engine_adapters import EngineSettings, get_engine
from swingpoints.engine_adapters.common import audit_accounting, reconcile
from swingpoints.engine_adapters.experiment import validate_plan

ROOT=Path(__file__).resolve().parents[1]
AVAILABLE=importlib.util.find_spec("backtesting") is not None
NATIVE=importlib.util.find_spec("swingpoints.trading") is not None


def bars_from(rows):
    """Create hand-checkable daily OHLC candles; a number means range +/-1."""
    result=[]
    for i,row in enumerate(rows):
        o,h,l,c=(row,row+1,row-1,row) if isinstance(row,(int,float)) else row
        result.append(Bar(datetime(2020,1,1)+timedelta(days=i),h,l,c,o))
    return result


def event(direction="breakout", confirmation=3, line="L1", failure=None, created=1):
    """Supply only the causal fields used at entry plus a deliberately unused label."""
    return SimpleNamespace(line_id=line,direction=direction,created_index=created,candidate_index=2,
                           confirmation_index=confirmation,failure_index=failure)


def config(**kwargs):
    """ATR(1)=2 in the initial candles; one ATR stop and two-risk profit target."""
    return replace(EngineSettings(atr_period=1,atr_stop_multiple=1),**kwargs)


@unittest.skipUnless(AVAILABLE,"Optional engine not installed; pip install -r requirements-engines.txt")
class BacktestingAdapterTests(unittest.TestCase):
    """Check framework outputs against numbers calculated by hand."""
    def setUp(self):
        self.engine=get_engine("backtesting_py")

    def run_case(self,rows,events=None,settings=None):
        bars=bars_from(rows)
        settings=settings or config()
        result=self.engine.run(bars,[event()] if events is None else events,settings)
        audit_accounting(bars,result,settings)
        return result

    def test_long_target_in_entry_bar(self):
        r=self.run_case([100]*4+[(100,105,99,104)])
        t=r.trades[0]
        self.assertEqual((t["entry_index"],t["exit_index"],t["stop_price"],t["target_price"]),(4,4,98,104))
        self.assertEqual(t["net_pnl"],4)

    def test_short_target_and_two_commissions(self):
        r=self.run_case([100]*4+[(100,101,95,96)],[event("breakdown")],config(fee_per_order=.25))
        self.assertAlmostEqual(r.trades[0]["net_pnl"],3.5)
        self.assertAlmostEqual(r.equity[-1],10003.5)

    def test_open_long_marks_and_no_forced_exit(self):
        r=self.run_case([100]*4+[(100,101.5,99,101)],settings=config(fee_per_order=.25))
        self.assertIsNone(r.trades[0]["exit_index"])
        self.assertAlmostEqual(r.trades[0]["net_pnl"],.75)
        self.assertAlmostEqual(r.equity[-1],10000.75)

    def test_open_short_marks_without_short_sale_cash_profit(self):
        r=self.run_case([100]*4+[(100,101,98.5,99)],[event("breakdown")],config(fee_per_order=.25))
        self.assertIsNone(r.trades[0]["exit_index"])
        self.assertAlmostEqual(r.equity[-1],10000.75)

    def test_both_levels_intrabar_stop_first_both_sides(self):
        for side,row,stop in (("breakout",(100,105,97,100),98),("breakdown",(100,103,95,100),102)):
            with self.subTest(side=side):
                r=self.run_case([100]*4+[row],[event(side)])
                self.assertEqual(r.trades[0]["exit_price"],stop)
                self.assertEqual(r.trades[0]["net_pnl"],-2)

    def test_adverse_gap_stop_fills_at_open_both_sides(self):
        for side,row,price in (("breakout",(95,97,94,96),95),("breakdown",(105,106,103,104),105)):
            r=self.run_case([100]*5+[row],[event(side)])
            self.assertEqual(r.trades[0]["exit_price"],price)
            self.assertEqual(r.trades[0]["net_pnl"],-5)

    def test_favourable_gap_has_priority_over_later_stop(self):
        r=self.run_case([100]*5+[(105,106,97,100)])
        self.assertEqual(r.trades[0]["exit_price"],105)
        self.assertEqual(r.trades[0]["net_pnl"],5)

    def test_favourable_short_gap_improves_limit(self):
        r=self.run_case([100]*5+[(95,103,94,100)],[event("breakdown")])
        self.assertEqual(r.trades[0]["exit_price"],95)
        self.assertEqual(r.trades[0]["net_pnl"],5)

    def test_confirmation_atr_not_entry_range(self):
        r=self.run_case([100]*4+[(110,130,109,112)])
        self.assertEqual((r.trades[0]["entry_price"],r.trades[0]["stop_price"],r.trades[0]["target_price"]),(110,108,114))

    def test_final_signal_does_not_fill(self):
        r=self.run_case([100]*4)
        self.assertEqual(r.trades,[])
        self.assertEqual(r.decisions[0]["status"],"queued")

    def test_opposing_signals_do_not_choose_a_direction(self):
        r=self.run_case([100]*5,[event(),event("breakdown",line="L2")])
        self.assertEqual(r.trades,[])
        self.assertEqual(r.decisions[0]["reason"],"opposing_signals")

    def test_same_direction_events_are_one_trade(self):
        r=self.run_case([100]*5,[event(line="B"),event(line="A",created=0)])
        self.assertEqual(len(r.trades),1)
        self.assertEqual(r.trades[0]["line_ids"],["A","B"])

    def test_occupied_signal_does_not_close_or_reverse(self):
        r=self.run_case([100]*7,[event(),event("breakdown",confirmation=4,line="L2")])
        self.assertEqual(len(r.trades),1)
        self.assertIsNone(r.trades[0]["exit_index"])
        self.assertEqual(r.decisions[1]["reason"],"position_open")

    def test_later_false_label_does_not_erase_a_fill(self):
        a=self.run_case([100]*7,[event(failure=5)])
        b=self.run_case([100]*7,[event()])
        self.assertEqual(a.trades,b.trades)
        self.assertEqual(a.equity,b.equity)

    def test_short_disabled_and_atr_unavailable(self):
        self.assertEqual(self.run_case([100]*5,[event("breakdown")],config(allow_short=False)).trades,[])
        self.assertEqual(self.run_case([100]*5,settings=config(atr_period=14)).trades,[])

    def test_capital_checked_at_gapped_entry_and_invalid_levels(self):
        for settings,rows,reason in ((config(initial_equity=101),[100]*4+[(110,111,109,110)],"insufficient_equity"),
                                     (config(atr_stop_multiple=100),[100]*5,"invalid_price_levels")):
            r=self.run_case(rows,settings=settings)
            self.assertEqual(r.trades,[])
            self.assertEqual(r.decisions[0]["reason"],reason)

    def test_fee_is_in_capital_check(self):
        r=self.run_case([100]*5,settings=config(initial_equity=100,fee_per_order=.1))
        self.assertEqual(r.trades,[])

    def test_phase_frame_contains_no_future_range_at_open(self):
        from swingpoints.engine_adapters.framework import phase_frame
        frame=phase_frame(bars_from([(100,120,80,115)]))
        self.assertEqual(list(frame.loc[0,["Open","High","Low","Close"]]),[100]*4)
        self.assertEqual(list(frame.loc[1,["Open","High","Low","Close"]]),[100,120,80,115])

    def test_alternative_runs_without_native_trading_module(self):
        with patch.dict(sys.modules,{"swingpoints.trading":None}):
            self.assertEqual(len(self.run_case([100]*5).trades),1)

    def test_prefix_equity_is_unchanged_when_future_bars_added(self):
        short=self.run_case([100]*5)
        longer=self.run_case([100]*5+[(105,106,97,100),110])
        self.assertEqual(short.equity,longer.equity[:5])
        self.assertIsNone(short.trades[0]["exit_index"])
        self.assertEqual(longer.trades[0]["exit_index"],5)

    @unittest.skipUnless(NATIVE,"Reference trading.py belongs to the separate Step 5–6/backtesting PR")
    def test_reconciliation_separates_gap_policy_from_bookkeeping(self):
        bars=bars_from([100]*5+[(105,106,97,100)])
        cfg=config(fee_per_order=.25)
        ref=get_engine("application").run(bars,[event()],cfg)
        alt=self.engine.run(bars,[event()],cfg)
        rec=reconcile(ref,alt,bars)
        self.assertTrue(rec["reconciled"])
        self.assertEqual(rec["raw_pnl_difference"],1)
        self.assertEqual(rec["target_gap_gain"],1)
        self.assertLess(rec["maximum_policy_adjusted_equity_difference"],1e-8)

    @unittest.skipUnless(NATIVE,"Reference trading.py belongs to the separate Step 5–6/backtesting PR")
    def test_reconciliation_detects_actual_error(self):
        bars=bars_from([100]*5)
        ref=get_engine("application").run(bars,[event()],config())
        alt=self.engine.run(bars,[event()],config())
        alt.equity[-1]+=1
        self.assertFalse(reconcile(ref,alt,bars)["reconciled"])
        with self.assertRaises(AssertionError): audit_accounting(bars,alt,config())

    def test_no_events_does_not_charge_commission(self):
        r=self.run_case([100]*5,[],config(fee_per_order=.25))
        self.assertEqual(r.equity,[10000]*5)

    def test_nonpositive_or_missing_open_is_rejected(self):
        for opening in (None,0,float("nan")):
            bars=bars_from([100]*5)
            bars[4]=replace(bars[4],open=opening)
            with self.assertRaises(ValueError): self.engine.run(bars,[event()],config())


class ComparisonContractTests(unittest.TestCase):
    """Fail early for incompatible settings and overlapping experiments."""
    def test_settings_reject_fractional_or_nonfinite_values(self):
        for args in ({"quantity":.5},{"quantity":True},{"atr_period":0},{"fee_per_order":-1},
                     {"initial_equity":float("inf")},{"allow_short":1}):
            with self.subTest(args=args),self.assertRaises(ValueError): EngineSettings(**args)

    def test_unsupported_costs_are_not_silently_ignored(self):
        with self.assertRaises(TypeError): EngineSettings(slippage_bps=5)

    def test_plan_forbids_overlapping_periods(self):
        plan=json.loads((ROOT/"engine_comparison_plan.json").read_text())
        plan["periods"][1]["start"]="2014-12-31"
        with self.assertRaises(ValueError): validate_plan(plan)

    def test_registry_unknown_engine_is_clear(self):
        with self.assertRaises(ValueError): get_engine("missing")

    def test_help_does_not_need_optional_libraries(self):
        p=subprocess.run([sys.executable,str(ROOT/"compare_engines.py"),"--help"],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn("--engines",p.stdout)

    @unittest.skipUnless(AVAILABLE,"Install optional engine for CLI smoke test")
    def test_single_input_cli_exports_before_reference_pr_is_merged(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/"out"
            p=subprocess.run([sys.executable,str(ROOT/"compare_engines.py"),"--input",str(ROOT/"data/data.csv"),
                              "--engines","backtesting_py","--repetitions","1","--output",str(output)],
                             capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            v=json.loads((output/"validation.json").read_text())
            self.assertTrue(v["all_accounting_passed"])
            self.assertIsNone(v["all_comparisons_reconciled"])
            self.assertEqual(v["audit_runs"],8)


if __name__=="__main__":
    unittest.main()
