"""Build the fully offline Windows ZIP from an authenticated runtime and wheel cache."""
import argparse
from email.parser import Parser
import hashlib
import json
import ntpath
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
RUNTIME_HASH='6fba7f2ae506facf41d457ea8293c7497910a675c69a4e954875169410a50402'
RUNTIME_URL='https://github.com/astral-sh/python-build-standalone/releases/download/20261003/cpython-3.12.15%2B20261003-x86_64-pc-windows-msvc-install_only_stripped.tar.gz'
PINS={'certifi':'2026.7.22','charset-normalizer':'3.5.2','idna':'3.20','protobuf':'7.36.2',
      'python-dateutil':'2.9.0.post0','requests':'2.32.5','six':'1.17.0','tzdata':'2025.2',
      'upstox-python-sdk':'2.23.0','urllib3':'2.8.0','uuid':'1.30','websocket-client':'1.9.2'}


def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda:file.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def safe_relative(value: str) -> str:
    if (not value or '\\' in value or ':' in value or ntpath.splitdrive(value)[0] or
            value.startswith('/') or any(p in ('','..','.') for p in value.split('/'))):
        raise ValueError('Unsafe package path.')
    return value


def manifest_for(root: Path) -> dict:
    return {'version':'1.0.0','runtime_source_sha256':RUNTIME_HASH,'runtime_source_url':RUNTIME_URL,
            'files':{safe_relative(p.relative_to(root).as_posix()):digest(p)
                     for p in sorted(root.rglob('*')) if p.is_file() and p.name!='manifest.json'}}


def verify_tree(root: Path):
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    files=manifest['files']
    for rel,sha in files.items():
        safe_relative(rel)
        path=root/rel
        if not path.is_file():raise ValueError('missing package file: '+rel)
        if digest(path)!=sha:raise ValueError('hash mismatch: '+rel)
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name!='manifest.json'}
    if actual-set(files):raise ValueError('unexpected package files')


def validate_wheels(folder: Path) -> list[dict]:
    records=[]
    for path in sorted(folder.glob('*.whl')):
        if not (path.name.endswith('-none-any.whl') or path.name.endswith('-win_amd64.whl')):
            raise ValueError('Not a compatible Windows x64 wheel: '+path.name)
        with zipfile.ZipFile(path) as wheel:
            name=next(n for n in wheel.namelist() if n.endswith('.dist-info/METADATA'))
            meta=Parser().parsestr(wheel.read(name).decode('utf-8'))
        pkg=meta['Name'].lower().replace('_','-')
        if PINS.get(pkg)!=meta['Version']:raise ValueError('Unexpected wheel version: '+pkg)
        records.append({'name':pkg,'version':meta['Version'],'file':path.name,'sha':digest(path)})
    if {r['name'] for r in records}!=set(PINS) or len(records)!=len(PINS):
        raise ValueError('Missing or duplicate pinned dependencies.')
    return records


def build_lock(records) -> str:
    return ''.join(f"{r['name']}=={r['version']} --hash=sha256:{r['sha']}\n" for r in records)


def add_zip_file(zipper,rel,data):
    info=zipfile.ZipInfo(safe_relative(rel),(2026,10,5,0,0,0))
    info.compress_type=zipfile.ZIP_DEFLATED
    info.external_attr=0o644<<16
    zipper.writestr(info,data)


def runtime_zip(archive: Path,output: Path):
    if digest(archive)!=RUNTIME_HASH:raise ValueError('Runtime source SHA-256 mismatch.')
    names=set()
    with tarfile.open(archive) as source,zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as target:
        for member in source:
            if member.isdir():continue
            if not member.isfile() or not member.name.startswith('python/'):
                raise ValueError('Unexpected runtime archive entry.')
            rel=member.name[len('python/'):]
            names.add(rel)
            add_zip_file(target,rel,source.extractfile(member).read())
    required={'python.exe','pythonw.exe','python312.dll','DLLs/_tkinter.pyd','tcl/tcl8.6/init.tcl','tcl/tk8.6/tk.tcl','Lib/site-packages/pip/__init__.py'}
    if not required<=names:raise ValueError('Runtime lacks Python, pip or Tcl/Tk.')


def build(archive: Path) -> Path:
    wheels=ROOT/'build'/'wheels';records=validate_wheels(wheels)
    destination=ROOT/'build'/'release'/'EMA_PreCross_Scanner_1.0.0'
    if destination.exists():shutil.rmtree(destination)
    destination.mkdir(parents=True)
    app=destination/'app';app.mkdir()
    for folder in ['ema_scanner','tests','tools','docs','installer']:
        shutil.copytree(ROOT/folder,app/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ['run_app.pyw','verify_install.py','requirements.txt','requirements.lock.txt','README.md']:
        shutil.copy2(ROOT/name,app/name)
    for name in ['INSTALL.bat','install.ps1','uninstall.ps1','common.ps1']:
        raw=(ROOT/'installer'/name).read_text(encoding='utf-8').replace('\r\n','\n').replace('\n','\r\n')
        (destination/name).write_bytes(raw.encode('utf-8-sig' if name.endswith('.ps1') else 'utf-8'))
    shutil.copy2(ROOT/'README_FIRST.txt',destination/'README_FIRST.txt')
    shutil.copytree(wheels,destination/'wheels',ignore=shutil.ignore_patterns('*.log'))
    (destination/'requirements-windows.lock.txt').write_text(build_lock(records),encoding='utf-8')
    runtime_zip(archive,destination/'runtime.zip')
    (destination/'manifest.json').write_text(json.dumps(manifest_for(destination),indent=2),encoding='utf-8')
    verify_tree(destination)
    dist=ROOT/'dist';dist.mkdir(exist_ok=True)
    output=dist/'EMA_PreCross_Scanner_1.0.0_Windows_x64.zip'
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as zip:
        for path in sorted(destination.rglob('*')):
            if path.is_file():add_zip_file(zip,'EMA_PreCross_Scanner_1.0.0/'+path.relative_to(destination).as_posix(),path.read_bytes())
    (output.with_suffix('.zip.sha256')).write_text(digest(output)+'  '+output.name+'\n',encoding='utf-8')
    print(json.dumps({'file':str(output),'bytes':output.stat().st_size,'sha256':digest(output),'verified_files':len(manifest_for(destination)['files'])},indent=2))
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path);parser.add_argument('--verify',type=Path)
    args=parser.parse_args()
    if args.verify:verify_tree(args.verify);print('All packaged file hashes verified.')
    elif args.runtime:build(args.runtime)
    else:parser.error('--runtime ARCHIVE or --verify FOLDER required')
