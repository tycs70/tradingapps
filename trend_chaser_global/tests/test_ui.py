from dataclasses import replace
from pathlib import Path
import os
import tempfile
import tkinter as tk
import unittest
from global_trend.ui import App
from global_trend.demo import DemoEngine
from global_trend.storage import SettingsStore
from global_trend.credentials import CredentialStore


@unittest.skipUnless(os.environ.get('DISPLAY') or os.name=='nt','Requires a display')
class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=tk.Tk();self.engine=DemoEngine()
        base=Path(self.tmp.name)
        self.app=App(self.root,self.engine,SettingsStore(base/'settings.json'),
                     CredentialStore(base/'credentials.dpapi'),demo=True)
        self.root.update()
    def tearDown(self):
        self.app.close();self.tmp.cleanup()

    def test_three_sections_and_direction_colors_are_visible(self):
        self.assertEqual(tuple(self.app.sections),('Indices','Forex','Shares'))
        for group,section in self.app.sections.items():
            tree=section.tree
            self.assertEqual(len(tree.get_children()),len(self.engine.snapshot().groups[group]))
            tags=[tree.item(i)['tags'] for i in tree.get_children()]
            self.assertTrue(any('LONG' in t for t in tags));self.assertTrue(any('SHORT' in t for t in tags))

    def test_selection_stays_on_instrument_when_ranking_moves(self):
        section=self.app.sections['Shares'];tree=section.tree
        key=tree.get_children()[1];tree.selection_set(key)
        rows=list(self.engine.snapshot().groups['Shares']);rows.reverse()
        section.update_rows(rows)
        self.assertEqual(tree.selection(),(key,))
        self.assertEqual(tree.get_children()[0],rows[0].key)

    def test_indices_remain_above_scrolled_lower_dashboard(self):
        before=self.app.index_frame.winfo_rooty()
        self.app.lower_canvas.yview_moveto(1);self.root.update()
        self.assertEqual(self.app.index_frame.winfo_rooty(),before)
        self.assertTrue(self.app.sections['Forex'].scrollbar.winfo_exists())

    def test_code_and_secret_are_masked_and_demo_cannot_connect(self):
        conn=self.app.connection
        self.assertTrue(conn.secret_entry.cget('show'))
        self.assertTrue(conn.code_entry.cget('show'))
        self.assertIn('disabled',conn.connect_button.state())
        self.assertFalse(list(Path(self.tmp.name).rglob('*')))

    def test_chart_is_optional_and_displays_selected_reference(self):
        key=self.app.sections['Shares'].tree.get_children()[0]
        self.app.select_asset(key);self.app.show_chart();self.root.update()
        self.assertEqual(self.app.notebook.select(),str(self.app.chart_tab))
        self.assertGreater(len(self.app.chart.find_withtag('ema9')),0)

    def test_close_cancels_callbacks_and_is_idempotent(self):
        self.app.close();self.app.close()
        self.assertTrue(self.app.closed);self.assertTrue(self.engine.closed)

    def test_inactive_rows_are_grey_and_selected_details_include_distance(self):
        section=self.app.sections['Shares'];row=self.engine.snapshot().groups['Shares'][0]
        section.update_rows([replace(row,rank=None,status='STALE')])
        self.assertIn('INACTIVE',section.tree.item(row.key)['tags'])
        self.app.select_asset(row.key)
        self.assertIn('Distance',self.app.detail.get())
        self.assertTrue(self.app.diagnostics_tab.winfo_exists())

    def test_preferences_expose_global_day_boundary(self):
        self.assertEqual(self.app.day_boundary.get(),'17:00')
        self.assertEqual(self.app.day_zone.get(),'America/New_York')


if __name__=='__main__':unittest.main()
