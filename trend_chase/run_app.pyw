"""Private-runtime Windows entry point; --demo never creates live services."""
import argparse
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
runtime=Path(sys.executable).resolve().parent
if (runtime/'tcl'/'tcl8.6').exists():
    os.environ['TCL_LIBRARY']=str(runtime/'tcl'/'tcl8.6')
    os.environ['TK_LIBRARY']=str(runtime/'tcl'/'tk8.6')


def main(argv=None):
    parser=argparse.ArgumentParser(description='Trend Chase Version 1')
    parser.add_argument('--demo',action='store_true',help='Open offline sample data without broker or token access')
    args=parser.parse_args(argv)
    import tkinter as tk
    from tkinter import messagebox
    from ema_scanner.storage import data_directory, SettingsStore, InstanceLock, EventLogger, TrendStore
    from ema_scanner.scanner import Scanner
    from ema_scanner.demo import OfflineScanner
    from ema_scanner.ui import App
    data=data_directory()
    lock=None;scanner=None;logger=None;trend_store=None;root=None
    def record_error(label,exc_type):
        # Generated label and exception type only: broker bodies/token values never logged.
        try:
            data.mkdir(parents=True,exist_ok=True)
            (data/'startup-error.txt').write_text(label+': '+exc_type.__name__,encoding='utf-8')
        except OSError:pass
    try:
        if not args.demo:
            data.mkdir(parents=True,exist_ok=True)
            lock=InstanceLock(data/'instance.lock')
            if not lock.acquire():
                root=tk.Tk();root.withdraw()
                messagebox.showinfo('Trend Chase Version 1','The app is already running. Check the taskbar.',parent=root)
                return
        root=tk.Tk()
        def safe_error(exc_type,exc,tb):
            record_error('GUI error',exc_type)
            try:
                messagebox.showerror('Trend Chase Version 1','A desktop error occurred. Restart the app; see data/startup-error.txt.',parent=root)
            except Exception:pass
        root.report_callback_exception=safe_error
        store=SettingsStore(data/'settings.json')
        if args.demo:
            scanner=OfflineScanner()
        else:
            logger=EventLogger(data/'logs')
            trend_store=TrendStore(data/'trends.json')
            scanner=Scanner(store.load(),logger=logger,trend_store=trend_store)
        App(root,scanner,store,demo_mode=args.demo)
        root.mainloop()
    except Exception as exc:
        record_error('Startup error',type(exc))
        try:messagebox.showerror('Trend Chase Version 1','Startup failed. See data/startup-error.txt or reinstall the app.',parent=root)
        except Exception:pass
        raise SystemExit(1) from None
    finally:
        if scanner:scanner.close()
        else:
            if logger:logger.close()
            if trend_store:trend_store.close()
        if root:
            try:root.destroy()
            except tk.TclError:pass
        if lock:lock.release()


if __name__=='__main__':main()
