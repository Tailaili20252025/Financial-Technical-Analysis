"""Regression fixtures for the previously delivered Steps 5-6 trading engine."""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from swingpoints.breakouts import BreakoutEvent
from swingpoints.data import Bar
from swingpoints.trading import TradeSettings, simulate_trades


def bars_from(rows):
    """Make chronological OHLC bars; numbers mean a +/-1 range and equal Open/Close."""
    bars = []
    for i, row in enumerate(rows):
        o, h, l, c = (row, row+1, row-1, row) if isinstance(row, (int, float)) else row
        bars.append(Bar(datetime(2023, 1, 1)+timedelta(minutes=i), h, l, c, o))
    return bars


def event(direction="breakout", confirmed=3, name="L1", failure=None, created=1):
    """Make an event with separate candidate, confirmation and failure times."""
    return BreakoutEvent(name, direction, created, 2, 100, 99, .5, confirmed, failure, 7,
                         "false_"+direction if failure is not None else "pending", failure, 99)


def settings(**kwargs):
    """Use ATR(1) and one ATR of risk so expected fixtures are hand-calculable."""
    return replace(TradeSettings(atr_period=1, atr_stop_multiple=1), **kwargs)


class TradeArithmeticTests(unittest.TestCase):
    """Check independent long/short arithmetic, frozen levels, costs and equity."""

    def test_long_and_short_slide_targets(self):
        """Both sides gain four units with two units of risk; short target is lower."""
        for direction, row, expected_stop, expected_target in (
            ("breakout", (101,105,99,104), 98,104), ("breakdown", (99,101,95,96), 102,96)):
            bars = bars_from([100]*4+[row])
            result = simulate_trades(bars, [event(direction)], settings())
            trade = result.trades[0]
            self.assertEqual((trade.entry_index, trade.entry_price), (3,100))
            self.assertEqual((trade.stop_price, trade.target_price), (expected_stop, expected_target))
            self.assertEqual((trade.net_pnl, trade.exit_reason), (4,"take_profit"))
            self.assertEqual(result.equity[-1]['equity'],10004)

    def test_report_short_worked_example(self):
        """E=500, ATR=10, q=10, S=520, T=460, total fees=10 gives net +390."""
        bars = bars_from([(500,505,495,500)]*4+[(490,510,450,460)])
        result = simulate_trades(bars,[event('breakdown')],settings(atr_stop_multiple=2,quantity=10,fee_per_order=5))
        trade = result.trades[0]
        self.assertEqual((trade.stop_price,trade.target_price),(520,460))
        self.assertEqual(trade.net_pnl,390)
        self.assertEqual(trade.as_record(bars)['return_percent'],7.8)

    def test_slippage_is_in_price_not_double_counted(self):
        """10bp adverse entry and two fixed fees leave zero net at a 4-unit target."""
        bars = bars_from([100]*4+[(102,106,100,104)])
        result = simulate_trades(bars,[event()],settings(slippage_bps=10,fee_per_order=2))
        trade = result.trades[0]
        self.assertAlmostEqual(trade.entry_price,100.1)
        self.assertAlmostEqual(trade.exit_price,104.1)
        self.assertAlmostEqual(trade.net_pnl,0)
        self.assertAlmostEqual(result.equity[3]['equity'],9997.9)

    def test_short_stop_slippage(self):
        """Short cover is a buy and therefore receives an adverse upward adjustment."""
        bars = bars_from([100]*4+[(101,103,99,102)])
        trade = simulate_trades(bars,[event('breakdown')],settings(slippage_bps=10)).trades[0]
        self.assertAlmostEqual(trade.entry_price,99.9)
        self.assertAlmostEqual(trade.exit_price,101.9*1.001)

    def test_open_mark_is_not_realized(self):
        """A still-open position has no exit, realised P/L or win-rate observation."""
        bars = bars_from([100]*4+[(101,102,100,101)])
        result = simulate_trades(bars,[event()],settings(fee_per_order=.25))
        record = result.trades[0].as_record(bars)
        self.assertIsNone(record['exit_price'])
        self.assertIsNone(record['net_pnl'])
        self.assertEqual(record['unrealized_net_pnl'],.75)
        self.assertEqual(result.summary()['final_equity'],10000.75)
        self.assertIsNone(result.summary()['win_rate_percent'])

    def test_short_borrow_cost_and_equity(self):
        """One day at 36.5% on notional 100 costs 0.1, with no sale-proceeds gain."""
        bars = bars_from([100]*5)
        bars[4] = replace(bars[4],timestamp=bars[3].timestamp+timedelta(days=1))
        result = simulate_trades(bars,[event('breakdown')],settings(short_borrow_rate_percent=36.5))
        self.assertAlmostEqual(result.trades[0].borrow_cost,.1)
        self.assertAlmostEqual(result.summary()['final_equity'],9999.9)

    def test_gap_stops_are_not_guaranteed_stop_prices(self):
        """Adverse opening gaps fill at Open, on either side."""
        for direction,row,price in (("breakout",(95,97,94,96),95),("breakdown",(105,106,103,104),105)):
            trade = simulate_trades(bars_from([100]*4+[row]),[event(direction)],settings()).trades[0]
            self.assertEqual((trade.exit_price,trade.exit_reason),(price,'stop_gap'))
            self.assertEqual(trade.net_pnl,-5)

    def test_ambiguous_bar_stop_first_and_target_gap_priority(self):
        """Unknown intrabar sequence uses stop-first; known target at Open takes priority."""
        for direction,row,stop in (("breakout",(100,105,97,100),98),("breakdown",(100,103,95,100),102)):
            trade = simulate_trades(bars_from([100]*4+[row]),[event(direction)],settings()).trades[0]
            self.assertEqual(trade.exit_price,stop)
            self.assertTrue(trade.ambiguous_exit)
        trade = simulate_trades(bars_from([100]*4+[(105,106,97,100)]),[event()],settings()).trades[0]
        self.assertEqual((trade.exit_price,trade.exit_phase),(104,'open'))
        self.assertFalse(trade.ambiguous_exit)

    def test_invalid_numbers_and_capital(self):
        """Bad attributes fail early; insufficient equity and nonpositive targets are audited."""
        for options in ({'quantity':0},{'quantity':True},{'atr_period':2.5},{'fee_per_order':-1},
                        {'slippage_bps':10000},{'initial_equity':float('inf')},{'ema_filter':'yes'},
                        {'entry_timing':'future'},{'reward_risk_multiple':float('nan')}):
            with self.subTest(options=options),self.assertRaises(ValueError): TradeSettings(**options)
        bars = bars_from([100]*4)
        for config,reason in ((settings(initial_equity=99),'insufficient_equity'),
                              (settings(atr_stop_multiple=100),'invalid_price_levels')):
            result = simulate_trades(bars,[event()],config)
            self.assertEqual(result.trades,[])
            self.assertEqual(result.signals[0]['reason'],reason)


class TradeTimingTests(unittest.TestCase):
    """Confirm that the pictured entries and the optional report timing stay causal."""

    def test_close_entry_does_not_use_prior_intrabar_extremes(self):
        """Signal bar crosses both eventual levels, but protection has not begun yet."""
        bars = bars_from([100]*3+[(100,110,90,100),(100,100.1,99.9,100)])
        result = simulate_trades(bars,[event()],settings(atr_stop_multiple=.05))
        self.assertIsNone(result.trades[0].exit_index)
        self.assertEqual(result.trades[0].stop_price,99)

    def test_next_open_uses_confirmation_atr_not_fill_bar_atr(self):
        """A large gap/range at fill must not change the already-known ATR."""
        bars = bars_from([100]*4+[(110,111,109,110)])
        result = simulate_trades(bars,[event()],settings(entry_timing='next_open'))
        trade = result.trades[0]
        self.assertEqual((trade.signal_index,trade.entry_index,trade.entry_price),(3,4,110))
        self.assertEqual((trade.atr_at_signal,trade.stop_price,trade.target_price),(2,108,114))

    def test_next_open_same_bar_stop_and_final_signal(self):
        """Next-Open entry permits that bar's protection; final Close signal is unfilled."""
        bars = bars_from([100]*4+[(100,101,97,99)])
        result = simulate_trades(bars,[event()],settings(entry_timing='next_open'))
        self.assertEqual((result.trades[0].entry_index,result.trades[0].exit_index),(4,4))
        pending = simulate_trades(bars[:4],[event()],settings(entry_timing='next_open'))
        self.assertEqual(pending.trades,[])
        self.assertEqual(pending.summary()['pending_entries'],1)

    def test_later_false_label_never_erases_entry(self):
        """Failure at Close 5 is observed later; an optional exit occurs at Open 6."""
        bars = bars_from([100]*6+[(99,100,98,99)])
        e = event(failure=5)
        result = simulate_trades(bars,[e],settings(exit_on_false_break=True))
        trade = result.trades[0]
        self.assertEqual((trade.entry_index,trade.exit_signal_index,trade.exit_index),(3,5,6))
        self.assertEqual((trade.exit_price,trade.exit_reason),(99,'false_break'))
        default = simulate_trades(bars[:6],[e],settings())
        self.assertIsNone(default.trades[0].exit_index)
        pending = simulate_trades(bars[:6],[e],settings(exit_on_false_break=True))
        self.assertEqual(pending.trades[0].pending_exit_reason,'false_break')
        self.assertIsNone(pending.trades[0].net_pnl)

    def test_opposite_signal_exits_without_automatic_reverse(self):
        """Optional opposite exit queues a close, not a new short at that earlier signal."""
        bars = bars_from([100]*7)
        result = simulate_trades(bars,[event(),event('breakdown',confirmed=5,name='L2')],settings(exit_on_opposite=True))
        self.assertEqual(len(result.trades),1)
        self.assertEqual((result.trades[0].exit_index,result.trades[0].exit_reason),(6,'opposite_signal'))

    def test_deduplication_order_and_conflicts(self):
        """Primary reference is stable; opposite directions together are not traded."""
        bars = bars_from([100]*5)
        group = [event(name='Z'),event(name='A',created=0)]
        result = simulate_trades(bars,group,settings())
        self.assertEqual(len(result.trades),1)
        self.assertEqual(result.trades[0].line_ids,('A','Z'))
        reverse = simulate_trades(bars,list(reversed(group)),settings())
        self.assertEqual(result,reverse)
        mixed = simulate_trades(bars,[event(),event('breakdown',name='other')],settings())
        self.assertEqual(mixed.signals[0]['reason'],'opposing_signals')
        self.assertEqual(mixed.trades,[])

    def test_no_pyramiding_and_short_toggle(self):
        """Later same-direction confirmations do not add positions; long-only logs Sell skips."""
        bars = bars_from([100]*7)
        result = simulate_trades(bars,[event(),event(name='L2',confirmed=5)],settings())
        self.assertEqual(len(result.trades),1)
        self.assertEqual(result.signals[1]['reason'],'position_open')
        result = simulate_trades(bars,[event('breakdown')],settings(allow_short=False))
        self.assertEqual(result.signals[0]['reason'],'short_disabled')

    def test_warmup_filter_missing_open_and_empty(self):
        """Unavailable observations are explicit; they are never backfilled."""
        bars = bars_from([100]*4)
        for config,reason in ((TradeSettings(),'atr_unavailable'),
                              (settings(ema_filter=True,ema_period=20),'ema_unavailable'),
                              (settings(ema_filter=True,ema_period=1),'ema_filter')):
            result=simulate_trades(bars,[event()],config)
            self.assertEqual(result.signals[0]['reason'],reason)
        zero=simulate_trades(bars_from([(100,100,100,100)]*4),[event()],settings())
        self.assertEqual(zero.signals[0]['reason'],'atr_unavailable')
        missing=simulate_trades([replace(b,open=None) for b in bars],[event()],settings())
        self.assertEqual(missing.status,'unavailable_missing_open')
        self.assertEqual(simulate_trades([],[],settings()).summary()['trades'],0)
        self.assertEqual(simulate_trades(bars,[],settings(),basis='high-low').status,'not_supported_high_low')

    def test_unsupported_or_inconsistent_events_rejected(self):
        """Bad event timing and duplicate IDs cannot create accidental repeated trades."""
        bars=bars_from([100]*5)
        for events in ([event(),event()], [event(confirmed=8)], [event(failure=3)],
                       [replace(event(),direction='unknown')]):
            with self.assertRaises(ValueError): simulate_trades(bars,events,settings())


