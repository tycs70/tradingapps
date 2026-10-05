from dataclasses import replace
import os
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock

from ema_scanner.models import Settings
from ema_scanner.models import Event
from ema_scanner.scanner import Scanner
from ema_scanner.storage import SettingsStore
from ema_scanner.ui import App, plot_bounds
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

    def test_both_sides_filter_and_closed_market_empty(self):
        self.assertEqual(len(self.app.board.get_children()),2)
        self.app.filter.set('Bearish');self.app.refresh()
        self.assertEqual(len(self.app.board.get_children()),1)
        self.assertEqual(self.app.board.item(self.app.board.get_children()[0])['values'][1],'BSHORT')
        self.data['armed']=[];self.data['rows']=[];self.data['market']='CLOSED'
        self.app.refresh()
        self.assertEqual(self.app.board.get_children(),())

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
