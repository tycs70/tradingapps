from dataclasses import replace
import unittest
from global_trend.ranking import rank_group
from global_trend.trends import TrendBook
from tests.test_trends import snap, observed
from tests.test_data import NOW


class RankingTest(unittest.TestCase):
    def test_mixed_directions_use_frozen_strength_and_stable_ties(self):
        book=TrendBook(NOW.date())
        for key,side,angle in [('B','SHORT',40),('A','LONG',40),('C','LONG',20)]:
            observed(book,side,key,angle)
        latest={k:replace(snap(side,key=k),angle=1 if side=='LONG' else -89)
                for k,side in [('A','LONG'),('B','SHORT'),('C','LONG')]}
        rows=book.top('LONG',latest,100)+book.top('SHORT',latest,100)
        result=rank_group(rows)
        self.assertEqual([r.key for r in result],['A','B','C'])
        self.assertEqual([r.strength for r in result],[40,40,20])


if __name__=='__main__': unittest.main()
