"""Current Nifty 50 membership boundary; signal and ranking rules are unchanged."""
import csv
import io
import re
from datetime import date

from .models import Instrument
from .universe import eligible_stocks

NIFTY50_URL = 'https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv'


def parse_constituents(text: str) -> dict[str, str]:
    """Return ISIN -> current NSE symbol from the official constituent CSV."""
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff')), strict=True)
    try:
        rows = list(reader)
    except csv.Error:
        raise ValueError('The Nifty 50 constituent CSV is malformed.') from None
    if not reader.fieldnames or not {'Symbol', 'Series', 'ISIN Code'} <= set(reader.fieldnames):
        raise ValueError('Nifty 50 constituent columns are missing.')
    members = {}
    symbols = set()
    for row in rows:
        symbol = (row.get('Symbol') or '').strip()
        isin = (row.get('ISIN Code') or '').strip()
        if ((row.get('Series') or '').strip() != 'EQ'
                or not re.fullmatch(r'[A-Z0-9&._-]+', symbol)
                or not re.fullmatch(r'INE[A-Z0-9]{9}', isin)
                or isin in members or symbol in symbols):
            raise ValueError('Nifty 50 constituent rows are invalid or duplicated.')
        members[isin] = symbol
        symbols.add(symbol)
    if len(members) != 50:
        raise ValueError('The current Nifty 50 constituent list must contain 50 shares.')
    return members


def select_nifty50(master: list[dict], today: date,
                   members: dict[str, str]) -> tuple[list[Instrument], list[str]]:
    """Intersect existing option eligibility with index membership by ISIN."""
    eligible, reasons = eligible_stocks(master, today)
    equities = {row.get('instrument_key'): row for row in master
                if row.get('segment') == 'NSE_EQ' and row.get('instrument_type') == 'EQ'}
    selected = {}
    for stock in eligible:
        equity = equities[stock.key]
        isin = equity.get('isin') or stock.key.partition('|')[2]
        if isin in members:
            selected[isin] = Instrument(members[isin], stock.key, stock.name)
    reasons += [f'Nifty 50 member {symbol} has no current stock-option contract.'
                for isin, symbol in members.items() if isin not in selected]
    return sorted(selected.values(), key=lambda stock: stock.symbol), sorted(set(reasons))
