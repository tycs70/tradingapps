"""Observed intraday trend membership; historical candles can only validate it."""
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
import math

from .models import Candle, Event, IST, Snapshot, bucket_time
from .calendar import trading_day


@dataclass(frozen=True)
class TrendCandidate:
    key: str
    symbol: str
    side: str
    crossover_time: datetime
    crossover_angle: float
    status: str
    checked_through: datetime

    @property
    def strength(self) -> float:
        return self.crossover_angle if self.side == 'LONG' else -self.crossover_angle


@dataclass(frozen=True)
class TrendRow:
    candidate: TrendCandidate
    snapshot: Snapshot

    @property
    def key(self): return self.candidate.key
    @property
    def symbol(self): return self.candidate.symbol
    @property
    def side(self): return self.candidate.side
    @property
    def status(self): return self.candidate.status
    @property
    def crossover_time(self): return self.candidate.crossover_time
    @property
    def crossover_angle(self): return self.candidate.crossover_angle
    @property
    def strength(self): return self.candidate.strength
    @property
    def current_angle(self): return self.snapshot.angle
    @property
    def angle(self): return self.current_angle
    @property
    def ema9(self): return self.snapshot.ema9
    @property
    def ema21(self): return self.snapshot.ema21
    @property
    def price(self): return self.snapshot.price
    @property
    def distance_pct(self): return 100 * (self.price - self.ema9) / self.ema9


class TrendBook:
    def __init__(self, day: date, candidates=(), day_key=trading_day):
        self.day_key = day_key
        self.day = day
        self.candidates = {c.key:c for c in candidates
                           if c.status == 'CONFIRMED' and day_key(c.crossover_time) == day}
        self._relations = {}
        self._latest = {}

    def _event(self, candidate, action, time, reason, price=None, ema9=None, ema21=None,
               candle_time=None, angle=None):
        states = {'ADD':'TREND_ADDED', 'CONFIRM':'TREND_CONFIRMED', 'REMOVE':'TREND_REMOVED'}
        return Event(candidate.symbol, states[action], candidate.side, time, reason,
                     candidate.crossover_angle if angle is None else angle,
                     price=price, ema9=ema9, ema21=ema21,
                     crossover_angle=candidate.crossover_angle, candle_time=candle_time,
                     action=action)

    def _remove(self, key, time, reason, **details):
        latest = self._latest.get(key)
        if latest:
            for name,value in (('price',latest.price),('ema9',latest.ema9),('ema21',latest.ema21),
                               ('candle_time',latest.bucket),('angle',latest.angle)):
                details.setdefault(name,value)
        c = self.candidates.pop(key, None)
        return [self._event(c, 'REMOVE', time, reason, **details)] if c else []

    def observe(self, s: Snapshot, initial=False) -> list[Event]:
        """Only successive live observations can earn a new candidate."""
        self._latest[s.key] = s
        relation = (s.ema9 > s.ema21) - (s.ema9 < s.ema21)
        prior = None if initial else self._relations.get(s.key)
        events = []
        if prior and relation and prior != relation:
            side = 'LONG' if relation > 0 else 'SHORT'
            existing = self.candidates.get(s.key)
            details = dict(price=s.price, ema9=s.ema9, ema21=s.ema21,
                           candle_time=s.bucket, angle=s.angle)
            if existing and existing.side != side:
                events += self._remove(s.key, s.quote_time, 'Observed EMA crossover reversed the trend.', **details)
            strength = s.angle if side == 'LONG' else -s.angle
            on_side = s.price > s.ema9 if side == 'LONG' else s.price < s.ema9
            if s.key not in self.candidates and math.isfinite(strength) and strength > 0 and on_side:
                candidate = TrendCandidate(s.key, s.symbol, side, s.quote_time, s.angle,
                                           'PROVISIONAL', s.candles[-2].time)
                self.candidates[s.key] = candidate
                events.append(self._event(candidate, 'ADD', s.quote_time,
                                          'Qualifying live EMA crossover observed.', **details))
        # Equality is a touch: retain the last non-zero relation across touches.
        if relation:
            self._relations[s.key] = relation
        elif prior is None:
            self._relations[s.key] = 0
        return events

    def verified_candle(self, key: str, candle: Candle, ema9: float, ema21: float,
                        revalidate=False) -> list[Event]:
        relation = (ema9 > ema21) - (ema9 < ema21)
        if relation:
            self._relations[key] = relation
        elif key not in self._relations:
            self._relations[key] = 0
        c = self.candidates.get(key)
        if not c or candle.time < bucket_time(c.crossover_time): return []
        if not revalidate and candle.time <= c.checked_through: return []
        sign = 1 if c.side == 'LONG' else -1
        relation = sign * (ema9 - ema21)
        distance = sign * (candle.close - ema9)
        details = dict(price=candle.close, ema9=ema9, ema21=ema21, candle_time=candle.time)
        end = candle.time + timedelta(minutes=5)
        if distance < 0:
            return self._remove(key, end, 'Completed candle closed across EMA9.', **details)
        if relation < 0:
            return self._remove(key, end, 'Completed candle verified the opposite EMA relationship.', **details)
        if c.status == 'PROVISIONAL':
            if candle.time != bucket_time(c.crossover_time) or relation <= 0 or distance <= 0:
                return self._remove(key, end, 'Crossing candle did not confirm the trend side and close.', **details)
            c = replace(c, status='CONFIRMED', checked_through=candle.time)
            self.candidates[key] = c
            return [self._event(c, 'CONFIRM', end, 'Crossing five-minute candle verified.', **details)]
        self.candidates[key] = replace(c, checked_through=max(c.checked_through,candle.time))
        return []

    def verified_history(self, key, history, now) -> tuple[list[Event], bool]:
        """Check every candle from the capture, including corrected/missed bars.

        The caller validates session completeness first. Absent required bars hide
        retained membership; neither successful nor failed backfill adds a trend.
        """
        c = self.candidates.get(key)
        if not c: return [], True
        crossing = bucket_time(c.crossover_time)
        last = history.candles[-1].time
        if c.crossover_time > now or c.checked_through > last: return [], False
        if crossing > last:
            return [], c.status == 'PROVISIONAL' and c.checked_through == last
        indices = [i for i,b in enumerate(history.candles) if crossing <= b.time <= last]
        if not indices or history.candles[indices[0]].time != crossing: return [], False
        times = [history.candles[i].time for i in indices]
        if any(b-a != timedelta(minutes=5) for a,b in zip(times,times[1:])): return [], False
        events = []
        for i in indices:
            events += self.verified_candle(key,history.candles[i],history.ema9[i],history.ema21[i],revalidate=True)
            if key not in self.candidates: break
        return events, True

    def pause(self, key, reason, time, discard_provisional=True) -> list[Event]:
        self._relations.pop(key, None)
        c = self.candidates.get(key)
        if c and c.status == 'PROVISIONAL' and discard_provisional:
            return self._remove(key,time,'Provisional observation continuity lost: '+reason)
        return []

    def reset_day(self, day: date, time: datetime) -> list[Event]:
        if self.day == day: return []
        events = []
        for key in list(self.candidates):
            events += self._remove(key,time,'New trading session; intraday membership reset.')
        self.day = day
        self._relations.clear()
        self._latest.clear()
        return events

    def top(self, side, snapshots: dict[str,Snapshot], limit=5) -> list[TrendRow]:
        candidates = sorted((c for c in self.candidates.values() if c.side == side and c.key in snapshots),
                            key=lambda c:(-c.strength,c.crossover_time,c.symbol,c.key))
        return [TrendRow(c,snapshots[c.key]) for c in candidates[:limit]]

    def confirmed(self) -> tuple[TrendCandidate,...]:
        return tuple(sorted((c for c in self.candidates.values() if c.status == 'CONFIRMED'),key=lambda c:c.key))
