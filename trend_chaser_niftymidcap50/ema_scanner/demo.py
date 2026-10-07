"""Fictional layout samples, completely separate from live scanner membership."""
from dataclasses import replace
from datetime import datetime, timedelta
from html import escape

from . import VERSION
from .indicators import EMAHistory
from .models import Candle, Instrument, IST, Settings
from .trends import TrendCandidate, TrendRow

SAMPLE_TIME = datetime(2026, 10, 7, 11, 20, tzinfo=IST)
LABEL = 'DEMO — SAMPLE DATA'
DISCLAIMER = '7 October 2026 · fictional shares and prices · layout illustration, not market outcomes or predictions.'
TREND_COLUMNS = ('#', 'Share', 'Status', 'Cross °', 'Live °', 'Live price', 'Entry IST')


def _snapshot(symbol, side, base, step):
    sign = 1 if side == 'LONG' else -1
    candles = []
    for i in range(100):
        close = base + sign * step * i
        opened = close - sign * step * .5
        candles.append(Candle(SAMPLE_TIME-timedelta(minutes=5*(100-i)), opened,
                              max(opened, close)+step, min(opened, close)-step, close, 10000))
    history = EMAHistory(candles, Instrument(symbol, 'SAMPLE|'+symbol))
    snapshot = history.snapshot(candles[-1].close+sign*step*.8, SAMPLE_TIME, Settings())
    return replace(snapshot, side=side, state='SAMPLE')


def sample_data():
    """Return fresh immutable samples. Never submitted to Scanner or TrendStore."""
    bullish, bearish = [], []
    for side, target in [('LONG', bullish), ('SHORT', bearish)]:
        for i in range(7):
            snapshot = _snapshot(f'SAMPLE-{side}-{i+1}', side, 800+i*350, 1.2+i*.22)
            crossover = SAMPLE_TIME-timedelta(minutes=45+i*5, seconds=12+i)
            angle = (1 if side == 'LONG' else -1)*(42-i*5.25)
            status = 'PROVISIONAL' if i == 6 else 'CONFIRMED'
            if status == 'PROVISIONAL':
                crossover = SAMPLE_TIME-timedelta(seconds=25)
            candidate = TrendCandidate(snapshot.key, snapshot.symbol, side, crossover, angle,
                                       status, snapshot.bucket-timedelta(minutes=5))
            target.append(TrendRow(candidate, snapshot))
    armed = []
    for i, side in enumerate(('LONG', 'SHORT', 'LONG')):
        snapshot = _snapshot(f'SAMPLE-PRE-{i+1}', side, 1200+i*450, .7)
        # Illustrate a still pre-cross relationship with a small EMA gap.
        sign = 1 if side == 'LONG' else -1
        ema21 = snapshot.ema9 + sign*.04
        points = tuple(value+sign*.04*(len(snapshot.ema9_points)-i)
                       for i,value in enumerate(snapshot.ema9_points))
        armed.append(replace(snapshot, ema21=ema21, previous21=snapshot.previous9+sign*.08, ema21_points=points,
                             state='ARMED', armed_time=SAMPLE_TIME-timedelta(seconds=15)))
    return {'settings': Settings(), 'status': LABEL, 'market': 'SAMPLE / OFFLINE',
            'connected': False, 'connecting': False, 'trends_long': bullish, 'trends_short': bearish,
            'armed': armed, 'rows': [r.snapshot for r in bullish+bearish],
            'trend_counts': {'total': 14, 'long': 7, 'short': 7, 'confirmed': 12, 'provisional': 2,
                             'active_long': 7, 'active_short': 7, 'hidden': 0},
            'counts': {'eligible': 0, 'subscribed': 0, 'receiving': 0, 'ready': 0, 'paused': 0},
            'events': [], 'stocks': [], 'diagnostics': [], 'trend_status': 'Sample only; no live membership or saved trends.'}


class OfflineScanner:
    """Entry-point adapter with no broker, worker, logger or persistence."""
    def snapshot(self):
        data = sample_data()
        for name in ('trends_long', 'trends_short', 'armed', 'rows'):
            data[name] = []
        data['trend_counts'] = dict.fromkeys(data['trend_counts'], 0)
        data['status'] = 'Offline demo · no broker connection'
        return data

    def connect(self, token):
        return

    def disconnect(self):
        return

    def close(self):
        return


def _chart_svg(snapshot):
    width, height = 900, 450
    def point(i, value):
        x, y = snapshot.scale.point(i, value, width, height)
        return x+65, y+25
    pieces = ['<svg viewBox="0 0 1030 520" role="img" aria-label="Sample five-minute reference chart">']
    for i, candle in enumerate(snapshot.candles):
        x, high = point(i, candle.high)
        _, low = point(i, candle.low)
        _, opened = point(i, candle.open)
        _, closed = point(i, candle.close)
        color = '#46d8a3' if candle.close >= candle.open else '#ff8190'
        pieces.append(f'<path d="M{x:.2f} {high:.2f}V{low:.2f} M{x:.2f} {opened:.2f}V{closed:.2f}" stroke="{color}" stroke-width="3"/>')
    for values, color in [(snapshot.ema21_points, '#57a6ff'), (snapshot.ema9_points, '#46d8a3')]:
        points = ' '.join(f'{x:.2f},{y:.2f}' for x, y in (point(i,v) for i,v in enumerate(values)))
        pieces.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>')
    start, end = len(snapshot.ema9_points)-3, len(snapshot.ema9_points)-1
    a, b = point(start,snapshot.ema9_points[start]), point(end,snapshot.ema9_points[end])
    pieces.append(f'<path d="M{a[0]:.2f} {a[1]:.2f}L{b[0]:.2f} {b[1]:.2f}" stroke="#f2c66f" stroke-width="4"/>')
    for i in (0, len(snapshot.candles)//2, len(snapshot.candles)-1):
        x, _ = point(i,snapshot.candles[i].close)
        label = snapshot.candles[i].time.strftime('%d %b %H:%M')
        pieces.append(f'<text x="{x:.2f}" y="500" text-anchor="middle" fill="#91a4bc">{label}</text>')
    pieces.append('</svg>')
    return ''.join(pieces)


def render_html():
    """Standalone offline sheet uses exactly the desktop's sample records."""
    data = sample_data()
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
             '<title>Trend Chaser Nifty Midcap 50 — Demo</title>',
             '<style>body{margin:0;background:#101925;color:#e6edf5;font:14px "Segoe UI",sans-serif}main{max-width:1360px;margin:auto;padding:30px}h1{font-size:28px;margin:0}p{color:#91a4bc}h2{font-size:19px;margin:24px 0 10px}.bull{color:#46d8a3}.bear{color:#ff8190}.label{color:#f2c66f;font-size:20px;font-weight:700}.panels{display:grid;grid-template-columns:1fr 1fr;gap:16px}.table{overflow:auto}h2{margin-top:12px}table{border-collapse:collapse;width:100%;background:#172334;white-space:nowrap}th{background:#21324a;color:#91a4bc;font-size:12px}td,th{text-align:center;padding:10px 5px;border-bottom:1px solid #25344a}.pill{font-size:11px;border:1px solid #45566e;border-radius:4px;padding:4px 7px}details{margin-top:20px}summary{cursor:pointer;color:#57a6ff;padding:12px 0}select{background:#172334;color:#e6edf5;padding:8px;border:1px solid #45566e}svg{width:100%;max-height:360px;background:#172334;margin-top:12px}.chart[hidden]{display:none}footer{margin-top:20px;color:#91a4bc}</style>',
             f'<main><h1>TREND CHASER NIFTY MIDCAP 50 <small>· {VERSION}</small></h1>',
             '<p>9 / 21 · Nifty Midcap 50 shares · 5 MIN · Offline visual demo</p>',
             f'<div class="label">{LABEL}</div><p>{DISCLAIMER}</p>']
    parts.append('<div class="panels">')
    for side, rows in [('BULLISH',data['trends_long']),('BEARISH',data['trends_short'])]:
        color='bull' if side=='BULLISH' else 'bear'
        parts.extend([f'<section><h2 class="{color}">TOP 7 {side}</h2><div class="table"><table><thead><tr>',
                      ''.join(f'<th>{escape(col)}</th>' for col in TREND_COLUMNS),'</tr></thead><tbody>'])
        for rank,row in enumerate(rows,1):
            values=(rank,row.symbol,row.status,f'{row.crossover_angle:+.2f}°',f'{row.current_angle:+.2f}°',
                    f'{row.price:.2f}',row.crossover_time.strftime('%H:%M:%S'))
            parts.append(f'<tr class="{color}">'+''.join(f'<td>{escape(str(value))}</td>' for value in values)+'</tr>')
        parts.append('</tbody></table></div></section>')
    parts.append('</div>')
    parts.append('<p>Rank freezes crossover angle strength; current angle changes independently. Provisional entries await completed-candle verification.</p>')
    parts.append('<details><summary>Show Chart · sample reference chart</summary><label>Sample share <select id="pick">')
    for i,row in enumerate(data['rows']):
        parts.append(f'<option value="{i}">{escape(row.symbol)}</option>')
    parts.append('</select></label><p>Fixed 2:1 plot · green EMA9 / blue EMA21 · gold measured chord · times IST</p>')
    for i,row in enumerate(data['rows']):
        parts.append(f'<div class="chart" id="chart-{i}"'+(' hidden' if i else '')+'>'+_chart_svg(row)+'</div>')
    parts.append('</details><footer>Sample only. No broker connection, token, live alerts, saved membership, or orders.</footer></main><script>document.getElementById("pick").addEventListener("change",function(){document.querySelectorAll(".chart").forEach((chart,i)=>{chart.hidden=i!==Number(this.value)})});</script></html>\n')
    return ''.join(parts)
