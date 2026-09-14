"""Run with: python -m unittest discover -s tests -v"""

import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

from swingpoints import Bar, DataError, SwingDetector, detect_swings, load_prices

ROOT = Path(__file__).resolve().parents[1]


def make_bars(values):
    """
    Create evenly spaced synthetic bars for detector tests.

    Args:
        values (Iterable[float]): Numeric Close prices; use values above 1 for
            positive Low prices. This helper does not validate market data.

    Result:
        list[Bar]: One-minute bars starting at 2023-05-19 09:16, with High equal
            to Close + 1, Low equal to Close - 1, and no Open value.

    Exception:
        TypeError or ValueError: If a value cannot be used in arithmetic or converted
            to float.
    """
    start = datetime(2023, 5, 19, 9, 16)
    return [Bar(start+timedelta(minutes=i), value+1, value-1, float(value)) for i, value in enumerate(values)]


class DetectionTests(unittest.TestCase):
    def test_known_extrema_and_delays(self):
        """
        Verify exact pivot types, prices and one-bar confirmation delays.

        Uses a hand-calculated five-bar sequence to compare the complete event list.

        Args:
            None.

        Result:
            None: The test completes when all assertions pass.

        Exception:
            AssertionError: If an expected result or exception does not match.
            Unexpected runtime, fixture I/O or dependency errors propagate to unittest.
        """
        points = detect_swings(make_bars([100, 102, 101, 105, 103]), window=1)
        self.assertEqual([(p.kind, p.pivot_index, p.confirmed_index, p.price) for p in points],
                         [("high", 1, 2, 102), ("low", 2, 3, 101), ("high", 3, 4, 105)])

    def test_window_two_only_confirms_after_two_later_bars(self):
        """
        Verify that a window of two requires two completed bars after the pivot.

        Checks that the four-bar prefix emits nothing and the fifth bar confirms it.

        Args:
            None.

        Result:
            None: The test completes when all assertions pass.

        Exception:
            AssertionError: If an expected result or exception does not match.
            Unexpected runtime, fixture I/O or dependency errors propagate to unittest.
        """
        bars = make_bars([100, 101, 105, 102, 101])
        self.assertEqual(detect_swings(bars[:4], 2), [])
        point, = detect_swings(bars, 2)
        self.assertEqual((point.pivot_index, point.confirmed_index), (2, 4))

    def test_every_prefix_equals_events_available_by_cutoff(self):
        # Directly checks the PDF's most important requirement on the actual data.
        """
        Verify that each historical prefix contains exactly the events known by then.

        Checks all 374 prefixes of the supplied CSV for both price bases against the
        full-run events filtered by confirmation index.

        Args:
            None.

        Result:
            None: The test completes when all assertions pass.

        Exception:
            AssertionError: If an expected result or exception does not match.
            Unexpected runtime, fixture I/O or dependency errors propagate to unittest.
        """
        bars = load_prices(ROOT / "data/data.csv")
        for basis in ("close", "high-low"):
            full = detect_swings(bars, 2, basis)
            for size in range(1, len(bars)+1):
                self.assertEqual(detect_swings(bars[:size], 2, basis),
                                 [p for p in full if p.confirmed_index < size])

    def test_changed_future_cannot_change_prior_events(self):
        """
        Verify that changing future prices leaves already confirmed events unchanged.

        Replaces bars after a fixed cutoff with extreme prices and compares earlier events.

        Args:
            None.

        Result:
            None: The test completes when all assertions pass.

        Exception:
            AssertionError: If an expected result or exception does not match.
            Unexpected runtime, fixture I/O or dependency errors propagate to unittest.
        """
        bars = make_bars([100, 104, 101, 106, 102, 103, 99, 107, 100])
        changed = bars[:5] + [Bar(b.timestamp, 501, 499, 500) for b in bars[5:]]
        expected = detect_swings(bars[:5], 1)
        self.assertEqual([p for p in detect_swings(changed, 1) if p.confirmed_index < 5], expected)

    def test_constant_monotone_and_plateau_have_no_strict_pivots(self):
        """
        Verify that the selected flat, increasing and plateau sequences emit no swings.

        Exercises strict comparisons using three small synthetic sequences.

        Args:
            None.

        Result:
            None: The test completes when all assertions pass.

        Exception:
            AssertionError: If an expected result or exception does not match.
            Unexpected runtime, fixture I/O or dependency errors propagate to unittest.
        """
        for values in ([100]*7, [100,101,102,103,104], [100,103,103,100]):
            self.assertEqual(detect_swings(make_bars(values), 1), [])

    def test_short_input(self):
        """
        Verify that insufficient history produces no confirmed swings.

        Supplies two bars to a detector requiring a five-bar window.

        Args:
            None.

        Result:
            None: The test completes when all assertions pass.

        Exception:
            AssertionError: If an expected result or exception does not match.
            Unexpected runtime, fixture I/O or dependency errors propagate to unittest.
        """
        self.assertEqual(detect_swings(make_bars([100, 102]), 2), [])

    def test_high_low_outside_bar_can_have_both_kinds(self):
        """
        Verify that an outside bar can be both a High peak and a Low trough.

        Compares high-low mode with close mode on a flat-Close synthetic sequence.

        Args:
            None.

        Result:
            None: The test completes when all assertions pass.

        Exception:
            AssertionError: If an expected result or exception does not match.
            Unexpected runtime, fixture I/O or dependency errors propagate to unittest.
        """
        bars = make_bars([100, 100, 100])
        bars[1] = Bar(bars[1].timestamp, 110, 90, 100)
        self.assertEqual(detect_swings(bars, 1, "close"), [])
        self.assertEqual([p.kind for p in detect_swings(bars, 1, "high-low")], ["high", "low"])

    def test_bad_settings_and_order(self):
        """
        Verify rejection of invalid detector settings and repeated timestamps.

        Checks nonpositive, noninteger and boolean windows, an unsupported basis,
        and feeding the same bar to the detector twice.

        Args:
            None.

        Result:
            None: The test completes when all assertions pass.

        Exception:
            AssertionError: If an expected result or exception does not match.
            Unexpected runtime, fixture I/O or dependency errors propagate to unittest.
        """
        for window in (0, -1, 1.5, True):
            with self.assertRaises(ValueError): SwingDetector(window)
        with self.assertRaises(ValueError): SwingDetector(basis="unknown")
        detector = SwingDetector()
        bar = make_bars([100])[0]
        detector.update(bar)
        with self.assertRaises(ValueError): detector.update(bar)


class LoadingTests(unittest.TestCase):
    def test_supplied_csv_json_equivalence(self):
        """
        Verify that the supplied CSV and JSON produce identical validated bars.

        Also checks the expected 374 observations and the first and last timestamps.

        Args:
            None.

        Result:
            None: The test completes when all assertions pass.

        Exception:
            AssertionError: If an expected result or exception does not match.
            Unexpected runtime, fixture I/O or dependency errors propagate to unittest.
        """
        csv_bars = load_prices(ROOT / "data/data.csv")
        self.assertEqual(csv_bars, load_prices(ROOT / "data/data.json"))
        self.assertEqual(len(csv_bars), 374)
        self.assertEqual(csv_bars[0].timestamp, datetime(2023,5,19,9,16))
        self.assertEqual(csv_bars[-1].timestamp, datetime(2023,5,19,15,29))

    def json_file(self, payload, check):
        """
        Write a temporary JSON fixture and pass its path to a checking function.

        Args:
            payload: JSON-serializable input records or wrapper object.
            check (callable): Function accepting the temporary Path and performing checks.

        Result:
            None: Removes the temporary directory after the callback completes or fails.

        Exception:
            OSError: If the fixture cannot be written.
            TypeError or ValueError: If the payload cannot be serialized.
            Exceptions raised by check(), including assertion failures, propagate.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            check(path)

    def test_iso_wrapper_case_and_sorting(self):
        """
        Verify wrapped JSON, mixed-case field names, UTC timestamps and time sorting.

        Writes two records in reverse order and checks which Close appears first.

        Args:
            None.

        Result:
            None: The test completes when all assertions pass.

        Exception:
            AssertionError: If an expected result or exception does not match.
            Unexpected runtime, fixture I/O or dependency errors propagate to unittest.
        """
        payload = {"data": [
            {"Timestamp":"2023-05-19T09:17:00Z", "High":102, "Low":99, "Close":101},
            {"Timestamp":"2023-05-19T09:16:00Z", "High":101, "Low":99, "Close":100}]}
        self.json_file(payload, lambda p: self.assertEqual(load_prices(p)[0].close, 100))

    def test_invalid_records_are_rejected(self):
        """
        Verify that malformed or inconsistent input records raise DataError.

        Covers empty data, duplicates, invalid prices/dates, missing fields and mixed
        naive/aware timestamps. Each case is written to a temporary JSON file.

        Args:
            None.

        Result:
            None: The test completes when all assertions pass.

        Exception:
            AssertionError: If an expected result or exception does not match.
            Unexpected runtime, fixture I/O or dependency errors propagate to unittest.
        """
        good = {"timestamp":"2023-05-19T09:16:00", "high":102,"low":99,"close":100}
        bad_records = [[], [good, good], [{**good, "close":"NaN"}], [{**good,"high":98}],
                       [{**good,"low":101}], [{**good,"open":103}], [{**good,"timestamp":"not a date"}],
                       [{**good,"close":True}], [{**good,"close":0}], [{"timestamp":good["timestamp"]}],
                       [good, {**good,"timestamp":"2023-05-19T09:17:00Z"}]]
        for payload in bad_records:
            with self.subTest(payload=payload):
                def check(path):
                    """
                    Assert that the current invalid JSON fixture is rejected.

                    Args:
                        path (Path): Temporary JSON file containing the invalid test payload.

                    Result:
                        None: Succeeds when load_prices raises DataError.

                    Exception:
                        AssertionError: If loading does not raise the expected DataError.
                        Unexpected exceptions from loading propagate.
                    """
                    with self.assertRaises(DataError): load_prices(path)
                self.json_file(payload, check)

    def test_csv_bom_semicolon_and_duplicate_headers(self):
        """
        Verify CSV BOM/semicolon support and rejection of duplicate column names.

        Loads a temporary valid CSV, then replaces it with duplicate normalized headers.

        Args:
            None.

        Result:
            None: The test completes when all assertions pass.

        Exception:
            AssertionError: If an expected result or exception does not match.
            Unexpected runtime, fixture I/O or dependency errors propagate to unittest.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"test.csv"
            path.write_text("\ufefftimestamp;high;low;close\n19/05/23 9:16;102;99;100\n", encoding="utf-8")
            self.assertEqual(load_prices(path)[0].close, 100)
            path.write_text("timestamp,high,low,close,Close\na,1,1,1,1\n")
            with self.assertRaises(DataError): load_prices(path)


class IntegrationTests(unittest.TestCase):
    def test_cli_both_formats_and_replay(self):
        """
        Verify command-line analysis, replay cutoff and exported CSV/JSON consistency.

        Runs the CLI on the first 100 observations of each supplied format, checks
        the PNG and summary, and compares exported swings. Results use temporary
        directories and the noninteractive Agg backend.

        Args:
            None.

        Result:
            None: The test completes when all assertions pass.

        Exception:
            AssertionError: If an expected result or exception does not match.
            Unexpected runtime, fixture I/O or dependency errors propagate to unittest.
        """
        with tempfile.TemporaryDirectory() as directory:
            for extension in ("csv", "json"):
                output = Path(directory)/extension
                result = subprocess.run([sys.executable, "app.py", f"data/data.{extension}",
                                         "--window","2","--until","100","--output",str(output)],
                                        cwd=ROOT, capture_output=True, text=True,
                                        env={**os.environ, "MPLBACKEND":"Agg"})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertGreater((output/"prices.png").stat().st_size, 10000)
                summary = json.loads((output/"run_summary.json").read_text())
                self.assertEqual(summary["observed_bars"], 100)
                points = json.loads((output/"swing_points.json").read_text())
                self.assertTrue(all(p["confirmed_bar"] <= 100 for p in points))
                with (output/"swing_points.csv").open() as stream:
                    self.assertEqual(len(list(csv.DictReader(stream))), len(points))
            self.assertEqual((Path(directory)/"csv/swing_points.json").read_text(),
                             (Path(directory)/"json/swing_points.json").read_text())

    def test_cli_rejects_bad_window_and_cutoff(self):
        """
        Verify that invalid CLI settings fail with a readable error and no traceback.

        Tests a zero window and a cutoff beyond the available observations in subprocesses.

        Args:
            None.

        Result:
            None: The test completes when all assertions pass.

        Exception:
            AssertionError: If an expected result or exception does not match.
            Unexpected runtime, fixture I/O or dependency errors propagate to unittest.
        """
        for args in (["--window","0"], ["--until","9999"]):
            result = subprocess.run([sys.executable,"app.py","data/data.csv",*args], cwd=ROOT,
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)

    def test_export_refuses_source_overwrite(self):
        """
        Verify that export rejects a destination that would overwrite its input.

        Checks that the input file content is retained after the expected ValueError.

        Args:
            None.

        Result:
            None: The test completes when all assertions pass.

        Exception:
            AssertionError: If an expected result or exception does not match.
            Unexpected runtime, fixture I/O or dependency errors propagate to unittest.
        """
        from swingpoints.output import export_results
        bars = make_bars([100])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"swing_points.json"
            path.write_text("keep me")
            with self.assertRaises(ValueError):
                export_results(directory,path,bars,[],2,"close",None)
            self.assertEqual(path.read_text(),"keep me")


if __name__ == "__main__":
    unittest.main()
