"""Reproduce message classes from pinned, hash-verified Spotware schemas."""
from pathlib import Path
import hashlib
import json
import re
from grpc_tools import protoc

ROOT=Path(__file__).resolve().parents[1]/'global_trend'/'protocol'


def generate():
    records=json.loads((ROOT/'PROVENANCE.json').read_text())['sha256']
    for name,expected in records.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Protocol source checksum mismatch: '+name)
    result=protoc.main(['protoc','-I'+str(ROOT),'--python_out='+str(ROOT),
                        *[str(ROOT/name) for name in records]])
    if result:raise RuntimeError('Protocol generation failed.')
    for path in ROOT.glob('*_pb2.py'):
        text=path.read_text()
        text=re.sub(r'^import (OpenApi\w+_pb2) as ',r'from . import \1 as ',text,flags=re.M)
        path.write_text(text)
    print('Generated four verified Spotware protocol modules.')


if __name__=='__main__':generate()
