"""Broker schedules and the global desk's daily trend-membership boundary."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc


def trading_day(when: datetime, boundary='17:00', zone='America/New_York'):
    if when.tzinfo is None:
        raise ValueError('An aware timestamp is required.')
    h,m=map(int,boundary.split(':'))
    if not 0<=h<24 or not 0<=m<60:
        raise ValueError('Invalid daily boundary.')
    local=when.astimezone(ZoneInfo(zone))
    return local.date()+timedelta(days=(local.hour,local.minute)>=(h,m))


class MarketCalendar:
    def __init__(self, intervals=(), zone='UTC', holidays=()):
        self.zone=ZoneInfo(zone or 'UTC')
        self.intervals=tuple((int(a),int(b)) for a,b in intervals)
        if any(not 0<=a<b<=604800 for a,b in self.intervals):
            raise ValueError('Invalid broker schedule.')
        self.holidays=frozenset(holidays)

    def is_open(self, when):
        if when.tzinfo is None:
            raise ValueError('An aware timestamp is required.')
        t=when.astimezone(self.zone)
        if t.date() in self.holidays:
            return False
        second=((t.weekday()+1)%7)*86400+t.hour*3600+t.minute*60+t.second
        return any(a<=second<b for a,b in self.intervals)

    def expected_buckets(self,start,end):
        t=start.astimezone(UTC).replace(second=0,microsecond=0)
        t=t.replace(minute=t.minute//5*5)
        if t<start:t+=timedelta(minutes=5)
        out=[]
        while t+timedelta(minutes=5)<=end:
            if self.is_open(t) and self.is_open(t+timedelta(minutes=5,microseconds=-1)):
                out.append(t)
            t+=timedelta(minutes=5)
        return tuple(out)
