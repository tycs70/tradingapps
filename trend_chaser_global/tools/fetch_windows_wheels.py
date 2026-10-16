"""Fetch only pinned Windows CPython 3.12 x64/universal wheels; verify lock hashes."""
from pathlib import Path
import hashlib,json,re,urllib.request
from tools.build_release import ROOT,PINS,validate_wheels

def fetch():
    destination=ROOT/'build/wheels';destination.mkdir(parents=True,exist_ok=True)
    trusted=set(re.findall(r'--hash=sha256:([a-f0-9]{64})',(ROOT/'requirements.lock.txt').read_text()))
    for name,version in PINS.items():
        with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{version}/json',timeout=30) as response:meta=json.load(response)
        eligible=[]
        for item in meta['urls']:
            filename=item['filename']
            if item['packagetype']!='bdist_wheel' or item['yanked']:continue
            tag=filename[:-4].rsplit('-',3)[-3:]
            py,abi,platform=tag
            compatible=(platform=='any' and abi=='none' and ('py3' in py.split('.')) or
                        platform=='win_amd64' and (py=='cp312' or abi=='abi3' and py in ('cp39','cp310','cp311','cp312')))
            if compatible:eligible.append(item)
        if not eligible:raise ValueError('No compatible trusted wheel for '+name)
        eligible.sort(key=lambda item:('cp312' not in item['filename'],not item['filename'].endswith('none-any.whl'),item['filename']))
        item=eligible[0];sha=item['digests']['sha256']
        if sha not in trusted:raise ValueError('PyPI hash not in dependency lock for '+name)
        with urllib.request.urlopen(item['url'],timeout=60) as response:data=response.read()
        if hashlib.sha256(data).hexdigest()!=sha:raise ValueError('Download hash mismatch.')
        (destination/item['filename']).write_bytes(data)
        print(item['filename'])
    validate_wheels(destination)

if __name__=='__main__':fetch()
