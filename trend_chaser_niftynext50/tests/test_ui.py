from dataclasses import replace
import os
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from ema_scanner.models import Settings
from ema_scanner.models import Event
from ema_scanner.scanner import Scanner
from ema_scanner.storage import SettingsStore
from ema_scanner.ui import App, plot_bounds
from ema_scanner.trends import TrendCandidate, TrendRow
from tests.test_strategy import candidate


class GeometryTest(unittest.TestCase):
    def test_reference_aspect_survives_resize(self):
        for w,h in [(1000,400),(1200,300),(600,500)]:
            x,y,pw,ph=plot_bounds(w,h)
            self.assertAlmostEqual(pw/ph,2)
            self.assertGreaterEqual(x,60)
            self.assertGreaterEqual(y,20)


@unittest.skipUnless(os.environ.get('DISPLAY') or os.name=='nt','Requires a desktop/offscreen display')
class DesktopTest(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk()
        self.temp=tempfile.TemporaryDirectory()
        self.long=replace(candidate(symbol='ALONG'),key='ALONG',state='ARMED',side='LONG')
        self.short=replace(candidate('SHORT',symbol='BSHORT'),key='BSHORT',state='ARMED',side='SHORT')
        self.data={'connected':True,'connecting':False,'status':'Connected','market':'NORMAL_OPEN',
                   'settings':Settings(),'armed':[self.long,self.short],'rows':[self.long,self.short],
                   'counts':{'eligible':210,'subscribed':210,'receiving':210,'ready':210,'paused':0},
                   'events':[],'stocks':[('ALONG',True,'Ready')],'diagnostics':[]}
        self.scanner=Mock();self.scanner.snapshot.return_value=self.data
        self.app=App(self.root,self.scanner,SettingsStore(Path(self.temp.name)/'settings.json'))
        self.root.update()

    def tearDown(self):
        try:self.app.close()
        except tk.TclError:pass
        self.temp.cleanup()

    def test_closed_market_clears_trends(self):
        self.data['trends_long']=[TrendRow(TrendCandidate('ALONG','ALONG','LONG',self.long.quote_time,40,'CONFIRMED',self.long.bucket),self.long)]
        self.app.refresh()
        self.assertEqual(len(self.app.bullish_board.get_children()),1)
        self.data['armed']=[];self.data['rows']=[];self.data['trends_long']=[];self.data['market']='CLOSED'
        self.app.refresh()
        self.assertEqual(self.app.bullish_board.get_children(),())

    def ranked_rows(self):
        return [replace(self.long if i<25 else self.short,
                        symbol=f'STOCK{i:02}',key=f'STOCK{i:02}',
                        angle=60-i if i<25 else -(60-i)) for i in range(50)]

    def test_hidden_pre_cross_table_preserves_full_scan_coverage(self):
        rows=self.ranked_rows()
        self.data['armed']=rows;self.data['rows']=rows
        self.data['stocks']=[(r.symbol,True,'Ready') for r in rows]
        self.app.refresh()
        self.assertFalse(hasattr(self.app,'board'),'Pre-cross table must be removed')
        self.assertIn('Eligible: 210',self.app.coverage.get())
        self.assertEqual(len(self.app.stock_table.get_children()),50)
        self.assertEqual(len(self.app.stock_pick.cget('values')),50)

    def use_token_store(self,remember=False):
        from ema_scanner.credentials import TokenStore
        from tests.test_credentials import FakeCipher
        self.app.close();self.root=tk.Tk()
        store=SettingsStore(Path(self.temp.name)/'settings.json')
        store.save(Settings(remember_token=remember))
        token_store=TokenStore(store.path.parent/'upstox-token.dpapi',cipher=FakeCipher())
        self.app=App(self.root,self.scanner,store,token_store=token_store)
        self.root.update()
        return token_store

    def test_remembered_token_restores_masked_input_without_auto_connect(self):
        self.assertTrue(hasattr(self.app,'remember_token'),'Remember token is not implemented')
        token_store=self.use_token_store()
        self.app.remember_token.set(True);self.app.remember_changed()
        self.app.token.set('Bearer saved-secret-token');self.app.connect()
        self.assertEqual(token_store.load(),'saved-secret-token')
        self.assertNotIn('saved-secret-token',self.app.store.path.read_text())
        self.assertEqual(self.app.token.get(),'')
        self.app.close();self.root=tk.Tk();self.scanner.reset_mock()
        self.app=App(self.root,self.scanner,self.app.store,token_store=token_store)
        self.root.update()
        self.assertEqual(self.app.token.get(),'saved-secret-token')
        self.assertEqual(self.app.token_entry.cget('show'),'•')
        self.scanner.connect.assert_not_called()

    def test_unchecking_remember_deletes_saved_token_and_preference(self):
        self.assertTrue(hasattr(self.app,'remember_token'),'Remember token is not implemented')
        token_store=self.use_token_store(remember=True)
        token_store.save('saved-secret-token')
        self.app.remember_token.set(False);self.app.remember_changed()
        self.assertFalse(token_store.path.exists())
        self.assertFalse(self.app.store.load().remember_token)
        self.app.apply_settings()
        self.assertFalse(self.app.store.load().remember_token)

    def test_reconnect_reuses_saved_token_after_input_is_cleared(self):
        token_store=self.use_token_store(remember=True)
        self.app.token.set('saved-secret-token');self.app.connect()
        self.assertEqual(self.app.token.get(),'')
        self.scanner.reset_mock()
        self.app.connect()
        self.scanner.connect.assert_called_once_with('saved-secret-token')
        self.assertEqual(token_store.load(),'saved-secret-token')

    def test_token_storage_failure_has_no_plaintext_fallback(self):
        self.assertTrue(hasattr(self.app,'remember_token'),'Remember token is not implemented')
        token_store=self.use_token_store(remember=True)
        self.scanner.reset_mock();self.app.token.set('private-token')
        with patch.object(token_store.cipher,'protect',side_effect=OSError('private-token')),patch('ema_scanner.ui.messagebox.showerror') as error:
            self.app.connect()
        self.scanner.connect.assert_not_called()
        self.assertFalse(token_store.path.exists())
        self.assertNotIn('private-token',str(error.call_args))

    def test_unreadable_saved_token_does_not_prevent_startup(self):
        self.assertTrue(hasattr(self.app,'remember_token'),'Remember token is not implemented')
        token_store=self.use_token_store(remember=True)
        token_store.path.write_bytes(b'corrupt blob')
        self.app.close();self.root=tk.Tk()
        self.app=App(self.root,self.scanner,self.app.store,token_store=token_store)
        self.root.update()
        self.assertEqual(self.app.token.get(),'')
        self.assertIn('unavailable',self.app.token_status.get().lower())

    def test_chart_uses_same_geometry_and_measured_chord(self):
        self.app.selected='ALONG';self.app.refresh();self.root.update()
        self.assertEqual(len(self.app.canvas.find_withtag('measured_chord')),1)
        self.assertEqual(len(self.app.canvas.find_withtag('ema9')),1)

    def test_masked_token_and_settings_persist_without_token(self):
        self.assertEqual(self.app.token_entry.cget('show'),'•')
        self.app.token.set('secret-value')
        self.app.proximity.set('0.07')
        self.app.apply_settings()
        self.assertEqual(self.app.store.load().proximity_pct,.07)
        self.assertNotIn('secret-value',self.app.store.path.read_text())
        self.app.connect()
        self.scanner.connect.assert_called_with('secret-value')
        self.assertEqual(self.app.token.get(),'')

    def test_close_cleans_up_scanner(self):
        self.app.close()
        self.scanner.close.assert_called_once()

    def test_seven_per_side_are_visible_and_preserve_crossover_scores(self):
        rows=[]
        for i in range(9):
            snap=replace(self.long,key=f'L{i}',symbol=f'L{i}',angle=7+i)
            rows.append(TrendRow(TrendCandidate(snap.key,snap.symbol,'LONG',snap.quote_time,40-i,'CONFIRMED',snap.bucket),snap))
        self.data['trends_long']=rows
        self.data['trends_short']=[TrendRow(TrendCandidate(f'S{i}',f'S{i}','SHORT',self.short.quote_time,-30+i,'PROVISIONAL',self.short.bucket),replace(self.short,key=f'S{i}',symbol=f'S{i}')) for i in range(9)]
        self.app.refresh()
        self.assertEqual(len(self.app.bullish_board.get_children()),7)
        self.assertEqual(len(self.app.bearish_board.get_children()),7)
        self.root.geometry('1200x680');self.root.update()
        for table,key in [(self.app.bullish_board,'L6'),(self.app.bearish_board,'S6')]:
            bbox=table.bbox(key)
            self.assertTrue(bbox,'Seventh row must be visible without scrolling')
            self.assertLessEqual(table.winfo_rooty()+bbox[1]+bbox[3],self.root.winfo_rooty()+self.root.winfo_height())
        values=self.app.bullish_board.item('L0')['values']
        self.assertEqual(values[2:5],['CONFIRMED','+40.00°','+7.00°'])
        self.assertEqual(self.app.bearish_board.item('S0')['values'][2],'PROVISIONAL')

    def test_chart_hidden_toggle_never_changes_settings_or_geometry(self):
        self.assertFalse(self.app.show_chart.get())
        self.assertEqual(self.app.chart_frame.winfo_manager(),'')
        settings=self.app.settings;scale=self.long.scale
        self.app.show_chart.set(True);self.app.toggle_chart();self.root.update()
        self.assertEqual(self.app.chart_frame.winfo_manager(),'pack')
        self.assertGreaterEqual(self.app.canvas.winfo_height(),200)
        self.app.tabs.select(self.app.main);self.root.update()
        toggle=next(widget for parent in self.app.main_body.winfo_children() for widget in parent.winfo_children()
                    if widget.winfo_class()=='TCheckbutton' and widget.cget('text')=='Show Chart')
        toggle.invoke();self.root.update()
        self.assertEqual(self.app.tabs.select(),str(self.app.chart_tab),'One click must reopen the chart after returning to Scanner')
        self.app.show_chart.set(False);self.app.toggle_chart()
        self.assertEqual(self.app.settings,settings)
        self.assertEqual(self.long.scale,scale)
        self.scanner.set_settings.assert_not_called()

    def test_forget_token_clears_input_blob_and_preference(self):
        token_store=self.use_token_store(remember=True)
        token_store.save('saved-secret-token');self.app.token.set('saved-secret-token')
        self.app.forget_token()
        self.assertFalse(token_store.path.exists())
        self.assertEqual(self.app.token.get(),'')
        self.assertFalse(self.app.remember_token.get())
        self.assertFalse(self.app.store.load().remember_token)

    def test_native_remember_default_and_non_native_gating(self):
        token_store=self.use_token_store(remember=True)
        self.assertTrue(self.app.remember_token.get())
        self.app.close();self.root=tk.Tk()
        token_store.cipher.available=False
        self.app=App(self.root,self.scanner,self.app.store,token_store=token_store)
        self.assertFalse(self.app.remember_token.get())
        self.assertIn('disabled',self.app.remember_check.state())

    def test_identity_and_independent_data_directory(self):
        from ema_scanner import VERSION
        from ema_scanner.storage import data_directory
        self.assertEqual(VERSION,'1.0.0')
        self.assertIn('Trend Chaser Nifty Next 50',self.root.title())
        with patch.dict(os.environ,{'LOCALAPPDATA':self.temp.name}):
            self.assertEqual(data_directory(),Path(self.temp.name)/'Trend_Chaser_Nifty_Next_50'/'data')

    def test_alert_checks_every_new_event_and_deduplicates_batches(self):
        from tests.test_strategy import NOW
        source=Scanner(Settings(),start_worker=False)
        try:
            self.root.bell=Mock()
            source._emit([Event('ALONG','ARMED','LONG',NOW,'Live provisional signal'),
                          Event('OTHER','PAUSED','',NOW,'Stale quote')])
            self.data['events']=list(source.events)
            self.app.refresh()
            self.root.bell.assert_called_once()
            self.app.refresh()
            self.root.bell.assert_called_once()
            source._emit([Event('OTHER','ARMED','SHORT',NOW,'Initial',initial=True)])
            self.data['events']=list(source.events);self.app.refresh()
            self.root.bell.assert_called_once()
        finally:source.close()


if __name__=='__main__':unittest.main()
