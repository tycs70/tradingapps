"""Trend membership is earned by observations, never reconstructed from history."""
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from global_trend.models import Candle, IST, Instrument, Settings
from global_trend.indicators import EMAHistory
from global_trend.trends import TrendBook, TrendCandidate, TrendRow
from tests.test_data import NOW, session


def snap(side='LONG', crossed=True, key='A', angle=20, at=NOW):
    history = EMAHistory(session(1)+session(2)+session(5,15), Instrument(key,key))
    row = history.snapshot(100, at, Settings())
    direction = 1 if side == 'LONG' else -1
    relation = direction if crossed else -direction
    return replace(row, ema9=100 + relation*.1, ema21=100,
                   price=100+direction, angle=direction*angle)


def observed(book, side='LONG', key='A', angle=20):
    book.observe(snap(side,False,key,angle))
    return book.observe(snap(side,True,key,angle,at=NOW+timedelta(seconds=1)))


def bar(at=NOW, close=101):
    return Candle(at,100,max(110,close),min(90,close),close)


class TrendBookTest(unittest.TestCase):
    def setUp(self): self.book=TrendBook(NOW.date())

    def test_observed_crossover_add_confirm_mirrors_and_records_details(self):
        for side, key, close, e9 in [('LONG','A',101,100.1),('SHORT','B',99,99.9)]:
            events=observed(self.book,side,key)
            self.assertEqual(events[-1].state,'TREND_ADDED')
            self.assertEqual(events[-1].price,close)
            self.assertEqual(events[-1].ema9,e9)
            self.assertEqual(events[-1].crossover_angle,20 if side=='LONG' else -20)
            self.assertEqual(events[-1].candle_time,NOW)
            c=self.book.candidates[key]
            self.assertEqual(c.status,'PROVISIONAL')
            self.assertEqual(c.crossover_time,NOW+timedelta(seconds=1))
            events=self.book.verified_candle(key,bar(close=close),e9,100)
            self.assertEqual(events[-1].state,'TREND_CONFIRMED')
            self.assertEqual(events[-1].time,NOW+timedelta(minutes=5))
            self.assertEqual(self.book.candidates[key].checked_through,NOW)
            self.assertEqual(self.book.candidates[key].status,'CONFIRMED')

    def test_no_initial_snapshot_or_history_creates_membership(self):
        self.assertEqual(self.book.observe(snap()),[])
        self.assertEqual(self.book.verified_candle('A',bar(),100.1,100),[])
        self.book.pause('A','disconnect',NOW)
        self.assertEqual(self.book.observe(snap('SHORT')),[])
        self.assertEqual(self.book.candidates,{})

    def test_direction_aligned_angle_and_price_are_required_without_minimum(self):
        for side in ['LONG','SHORT']:
            for angle,wrong_price,expected in [(0,False,False),(-1,False,False),(.00001,False,True),(20,True,False)]:
                with self.subTest(side=side,angle=angle,wrong_price=wrong_price):
                    b=TrendBook(NOW.date());b.observe(snap(side,False))
                    row=snap(side,angle=angle)
                    if wrong_price: row=replace(row,price=row.ema9)
                    b.observe(row)
                    self.assertEqual(bool(b.candidates),expected)

    def test_provisional_requires_crossing_bar_relationship_and_strict_price_side(self):
        for side in ['LONG','SHORT']:
            sign=1 if side=='LONG' else -1
            for close,e9 in [(100+sign,100-sign*.1),(100+sign*.1,100+sign*.1)]:
                with self.subTest(side=side,close=close,e9=e9):
                    b=TrendBook(NOW.date());observed(b,side)
                    self.assertEqual(b.verified_candle('A',bar(close=close),e9,100)[-1].state,'TREND_REMOVED')
                    self.assertFalse(b.candidates)

    def test_confirmed_wicks_intrabar_and_equality_preserve_adverse_close_removes(self):
        for side in ['LONG','SHORT']:
            sign=1 if side=='LONG' else -1
            b=TrendBook(NOW.date());observed(b,side)
            b.verified_candle('A',bar(close=100+sign),100+sign*.1,100)
            b.observe(replace(snap(side),price=100-sign*5))
            self.assertIn('A',b.candidates)
            b.verified_candle('A',bar(NOW+timedelta(minutes=5),100+sign*.1),100+sign*.1,100)
            self.assertIn('A',b.candidates)
            events=b.verified_candle('A',bar(NOW+timedelta(minutes=10),100-sign),100+sign*.1,100)
            self.assertEqual(events[-1].state,'TREND_REMOVED')
            self.assertIn('close',events[-1].reason.lower())
            b.verified_candle('A',bar(NOW+timedelta(minutes=15),100+sign),100+sign*.1,100)
            b.observe(snap(side))
            self.assertNotIn('A',b.candidates)

    def test_provisional_reversal_removes_and_new_side_independently_qualifies(self):
        observed(self.book)
        events=self.book.observe(snap('SHORT',angle=-1))
        self.assertEqual([e.state for e in events],['TREND_REMOVED'])
        self.assertNotIn('A',self.book.candidates)
        self.book.observe(snap('LONG'))
        self.book.observe(snap('SHORT'))
        self.assertEqual(self.book.candidates['A'].side,'SHORT')

    def test_pause_discards_provisional_retains_confirmed_and_resets_observation(self):
        observed(self.book,key='A');observed(self.book,key='B')
        self.book.verified_candle('B',bar(),100.1,100)
        self.book.pause('A','Disconnected',NOW);self.book.pause('B','Disconnected',NOW)
        self.assertNotIn('A',self.book.candidates)
        self.assertIn('B',self.book.candidates)
        self.assertEqual(self.book.observe(snap('SHORT',key='A')),[])

    def test_provisional_continuity_removal_retains_last_observed_market_details(self):
        observed(self.book)
        event=self.book.pause('A','Disconnected',NOW+timedelta(seconds=2))[-1]
        self.assertEqual(event.price,101)
        self.assertEqual(event.ema9,100.1)
        self.assertEqual(event.ema21,100)
        self.assertEqual(event.candle_time,NOW)
        self.assertEqual(event.crossover_angle,20)

    def test_routine_boundary_can_verify_provisional_from_backfill(self):
        observed(self.book)
        self.book.pause('A','Waiting for completed candle',NOW+timedelta(minutes=5),discard_provisional=False)
        self.book.verified_candle('A',bar(),100.1,100)
        self.assertEqual(self.book.candidates['A'].status,'CONFIRMED')

    def test_frozen_strength_top5_replacement_and_ties_are_stable(self):
        snapshots={}
        for side in ['LONG','SHORT']:
            for i in range(7):
                key=f'{side}{i}';observed(self.book,side,key,angle=i+1)
                snapshots[key]=replace(snap(side,key=key),angle=(100-i)*(1 if side=='LONG' else -1))
            rows=self.book.top(side,snapshots)
            self.assertEqual([r.key for r in rows],[f'{side}{i}' for i in range(6,1,-1)])
            self.assertEqual(rows[0].current_angle,94 if side=='LONG' else -94)
            self.assertEqual(rows[0].crossover_angle,7 if side=='LONG' else -7)
            with self.assertRaises(FrozenInstanceError): rows[0].candidate.crossover_angle=999
            with self.assertRaises(FrozenInstanceError): rows[0].snapshot=snap()
            self.book.pause(f'{side}6','Disconnected',NOW)
            self.assertEqual(self.book.top(side,snapshots)[-1].key,f'{side}1')
        b=TrendBook(NOW.date());observed(b,key='Z');observed(b,key='A')
        self.assertEqual([r.symbol for r in b.top('LONG',{'A':snap(key='A'),'Z':snap(key='Z')})],['A','Z'])

    def test_verified_bar_advances_relation_without_creating_membership(self):
        self.book.observe(snap('LONG',False))
        self.book.verified_candle('A',bar(),100.1,100)
        self.assertEqual(self.book.observe(snap('LONG')),[])
        self.assertEqual(self.book.candidates,{})
        events=self.book.observe(snap('SHORT'))
        self.assertEqual(events[-1].state,'TREND_ADDED')
        self.assertEqual(events[-1].side,'SHORT')

    def test_new_day_clears_candidates_and_observation_baseline(self):
        observed(self.book)
        self.assertTrue(self.book.reset_day(NOW.date()+timedelta(days=1),NOW+timedelta(days=1)))
        self.assertFalse(self.book.candidates)
        self.assertEqual(self.book.observe(replace(snap(),quote_time=NOW+timedelta(days=1))),[])

    def test_broker_closure_gap_is_allowed_but_missing_open_bar_is_not(self):
        from types import SimpleNamespace
        from global_trend.calendar import MarketCalendar,trading_day
        start=NOW.replace(day=12,hour=15,minute=25)  # Monday 09:55 UTC.
        calendar=MarketCalendar([(118800,122400),(126000,129600)],'UTC')
        c=TrendCandidate('A','A','LONG',start+timedelta(seconds=1),20,'CONFIRMED',start)
        for gap,valid in [(65,True),(70,False)]:
            b=TrendBook(trading_day(start),[c])
            bars=[bar(start),bar(start+timedelta(minutes=gap))]
            history=SimpleNamespace(candles=bars,ema9=[100,100.1],ema21=[99,99.1])
            _,result=b.verified_history('A',history,bars[-1].time+timedelta(minutes=5),calendar=calendar)
            self.assertEqual(result,valid)

    def test_initial_opposing_quote_invalidates_saved_trend_without_new_entry(self):
        c=TrendCandidate('A','A','LONG',NOW,20,'CONFIRMED',NOW)
        b=TrendBook(NOW.date(),[c])
        events=b.observe(snap('SHORT'),initial=True)
        self.assertFalse(b.candidates)
        self.assertEqual([e.state for e in events],['TREND_REMOVED'])
