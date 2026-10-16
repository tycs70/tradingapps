"""Completed-bar EMA state and the exact 2:1 reference-chart coordinates."""
from dataclasses import dataclass
from datetime import datetime
import math

from .models import Candle, Instrument, Settings, Snapshot, bucket_time


def ema_values(closes: list[float], period: int) -> list[float]:
    if not closes:
        return []
    result = [closes[0]]
    alpha = 2 / (period + 1)
    for close in closes[1:]:
        result.append(result[-1] + alpha * (close - result[-1]))
    return result


@dataclass(frozen=True)
class ChartScale:
    minimum: float
    maximum: float
    count: int

    def point(self, index: int, price: float, width: float, height: float) -> tuple[float, float]:
        if not math.isclose(width, height * 2, rel_tol=1e-8):
            raise ValueError('Reference plot must have a 2:1 aspect ratio.')
        span = self.maximum - self.minimum
        y = height / 2 if span <= 0 else height * (self.maximum - price) / span
        return index * width / max(1, self.count - 1), y

    def angle(self, start: float, end: float, intervals: int) -> float:
        if self.maximum <= self.minimum or self.count <= 1:
            return 0
        upward = (end - start) / (self.maximum - self.minimum)
        horizontal = 2 * intervals / (self.count - 1)
        return math.degrees(math.atan2(upward, horizontal))


class EMAHistory:
    def __init__(self, candles: list[Candle], instrument: Instrument = Instrument('', '')):
        self.instrument = instrument
        self._scale = None
        self._scale_key = None
        self._forming = None
        self.replace(candles)

    def replace(self, candles: list[Candle]):
        if len(candles) < 100 or any(not c.valid() for c in candles):
            raise ValueError('At least 100 valid completed candles are required.')
        if any(a.time >= b.time for a, b in zip(candles, candles[1:])):
            raise ValueError('Completed candles must be unique and chronological.')
        self.candles = list(candles[-1500:])
        closes = [c.close for c in self.candles]
        self.ema9 = ema_values(closes, 9)
        self.ema21 = ema_values(closes, 21)
        self._scale = None
        self._forming = None

    def append(self, candle: Candle):
        if not candle.valid() or candle.time <= self.candles[-1].time:
            raise ValueError('New completed candle must follow history.')
        self.candles.append(candle)
        self.ema9.append(self.ema9[-1] + .2 * (candle.close - self.ema9[-1]))
        self.ema21.append(self.ema21[-1] + (candle.close - self.ema21[-1]) / 11)
        self._scale = None
        self._forming = None

    def snapshot(self, price: float, quote_time: datetime, settings: Settings) -> Snapshot:
        if not math.isfinite(price) or price <= 0 or quote_time.tzinfo is None:
            raise ValueError('Invalid quote.')
        bucket = bucket_time(quote_time)
        if self.candles[-1].time >= bucket:
            raise ValueError('History must exclude the developing candle.')
        if self._forming is None or self._forming.time != bucket:
            self._forming = Candle(bucket, price, price, price, price)
        else:
            c = self._forming
            self._forming = Candle(bucket, c.open, max(c.high, price), min(c.low, price), price)
        live9 = self.ema9[-1] + .2 * (price - self.ema9[-1])
        live21 = self.ema21[-1] + (price - self.ema21[-1]) / 11
        count = settings.chart_bars
        bars = tuple(self.candles[-(count-1):]) + (self._forming,)
        points9 = tuple(self.ema9[-(count-1):]) + (live9,)
        points21 = tuple(self.ema21[-(count-1):]) + (live21,)
        lo = min(min(c.low for c in bars), min(points9), min(points21))
        hi = max(max(c.high for c in bars), max(points9), max(points21))
        key = (bucket, count, settings.angle_intervals)
        if (self._scale is None or key != self._scale_key or
                lo < self._scale.minimum or hi > self._scale.maximum):
            padding = max((hi-lo)*.05, price*.00001)
            self._scale = ChartScale(lo-padding, hi+padding, len(bars))
            self._scale_key = key
        angle = self._scale.angle(points9[-1-settings.angle_intervals], live9, settings.angle_intervals)
        return Snapshot(self.instrument.symbol, self.instrument.key, price, quote_time, bucket,
                        live9, live21, self.ema9[-1], self.ema21[-1], angle,
                        self._scale, bars, points9, points21)
