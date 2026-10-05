import math
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from ema_scanner.models import Candle, Instrument, Settings
from ema_scanner.indicators import EMAHistory, ChartScale, ema_values
from ema_scanner.strategy import SignalMachine, qualification, rank_armed

NOW = datetime(2026, 10, 5, 5, 0, tzinfo=timezone.utc)
INST = Instrument('TEST', 'NSE_EQ|TEST', 'Test stock')


def candles(values):
    return [Candle(NOW - timedelta(minutes=5 * (len(values) - i)), v, v + .1, v - .1, v, 10) for i, v in enumerate(values)]


def candidate(side='LONG', gap=.04, angle=20, symbol='TEST'):
    snap = EMAHistory(candles([100] * 100), INST).snapshot(100, NOW, Settings())
    if side == 'LONG':
        return replace(snap, symbol=symbol, ema9=99.98, ema21=99.98 + gap,
                       previous9=99.95, previous21=100.05, angle=angle)
    return replace(snap, symbol=symbol, ema9=100.02, ema21=100.02 - gap,
                   previous9=100.05, previous21=99.95, angle=-angle)


class IndicatorsTest(unittest.TestCase):
    def test_standard_recursion(self):
        self.assertEqual(ema_values([10, 20, 30], 9), [10, 12, 15.6])

    def test_ticks_never_advance_completed_ema(self):
        history = EMAHistory(candles([100] * 100), INST)
        for price in [101, 102, 103, 105] * 100:
            snap = history.snapshot(price, NOW, Settings())
            self.assertAlmostEqual(snap.ema9, 100 + .2 * (price - 100))
            self.assertAlmostEqual(snap.ema21, 100 + (price - 100) / 11)
        self.assertEqual(history.ema9[-1], 100)

    def test_chord_matches_rendered_coordinates_and_aspect(self):
        snap = EMAHistory(candles([100 + i * .02 for i in range(100)]), INST).snapshot(102.1, NOW, Settings())
        x1, y1 = snap.scale.point(len(snap.ema9_points) - 3, snap.ema9_points[-3], 800, 400)
        x2, y2 = snap.scale.point(len(snap.ema9_points) - 1, snap.ema9_points[-1], 800, 400)
        self.assertAlmostEqual(snap.angle, math.degrees(math.atan2(y1-y2, x2-x1)))
        self.assertGreater(snap.angle, 0)
        with self.assertRaises(ValueError):
            snap.scale.point(1, 100, 800, 300)

    def test_scale_held_within_bar_and_refreshes_on_breach(self):
        h = EMAHistory(candles([100] * 100), INST)
        first = h.snapshot(100, NOW, Settings())
        small = h.snapshot(100.01, NOW + timedelta(seconds=1), Settings())
        extreme = h.snapshot(110, NOW + timedelta(seconds=2), Settings())
        self.assertEqual(first.scale, small.scale)
        self.assertGreater(extreme.scale.maximum, 110)

    def test_mirrored_series_have_opposite_angles(self):
        values = [100 + .1 * math.sin(i/5) - i*.002 for i in range(100)]
        a = EMAHistory(candles(values), INST).snapshot(100.2, NOW, Settings())
        b = EMAHistory(candles([200-v for v in values]), INST).snapshot(99.8, NOW, Settings())
        self.assertAlmostEqual(a.angle, -b.angle, places=9)

    def test_flat_range_and_invalid_prices(self):
        self.assertEqual(ChartScale(100, 100, 60).angle(100, 100, 2), 0)
        h = EMAHistory(candles([100]*100), INST)
        with self.assertRaises(ValueError):
            h.snapshot(float('nan'), NOW, Settings())


class RulesTest(unittest.TestCase):
    def test_both_directions_and_exact_proximity_boundary(self):
        for side in ['LONG', 'SHORT']:
            self.assertEqual(qualification(candidate(side, .05), Settings()), side)
            self.assertIsNone(qualification(candidate(side, .05001), Settings()))

    def test_convergence_direction_and_angle_are_all_required(self):
        snap = candidate()
        for bad in [replace(snap, previous9=100.1), replace(snap, angle=-1),
                    replace(snap, previous21=99.951), replace(snap, ema21=snap.ema9)]:
            self.assertIsNone(qualification(bad, Settings()))

    def test_bearish_mirrors_conditions(self):
        snap = candidate('SHORT')
        for bad in [replace(snap, previous9=99.9), replace(snap, angle=1),
                    replace(snap, previous21=100.049), replace(snap, ema21=snap.ema9)]:
            self.assertIsNone(qualification(bad, Settings()))

    def test_ranking_current_strength_gap_symbol(self):
        rows = [replace(candidate('SHORT', angle=30, symbol='B'), state='ARMED', side='SHORT'),
                replace(candidate(angle=20, symbol='A'), state='ARMED', side='LONG'),
                replace(candidate(angle=30, gap=.03, symbol='C'), state='ARMED', side='LONG')]
        self.assertEqual([x.symbol for x in rank_armed(rows)], ['C','B','A'])
        self.assertEqual(rank_armed([replace(rows[0], state='PAUSED')]), [])


class StateTest(unittest.TestCase):
    def test_verified_close_updates_baseline_in_both_directions(self):
        for side in ['LONG','SHORT']:
            before=candidate(side)
            after=replace(before,ema9=100.1 if side=='LONG' else 99.9,ema21=100)
            m=SignalMachine('TEST',Settings());m.observe(before);m.observe(after);m.closed(before)
            self.assertEqual(m.observe(after)[-1].state,'CROSSED')
            self.assertEqual(m.side,side)
            n=SignalMachine('TEST',Settings());n.observe(before);n.observe(after);n.closed(before)
            self.assertNotIn('CROSSED',[e.state for e in n.observe(before)])

    def test_confirmation_is_timestamped_at_bar_completion(self):
        before=candidate()
        after=replace(before,ema9=100.1,ema21=100,quote_time=NOW+timedelta(minutes=4))
        m=SignalMachine('TEST',Settings());m.observe(before);m.observe(after)
        event=m.closed(after)[-1]
        self.assertEqual(event.time,NOW+timedelta(minutes=5))
        self.assertGreater(event.time,after.quote_time)

    def test_initial_armed_is_labelled_and_unchanged_does_not_repeat(self):
        m = SignalMachine('TEST', Settings())
        events = m.observe(candidate(), initial=True)
        self.assertEqual([e.state for e in events], ['ARMED'])
        self.assertTrue(events[0].initial)
        self.assertEqual(m.observe(candidate()), [])

    def test_cross_confirm_in_both_directions(self):
        for side in ['LONG','SHORT']:
            m = SignalMachine('TEST', Settings())
            before = candidate(side)
            m.observe(before)
            after = replace(before, ema9=100.1 if side=='LONG' else 99.9, ema21=100)
            self.assertEqual(m.observe(after)[-1].state, 'CROSSED')
            self.assertEqual(m.closed(after)[-1].state, 'CONFIRMED')
            self.assertEqual(m.side, side)

    def test_cancellation_reversal_and_equality(self):
        m = SignalMachine('TEST', Settings())
        snap = candidate()
        m.observe(snap)
        self.assertEqual(m.observe(replace(snap, angle=-1))[-1].state, 'CANCELLED')
        m.observe(snap)
        self.assertNotIn('CROSSED', [e.state for e in m.observe(replace(snap, ema9=snap.ema21))])
        crossed = replace(snap, ema9=100.1, ema21=100)
        self.assertEqual(m.observe(crossed)[-1].state, 'CROSSED')
        self.assertIn('REVERSED', [e.state for e in m.observe(snap)])

    def test_initial_crossed_and_reconnect_do_not_invent_crossings(self):
        m = SignalMachine('TEST', Settings())
        above = replace(candidate(), ema9=101, ema21=100)
        self.assertNotIn('CROSSED', [e.state for e in m.observe(above, initial=True)])
        m.pause('reconnecting', NOW)
        self.assertNotIn('CROSSED', [e.state for e in m.observe(candidate())])

    def test_jump_cross_without_prior_arm_is_honest(self):
        m = SignalMachine('TEST', Settings())
        before = replace(candidate(), angle=0)
        m.observe(before)
        event = m.observe(replace(before, ema9=101, ema21=100))[-1]
        self.assertEqual(event.state, 'CROSSED')
        self.assertIn('without prior ARMED', event.reason)


if __name__ == '__main__':
    unittest.main()
