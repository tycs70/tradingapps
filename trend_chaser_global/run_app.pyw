"""Standalone entry point; --demo never accesses live user storage."""
from pathlib import Path
import argparse,tempfile,tkinter as tk
from tkinter import messagebox
from global_trend.credentials import CredentialStore
from global_trend.storage import data_directory,SettingsStore,TrendStore,EventLogger,InstanceLock
from global_trend.engine import Engine
from global_trend.ui import App
from global_trend.demo import DemoEngine

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--demo',action='store_true')
    parser.add_argument('--smoke-seconds',type=float,default=0,help=argparse.SUPPRESS)
    args=parser.parse_args();temporary=tempfile.TemporaryDirectory() if args.demo else None
    base=Path(temporary.name) if temporary else data_directory();lock=None;engine=None
    root=tk.Tk()
    try:
        if not args.demo:
            lock=InstanceLock(base/'global.lock')
            if not lock.acquire():messagebox.showinfo('Trend Chaser Global','Trend Chaser Global is already running.');return
        settings=SettingsStore(base/'settings.json')
        engine=DemoEngine() if args.demo else Engine(settings.load(),EventLogger(base/'events'),TrendStore(base/'trends.json'))
        app=App(root,engine,settings,CredentialStore(base/'credentials.dpapi'),demo=args.demo)
        if args.smoke_seconds:root.after(int(args.smoke_seconds*1000),app.close)
        root.mainloop()
    finally:
        if engine:engine.close()
        if lock:lock.release()
        if temporary:temporary.cleanup()

if __name__=='__main__':main()
