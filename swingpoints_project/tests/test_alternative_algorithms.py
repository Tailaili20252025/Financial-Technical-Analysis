"""Hand calculations, causal availability, boundaries and pipeline regression tests."""
from datetime import datetime,timedelta
from pathlib import Path
from dataclasses import replace
import csv
import json
import tempfile
import unittest
from swingpoints.data import Bar,DataError,load_prices
from swingpoints.alternative_algorithms import (PercentageSettings,ATRSettings,ProminenceSettings,
                                 SwingPoint,detect_swings,atr_values,local_prominence)
from swingpoints.trendlines import TrendSettings,detect_trendlines,select_trendlines


def bars(values,spread=1):
    """Construct synthetic minute bars for deterministic algorithm tests."""
    return [Bar(datetime(2020,1,1)+timedelta(minutes=i),x+spread,max(.01,x-spread),x,x) for i,x in enumerate(values)]


def point(bb,kind,pivot,confirmed):
    """Construct a known historical pivot with separate availability time."""
    return SwingPoint(kind,bb[pivot].close,pivot,bb[pivot].timestamp,confirmed,bb[confirmed].timestamp)


class ReversalTests(unittest.TestCase):
    def test_percentage_hand_example_and_alternation(self):
        bb=bars([100,110,108,106.7,100,103])
        pp=detect_swings(bb,PercentageSettings(3))
        self.assertEqual([(p.kind,p.pivot_index,p.confirmed_index) for p in pp],
                         [('low',0,1),('high',1,3),('low',4,5)])
        self.assertAlmostEqual(pp[1].threshold_price,3.3)

    def test_equal_extreme_keeps_first(self):
        pp=detect_swings(bars([100,110,110,104]),PercentageSettings(5))
        self.assertEqual(pp[-1].pivot_index,1)
        self.assertEqual(pp[-1].confirmed_index,3)

    def test_terminal_extreme_not_forced(self):
        pp=detect_swings(bars([100,105,110,120]),PercentageSettings(5))
        self.assertEqual(len(pp),1);self.assertEqual(pp[0].kind,'low')

    def test_atr_hand_values_and_gaps(self):
        bb=bars([100,103,101],1)
        self.assertEqual(atr_values(bb,2),[None,3,3])
        self.assertEqual(atr_values(bb,1),[2,4,3])

    def test_atr_warmup(self):
        self.assertEqual(detect_swings(bars([100,110,90]),ATRSettings(5,2)),[])

    def test_atr_threshold_frozen_despite_later_volatility(self):
        bb=bars([100,100,110,109,108])
        # Seed=2; ATR at extreme index2=(2+11)/2=6.5; multiplier .25 => 1.625.
        bb[3]=replace(bb[3],high=200,low=50)
        pp=detect_swings(bb,ATRSettings(2,.25))
        high=next(p for p in pp if p.kind=='high')
        self.assertEqual((high.pivot_index,high.confirmed_index),(2,4))
        self.assertAlmostEqual(high.atr_at_pivot,6.5)
        self.assertAlmostEqual(high.threshold_price,1.625)

    def test_new_atr_extreme_updates_threshold(self):
        bb=bars([100,100,110,112,100])
        pp=detect_swings(bb,ATRSettings(2,1))
        high=next(p for p in pp if p.kind=='high')
        self.assertEqual(high.pivot_index,3)
        self.assertAlmostEqual(high.threshold_price,4.75)

    def test_constant_zero_range_produces_no_swings(self):
        for st in [PercentageSettings(),ATRSettings(2,1),ProminenceSettings()]:
            self.assertEqual(detect_swings(bars([100]*30,0),st),[])


class ProminenceTests(unittest.TestCase):
    def test_higher_of_two_bases(self):
        self.assertEqual(local_prominence([105,110,107],1),3)
        bb=bars([105,110,107])
        pp=detect_swings(bb,ProminenceSettings(1,2,1))
        self.assertEqual(len(pp),1);self.assertEqual(pp[0].prominence_price,3)
        self.assertEqual(pp[0].confirmed_index,2)
        self.assertEqual(detect_swings(bb,ProminenceSettings(1,4,1)),[])

    def test_higher_peak_stops_base_search(self):
        self.assertEqual(local_prominence([1,7,5,6,4],3),1)

    def test_trough_and_exact_threshold(self):
        pp=detect_swings(bars([103,100,102]),ProminenceSettings(1,2,1))
        self.assertEqual([(p.kind,p.price) for p in pp],[('low',100)])

    def test_plateaus_excluded(self):
        pp=detect_swings(bars([100,110,110,100]),ProminenceSettings(1,1,1))
        self.assertEqual(pp,[])

    def test_spacing_first_accepted_not_largest_future(self):
        pp=detect_swings(bars([100,110,100,120,100]),ProminenceSettings(1,1,3))
        self.assertEqual([p.pivot_index for p in pp if p.kind=='high'],[1])

    def test_window_edge_not_emitted(self):
        pp=detect_swings(bars([100,105,110,100]),ProminenceSettings(2,1,1))
        self.assertEqual(pp,[])


class TrendTests(unittest.TestCase):
    def test_hand_line_creation_break_and_touches(self):
        bb=bars([105,100,106,102,108,104,110,99])
        pp=[point(bb,'low',1,2),point(bb,'low',3,4),point(bb,'low',5,6)]
        ls=detect_trendlines(bb,pp,TrendSettings(0))
        line=next(l for l in ls if l.line_id=='up-2-4')
        self.assertEqual(line.slope,1);self.assertEqual(line.broken_index,7)
        self.assertEqual(len(line.touches),3)
        self.assertEqual(line.as_record(bb)['created_bar'],5)
        self.assertEqual(line.value_at(bb[5].timestamp),104)

    def test_down_line(self):
        bb=bars([105,110,104,108,102,106,100])
        pp=[point(bb,'high',1,2),point(bb,'high',3,4)]
        line=detect_trendlines(bb,pp,TrendSettings(0))[0]
        self.assertEqual(line.kind,'down');self.assertEqual(line.slope,-1)

    def test_late_confirmation_rejects_precreation_break(self):
        bb=bars([105,100,106,102,99,104])
        pp=[point(bb,'low',1,2),point(bb,'low',3,5)]
        self.assertEqual(detect_trendlines(bb,pp,TrendSettings(0)),[])

    def test_wrong_direction_and_flat_rejected(self):
        for v in [100,99]:
            bb=bars([105,100,106,v,110]);pp=[point(bb,'low',1,2),point(bb,'low',3,4)]
            self.assertEqual(detect_trendlines(bb,pp,TrendSettings()),[])

    def test_tolerance_absolute_and_exact_boundary(self):
        bb=bars([105,100,106,102,108,104,104.5])
        pp=[point(bb,'low',1,2),point(bb,'low',3,4)]
        line=detect_trendlines(bb,pp,TrendSettings(1.5))[0]
        self.assertEqual(line.tolerance,1.5);self.assertIsNone(line.broken_index)

    def test_elapsed_time_including_gaps(self):
        bb=bars([105,100,106,102,108]);bb=[replace(b,timestamp=datetime(2020,1,1)+timedelta(days=i)) for i,b in enumerate(bb)]
        pp=[point(bb,'low',1,2),point(bb,'low',3,4)]
        self.assertAlmostEqual(detect_trendlines(bb,pp,TrendSettings(0))[0].slope,1/1440)


class ValidationTests(unittest.TestCase):
    def test_bad_settings(self):
        for ctor in [lambda:PercentageSettings(0),lambda:PercentageSettings(100),lambda:PercentageSettings(float('nan')),
                     lambda:ATRSettings(True,1),lambda:ATRSettings(2,-1),lambda:ProminenceSettings(1.5,1,1),
                     lambda:ProminenceSettings(2,1,0),lambda:TrendSettings(float('inf'))]:
            with self.assertRaises(ValueError):ctor()

    def test_timestamp_rejection(self):
        bb=bars([100,101]);bb[1]=replace(bb[1],timestamp=bb[0].timestamp)
        with self.assertRaises(ValueError):detect_swings(bb,PercentageSettings())

    def test_csv_rejects_duplicate_and_bad_ohlc(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'x.csv'
            for content in ['timestamp,High,Low,Close\n2020-01-01,101,99,102\n',
                            'timestamp,High,Low,Close\n2020-01-01,101,99,100\n2020-01-01,101,99,100\n']:
                path.write_text(content)
                with self.assertRaises(DataError):load_prices(path)

    def test_swing_prefix_invariance_all_tsla_prefixes(self):
        bb=load_prices(Path(__file__).resolve().parents[1]/'data/TSLA_ready.csv')
        for st in [PercentageSettings(),ATRSettings(),ProminenceSettings()]:
            full=detect_swings(bb,st)
            for n in range(1,len(bb)+1):
                self.assertEqual(detect_swings(bb[:n],st),[p for p in full if p.confirmed_index<n])
            for p in full:self.assertLess(p.pivot_index,p.confirmed_index)

    def test_trend_prefix_geometry_and_first_break_are_stable(self):
        bb=load_prices(Path(__file__).resolve().parents[1]/'data/TSLA_ready.csv')
        for st in [PercentageSettings(),ATRSettings(),ProminenceSettings()]:
            pp=detect_swings(bb,st);full=detect_trendlines(bb,pp,TrendSettings())
            for n in [30,100,200,374,500,len(bb)]:
                prefix=detect_trendlines(bb[:n],detect_swings(bb[:n],st),TrendSettings())
                expected=[l for l in full if l.second.confirmed_index<n]
                self.assertEqual({l.line_id for l in prefix},{l.line_id for l in expected})
                for line in prefix:
                    ref=next(l for l in expected if l.line_id==line.line_id)
                    self.assertEqual((line.first,line.second,line.slope,line.tolerance),(ref.first,ref.second,ref.slope,ref.tolerance))
                    self.assertEqual(line.broken_index,ref.broken_index if ref.broken_index is not None and ref.broken_index<n else None)
                    self.assertEqual(line.touches,tuple(p for p in ref.touches if p.confirmed_index<n))


if __name__=='__main__':unittest.main()
