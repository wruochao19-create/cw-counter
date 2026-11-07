import unittest
import itertools
import numpy as np
from candidate_ocr import ctc_log_score,rank_pixels
from pixel_ocr import NotificationTracker
from tests.test_stress import line

CHARS=['blank']+list('0123456789+()EXP B')


def pixels(text,alternatives=None):
    rows=[]
    for n,char in enumerate(text):
        p=np.full(len(CHARS),1e-8);p[CHARS.index(char)]=.99
        if alternatives and n in alternatives:
            p[:]=1e-8
            for c,v in alternatives[n].items():p[CHARS.index(c)]=v
        p/=p.sum();rows.append(p)
        blank=np.full(len(CHARS),1e-8);blank[0]=1.;rows.append(blank/blank.sum())
    return np.array(rows)


class CandidateTests(unittest.TestCase):
    def test_ctc_sum_matches_exhaustive_paths(self):
        p=np.array([[.2,.5,.3],[.4,.1,.5],[.3,.4,.3]])
        for target in ([1],[1,1],[1,2]):
            expected=0.
            for path in itertools.product(range(3),repeat=3):
                collapsed=[v for i,v in enumerate(path)if v and(i==0 or path[i-1]!=v)]
                if collapsed==target:expected+=np.prod([p[t,v]for t,v in enumerate(path)])
            self.assertAlmostEqual(np.exp(ctc_log_score(p,target)),expected,places=8)

    def test_visual_alternative_can_beat_non_numeric_greedy(self):
        text='EXP(+4B)';p=pixels(text,{6:{'B':.52,'6':.46,'3':.02}})
        result=rank_pixels(p,CHARS,[21,32,43,46,60])
        self.assertTrue(result['accepted']);self.assertEqual(result['value'],46)
        self.assertTrue(result['inferred'])

    def test_close_candidates_missing_boundary_and_strong_outside_rejected(self):
        p=pixels('EXP(+46)',{6:{'6':.51,'3':.49}})
        self.assertFalse(rank_pixels(p,CHARS,[43,46])['accepted'])
        self.assertFalse(rank_pixels(pixels('EXP(+4'),CHARS,[43,46])['accepted'])
        self.assertFalse(rank_pixels(pixels('EXP(+40)'),CHARS,[46])['accepted'])

    def test_no_map_or_zero_pixels_never_force_a_monster(self):
        self.assertFalse(rank_pixels(pixels('EXP(+46)'),CHARS,[])['accepted'])
        self.assertFalse(rank_pixels(pixels(''),CHARS,[46])['accepted'])

    def test_candidate_only_is_estimated_and_requires_two_frames(self):
        tracker=NotificationTracker();tracker.update([],0)
        row=line(46,verified=False);row['candidate_verified']=True
        self.assertEqual(tracker.update([row],.2)[0],[])
        self.assertEqual(tracker.update([row],.4)[0],[])
        events=tracker.finish();self.assertEqual(len(events),1)
        self.assertTrue(events[0]['estimated']);self.assertEqual(events[0]['amount'],46)
