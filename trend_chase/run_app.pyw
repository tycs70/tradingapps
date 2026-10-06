"""Private-runtime Windows entry point; no network until the user connects."""
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
runtime=Path(sys.executable).resolve().parent
if (runtime/'tcl'/'tcl8.6').exists():
    os.environ['TCL_LIBRARY']=str(runtime/'tcl'/'tcl8.6')
    os.environ['TK_LIBRARY']=str(runtime/'tcl'/'tk8.6')


def main():
    import tkinter as tk
    from tkinter import messagebox
    from ema_scanner.storage import data_directory, SettingsStore, InstanceLock, EventLogger
    from ema_scanner.scanner import Scanner
    from ema_scanner.ui import App
    data=data_directory();data.mkdir(parents=True,exist_ok=True)
    lock=InstanceLock(data/'instance.lock')
    if not lock.acquire():
        root=tk.Tk();root.withdraw()
        messagebox.showinfo('EMA Pre-Cross Scanner','The app is already running. Check the taskbar.',parent=root)
        root.destroy();return
    scanner=None
    try:
        root=tk.Tk()
        def safe_error(exc_type,exc,tb):
            (data/'startup-error.txt').write_text('GUI error: '+exc_type.__name__,encoding='utf-8')
            messagebox.showerror('EMA Pre-Cross Scanner','A desktop error occurred. Restart the app; see data/startup-error.txt.',parent=root)
        root.report_callback_exception=safe_error
        store=SettingsStore(data/'settings.json')
        scanner=Scanner(store.load(),logger=EventLogger(data/'logs'))
        app=App(root,scanner,store)
        root.mainloop()
    except Exception as exc:
        (data/'startup-error.txt').write_text('Startup error: '+type(exc).__name__,encoding='utf-8')
        try:messagebox.showerror('EMA Pre-Cross Scanner','Startup failed. See data/startup-error.txt or reinstall the app.')
        except Exception:pass
        raise SystemExit(1) from None
    finally:
        if scanner:scanner.close()
        lock.release()


if __name__=='__main__':main()
