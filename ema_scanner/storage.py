"""Whitelisted preferences, asynchronous event logs and an OS-held instance lock."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import queue
import threading

from .models import Settings


def data_directory() -> Path:
    base = Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'.local/share')))
    return base/'EMA_PreCross_Scanner'/'data'


class SettingsStore:
    def __init__(self,path: Path): self.path=Path(path)

    def load(self) -> Settings:
        try:
            obj=json.loads(self.path.read_text(encoding='utf-8'))
            names=asdict(Settings())
            return Settings(**{k:obj[k] for k in names if k in obj})
        except (OSError,ValueError,TypeError,KeyError): return Settings()

    def save(self,settings: Settings):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(asdict(settings),indent=2),encoding='utf-8')
        os.replace(temp,self.path)


class InstanceLock:
    def __init__(self,path: Path): self.path,self.file=Path(path),None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True,exist_ok=True)
        file=self.path.open('a+b')
        if file.tell()==0:
            file.write(b'0'); file.flush()
        file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            file.close();return False
        self.file=file;return True

    def release(self):
        if self.file:
            if os.name=='nt':
                import msvcrt
                self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_UN)
            self.file.close();self.file=None


class EventLogger:
    def __init__(self,directory: Path):
        self.directory=Path(directory)
        self.queue=queue.SimpleQueue()
        self.thread=threading.Thread(target=self._run,name='event-log',daemon=True)
        self.thread.start()

    def write(self,event):
        # Events contain only generated reasons and public market data.
        self.queue.put(event)

    def _run(self):
        while True:
            event=self.queue.get()
            if event is None: return
            try:
                self.directory.mkdir(parents=True,exist_ok=True)
                record=asdict(event)
                record['time']=event.time.isoformat()
                path=self.directory/('events-'+event.time.strftime('%Y-%m-%d')+'.jsonl')
                with path.open('a',encoding='utf-8') as file: file.write(json.dumps(record)+'\n')
            except OSError:
                pass

    def close(self):
        self.queue.put(None)
        self.thread.join(timeout=2)
