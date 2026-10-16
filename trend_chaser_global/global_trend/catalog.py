"""Explicit cross-platform names; broker IDs are discovered, never guessed."""
from dataclasses import dataclass
import re

GROUPS=('Indices','Forex','Shares')


@dataclass(frozen=True)
class CatalogEntry:
    key:str
    group:str
    olymp_name:str
    ctrader_name:str
    verified:bool=False


@dataclass(frozen=True)
class ResolvedAsset:
    entry:CatalogEntry
    symbol_id:int
    digits:int=5
    schedule:object=None


def default_catalog():
    rows=[('SP500','Indices','S&P 500','US 500',True),
          ('DOW30','Indices','Dow Jones','US 30',True),
          ('NASDAQ','Indices','NASDAQ','US TECH 100',False)]
    rows.extend((pair,'Forex',pair[:3]+'/'+pair[3:],pair,False) for pair in
                ('EURUSD','GBPUSD','USDJPY','USDCHF','AUDUSD','USDCAD','NZDUSD','EURJPY','GBPJPY','EURGBP'))
    rows.extend((key,'Shares',name,broker,True) for key,name,broker in
                [('AAPL','Apple','APPLE'),('CAT','Caterpillar','CATERPILLAR'),
                 ('MA','MasterCard','MASTERCARD'),('BA','Boeing','BOEING'),
                 ('XOM','Exxon Mobil','EXXON'),('WMT','Walmart','WAL-MART'),
                 ('GS','Goldman Sachs','GOLDMAN SACHS')])
    return tuple(CatalogEntry(*r) for r in rows)


def normalized(value):
    return re.sub('[^A-Z0-9]','',str(value).upper())


def resolve_catalog(entries,symbols):
    result=[];reasons={}
    for entry in entries:
        hits={int(s['symbolId']):s for s in symbols
              if s.get('enabled',True) and normalized(s.get('symbolName',''))==normalized(entry.ctrader_name)}
        if len(hits)==1:
            result.append(ResolvedAsset(entry,next(iter(hits))))
        else:
            reasons[entry.key]='Not offered by this account' if not hits else 'Ambiguous symbol; select a mapping'
    return result,reasons
