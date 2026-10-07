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
    return base/'Trend_Chaser_Nifty_50'/'data'


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
                if event.candle_time is not None:
                    record['candle_time']=event.candle_time.isoformat()
                path=self.directory/('events-'+event.time.strftime('%Y-%m-%d')+'.jsonl')
                with path.open('a',encoding='utf-8') as file: file.write(json.dumps(record)+'\n')
            except OSError:
                pass

    def close(self):
        self.queue.put(None)
        self.thread.join(timeout=2)


class TrendStore:
    """Confirmed-only atomic snapshots written by a dedicated file worker.

    load(day) is for startup, outside the signal worker. save(candidates, day)
    captures an immutable value immediately and queues it without touching disk.
    flush() is for shutdown/tests, never for the quote path.
    """
    def __init__(self, path: Path):
        self.path = Path(path)
        self.queue = queue.Queue()
        self.error = ''
        self._closed = False
        self._close_lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, name='trend-store', daemon=True)
        self.thread.start()

    def load(self, day):
        from datetime import datetime
        import math
        from .history import regular_session
        from .models import IST, bucket_time
        from .trends import TrendCandidate
        try:
            obj = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(obj,dict) or obj.get('version') != 1 or obj.get('day') != day.isoformat(): return []
            rows = obj['candidates']
            if not isinstance(rows,list): return []
            result = []
            keys = set()
            names = {'key','symbol','side','crossover_time','crossover_angle','status','checked_through'}
            for row in rows:
                if not isinstance(row,dict) or set(row) != names: return []
                values = dict(row)
                for field in ('crossover_time','checked_through'):
                    values[field] = datetime.fromisoformat(values[field])
                    if values[field].tzinfo is None or values[field].astimezone(IST).date() != day: return []
                c = TrendCandidate(**values)
                if (not isinstance(c.key,str) or not c.key or c.key in keys or
                        not isinstance(c.symbol,str) or not c.symbol or c.side not in ('LONG','SHORT') or
                        c.status != 'CONFIRMED' or isinstance(c.crossover_angle,bool) or
                        not isinstance(c.crossover_angle,(int,float)) or
                        not math.isfinite(c.crossover_angle) or c.strength <= 0 or
                        c.checked_through != bucket_time(c.checked_through) or
                        c.checked_through < bucket_time(c.crossover_time) or
                        not regular_session(c.crossover_time) or not regular_session(c.checked_through)):
                    return []
                keys.add(c.key);result.append(c)
            return result
        except (OSError,ValueError,TypeError,KeyError,OverflowError):
            return []

    def save(self, candidates, day):
        from .models import IST
        # Keep accepted saves ahead of the shutdown sentinel, even if a caller
        # begins closing while the signal worker queues its final snapshot.
        with self._close_lock:
            if self._closed: return
            snapshot = tuple(c for c in candidates if c.status == 'CONFIRMED' and
                             c.crossover_time.astimezone(IST).date() == day)
            self.queue.put((snapshot,day))

    def _run(self):
        while True:
            item = self.queue.get()
            try:
                if item is None: return
                candidates, day = item
                rows = []
                for c in candidates:
                    row = asdict(c)
                    row['crossover_time'] = c.crossover_time.isoformat()
                    row['checked_through'] = c.checked_through.isoformat()
                    rows.append(row)
                self.path.parent.mkdir(parents=True,exist_ok=True)
                temp = self.path.with_suffix(self.path.suffix+'.tmp')
                temp.write_text(json.dumps({'version':1,'day':day.isoformat(),'candidates':rows},allow_nan=False),encoding='utf-8')
                os.replace(temp,self.path)
                self.error = ''
            except (OSError,ValueError,TypeError):
                self.error = 'Unable to save confirmed trend state.'
            finally:
                self.queue.task_done()

    def flush(self):
        self.queue.join()

    def close(self):
        # Called during shutdown, outside the serialized quote path. A closed
        # queue can still have pending writes: every caller waits for its worker.
        with self._close_lock:
            if not self._closed:
                self._closed = True
                self.queue.put(None)
        self.thread.join()
