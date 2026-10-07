import os
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
import importlib.machinery
import importlib.util
from unittest.mock import Mock, patch

from ema_scanner import demo
from ema_scanner.models import Settings
from ema_scanner.storage import SettingsStore
from ema_scanner.ui import App
from ema_scanner.strategy import qualification


class DemoDataTest(unittest.TestCase):
    def test_samples_and_standalone_sheet_match(self):
        data=demo.sample_data()
        self.assertEqual(len(data['trends_long']),7)
        self.assertEqual(len(data['trends_short']),7)
        self.assertGreater(len(data['armed']),0)
        self.assertFalse(data['connected'])
        self.assertEqual(data['events'],[])
        self.assertIn('DEMO — SAMPLE DATA',data['status'])
        html=Path('demo.html').read_text(encoding='utf-8')
        self.assertEqual(html,demo.render_html())
        for row in data['trends_long']+data['trends_short']:
            self.assertIn(row.symbol,html)
            self.assertTrue(row.snapshot.candles)

    def test_normal_samples_illustrate_qualifying_pre_cross_relationships(self):
        for row in demo.sample_data()['armed']:
            self.assertEqual(qualification(row,Settings()),row.side)


@unittest.skipUnless(os.environ.get('DISPLAY') or os.name=='nt','Requires display')
class DemoDesktopTest(unittest.TestCase):
    def entrypoint(self):
        loader=importlib.machinery.SourceFileLoader('trend_chase_entry',str(Path('run_app.pyw').resolve()))
        spec=importlib.util.spec_from_loader(loader.name,loader)
        module=importlib.util.module_from_spec(spec);loader.exec_module(module)
        return module

    def test_actual_demo_entrypoint_never_constructs_broker_or_live_store(self):
        entry=self.entrypoint()
        real_app=App
        def launch(root,scanner,store,**kwargs):
            app=real_app(root,scanner,store,**kwargs)
            root.after(80,app.close)
            return app
        with tempfile.TemporaryDirectory() as folder, patch('ema_scanner.storage.data_directory',return_value=Path(folder)), \
             patch('ema_scanner.scanner.Scanner',side_effect=AssertionError('Live scanner in demo')), \
             patch('ema_scanner.storage.TrendStore',side_effect=AssertionError('Live persistence in demo')), \
             patch('ema_scanner.storage.EventLogger',side_effect=AssertionError('Live logger in demo')), \
             patch('ema_scanner.ui.App',side_effect=launch):
            entry.main(['--demo'])
            self.assertEqual(list(Path(folder).iterdir()),[])

    def test_demo_startup_error_never_creates_or_overwrites_live_data(self):
        entry=self.entrypoint()
        for existing in (False,True):
            with self.subTest(existing=existing),tempfile.TemporaryDirectory() as folder:
                data=Path(folder)/'Trend_Chaser_Nifty_Next_50'/'data'
                error_file=data/'startup-error.txt'
                if existing:
                    data.mkdir(parents=True);error_file.write_text('Existing live diagnostic',encoding='utf-8')
                with patch('ema_scanner.storage.data_directory',return_value=data), \
                     patch('tkinter.Tk',side_effect=RuntimeError('private-token')), \
                     patch('tkinter.messagebox.showerror') as dialog:
                    with self.assertRaises(SystemExit) as raised:entry.main(['--demo'])
                    self.assertEqual(raised.exception.code,1)
                if existing:self.assertEqual(error_file.read_text(),'Existing live diagnostic')
                else:self.assertFalse(data.exists())
                self.assertNotIn('startup-error.txt',str(dialog.call_args))
                self.assertNotIn('private-token',str(dialog.call_args))

    def test_demo_callback_error_never_creates_or_overwrites_live_data(self):
        entry=self.entrypoint()
        def launch(root,scanner,store,**kwargs):
            app=App(root,scanner,store,**kwargs)
            def stop():
                root.report_callback_exception(ValueError,ValueError('private-token'),None)
                app.close()
            root.after(80,stop)
            return app
        for existing in (False,True):
            with self.subTest(existing=existing),tempfile.TemporaryDirectory() as folder:
                data=Path(folder)/'Trend_Chaser_Nifty_Next_50'/'data'
                error_file=data/'startup-error.txt'
                if existing:
                    data.mkdir(parents=True);error_file.write_text('Existing live diagnostic',encoding='utf-8')
                with patch('ema_scanner.storage.data_directory',return_value=data), \
                     patch('ema_scanner.ui.App',side_effect=launch),patch('tkinter.messagebox.showerror') as dialog:
                    entry.main(['--demo'])
                if existing:self.assertEqual(error_file.read_text(),'Existing live diagnostic')
                else:self.assertFalse(data.exists())
                self.assertNotIn('startup-error.txt',str(dialog.call_args))
                self.assertNotIn('private-token',str(dialog.call_args))

    def test_live_entrypoint_closes_real_workers_and_logs_safe_callback_type(self):
        entry=self.entrypoint();created=[]
        def launch(root,scanner,store,**kwargs):
            app=App(root,scanner,store,**kwargs);created.append(scanner)
            def stop():
                root.report_callback_exception(ValueError,ValueError('private-token'),None)
                app.close()
            root.after(80,stop)
            return app
        with tempfile.TemporaryDirectory() as folder, patch('ema_scanner.storage.data_directory',return_value=Path(folder)), \
             patch('ema_scanner.ui.App',side_effect=launch),patch('tkinter.messagebox.showerror'):
            entry.main([])
            scanner=created[0]
            self.assertFalse(scanner.thread.is_alive())
            self.assertFalse(scanner.logger.thread.is_alive())
            self.assertFalse(scanner.trend_store.thread.is_alive())
            self.assertEqual(scanner.trend_store.path,Path(folder)/'trends.json')
            text=(Path(folder)/'startup-error.txt').read_text()
            self.assertIn('ValueError',text);self.assertNotIn('private-token',text)

    def test_demo_is_offline_and_chart_selection_is_independent(self):
        with tempfile.TemporaryDirectory() as folder:
            root=tk.Tk();scanner=Mock();scanner.snapshot.return_value=demo.sample_data()
            store=SettingsStore(Path(folder)/'settings.json')
            token_store=Mock();token_store.available=True
            app=App(root,scanner,store,token_store=token_store,demo_mode=True)
            try:
                root.bell=Mock();root.update()
                self.assertEqual(app.tabs.select(),str(app.demo_tab))
                self.assertEqual(len(app.demo_bullish_board.get_children()),7)
                self.assertEqual(len(app.demo_bearish_board.get_children()),7)
                self.assertFalse(app.demo_show_chart.get())
                app.demo_show_chart.set(True);app.toggle_demo_chart();root.update()
                self.assertGreaterEqual(app.demo_canvas.winfo_height(),200,'Visible chart must retain usable height on the default window')
                app.demo_stock_pick.set('SAMPLE-SHORT-3');app._select_demo_pick();root.update()
                self.assertIn('SAMPLE-SHORT-3',app.demo_chart_title.get())
                self.assertEqual(len(app.demo_canvas.find_withtag('measured_chord')),1)
                app.connect();app.refresh()
                scanner.connect.assert_not_called();scanner.set_settings.assert_not_called()
                token_store.load.assert_not_called();token_store.save.assert_not_called();token_store.clear.assert_not_called()
                root.bell.assert_not_called()
                self.assertFalse(store.path.exists())
            finally:app.close()
