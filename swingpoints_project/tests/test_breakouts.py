"""Hand-calculated Step 4 rules, causal replay and application integration."""
import csv
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from matplotlib.figure import Figure
from swingpoints.data import Bar, load_prices
from swingpoints.detector import SwingPoint
from swingpoints.trendlines import TrendLine, TrendSettings
from swingpoints.breakouts import BreakoutSettings, detect_breakouts, breakout_summary, BREAKOUT_FIELDS
from swingpoints.breakout_plotting import draw_breakouts
from swingpoints.methods import METHODS, create_method
from swingpoints.pipeline import analyze, run_analysis
from swingpoints.output import export_results

ROOT = Path(__file__).resolve().parents[1]


def fixture(following, mirror=False, basis="close"):
    """Resistance at bars 5/6/7 = 100/99.9/99.8; tolerance = 0.5."""
    closes = [100.4, 100.2, 100.2, 100.0] + following
    if mirror:
        closes = [200-x for x in closes]
    bars = [Bar(datetime(2020, 1, 1)+timedelta(minutes=i), c+.1, c-.1, c) for i, c in enumerate(closes)]
    kind = "low" if mirror else "high"
    first = SwingPoint(kind, closes[0], 0, bars[0].timestamp, 1, bars[1].timestamp, basis)
    second = SwingPoint(kind, closes[2], 2, bars[2].timestamp, 3, bars[3].timestamp, basis)
    line = TrendLine("up" if mirror else "down", first, second, .1 if mirror else -.1,
                     .5, (first, second), None, len(bars)-1)
    return bars, line


class BreakoutTests(unittest.TestCase):
    def test_report_example_both_directions(self):
        for mirror in (False, True):
            bars, line = fixture([100.8, 100.9, 99.1], mirror)
            event, = detect_breakouts(bars, [line])
            self.assertEqual((event.candidate_index, event.confirmation_index, event.failure_index), (4, 5, 6))
            self.assertEqual(event.outcome, "false_breakdown" if mirror else "false_breakout")
            self.assertEqual(event.confirmation_status, "confirmed")
            record = event.as_record(bars)
            self.assertEqual(record['candidate_bar'], 5)
            self.assertEqual(record['confirmation_bar'], 6)
            self.assertEqual(record['failure_bar'], 7)
            self.assertEqual(record['deadline_bar'], 10)
            self.assertIsNone(record['deadline_at'])
            self.assertAlmostEqual(event.line_value, 100)

    def test_equality_and_numeric_allowance(self):
        bars, line = fixture([100.5, 100.4, 100.3])
        self.assertEqual(detect_breakouts(bars, [line]), [])
        bars[-1] = replace(bars[-1], close=100.3+1e-12)
        self.assertEqual(detect_breakouts(bars, [line]), [])
        bars[-1] = replace(bars[-1], close=100.3+1e-6)
        self.assertEqual(detect_breakouts(bars, [line])[0].candidate_index, 6)

    def test_wick_only_and_high_low_skip(self):
        bars, line = fixture([100.1, 100.0])
        bars[4] = replace(bars[4], high=110)
        self.assertEqual(detect_breakouts(bars, [line]), [])
        bars, line = fixture([100.8, 100.9], basis="high-low")
        self.assertEqual(detect_breakouts(bars, [line]), [])
        self.assertEqual(breakout_summary([], basis='high-low')['status'], 'not_supported_high_low')

    def test_neutral_resets_then_late_confirmation(self):
        bars, line = fixture([100.8, 99.9, 100.6, 100.5])
        event, = detect_breakouts(bars, [line])
        self.assertEqual(event.confirmation_index, 7)
        self.assertEqual(event.outcome, 'pending')
        self.assertIsNone(event.failure_index)

    def test_failure_before_confirmation_and_no_second_event(self):
        bars, line = fixture([100.8, 99.0, 101, 101, 101, 101, 101])
        event, = detect_breakouts(bars, [line])
        self.assertEqual(event.failure_index, 5)
        self.assertIsNone(event.confirmation_index)
        self.assertEqual(event.confirmation_status, 'not_confirmed')

    def test_opposite_threshold_equality_is_not_failure(self):
        bars, line = fixture([100.8, 99.4, 99.3, 100.5])
        event, = detect_breakouts(bars, [line])
        self.assertIsNone(event.failure_index)
        self.assertIsNone(event.confirmation_index)

    def test_deadline_inclusive_and_next_bar_excluded(self):
        bars, line = fixture([101]*5+[98])
        event, = detect_breakouts(bars, [line])
        self.assertEqual(event.failure_index, 9)
        self.assertEqual(event.outcome_index, 9)
        bars, line = fixture([101]*6+[98])
        event, = detect_breakouts(bars, [line])
        self.assertIsNone(event.failure_index)
        self.assertEqual(event.outcome, 'no_failure_within_window')
        self.assertEqual(event.outcome_index, 9)

    def test_incomplete_window_is_pending_even_if_confirmed(self):
        bars, line = fixture([101]*5)
        event, = detect_breakouts(bars, [line])
        self.assertEqual(event.confirmation_status, 'confirmed')
        self.assertEqual(event.outcome, 'pending')
        self.assertIsNone(event.outcome_index)
        self.assertIsNone(event.as_record(bars)['deadline_at'])

    def test_configurable_rules(self):
        bars, line = fixture([101]*4)
        event, = detect_breakouts(bars, [line], BreakoutSettings(3, 3))
        self.assertEqual(event.confirmation_index, 6)
        self.assertEqual(event.outcome_index, 7)
        self.assertEqual(detect_breakouts(bars[:5], [line], BreakoutSettings(1, 1))[0].confirmation_index, 4)
        for args in [(0,5), (True,5), (2,0), (2,1.5), (7,5)]:
            with self.assertRaises(ValueError): BreakoutSettings(*args)

    def test_confirmation_on_deadline_and_expiry_without_confirmation(self):
        bars, line = fixture([100.8, 99.9, 99.8, 99.7, 100.4, 100.3])
        event, = detect_breakouts(bars, [line])
        self.assertEqual(event.confirmation_index, 9)
        self.assertEqual(event.outcome, 'no_failure_within_window')
        bars, line = fixture([100.8, 99.9, 99.8, 99.7, 99.6, 99.5])
        event, = detect_breakouts(bars, [line])
        self.assertEqual(event.confirmation_status, 'not_confirmed')
        self.assertEqual(event.outcome, 'no_failure_within_window')

    def test_time_geometry_and_observed_bar_deadline_across_gap(self):
        bars, line = fixture([100.8, 100.9, 99.1])
        # Three minutes pass before candidate; value_at must use time, not row number.
        bars[4:] = [replace(b, timestamp=b.timestamp+timedelta(minutes=3)) for b in bars[4:]]
        event, = detect_breakouts(bars, [line])
        self.assertAlmostEqual(event.line_value, 99.7)
        self.assertEqual(event.deadline_index, 9)  # Still five observed bars, not minutes.
        self.assertIsNone(event.failure_index)  # Final Close is now within the shifted band.

    def test_creation_and_unobserved_line(self):
        bars, line = fixture([101, 101])
        self.assertEqual(detect_breakouts(bars[:4], [line]), [])
        event, = detect_breakouts(bars, [line])
        self.assertGreater(event.candidate_index, line.second.confirmed_index)
        with self.assertRaises(ValueError): detect_breakouts(bars, [line,line])
        with self.assertRaises(ValueError): detect_breakouts(bars[::-1], [line])

    def test_full_window_rate_excludes_early_known_failure(self):
        bars, line = fixture([100.8, 99.0])
        events = detect_breakouts(bars, [line])
        stats = breakout_summary(events)
        self.assertEqual(stats['false_breakouts'], 1)
        self.assertEqual(stats['fully_observed_candidates'], 0)
        self.assertIsNone(stats['failure_rate_full_windows'])
        bars, line = fixture([100.8, 99.0, 101, 101, 101, 101])
        stats = breakout_summary(detect_breakouts(bars, [line]))
        self.assertEqual(stats['failure_rate_full_windows'], 1)

    def test_batch_results_replayed_at_every_prefix(self):
        """Appending observations reveals statuses only at their recorded times."""
        bars = load_prices(ROOT/'data/TSLA_ready.csv')[:160]
        for name in METHODS:
            method = create_method(name)
            complete = analyze(bars, method)
            growing = []
            for cutoff, bar in enumerate(bars, 1):
                growing.append(bar)
                replay = analyze(growing, method)
                expected = []
                for e in complete.events:
                    if e.candidate_index >= cutoff:
                        continue
                    failed = e.failure_index if e.failure_index is not None and e.failure_index < cutoff else None
                    confirmed = e.confirmation_index if e.confirmation_index is not None and e.confirmation_index < cutoff else None
                    if failed is not None:
                        outcome, known = 'false_'+e.direction, failed
                    elif e.deadline_index < cutoff:
                        outcome, known = 'no_failure_within_window', e.deadline_index
                    else:
                        outcome, known = 'pending', None
                    expected.append(replace(e, confirmation_index=confirmed, failure_index=failed,
                                            outcome=outcome, outcome_index=known, observed_index=cutoff-1))
                self.assertEqual(replay.events, expected, (name, cutoff))

    def test_all_lines_not_just_display_subset_and_original_breaks(self):
        bars = load_prices(ROOT/'data/TSLA_ready.csv')
        for name in METHODS:
            a = analyze(bars, create_method(name), TrendSettings(max_per_direction=1))
            b = analyze(bars, create_method(name), TrendSettings(min_touches=99))
            self.assertEqual(a.events, b.events)
            self.assertGreater(len(a.events), len(a.selected))
            self.assertEqual({e.line_id:e.candidate_index for e in a.events},
                             {l.line_id:l.broken_index for l in a.lines if l.broken_index is not None})

    def test_exports_cutoff_and_input_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            result = run_analysis(ROOT/'data/TSLA_ready.csv', folder, until=160, breakout_settings=BreakoutSettings(3,4))
            records = json.loads((Path(folder)/'breakouts.json').read_text())
            self.assertEqual(records, [e.as_record(result.bars) for e in result.events])
            with (Path(folder)/'breakouts.csv').open() as f:
                reader = csv.DictReader(f)
                self.assertEqual(reader.fieldnames, BREAKOUT_FIELDS)
                self.assertEqual(len(list(reader)), len(records))
            self.assertEqual(len(list(Path(folder).iterdir())), 12)
            summary = json.loads((Path(folder)/'run_summary.json').read_text())
            self.assertEqual(summary['breakouts']['settings'], {'confirmation_bars':3, 'observation_bars':4})
            source = Path(folder)/'breakouts.csv'
            with self.assertRaises(ValueError):
                export_results(folder, source, result.bars, result.points, 2, 'close', Figure())

    def test_plot_markers_use_availability_times(self):
        bars, line = fixture([100.8,100.9,99.1])
        events = detect_breakouts(bars, [line])
        fig = Figure()
        draw_breakouts(fig, bars, events, [line])
        layers = {c.get_label():c for c in fig.axes[0].collections}
        for label, index in [('Candidate',4),('Time confirmed',5),('False break known',6)]:
            offsets = layers[label].get_offsets()
            self.assertEqual(len(offsets), 1)
            self.assertEqual(offsets[0,1], bars[index].close)
        self.assertLess(layers['Candidate'].get_offsets()[0,0], layers['False break known'].get_offsets()[0,0])

    def test_cli_parameters_and_high_low(self):
        with tempfile.TemporaryDirectory() as folder:
            cmd = [sys.executable,'app.py','data/data.csv','--output',folder]
            run = subprocess.run(cmd+['--break-confirmation-bars','3','--break-observation-bars','4','--basis','high-low'],
                                 cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(json.loads((Path(folder)/'breakouts.json').read_text()), [])
            self.assertEqual(json.loads((Path(folder)/'run_summary.json').read_text())['breakouts']['status'], 'not_supported_high_low')
            for args in [('--break-confirmation-bars','0'),('--break-observation-bars','-1'),('--break-confirmation-bars','7')]:
                run = subprocess.run(cmd+list(args), cwd=ROOT, text=True, capture_output=True)
                self.assertEqual(run.returncode,2,run.stderr)


if __name__ == '__main__': unittest.main()
