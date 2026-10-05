"""Resolve current stock OPTION contracts to their underlying NSE equity keys."""
from datetime import date, datetime

from .models import IST, Instrument


def expiry_date(value) -> date:
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        return datetime.fromtimestamp(float(value)/1000, IST).date()
    return date.fromisoformat(str(value)[:10])


def eligible_stocks(master: list[dict], today: date) -> tuple[list[Instrument], list[str]]:
    equities = {r.get('instrument_key'): r for r in master
                if r.get('segment') == 'NSE_EQ' and r.get('instrument_type') == 'EQ'}
    found, reasons = {}, set()
    for row in master:
        if (row.get('segment') != 'NSE_FO' or row.get('instrument_type') not in ('CE','PE') or
                row.get('underlying_type') != 'EQUITY'):
            continue
        try:
            if expiry_date(row['expiry']) < today:
                continue
        except (KeyError, ValueError, TypeError, OSError, OverflowError):
            reasons.add('Excluded option with invalid expiry.')
            continue
        key = row.get('underlying_key')
        equity = equities.get(key)
        if not equity:
            reasons.add(f"Excluded unresolved option underlying: {row.get('underlying_symbol','unknown')}.")
            continue
        symbol = row.get('underlying_symbol') or equity.get('trading_symbol')
        if key and symbol:
            found[key] = Instrument(str(symbol), str(key), str(equity.get('name','')))
    return sorted(found.values(), key=lambda i: i.symbol), sorted(reasons)
