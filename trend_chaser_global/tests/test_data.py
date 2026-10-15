from datetime import datetime, timedelta
from global_trend.models import Candle, IST
NOW = datetime(2026,10,5,10,30,tzinfo=IST)
def session(day, count=75):
    start=NOW.replace(day=day,hour=9,minute=15)
    return [Candle(t,100,101,99,100.5,10) for t in (start+timedelta(minutes=5*i) for i in range(count))]
