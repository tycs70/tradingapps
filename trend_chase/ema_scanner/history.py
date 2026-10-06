"""Validate regular-session candles and aggregate complete broker minute bars."""
from collections import defaultdict
from datetime import datetime, timedelta

from .models import Candle, IST, bucket_time


def regular_session(when: datetime) -> bool:
    local = when.astimezone(IST)
    minute = local.hour*60 + local.minute
    return local.weekday() < 5 and 555 <= minute < 930


def parse_time(value) -> datetime:
    if isinstance(value, (int,float)) or (isinstance(value,str) and value.isdigit()):
        return datetime.fromtimestamp(float(value)/1000,IST)
    time = datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if time.tzinfo is None:
        raise ValueError('Broker timestamps must include timezone.')
    return time.astimezone(IST)


def parse_candles(rows: list, now: datetime) -> list[Candle]:
    candles = {}
    for row in rows:
        try:
            t = parse_time(row[0])
            c = Candle(t,*(float(v) for v in row[1:6]))
        except (ValueError, TypeError, IndexError, OverflowError, OSError) as exc:
            raise ValueError('Invalid historical candle.') from exc
        if not c.valid():
            raise ValueError('Invalid historical OHLC.')
        if not regular_session(t):
            continue
        if t != bucket_time(t):
            raise ValueError('Historical candle is not five-minute aligned.')
        if t+timedelta(minutes=5) <= now:
            candles[t] = c
    return sorted(candles.values(),key=lambda c:c.time)


def validate_history(candles: list[Candle], now: datetime):
    if len(candles) < 100:
        raise ValueError('Fewer than 100 completed candles.')
    groups = defaultdict(list)
    for c in candles:
        if not c.valid() or not regular_session(c.time) or c.time != bucket_time(c.time):
            raise ValueError('Invalid regular-session history.')
        groups[c.time.astimezone(IST).date()].append(c.time)
    for day, times in groups.items():
        start = datetime(day.year,day.month,day.day,9,15,tzinfo=IST)
        if times[0] != start or any(b-a != timedelta(minutes=5) for a,b in zip(times,times[1:])):
            raise ValueError('Missing five-minute candles; backfill required.')
        if day < now.astimezone(IST).date() and times[-1].hour*60+times[-1].minute != 925:
            raise ValueError('Prior-session history is incomplete.')
    if regular_session(now):
        start = now.astimezone(IST).replace(hour=9,minute=15,second=0,microsecond=0)
        expected = bucket_time(now)-timedelta(minutes=5)
        if expected >= start and candles[-1].time != expected:
            raise ValueError('Current-session history needs backfill.')


class MinuteBook:
    def __init__(self):
        self.minutes = {}
        self.finalized = {}

    def update(self, rows: list[Candle], current_bucket: datetime) -> tuple[list[Candle], bool]:
        for c in rows:
            if not c.valid() or c.time.second or c.time.microsecond or not regular_session(c.time):
                raise ValueError('Invalid broker minute candle.')
            self.minutes[c.time] = c
        buckets = sorted({bucket_time(t) for t in self.minutes if bucket_time(t) < current_bucket})
        completed, gap = [], False
        for bucket in buckets:
            parts = [self.minutes.get(bucket+timedelta(minutes=i)) for i in range(5)]
            if any(c is None for c in parts):
                gap = True
                continue
            c = Candle(bucket,parts[0].open,max(p.high for p in parts),min(p.low for p in parts),
                       parts[-1].close,sum(p.volume for p in parts))
            if self.finalized.get(bucket) != c:
                self.finalized[bucket] = c
                completed.append(c)
        cutoff = current_bucket - timedelta(minutes=15)
        self.minutes = {t:c for t,c in self.minutes.items() if t >= cutoff}
        self.finalized = {t:c for t,c in self.finalized.items() if t >= cutoff}
        return completed,gap
