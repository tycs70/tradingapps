"""Current Nifty 50 membership boundary; signal and ranking rules are unchanged."""
import csv
import io
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import tempfile

from .models import Instrument, IST
from .universe import eligible_stocks

NIFTY50_URL = 'https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv'
MAX_CSV_BYTES = 256_000


@dataclass(frozen=True)
class ImportedConstituents:
    members: dict[str, str]
    imported_at: datetime

    def current(self, now: datetime) -> bool:
        return self.imported_at.astimezone(IST).date() == now.astimezone(IST).date()


class ConstituentStore:
    """A validated browser import, kept independently of rules and credentials."""
    def __init__(self, path):
        self.path = Path(path)

    def import_file(self, source, now=None):
        source = Path(source)
        if not re.fullmatch(r'ind_nifty50list(?: \(\d+\))?\.csv', source.name, re.IGNORECASE):
            raise ValueError('Choose the official Nifty 50 file ind_nifty50list.csv, not another index list.')
        with source.open('rb') as file:
            raw = file.read(MAX_CSV_BYTES+1)
        if len(raw) > MAX_CSV_BYTES:
            raise ValueError('The Nifty 50 CSV is too large. Download the official list again.')
        text = raw.decode('utf-8-sig')
        members = parse_constituents(text)
        stamp = (now or datetime.now(IST)).astimezone(IST)
        payload = {'index':'NIFTY50', 'imported_at':stamp.isoformat(), 'csv':text}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                             dir=self.path.parent, delete=False) as file:
                temporary = Path(file.name)
                json.dump(payload, file, ensure_ascii=False)
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return ImportedConstituents(members, stamp)

    def load(self):
        try:
            with self.path.open('rb') as file:
                raw = file.read(2*MAX_CSV_BYTES+1)
        except FileNotFoundError:
            return None
        try:
            if len(raw) > 2*MAX_CSV_BYTES:
                raise ValueError()
            obj = json.loads(raw)
            if obj['index'] != 'NIFTY50':
                raise ValueError()
            stamp = datetime.fromisoformat(obj['imported_at'])
            if stamp.tzinfo is None:
                raise ValueError()
            members = parse_constituents(obj['csv'])
            return ImportedConstituents(members, stamp.astimezone(IST))
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ValueError('The saved Nifty 50 CSV is invalid. Load a fresh official CSV.') from None

    def clear(self):
        self.path.unlink(missing_ok=True)


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
