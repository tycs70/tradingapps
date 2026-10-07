"""Build the Nifty Midcap 50 variant using a verified release's runtime and wheels.

Run from the source application directory with a clean, extracted base bundle.
No runtime downloads or dependency changes are performed.
"""
import argparse
import json
from pathlib import Path
import shutil
import tempfile
import zipfile

from tools.build_release import (ROOT, VERSION, RUNTIME_HASH, add_zip_file, build_lock,
                                 digest, manifest_for, validate_wheels, verify_tree)


def repackage(base: Path, output_folder: Path) -> Path:
    base=base.resolve()
    verify_tree(base)
    provenance=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
    if provenance['runtime_source_sha256']!=RUNTIME_HASH:
        raise ValueError('Base bundle does not use the pinned Windows runtime.')
    records=validate_wheels(base/'wheels')
    lock=build_lock(records)
    if (base/'requirements-windows.lock.txt').read_text(encoding='utf-8')!=lock:
        raise ValueError('Base Windows wheels differ from their hash-locked requirements.')
    release_name=f'Trend_Chaser_Nifty_Midcap_50_{VERSION}'
    output_folder.mkdir(parents=True,exist_ok=True)
    output=output_folder/f'{release_name}_Windows_x64.zip'
    with tempfile.TemporaryDirectory(prefix='trend-chase-release-') as temporary:
        release=Path(temporary)/release_name
        app=release/'app';app.mkdir(parents=True)
        for folder in ('ema_scanner','tests','tools','docs','installer','assets'):
            shutil.copytree(ROOT/folder,app/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        for name in ('run_app.pyw','verify_install.py','requirements.txt','requirements.lock.txt','README.md','demo.html','demo.png'):
            shutil.copy2(ROOT/name,app/name)
        for name in ('INSTALL.bat','install.ps1','uninstall.ps1','common.ps1'):
            text=(ROOT/'installer'/name).read_text(encoding='utf-8-sig').replace('\r\n','\n').replace('\n','\r\n')
            (release/name).write_bytes(text.encode('utf-8-sig' if name.endswith('.ps1') else 'utf-8'))
        for name in ('README_FIRST.txt','demo.html','demo.png'):
            shutil.copy2(ROOT/name,release/name)
        shutil.copytree(base/'wheels',release/'wheels')
        shutil.copy2(base/'runtime.zip',release/'runtime.zip')
        if digest(release/'runtime.zip')!=provenance['files']['runtime.zip']:
            raise ValueError('Bundled runtime changed during copy.')
        (release/'requirements-windows.lock.txt').write_text(lock,encoding='utf-8')
        (release/'manifest.json').write_text(json.dumps(manifest_for(release),indent=2),encoding='utf-8')
        verify_tree(release)
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for path in sorted(release.rglob('*')):
                if path.is_file():
                    add_zip_file(archive,release_name+'/'+path.relative_to(release).as_posix(),path.read_bytes())
    output.with_suffix('.zip.sha256').write_text(digest(output)+'  '+output.name+'\n',encoding='utf-8')
    print(json.dumps({'file':str(output),'bytes':output.stat().st_size,'sha256':digest(output),
                      'runtime_and_wheels':'unchanged from verified base bundle'},indent=2))
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'dist')
    args=parser.parse_args()
    repackage(args.base,args.output)
