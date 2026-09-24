"""Hand-calculated fixtures, causal-prefix and real application integration tests."""
from dataclasses import replace
from datetime import datetime, timedelta
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from swingpoints.data import Bar, DataError, load_prices
from swingpoints.indicators import (IndicatorSettings, calculate_indicators, sma, ema,
                                   rsi, macd, atr, vwap, roc, cci)
ROOT = Path(__file__).resolve().parents[1]


def bars(values, volumes=None):
    """Make flat-within-bar prices so HLC3 equals the hand-specified Close."""
    start = datetime(2023,5,19,9)
    return [Bar(start+timedelta(minutes=i),float(x),float(x),float(x),
                volume=None if volumes is None else volumes[i]) for i,x in enumerate(values)]


class FormulaTests(unittest.TestCase):
    def test_sma(self):
        """Trailing three-value sums, not centered or expanding averages."""
        self.assertEqual(sma([2,4,9,5],3),[None,None,5,6])

    def test_ema(self):
        """Period-three alpha=1/2, seeded with arithmetic mean 5."""
        self.assertEqual(ema([2,4,9,5,11],3),[None,None,5,5,8])

    def test_rsi_wilder(self):
        """Three changes seed gains 5/3 and loss 1/3; next RSI=2/3*100."""
        r=rsi([10,12,11,14,13],3)
        self.assertEqual(r[:3],[None]*3)
        self.assertAlmostEqual(r[3],100*5/6)
        self.assertAlmostEqual(r[4],100*2/3)

    def test_rsi_flat_and_one_sided(self):
        """Explicit boundary conventions avoid zero-denominator errors."""
        for prices,expected in [([2]*5,50),([1,2,3,4,5],100),([5,4,3,2,1],0)]:
            self.assertEqual(rsi(prices,3)[3:],[expected,expected])

    def test_macd_hand_values(self):
        """Independent rational results verify both EMA seeds and signal alignment."""
        line,signal,hist=macd([10,12,11,15,14,18],2,3,2)
        self.assertEqual(line[:2],[None]*2)
        self.assertEqual(signal[:3],[None]*3)
        for got,expected in zip(line[2:],[0,2/3,7/18,95/108]): self.assertAlmostEqual(got,expected)
        for got,expected in zip(signal[3:],[1/3,10/27,115/162]): self.assertAlmostEqual(got,expected)
        self.assertAlmostEqual(hist[-1],55/324)

    def test_atr_gaps_and_wilder(self):
        """TR=2,5,3,4; mean seed=10/3; next Wilder ATR=32/9."""
        b=[replace(x,high=h,low=l) for x,h,l in zip(bars([9,12,11,9]),[10,14,13,12],[8,11,10,8])]
        result=atr(b,3)
        self.assertEqual(result[:2],[None]*2)
        self.assertAlmostEqual(result[2],10/3)
        self.assertAlmostEqual(result[3],32/9)

    def test_vwap_weights(self):
        """Actual-volume weighting differs from an unweighted price average."""
        self.assertEqual(vwap(bars([10,20,30],[100,300,0]))[0],[10,17.5,17.5])

    def test_vwap_zero_volume(self):
        """Zero weight before the first trade leaves VWAP undefined."""
        result,status=vwap(bars([10,20],[0,100]))
        self.assertEqual(result,[None,20])
        self.assertEqual(status,['zero_cumulative_volume','ok'])

    def test_vwap_hlc3(self):
        """High=16, Low=10, Close=10 gives typical price 12."""
        self.assertEqual(vwap([replace(bars([10],[4])[0],high=16)])[0],[12])

    def test_vwap_reset(self):
        """Session anchor resets on input calendar date; cumulative does not."""
        b=bars([10,20],[1,3]);b[1]=replace(b[1],timestamp=b[1].timestamp+timedelta(days=1))
        self.assertEqual(vwap(b)[0],[10,20])
        self.assertEqual(vwap(b,'cumulative')[0],[10,17.5])

    def test_vwap_missing(self):
        """Missing weight invalidates the rest of an anchor; next day can recover."""
        b=bars([10,20,30,40],[1,None,2,3]);b[3]=replace(b[3],timestamp=b[3].timestamp+timedelta(days=1))
        self.assertEqual(vwap(b)[0],[10,None,None,40])
        self.assertEqual(vwap(b,'cumulative')[0],[10,None,None,None])
        self.assertEqual(vwap(b[:1])[0],vwap(b)[0][:1])

    def test_roc(self):
        """Lag is measured in changes; zero reference yields None."""
        self.assertEqual(roc([10,15,20,12],2)[:3],[None,None,100])
        self.assertAlmostEqual(roc([10,15,20,12],2)[3],-20)
        self.assertEqual(roc([0,1],1),[None,None])

    def test_cci(self):
        """HLC3=1,4,2 -> mean=7/3, MAD=10/9, CCI=-20 (not std deviation)."""
        self.assertAlmostEqual(cci(bars([1,4,2]),3)[-1],-20)
        self.assertEqual(cci(bars([5]*4),3),[None,None,0,0])

    def test_period_one(self):
        """Minimal periods and flat-window conventions remain well-defined."""
        self.assertEqual(sma([1,2],1),[1,2]);self.assertEqual(ema([1,2],1),[1,2])
        self.assertEqual(rsi([1,2,1,1],1),[None,100,0,50])
        self.assertEqual(cci(bars([1,2]),1),[0,0])

    def test_short_and_empty(self):
        """All arrays keep their alignment without invented warm-up observations."""
        for size in [0,1,5]:
            r=calculate_indicators(bars([10]*size))
            self.assertTrue(all(len(v)==size for v in r.series.values()))
            self.assertTrue(all(x is None for v in r.series.values() for x in v))

    def test_settings(self):
        """Reject bad periods, anchors and inconsistent MACD settings."""
        for x in [True,0,-1,1.5,'14']:
            with self.assertRaises(ValueError): IndicatorSettings(rsi_period=x)
        with self.assertRaises(ValueError): IndicatorSettings(macd_fast=26)
        with self.assertRaises(ValueError): IndicatorSettings(vwap_reset='weekly')
        with self.assertRaises(ValueError): macd([1,2],3,2,1)

    def test_invalid_inputs(self):
        """Public pipeline rejects nonfinite prices/volume and repeated timestamps."""
        for x in [float('nan'),float('inf'),True,None]:
            with self.assertRaises(ValueError): ema([x],2)
        for v in [-1,float('nan'),True]:
            with self.assertRaises(ValueError): calculate_indicators(bars([10],[v]))
        with self.assertRaises(ValueError): calculate_indicators(bars([10])*2)
        with self.assertRaises(ValueError): calculate_indicators([replace(bars([10])[0],high=9)])


class DataTests(unittest.TestCase):
    def test_original_data_and_warmup(self):
        """Each default series starts at the documented one-based bar."""
        b=load_prices(ROOT/'data/data.csv');r=calculate_indicators(b)
        self.assertEqual(len(b),374);self.assertTrue(all(x.volume is None for x in b))
        first={'sma':20,'ema':20,'rsi':15,'macd':26,'macd_signal':34,'macd_histogram':34,'atr':14,'roc':13,'cci':20}
        for key,bar in first.items():
            self.assertEqual(next(i+1 for i,x in enumerate(r.series[key]) if x is not None),bar)
            self.assertEqual(r.metadata()['valid_counts'][key],375-bar)
        self.assertEqual(r.series['vwap'],[None]*374)
        self.assertEqual(r.vwap_status,['missing_volume']*374)

    def test_all_prefixes(self):
        """All 374 data prefixes preserve previously calculated indicator values."""
        b=load_prices(ROOT/'data/data.csv');full=calculate_indicators(b)
        for size in range(1,len(b)+1):
            prefix=calculate_indicators(b[:size])
            for key,values in prefix.series.items():self.assertEqual(values,full.series[key][:size],(size,key))

    def test_optional_volume_loading(self):
        """Case-insensitive optional volume, zeros and blanks survive sorting."""
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input.csv'
            p.write_text('timestamp,high,low,close,Volume\n2023-01-01T09:01,12,10,11,0\n2023-01-01T09:00,11,9,10,100\n2023-01-01T09:02,13,11,12,\n')
            self.assertEqual([x.volume for x in load_prices(p)],[100,0,None])
            p=Path(d)/'input.json'
            p.write_text(json.dumps([dict(timestamp='2023-01-01',high=11,low=9,close=10,Volume=None)]))
            self.assertIsNone(load_prices(p)[0].volume)

    def test_bad_volume_loading(self):
        """Invalid present volume fails rather than being silently dropped."""
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input.json'
            for v in [-1,'NaN','Infinity',True,'unknown']:
                p.write_text(json.dumps([dict(timestamp='2023-01-01',high=11,low=9,close=10,volume=v)]))
                with self.assertRaises(DataError):load_prices(p)


class IntegrationTests(unittest.TestCase):
    def test_cli_overrides_export_dashboard(self):
        """Custom CLI periods reach JSON/CSV and both exported figures are valid PNGs."""
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            process=subprocess.run([sys.executable,'app.py','data/data.csv','--until','40','--sma-period','3',
                '--ema-period','4','--rsi-period','3','--macd-fast','2','--macd-slow','4','--macd-signal','2',
                '--atr-period','3','--roc-period','2','--cci-period','3','--vwap-reset','cumulative','--output',d],
                cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(process.returncode,0,process.stderr)
            rows=json.loads((p/'indicators.json').read_text())
            self.assertEqual(len(rows),40);self.assertTrue(all(r['vwap'] is None for r in rows))
            self.assertIsNotNone(rows[2]['sma']);self.assertIsNone(rows[1]['sma'])
            summary=json.loads((p/'run_summary.json').read_text())
            self.assertEqual(summary['indicators']['settings']['ema_period'],4)
            self.assertEqual(summary['indicators']['settings']['vwap_reset'],'cumulative')
            with (p/'indicators.csv').open() as f:records=list(csv.DictReader(f))
            self.assertEqual(records[0]['sma'],'');self.assertEqual(len(records),40)
            from PIL import Image
            for name in ['prices.png','indicators.png']:
                with Image.open(p/name) as im:im.verify()

    def test_volume_csv_through_export(self):
        """A temporary volume-bearing fixture produces real VWAP in exports and chart."""
        from matplotlib.figure import Figure
        from swingpoints.output import export_results
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'input.csv'
            source.write_text('timestamp,high,low,close,volume\n2023-01-01T09:00,10,10,10,1\n2023-01-01T09:01,20,20,20,3\n')
            observed=load_prices(source)
            destination=Path(d)/'results'
            export_results(destination,source,observed,[],2,'close',Figure())
            records=json.loads((destination/'indicators.json').read_text())
            self.assertEqual([r['vwap'] for r in records],[10,17.5])
            self.assertEqual([r['vwap_status'] for r in records],['ok','ok'])
            with Image.open(destination/'indicators.png') as image:image.verify()

    def test_cli_rejects_bad_macd(self):
        """Inconsistent MACD periods produce a readable CLI error."""
        p=subprocess.run([sys.executable,'app.py','data/data.csv','--macd-fast','30'],cwd=ROOT,capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0);self.assertIn('smaller',p.stderr);self.assertNotIn('Traceback',p.stderr)

    def test_export_source_guard(self):
        """The new indicator filenames cannot overwrite an input file."""
        from swingpoints.output import export_results
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'indicators.json';p.write_text('unchanged')
            with self.assertRaises(ValueError):export_results(d,p,bars([10]),[],2,'close',None)
            self.assertEqual(p.read_text(),'unchanged')


if __name__=='__main__':unittest.main()
