"""Step 3 tests: hand arithmetic, time availability, rendering and integration."""

from dataclasses import replace
from datetime import timedelta
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure

from swingpoints import Bar, detect_swings, load_prices
from swingpoints.trendlines import TrendSettings, detect_trendlines, select_trendlines
from swingpoints.plotting import draw_prices
from swingpoints.output import export_results
from test_system import make_bars

ROOT = Path(__file__).resolve().parents[1]


def analyze(values, tolerance=0):
    """Analyze a synthetic sequence with one-bar swing confirmation.

    Args:
        values (list[float]): Synthetic close prices.
        tolerance (float): Percent of the first anchor price.
    Result:
        tuple: Bars, confirmed swings, candidate lines and settings.
    Exception:
        ValueError: Invalid trend settings or inconsistent data.
    """
    bars = make_bars(values)
    points = detect_swings(bars, 1)
    settings = TrendSettings(tolerance_percent=tolerance)
    return bars, points, detect_trendlines(bars, points, settings), settings


class TrendTests(unittest.TestCase):
    def test_rising_lows_slope_touches_and_confirmation(self):
        """Check a hand-calculated rising line, three touches and delayed creation.

        Args:
            None.
        Result:
            None: Completes when the stated invariants hold.
        Exception:
            AssertionError: An expected value or error differs; other errors reach unittest.
        """
        bars, points, lines, settings = analyze([105, 100, 106, 102, 108, 104, 110])
        line = next(line for line in lines if line.line_id == "up-2-4")
        self.assertEqual(line.slope, 1)
        self.assertEqual(line.value_at(bars[5].timestamp), 104)
        self.assertEqual([p.pivot_index for p in line.touches], [1, 3, 5])
        self.assertEqual(line.second.confirmed_index, 4)
        self.assertIsNone(line.broken_index)
        self.assertNotIn(line.line_id, [x.line_id for x in detect_trendlines(bars[:4], points, settings)])
        self.assertIn(line.line_id, [x.line_id for x in detect_trendlines(bars[:5], points, settings)])
        selected = select_trendlines(lines, settings)
        self.assertEqual(len(selected), 1)  # Three collinear pairs collapse for display.
        self.assertEqual(len(selected[0].touches), 3)

    def test_falling_highs(self):
        """Check a hand-calculated falling resistance line and negative slope.

        Args:
            None.
        Result:
            None: Completes when the stated invariants hold.
        Exception:
            AssertionError: An expected value or error differs; other errors reach unittest.
        """
        bars, _, lines, _ = analyze([105, 110, 104, 108, 102, 106, 100])
        line = next(line for line in lines if line.line_id == "down-2-4")
        self.assertEqual(line.slope, -1)
        self.assertEqual(line.value_at(bars[5].timestamp), 106)
        self.assertEqual(len(line.touches), 3)

    def test_equal_anchors_and_insufficient_history(self):
        """Exclude horizontal lines, monotonic prices and insufficient observations.

        Args:
            None.
        Result:
            None: Completes when the stated invariants hold.
        Exception:
            AssertionError: An expected value or error differs; other errors reach unittest.
        """
        for values in ([], [100], [100]*6, [100,101,102,103], [105,100,106,100,107]):
            _, _, lines, _ = analyze(values)
            self.assertEqual(lines, [])

    def test_first_break_stops_line_and_late_touch_confirmation(self):
        """Stop at the first break and exclude touches confirmed at or after it.

        Args:
            None.
        Result:
            None: Completes when the stated invariants hold.
        Exception:
            AssertionError: An expected value or error differs; other errors reach unittest.
        """
        bars, _, lines, _ = analyze([105,100,106,102,108,104,110,99,120])
        line = next(line for line in lines if line.line_id == "up-2-4")
        self.assertEqual(line.broken_index, 7)
        self.assertEqual(line.as_record(bars)["broken_bar"], 8)
        self.assertEqual(len(line.touches), 3)
        # The third trough is on the line, but it is only confirmed at the break bar.
        _, _, late, _ = analyze([105,100,106,102,108,104,104.5])
        late_line = next(x for x in late if x.line_id == "up-2-4")
        self.assertEqual(late_line.broken_index, 6)
        self.assertEqual(len(late_line.touches), 2)

    def test_reject_crossing_before_creation(self):
        """Reject lines crossed between anchors or during confirmation delay.

        Args:
            None.
        Result:
            None: Completes when the stated invariants hold.
        Exception:
            AssertionError: An expected value or error differs; other errors reach unittest.
        """
        _, _, lines, _ = analyze([105,100,106,99,108,104,110])
        self.assertNotIn("up-2-6", [line.line_id for line in lines])
        # The second trough exists, but by its two-bar confirmation the line broke.
        bars = make_bars([104,103,100,106,108,109,110,105,109,106])
        points = detect_swings(bars, 2)
        lines = detect_trendlines(bars, points, TrendSettings(0))
        self.assertNotIn("up-3-8", [line.line_id for line in lines])

    def test_tolerance_boundary_and_near_touch(self):
        """Check inclusive tolerance boundaries and approximate swing touches.

        Args:
            None.
        Result:
            None: Completes when the stated invariants hold.
        Exception:
            AssertionError: An expected value or error differs; other errors reach unittest.
        """
        bars, points, _, _ = analyze([105,100,106,102,108,103.6,110])
        tolerant = detect_trendlines(bars, points, TrendSettings(.5))
        line = next(x for x in tolerant if x.line_id == "up-2-4")
        self.assertEqual(line.tolerance, .5)
        self.assertEqual(len(line.touches), 3)
        strict = detect_trendlines(bars, points, TrendSettings(0))
        self.assertEqual(next(x for x in strict if x.line_id == "up-2-4").broken_index, 5)
        for value, broken in ((103.5, None), (103.49, 5)):
            _, _, lines, _ = analyze([105,100,106,102,108,value,110], .5)
            self.assertEqual(next(x for x in lines if x.line_id == "up-2-4").broken_index, broken)

    def test_elapsed_time_handles_gaps(self):
        """Use elapsed minutes rather than bar numbers when timestamps have gaps.

        Args:
            None.
        Result:
            None: Completes when the stated invariants hold.
        Exception:
            AssertionError: An expected value or error differs; other errors reach unittest.
        """
        bars = make_bars([105,100,106,104,110])
        bars = [replace(bar, timestamp=bar.timestamp+timedelta(minutes=2 if i >= 3 else 0))
                for i, bar in enumerate(bars)]
        line = next(x for x in detect_trendlines(bars, detect_swings(bars, 1), TrendSettings(0)) if x.kind == "up")
        self.assertEqual(line.slope, 1)  # 4 price units / 4 elapsed minutes, not 2 bars.

    def test_high_low_uses_wicks_for_breaks(self):
        """Distinguish Close-based support from Low-based support on a long wick.

        Args:
            None.
        Result:
            None: Completes when the stated invariants hold.
        Exception:
            AssertionError: An expected value or error differs; other errors reach unittest.
        """
        bars = make_bars([105,100,106,102,108,107,110])
        bars[5] = replace(bars[5], low=90)
        close = detect_trendlines(bars, detect_swings(bars,1,"close"), TrendSettings(0))
        wicks = detect_trendlines(bars, detect_swings(bars,1,"high-low"), TrendSettings(0))
        self.assertIsNone(next(x for x in close if x.line_id == "up-2-4").broken_index)
        self.assertEqual(next(x for x in wicks if x.line_id == "up-2-4").broken_index, 5)
        self.assertEqual(next(x for x in wicks if x.line_id == "up-2-4").first.price, 99)

    def test_every_prefix_reproduces_available_candidate_history(self):
        """Compare every supplied-data prefix with the available full-run history for both bases.

        Args:
            None.
        Result:
            None: Completes when the stated invariants hold.
        Exception:
            AssertionError: An expected value or error differs; other errors reach unittest.
        """
        bars = load_prices(ROOT / "data/data.csv")
        settings = TrendSettings()
        for basis in ("close", "high-low"):
            full = detect_trendlines(bars, detect_swings(bars,2,basis), settings)
            for size in range(1, len(bars)+1):
                actual = detect_trendlines(bars[:size], detect_swings(bars[:size],2,basis), settings)
                expected = [replace(line, observed_end=size-1,
                            broken_index=line.broken_index if line.broken_index is not None and line.broken_index < size else None,
                            touches=tuple(p for p in line.touches if p.confirmed_index < size))
                            for line in full if line.second.confirmed_index < size]
                self.assertEqual(actual, expected, (basis, size))

    def test_unobserved_swings_ignored_and_future_changes_cannot_leak(self):
        """Ignore unconfirmed events and prevent changed future prices from affecting a prefix.

        Args:
            None.
        Result:
            None: Completes when the stated invariants hold.
        Exception:
            AssertionError: An expected value or error differs; other errors reach unittest.
        """
        bars, points, _, settings = analyze([105,100,106,102,108,104,110,99,120])
        before = detect_trendlines(bars[:5], detect_swings(bars[:5],1), settings)
        self.assertEqual(before, detect_trendlines(bars[:5], points, settings))
        changed = bars[:5] + [replace(b, high=501, low=499, close=500) for b in bars[5:]]
        self.assertEqual(before, detect_trendlines(changed[:5], detect_swings(changed,1), settings))

    def test_settings_validation_and_display_only_filter(self):
        """Validate numeric settings and keep display filtering separate from detection.

        Args:
            None.
        Result:
            None: Completes when the stated invariants hold.
        Exception:
            AssertionError: An expected value or error differs; other errors reach unittest.
        """
        for kwargs in ({"tolerance_percent":float("nan")}, {"tolerance_percent":float("inf")},
                       {"tolerance_percent":-1}, {"tolerance_percent":100}, {"lookback":0},
                       {"min_touches":1}, {"max_per_direction":True}):
            with self.assertRaises(ValueError): TrendSettings(**kwargs)
        bars, points, lines, _ = analyze([105,100,106,102,108])
        self.assertTrue(lines)
        settings = TrendSettings(0, min_touches=3)
        self.assertEqual(detect_trendlines(bars,points,settings),lines)
        self.assertEqual(select_trendlines(lines,settings),[])
        self.assertEqual(detect_trendlines([],[]),[])

    def test_mismatched_events_and_bad_order_rejected(self):
        """Reject duplicate or inconsistent swings and unordered input bars.

        Args:
            None.
        Result:
            None: Completes when the stated invariants hold.
        Exception:
            AssertionError: An expected value or error differs; other errors reach unittest.
        """
        bars, points, _, _ = analyze([105,100,106,102,108])
        for bad in ([replace(points[0],price=999)], points+[points[0]],
                    [replace(points[0],confirmed_index=-1)]):
            with self.assertRaises(ValueError): detect_trendlines(bars,bad)
        with self.assertRaises(ValueError): detect_trendlines(list(reversed(bars)),points)

    def test_lookback_limits_anchor_search(self):
        """Limit candidate pairs to the configured count of prior same-kind swings.

        Args:
            None.
        Result:
            None: Completes when the stated invariants hold.
        Exception:
            AssertionError: An expected value or error differs; other errors reach unittest.
        """
        bars, points, lines, _ = analyze([105,100,106,102,108,104,110])
        limited = detect_trendlines(bars, points, TrendSettings(0,lookback=1))
        self.assertIn("up-2-6", [line.line_id for line in lines])
        self.assertNotIn("up-2-6", [line.line_id for line in limited])

    def test_plot_creation_and_break_segments(self):
        """Verify dashed/solid timing segments stay within the observed timestamps.

        Args:
            None.
        Result:
            None: Completes when the stated invariants hold.
        Exception:
            AssertionError: An expected value or error differs; other errors reach unittest.
        """
        bars, points, lines, settings = analyze([105,100,106,102,108,104,110,99])
        fig = Figure()
        draw_prices(fig,bars,points,1,"close",lines=lines,settings=settings)
        trend_segments = [line for line in fig.axes[0].lines if line.get_color() in ("#079447", "#e32929")]
        self.assertTrue(trend_segments)
        self.assertEqual({line.get_linestyle() for line in trend_segments},{"--","-"})
        for segment in trend_segments:
            self.assertLessEqual(max(segment.get_xdata()),bars[-1].timestamp)
        fig.clear()

    def test_cli_csv_json_and_empty_outputs(self):
        """Check equivalent CSV/JSON trend exports and valid empty-result output files.

        Args:
            None.
        Result:
            None: Completes when the stated invariants hold.
        Exception:
            AssertionError: An expected value or error differs; other errors reach unittest.
        """
        with tempfile.TemporaryDirectory() as directory:
            outputs = []
            for ext in ("csv","json"):
                dest = Path(directory)/ext
                result = subprocess.run([sys.executable,"app.py",f"data/data.{ext}","--until","100",
                                         "--output",str(dest)],cwd=ROOT,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                records = json.loads((dest/"trendlines.json").read_text())
                self.assertTrue(records)
                self.assertTrue(all(r["created_bar"] <= 100 and r["end_bar"] <= 100 for r in records))
                with (dest/"trendlines.csv").open() as stream:
                    csv_records = list(csv.DictReader(stream))
                self.assertEqual(len(csv_records),len(records))
                self.assertEqual(json.loads(csv_records[0]["touch_bars"]),records[0]["touch_bars"])
                self.assertEqual({p.name for p in dest.iterdir()}, {
                    "prices.png", "swing_points.csv", "swing_points.json", "trendlines.csv", "trendlines.json",
                    "run_summary.json", "indicators.csv", "indicators.json", "indicators.png"})
                outputs.append(records)
            self.assertEqual(*outputs)
            dest = Path(directory)/"empty"
            result = subprocess.run([sys.executable,"app.py","data/data.csv","--until","1",
                                     "--output",str(dest)],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads((dest/"trendlines.json").read_text()),[])
            self.assertIn("line_id",(dest/"trendlines.csv").read_text())

    def test_cli_invalid_options(self):
        """Reject invalid trendline CLI settings without an unhandled traceback.

        Args:
            None.
        Result:
            None: Completes when the stated invariants hold.
        Exception:
            AssertionError: An expected value or error differs; other errors reach unittest.
        """
        for args in (["--trend-tolerance","nan"],["--trend-tolerance","-1"],
                     ["--min-touches","1"],["--trend-lookback","0"],["--max-trendlines","0"]):
            result = subprocess.run([sys.executable,"app.py","data/data.csv",*args],cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertNotIn("Traceback",result.stderr)

    def test_new_output_names_cannot_overwrite_source(self):
        """Protect source files named like either new trendline export.

        Args:
            None.
        Result:
            None: Completes when the stated invariants hold.
        Exception:
            AssertionError: An expected value or error differs; other errors reach unittest.
        """
        bars = make_bars([100])
        with tempfile.TemporaryDirectory() as directory:
            for name in ("trendlines.csv","trendlines.json"):
                source = Path(directory)/name
                source.write_text("keep")
                with self.assertRaises(ValueError): export_results(directory,source,bars,[],2,"close",None)
                self.assertEqual(source.read_text(),"keep")


    def test_gui_replay_uses_visible_prefix_and_updates_both_tables(self):
        """Exercise the actual refresh callback with mock widgets and real analysis.

        Args:
            None.
        Result:
            None: Only the visible prefix is analyzed and both tables match results.
        Exception:
            AssertionError: The saved run, rows or drawing call differs.
        """
        from swingpoints.gui import SwingApp
        app = SwingApp.__new__(SwingApp)
        app.bars = make_bars([105,100,106,102,108,104,110,99])
        app.source = Path("example.csv")
        for name, value in (("window","1"),("cutoff","7"),("basis","close"),
                            ("trend_tolerance","0"),("trend_lookback","20"),
                            ("min_touches","2"),("max_lines","3")):
            variable = MagicMock()
            variable.get.return_value = value
            setattr(app,name,variable)
        from swingpoints.indicators import IndicatorSettings, calculate_indicators
        app.indicator_settings = IndicatorSettings(sma_period=3)
        app.indicator_table = MagicMock()
        app.indicator_table.__getitem__.return_value = ("bar", "sma", "vwap_status")
        app.figure, app.canvas = Figure(), MagicMock()
        app.table, app.trend_table = MagicMock(), MagicMock()
        app.table.__getitem__.return_value = ("kind","pivot_bar")
        app.trend_table.__getitem__.return_value = ("line_id","touch_count","status")
        app.export_button, app.status = MagicMock(), MagicMock()
        app.refresh()
        source, visible, points, window, basis, lines, settings, indicator_settings = app.current_run
        self.assertEqual(len(visible),7)
        self.assertEqual(app.indicator_table.insert.call_count,7)
        self.assertEqual(app.indicator_result,calculate_indicators(visible,indicator_settings))
        self.assertEqual(lines,detect_trendlines(visible,detect_swings(visible,1),settings))
        self.assertEqual(app.table.insert.call_count,len(points))
        self.assertEqual(app.trend_table.insert.call_count,len(select_trendlines(lines,settings)))
        app.canvas.draw.assert_called_once()
        self.assertTrue(all(line.broken_index is None for line in lines))

    def test_gui_export_uses_applied_settings(self):
        """Export the stored run even when the control values have since changed.

        Args:
            None.
        Result:
            None: Export receives the previously applied candidate list and settings.
        Exception:
            AssertionError: The callback recomputes or exports different settings.
        """
        from swingpoints.gui import SwingApp
        app = SwingApp.__new__(SwingApp)
        bars, points, lines, settings = analyze([105,100,106,102,108])
        from swingpoints.indicators import IndicatorSettings
        indicator_settings = IndicatorSettings(sma_period=3)
        app.current_run = (Path("example.csv"),bars,points,1,"close",lines,settings,indicator_settings)
        app.indicator_settings = IndicatorSettings(sma_period=99)  # Unapplied edits must not leak into export.
        app.output, app.figure = Path("output"), Figure()
        app.trend_tolerance = MagicMock()
        app.trend_tolerance.get.return_value = "99"
        with patch("swingpoints.gui.filedialog.askdirectory",return_value="chosen"), \
             patch("swingpoints.gui.messagebox.showinfo"), \
             patch("swingpoints.gui.export_results") as export:
            app.export()
        export.assert_called_once_with("chosen",Path("example.csv"),bars,points,1,"close",app.figure,lines,settings,indicator_settings)
        app.trend_tolerance.get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
