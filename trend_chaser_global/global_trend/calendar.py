"""Broker schedules and the global desk's daily trend-membership boundary."""
from datetime import datetime, timedelta, timezone,time
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
    def __init__(self, intervals=(), zone='UTC', holidays=(), holiday_rules=()):
        self.zone=ZoneInfo(zone or 'UTC')
        self.intervals=tuple((int(a),int(b)) for a,b in intervals)
        if any(not 0<=a<b<=604800 for a,b in self.intervals):
            raise ValueError('Invalid broker schedule.')
        self.holidays=frozenset(holidays)
        self.holiday_rules=tuple(dict(r,timezone=ZoneInfo(r['zone'])) for r in holiday_rules)
        if any(not 0<=r['start']<r['end']<=86400 for r in self.holiday_rules):
            raise ValueError('Invalid holiday schedule.')

    def is_open(self, when):
        if when.tzinfo is None:
            raise ValueError('An aware timestamp is required.')
        t=when.astimezone(self.zone)
        if t.date() in self.holidays:
            return False
        for rule in self.holiday_rules:
            h=when.astimezone(rule['timezone'])
            same=((h.month,h.day)==(rule['date'].month,rule['date'].day)
                  if rule['recurring'] else h.date()==rule['date'])
            if same and rule['start']<=h.hour*3600+h.minute*60+h.second<rule['end']:
                return False
        second=((t.weekday()+1)%7)*86400+t.hour*3600+t.minute*60+t.second
        return any(a<=second<b for a,b in self.intervals)

    def expected_buckets(self,start,end):
        t=start.astimezone(UTC).replace(second=0,microsecond=0)
        t=t.replace(minute=t.minute//5*5)
        if t<start:t+=timedelta(minutes=5)
        out=[]
        while t+timedelta(minutes=5)<=end:
            if self.overlaps(t,t+timedelta(minutes=5)):
                out.append(t)
            t+=timedelta(minutes=5)
        return tuple(out)

    def overlaps(self,start,end):
        """A partial M5 candle exists whenever any portion is tradable."""
        last=end-timedelta(microseconds=1)
        if self.is_open(start) or self.is_open(last):return True
        points=set()
        # Opening instants cover sessions fully contained inside the candle.
        weeks=set()
        for instant in (start,last):
            local=instant.astimezone(self.zone)
            weeks.add(local.date()-timedelta(days=(local.weekday()+1)%7))
        for week in weeks:
            for a,b in self.intervals:
                naive=datetime.combine(week,time())+timedelta(seconds=a)
                for fold in (0,1):points.add(naive.replace(tzinfo=self.zone,fold=fold).astimezone(UTC))
        # A partial holiday can end inside a still-open broker session.
        for rule in self.holiday_rules:
            zone=rule['timezone']
            dates={instant.astimezone(zone).date() for instant in (start,last)}
            for day in dates:
                matches=((day.month,day.day)==(rule['date'].month,rule['date'].day)
                         if rule['recurring'] else day==rule['date'])
                if matches:
                    naive=datetime.combine(day,time())+timedelta(seconds=rule['end'])
                    for fold in (0,1):points.add(naive.replace(tzinfo=zone,fold=fold).astimezone(UTC))
        # A DST jump can enter an already-started local-time session.
        zones={self.zone}|{r['timezone'] for r in self.holiday_rules}
        for zone in zones:
            before=start.astimezone(zone).utcoffset()
            if before!=last.astimezone(zone).utcoffset():
                lo,hi=start,last
                while (hi-lo).total_seconds()>0.000001:
                    mid=lo+(hi-lo)/2
                    if mid.astimezone(zone).utcoffset()==before:lo=mid
                    else:hi=mid
                points.add(hi)
        return any(start<=p<end and self.is_open(p) for p in points)
