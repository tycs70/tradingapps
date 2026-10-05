"""Symmetric provisional pre-cross rules; no ATR and no order API."""
from dataclasses import replace
from datetime import datetime

from .models import Event, Settings, Snapshot


def qualification(s: Snapshot, settings: Settings) -> str | None:
    if s.gap_pct > settings.proximity_pct + 1e-10:
        return None
    if (s.ema9 < s.ema21 and s.ema9 > s.previous9 and s.angle > 0 and
            s.ema21-s.ema9 < s.previous21-s.previous9):
        return 'LONG'
    if (s.ema9 > s.ema21 and s.ema9 < s.previous9 and s.angle < 0 and
            s.ema9-s.ema21 < s.previous9-s.previous21):
        return 'SHORT'
    return None


def rank_armed(rows: list[Snapshot]) -> list[Snapshot]:
    return sorted((s for s in rows if s.state == 'ARMED'),
                  key=lambda s: (-s.strength, s.gap_pct, s.symbol))


class SignalMachine:
    def __init__(self, symbol: str, settings: Settings):
        self.symbol = symbol
        self.settings = settings
        self.state = 'WATCHING'
        self.side = ''
        self.reason = ''
        self.armed_time = None
        self._relation = None
        self._cross_side = None

    def _event(self, state, side, time, reason, angle=0, initial=False):
        self.state, self.side, self.reason = state, side, reason
        return Event(self.symbol, state, side, time, reason, angle, initial)

    def observe(self, s: Snapshot, initial: bool = False) -> list[Event]:
        relation = (s.ema9 > s.ema21) - (s.ema9 < s.ema21)
        first = initial or self._relation is None
        events = []
        armed = qualification(s, self.settings)
        if not first and relation and self._relation and relation != self._relation:
            side = 'LONG' if relation > 0 else 'SHORT'
            if self._cross_side:
                events.append(self._event('REVERSED', self._cross_side, s.quote_time,
                                          'Live crossover reversed before close.', s.angle))
            prior = self.state == 'ARMED' and self.side == side
            reason = 'Live EMA crossover observed' + ('.' if prior else ' without prior ARMED observation.')
            self._cross_side = side
            self.armed_time = None
            events.append(self._event('CROSSED', side, s.quote_time, reason, s.angle))
        elif not self._cross_side:
            if armed:
                if self.state != 'ARMED' or self.side != armed:
                    self.armed_time = s.quote_time
                    reason = 'Initial observation; provisional pre-cross.' if first else 'Provisional pre-cross conditions met.'
                    events.append(self._event('ARMED', armed, s.quote_time, reason, s.angle, first))
            elif self.state == 'ARMED':
                self.armed_time = None
                events.append(self._event('CANCELLED', self.side, s.quote_time,
                                          'Pre-cross conditions no longer hold.', s.angle))
            elif self.state not in ('CANCELLED', 'CONFIRMED') or first:
                self.state, self.side, self.reason = 'WATCHING', '', ''
        if relation:
            self._relation = relation
        elif first:
            self._relation = 0
        return events

    def closed(self, s: Snapshot) -> list[Event]:
        side = self._cross_side
        self._cross_side = None
        if not side:
            return []
        correct = s.ema9 > s.ema21 if side == 'LONG' else s.ema9 < s.ema21
        state = 'CONFIRMED' if correct else 'REVERSED'
        return [self._event(state, side, s.bucket, 'Completed five-minute candle verified.', s.angle)]

    def pause(self, reason: str, time: datetime) -> list[Event]:
        changed = self.state != 'PAUSED' or self.reason != reason
        self._relation = None
        self._cross_side = None
        self.armed_time = None
        return [self._event('PAUSED', '', time, reason)] if changed else []

    def decorate(self, s: Snapshot) -> Snapshot:
        return replace(s, state=self.state, side=self.side, armed_time=self.armed_time, reason=self.reason)
