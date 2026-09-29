"""Integration and regression against results generated from the untouched ZIPs."""
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from matplotlib.figure import Figure
from swingpoints.data import load_prices
from swingpoints.detector import SwingPoint
from swingpoints.methods import METHODS, SwingMethod, TASettings, create_method
from swingpoints.pipeline import analyze, run_analysis
from swingpoints.indicators import IndicatorSettings, calculate_indicators
from swingpoints.plotting import draw_prices
from run_methods import settings_product

ROOT = Path(__file__).resolve().parents[1]


def digest(rows):
    """Hash canonical records for comparison with independent legacy runs."""
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class MethodTests(unittest.TestCase):
    def test_original_zip_golden_results(self):
        """Match 14 legacy runs, including geometry, confirmation, touches and breaks."""
        for case in json.loads((ROOT/'tests/fixtures/legacy_results.json').read_text()):
            with self.subTest(case=case):
                bars = load_prices(ROOT/'data'/case['data'])
                result = analyze(bars, create_method(case['method'], **case['settings']))
                ids = {l.line_id for l in result.selected}
                self.assertEqual(digest([p.as_record() for p in result.points]), case['swings_sha256'])
                self.assertEqual(digest([l.as_record(bars, l.line_id in ids) for l in result.lines]), case['trends_sha256'])
                self.assertTrue(all(isinstance(p, SwingPoint) for p in result.points))

    def test_reuse_and_empty_detection(self):
        bars = load_prices(ROOT/'data/TSLA_ready.csv')
        for name in METHODS:
            method = create_method(name)
            before = method.detect(bars[:100])
            method.detect(bars)
            self.assertEqual(before, method.detect(bars[:100]))
            self.assertEqual(method.detect([]), [])

    def test_invalid_settings(self):
        for name, values in [('ta', {'window':0}), ('percentage', {'reversal_percent':100}),
                             ('atr', {'atr_period':True}), ('prominence', {'radius':0})]:
            with self.assertRaises(ValueError): create_method(name, **values)
        with self.assertRaises(ValueError): create_method('unknown')
        with self.assertRaises(TypeError): create_method('percentage', window=2)
        with self.assertRaises(TypeError): METHODS['ta'](METHODS['atr']().settings)
        with self.assertRaises(ValueError): analyze([])
        with self.assertRaises(TypeError): analyze([1], object())

    def test_new_strategy_without_pipeline_branch(self):
        class NoSwingMethod(SwingMethod):
            key, label, settings_type = 'none', 'No swings', TASettings
            def detect(self, bars): return []
        result = analyze(load_prices(ROOT/'data/data.csv')[:30], NoSwingMethod())
        self.assertEqual(result.points, [])
        self.assertEqual(result.lines, [])

    def test_indicators_independent_of_method(self):
        bars = load_prices(ROOT/'data/TSLA_ready.csv')[:100]
        expected = calculate_indicators(bars)
        for name in METHODS:
            self.assertEqual(calculate_indicators(analyze(bars, create_method(name)).bars), expected)

    def test_variable_delay_plot(self):
        bars = load_prices(ROOT/'data/TSLA_ready.csv')[:100]
        for name in METHODS:
            method = create_method(name)
            result = analyze(bars, method)
            fig = Figure()
            draw_prices(fig, bars, result.points, method.context_radius, method.basis,
                        lines=result.lines, method=method)
            self.assertEqual(len(fig.axes[0].patches), 1 if method.context_radius else 0)
            if name != 'ta':
                self.assertIn(method.label, fig.axes[0].get_title(loc='left'))
                self.assertNotIn('window:', fig.axes[0].get_title(loc='left'))
            fig.clear()

    def test_cli_all_methods_empty_output(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in METHODS:
                dest = Path(folder)/name
                run = subprocess.run([sys.executable, 'app.py', 'data/TSLA_ready.csv', '--method', name,
                    '--until', '1', '--output', str(dest)], cwd=ROOT, text=True, capture_output=True)
                self.assertEqual(run.returncode, 0, run.stderr)
                summary = json.loads((dest/'run_summary.json').read_text())
                self.assertEqual(summary['swing_method']['method'], name)
                self.assertEqual(summary['observed_bars'], 1)
                self.assertEqual(len(list(dest.iterdir())), 9)
                self.assertEqual(json.loads((dest/'swing_points.json').read_text()), [])
                with (dest/'swing_points.csv').open() as stream:
                    self.assertEqual('threshold_price' in csv.DictReader(stream).fieldnames, name != 'ta')

    def test_cli_inapplicable_flags_and_separate_atr_periods(self):
        for flags in [['--method', 'percentage', '--window', '2'],
                      ['--method', 'atr', '--basis', 'high-low'],
                      ['--method', 'ta', '--atr-multiplier', '3']]:
            run = subprocess.run([sys.executable, 'app.py', 'data/data.csv', *flags], cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(run.returncode, 2)
            self.assertIn('do not apply', run.stderr)
        with tempfile.TemporaryDirectory() as folder:
            run = subprocess.run([sys.executable, 'app.py', 'data/data.csv', '--method', 'atr',
                '--swing-atr-period', '7', '--atr-period', '20', '--until', '30', '--output', folder],
                cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            summary = json.loads((Path(folder)/'run_summary.json').read_text())
            self.assertEqual(summary['swing_method']['settings']['atr_period'], 7)
            self.assertEqual(summary['indicators']['settings']['atr_period'], 20)

    def test_pipeline_cutoff(self):
        with tempfile.TemporaryDirectory() as folder:
            source = ROOT/'data/TSLA_ready.csv'
            result = run_analysis(source, folder, create_method('percentage'), until=100)
            records = json.loads((Path(folder)/'swing_points.json').read_text())
            self.assertEqual(records, [p.as_record() for p in result.points])
            self.assertTrue(records)
            for cutoff in [0, True, 1.5, 100000]:
                with self.assertRaises(ValueError): run_analysis(source, folder, until=cutoff)

    def test_grid_validation(self):
        self.assertEqual([x.window for x in settings_product(TASettings, {'window':[1,5]})], [1,5])
        for grid in [{'bad':[1]}, {'window':[]}, {'window':[0]}, {'window':'2'}]:
            with self.assertRaises(ValueError): settings_product(TASettings, grid)
        with self.assertRaises(ValueError): settings_product(TASettings, {'window':[1,2]}, max_runs=1)

    def test_gui_all_methods_and_export_snapshot(self):
        """Exercise real callbacks with mock widgets; not a desktop display test."""
        from swingpoints.gui import SwingApp
        bars = load_prices(ROOT/'data/TSLA_ready.csv')
        for name in METHODS:
            app = SwingApp.__new__(SwingApp)
            app.bars, app.source = bars, ROOT/'data/TSLA_ready.csv'
            app.method_settings = {k: cls().settings for k, cls in METHODS.items()}
            for key, value in {'method_name':name,'window':'2','basis':'close','cutoff':'100',
                               'trend_tolerance':'0.5','trend_lookback':'20','min_touches':'2','max_lines':'3'}.items():
                var = MagicMock(); var.get.return_value = value; setattr(app,key,var)
            app.indicator_settings = IndicatorSettings()
            app.figure, app.canvas = Figure(), MagicMock()
            app.table, app.trend_table, app.indicator_table = MagicMock(), MagicMock(), MagicMock()
            app.table.__getitem__.return_value = ('kind','pivot_bar')
            app.trend_table.__getitem__.return_value = ('line_id',)
            app.indicator_table.__getitem__.return_value = ('bar','sma')
            app.export_button, app.status = MagicMock(), MagicMock()
            app.output = Path('output')
            app.refresh()
            snapshot = app.current_run
            self.assertEqual(snapshot[-1].key,name)
            self.assertEqual(snapshot[2],create_method(name).detect(bars[:100]))
            self.assertEqual(app.indicator_table.insert.call_count,100)
            app.method_name.get.return_value = 'unapplied-edit'
            with patch('swingpoints.gui.filedialog.askdirectory',return_value='chosen'), \
                 patch('swingpoints.gui.messagebox.showinfo'), patch('swingpoints.gui.export_results') as export:
                app.export()
                self.assertIs(export.call_args.kwargs['method'],snapshot[-1])
            app.figure.clear()


if __name__ == '__main__': unittest.main()
