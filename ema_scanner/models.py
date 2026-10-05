from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math

IST = timezone(timedelta(hours=5, minutes=30))


def bucket_time(when: datetime, minutes: int = 5) -> datetime:
    local = when.astimezone(IST)
    return local.replace(minute=local.minute // minutes * minutes, second=0, microsecond=0)


@dataclass(frozen=True)
class Instrument:
    symbol: str
    key: str
    name: str = ''


@dataclass(frozen=True)
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0

    def valid(self) -> bool:
        return (self.time.tzinfo is not None and
                all(math.isfinite(v) and v > 0 for v in (self.open, self.high, self.low, self.close)) and
                self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high and
                math.isfinite(self.volume) and self.volume >= 0)


@dataclass(frozen=True)
class Settings:
    proximity_pct: float = .05
    chart_bars: int = 60
    angle_intervals: int = 2
    fresh_seconds: int = 15
    remember_token: bool = False

    def __post_init__(self):
        if not math.isfinite(self.proximity_pct) or not .001 <= self.proximity_pct <= .5:
            raise ValueError('Proximity must be between 0.001% and 0.5%.')
        if not 20 <= self.chart_bars <= 120 or not 1 <= self.angle_intervals <= 5:
            raise ValueError('Chart bars: 20–120; angle intervals: 1–5.')
        if self.fresh_seconds != 15:
            raise ValueError('Quote freshness is fixed at 15 seconds.')
        if not isinstance(self.remember_token,bool):
            raise ValueError('Remember token must be enabled or disabled.')


@dataclass(frozen=True)
class Snapshot:
    symbol: str
    key: str
    price: float
    quote_time: datetime
    bucket: datetime
    ema9: float
    ema21: float
    previous9: float
    previous21: float
    angle: float
    scale: object
    candles: tuple[Candle, ...]
    ema9_points: tuple[float, ...]
    ema21_points: tuple[float, ...]
    state: str = 'WATCHING'
    side: str = ''
    armed_time: datetime | None = None
    reason: str = ''

    @property
    def gap_pct(self) -> float:
        return 100 * abs(self.ema9 - self.ema21) / self.price

    @property
    def strength(self) -> float:
        return self.angle if self.side == 'LONG' else -self.angle


@dataclass(frozen=True)
class Event:
    symbol: str
    state: str
    side: str
    time: datetime
    reason: str
    angle: float = 0
    initial: bool = False
    sequence: int = 0
