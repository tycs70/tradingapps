from datetime import datetime, timedelta, timezone, date
import unittest
from global_trend.calendar import MarketCalendar, trading_day

UTC = timezone.utc


class CalendarTest(unittest.TestCase):
    def test_indian_midnight_does_not_reset_us_trading_day(self):
        a = datetime(2026,10,15,18,29,tzinfo=UTC)
        self.assertEqual(trading_day(a), trading_day(a + timedelta(minutes=2)))
        self.assertEqual(trading_day(a), date(2026,10,15))

    def test_boundary_tracks_new_york_dst(self):
        for month,day,hour in [(1,15,22),(7,15,21),(3,8,21),(11,1,22)]:
            t=datetime(2026,month,day,hour,tzinfo=UTC)
            self.assertNotEqual(trading_day(t-timedelta(seconds=1)),trading_day(t))

    def test_expected_bars_exclude_scheduled_closure(self):
        # Sunday-based schedule: Monday 09:00–10:00 and 11:00–12:00 UTC.
        cal=MarketCalendar([(118800,122400),(126000,129600)],'UTC')
        a=datetime(2026,10,12,9,tzinfo=UTC)
        self.assertTrue(cal.is_open(a))
        self.assertFalse(cal.is_open(a+timedelta(hours=1)))
        bars=cal.expected_buckets(a,a+timedelta(hours=3))
        self.assertEqual(len(bars),24)
        self.assertNotIn(a+timedelta(hours=1),bars)

    def test_holiday_and_unknown_schedule_are_closed(self):
        t=datetime(2026,10,12,9,tzinfo=UTC)
        self.assertFalse(MarketCalendar().is_open(t))
        self.assertFalse(MarketCalendar([(0,604800)],'UTC',[t.date()]).is_open(t))

    def test_schedule_uses_reported_timezone(self):
        cal=MarketCalendar([(118800,122400)],'America/New_York')
        self.assertTrue(cal.is_open(datetime(2026,10,12,13,tzinfo=UTC)))
        self.assertFalse(cal.is_open(datetime(2026,10,12,9,tzinfo=UTC)))

    def test_recurring_partial_holiday_uses_its_own_timezone(self):
        rule={'date':date(2020,10,12),'zone':'America/New_York',
              'start':9*3600,'end':10*3600,'recurring':True}
        cal=MarketCalendar([(0,604800)],'UTC',holiday_rules=[rule])
        self.assertTrue(cal.is_open(datetime(2026,10,12,12,59,tzinfo=UTC)))
        self.assertFalse(cal.is_open(datetime(2026,10,12,13,30,tzinfo=UTC)))
        self.assertTrue(cal.is_open(datetime(2026,10,12,14,tzinfo=UTC)))

    def test_partial_session_and_holiday_reopening_produce_a_bar(self):
        a=datetime(2026,10,12,13,30,tzinfo=UTC);sec=86400+13*3600+30*60
        self.assertEqual(MarketCalendar([(sec+60,sec+120)]).expected_buckets(a,a+timedelta(minutes=5)),(a,))
        rule={'date':a.date(),'zone':'UTC','start':0,'end':13*3600+31*60,'recurring':False}
        cal=MarketCalendar([(sec,sec+120)],holiday_rules=[rule])
        self.assertEqual(cal.expected_buckets(a,a+timedelta(minutes=5)),(a,))

    def test_dst_jump_into_short_session_is_not_a_closed_bar(self):
        a=datetime(2026,3,8,6,59,tzinfo=UTC).replace(minute=55)
        # DST jumps 01:59:59 to 03:00; 02:30–03:02 yields a partial 07:00 UTC candle.
        cal=MarketCalendar([(2*3600+30*60,3*3600+2*60)],'America/New_York')
        start=datetime(2026,3,8,7,tzinfo=UTC)
        self.assertIn(start,cal.expected_buckets(a,start+timedelta(minutes=5)))


if __name__ == '__main__': unittest.main()
