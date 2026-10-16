"""Build the fully offline Windows ZIP from an authenticated runtime and wheel cache."""
import argparse
from email.parser import Parser
import hashlib
import json
import ntpath
from pathlib import Path, PurePosixPath
import shutil
import zipfile
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from global_trend import VERSION
RUNTIME_HASH='6fba7f2ae506facf41d457ea8293c7497910a675c69a4e954875169410a50402'
RUNTIME_URL='https://github.com/astral-sh/python-build-standalone/releases/download/20261003/cpython-3.12.15%2B20261003-x86_64-pc-windows-msvc-install_only_stripped.tar.gz'
PINS={'certifi':'2026.7.22','charset-normalizer':'3.5.2','idna':'3.20','protobuf':'7.36.2',
      'requests':'2.32.5','tzdata':'2025.2','urllib3':'2.8.0'}
REFERENCE_HASH='3167f252faad8c8b49e0d5d9a825f8b7753424585d93c479d87fbba270dbe687'
RUNTIME_ZIP_HASH='25feb75f1ec939422826f7ad3693a75fe47222662853af8441b46080eb0c756d'


def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as file:
        for block in iter(lambda:file.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def safe_relative(value: str) -> str:
    if (not value or '\\' in value or ':' in value or ntpath.splitdrive(value)[0] or
            value.startswith('/') or any(p in ('','..','.') or p.endswith((' ','.')) or
              re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',p) for p in value.split('/'))):
        raise ValueError('Unsafe package path.')
    return value


def manifest_for(root: Path) -> dict:
    if any(p.is_symlink() for p in root.rglob('*')):raise ValueError('Symlinks are not permitted in packages.')
    return {'version':VERSION,'runtime_source_sha256':RUNTIME_HASH,'runtime_source_url':RUNTIME_URL,
            'files':{safe_relative(p.relative_to(root).as_posix()):digest(p)
                     for p in sorted(root.rglob('*')) if p.is_file() and p!=root/'manifest.json'}}


def verify_tree(root: Path):
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    files=manifest['files']
    for rel,sha in files.items():
        safe_relative(rel)
        path=root/rel
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):raise ValueError('Unsafe package path.')
        if not path.is_file():raise ValueError('missing package file: '+rel)
        if digest(path)!=sha:raise ValueError('hash mismatch: '+rel)
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p!=root/'manifest.json'}
    if actual-set(files):raise ValueError('unexpected package files')


def validate_wheels(folder: Path) -> list[dict]:
    records=[]
    trusted=set(re.findall(r'--hash=sha256:([a-f0-9]{64})',(ROOT/'requirements.lock.txt').read_text()))
    for path in sorted(folder.glob('*.whl')):
        if digest(path) not in trusted:raise ValueError('Wheel hash is not in the trusted dependency lock: '+path.name)
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
    info=zipfile.ZipInfo(safe_relative(rel),(2026,10,15,0,0,0))
    info.compress_type=zipfile.ZIP_DEFLATED
    info.external_attr=0o644<<16
    zipper.writestr(info,data)


def verify_reference(archive:Path):
    if digest(archive)!=REFERENCE_HASH:raise ValueError('Reference archive hash mismatch.')
    with zipfile.ZipFile(archive) as source:
        prefix='Trend_Chaser_Nifty_Next_50_1.0.2/'
        manifest=json.loads(source.read(prefix+'manifest.json'))
        expected={prefix+safe_relative(rel):sha for rel,sha in manifest['files'].items()}
        if len(source.namelist())!=len(set(source.namelist())):raise ValueError('Duplicate archive names.')
        actual={n for n in source.namelist() if not n.endswith('/') and n!=prefix+'manifest.json'}
        if actual!=set(expected):raise ValueError('Reference file manifest mismatch.')
        for name,sha in expected.items():
            if hashlib.sha256(source.read(name)).hexdigest()!=sha:raise ValueError('Reference file hash mismatch.')
        runtime=source.read(prefix+'runtime.zip')
    if hashlib.sha256(runtime).hexdigest()!=RUNTIME_ZIP_HASH:raise ValueError('Runtime hash mismatch.')
    return runtime


def runtime_zip(archive: Path,output: Path):
    output.write_bytes(verify_reference(archive))
    with zipfile.ZipFile(output) as runtime:
        names={safe_relative(n) for n in runtime.namelist() if not n.endswith('/')}
    required={'python.exe','pythonw.exe','python312.dll','DLLs/_tkinter.pyd','tcl/tcl8.6/init.tcl','tcl/tk8.6/tk.tcl','Lib/site-packages/pip/__init__.py'}
    if not required<=names:raise ValueError('Runtime lacks Python, pip or Tcl/Tk.')


def build(archive: Path) -> Path:
    wheels=ROOT/'build'/'wheels';records=validate_wheels(wheels)
    release_name=f'Trend_Chaser_Global_{VERSION}'
    destination=ROOT/'build'/'release'/release_name
    if destination.exists():shutil.rmtree(destination)
    destination.mkdir(parents=True)
    app=destination/'app';app.mkdir()
    for folder in ['global_trend','tests','tools','docs','installer','assets']:
        shutil.copytree(ROOT/folder,app/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ['run_app.pyw','verify_install.py','requirements.in','requirements.lock.txt','README.md']:
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
    output=dist/f'{release_name}_Windows_x64.zip'
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as zip:
        for path in sorted(destination.rglob('*')):
            if path.is_file():add_zip_file(zip,release_name+'/'+path.relative_to(destination).as_posix(),path.read_bytes())
    (output.with_suffix('.zip.sha256')).write_text(digest(output)+'  '+output.name+'\n',encoding='utf-8')
    print(json.dumps({'file':str(output),'bytes':output.stat().st_size,'sha256':digest(output),'verified_files':len(manifest_for(destination)['files'])},indent=2))
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path);parser.add_argument('--verify',type=Path)
    args=parser.parse_args()
    if args.verify:verify_tree(args.verify);print('All packaged file hashes verified.')
    elif args.runtime:build(args.runtime)
    else:parser.error('--runtime ARCHIVE or --verify FOLDER required')
