from pathlib import Path
import tempfile
import unittest
from global_trend.demo import DemoEngine,make_demo_state,write_preview


class DemoTest(unittest.TestCase):
    def test_sample_has_three_independently_ranked_groups(self):
        state=make_demo_state()
        self.assertTrue(state.sample);self.assertIn('SAMPLE',state.source)
        self.assertEqual(set(state.groups),{'Indices','Forex','Shares'})
        self.assertEqual(len(state.groups['Forex']),10)
        for rows in state.groups.values():
            active=[r for r in rows if r.rank is not None]
            self.assertEqual([r.rank for r in active],list(range(1,len(active)+1)))
            self.assertEqual([abs(r.captured_angle) for r in active],sorted(
                [abs(r.captured_angle) for r in active],reverse=True))

    def test_demo_never_connects_and_preview_is_self_contained(self):
        engine=DemoEngine()
        with self.assertRaises(RuntimeError):engine.connect(None)
        engine.close();engine.close()
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'demo.html';write_preview(p)
            text=p.read_text()
            self.assertIn('OFFLINE SAMPLE',text);self.assertIn('Forex',text)
            self.assertNotIn('https://cdn',text);self.assertNotIn('client_secret',text)


if __name__=='__main__':unittest.main()
