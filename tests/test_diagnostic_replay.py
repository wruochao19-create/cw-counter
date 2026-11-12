import json
import unittest
from pathlib import Path
from PIL import Image
from pixel_ocr import RapidReader,NotificationTracker,apply_map_constraint
from catalog import Catalog
from counter import CounterSession
from tests.test_stress import line

RECORDING=Path(__file__).resolve().parents[1]/'diagnostics/20261105-235854-005808'


class FadingTests(unittest.TestCase):
    def test_scrolled_hint_with_missing_digit_is_not_counted_again(self):
        tracker=NotificationTracker();tracker.update([],0);events=[]
        sequence=[ [line(43)], [line(43)],
                   [line(21),line(3,y=275,verified=False)],
                   [line(21),line(43,y=275)],
                   [line(21),line(43,y=275)] ]
        for n,rows in enumerate(sequence,1):events+=tracker.update(rows,n*.3)[0]
        events+=tracker.finish()
        self.assertEqual([e['amount'] for e in events if e['confident']],[43,21])
        self.assertFalse(any(not e['confident'] for e in events))

    def test_valid_numeric_frames_separated_by_fading_are_not_discarded(self):
        tracker=NotificationTracker();tracker.update([],0);events=[]
        for n,(valid,color) in enumerate([(False,'white'),(False,'white'),(True,'white'),
                                         (False,'unknown'),(False,'unknown'),(True,'unknown')],1):
            row=line(60);row.update(digit_verified=valid,color=color)
            events+=tracker.update([row],n*.3)[0]
        self.assertEqual(len(events),1)
        self.assertTrue(events[0]['confident']);self.assertEqual(events[0]['amount'],60)
        self.assertEqual(events[0]['color'],'white')
        self.assertEqual(tracker.finish(),[])

    def test_unknown_color_does_not_bypass_map_validation(self):
        row=line(99);row['color']='unknown'
        apply_map_constraint([row],{'Fire Boar':60})
        self.assertFalse(row['map_verified'])

    def test_conflicting_known_colors_are_not_confirmed(self):
        tracker=NotificationTracker();tracker.update([],0);events=[]
        for n,color in enumerate(['white','yellow','unknown','white'],1):
            row=line(60);row['color']=color;events+=tracker.update([row],n*.3)[0]
        self.assertFalse(any(e['confident'] for e in events))


@unittest.skipUnless((RECORDING/'frames.jsonl').exists(),'Local user diagnostic not present')
class RealRecordingTests(unittest.TestCase):
    def test_original_pixels_eight_new_hints_without_duplicates(self):
        # Manually inspected births: frames 1,5,8,11,12,16,18,23.
        # Values: 21,43,60,21,21,60,43,21. Frame 0 has no EXP baseline.
        rows=[json.loads(s) for s in (RECORDING/'frames.jsonl').read_text(encoding='utf-8').splitlines()]
        reader=RapidReader(Catalog().profile('Deep Valley II'));counter=CounterSession(reader.profile)
        previous=None
        for row in rows:
            if previous and previous!=row['box']:reader.rebase(previous,row['box'])
            previous=row['box']
            with Image.open(RECORDING/f'{row["frame"]:03d}.png') as image:
                events,_=reader.read(image.convert('RGB'),row['t'])
            for event in events:counter.accept(**event)
        for event in reader.finish():counter.accept(**event)
        self.assertEqual(dict(counter.counts),{'Dark Stump':4,'Dark Axe Stump':2,'Fire Boar [Lv32, ID30]':2})
        self.assertEqual(counter.personal_exp,290)
        self.assertEqual(counter.unresolved,0)
        self.assertEqual(sum(counter.estimated_counts.values()),0)


class NewRecordingTests(unittest.TestCase):
    def replay(self,name):
        directory=RECORDING.parent/name
        if not (directory/'frames.jsonl').exists():self.skipTest('Local user diagnostic not present')
        rows=[json.loads(s) for s in (directory/'frames.jsonl').read_text(encoding='utf-8').splitlines()]
        reader=RapidReader(Catalog().profile('Deep Valley II'));counter=CounterSession(reader.profile)
        previous=None
        for row in rows:
            if previous and previous!=row['box']:reader.rebase(previous,row['box'])
            previous=row['box']
            with Image.open(directory/f'{row["frame"]:03d}.png') as image:
                events,_=reader.read(image.convert('RGB'),row['t'])
            for event in events:counter.accept(**event)
        for event in reader.finish():counter.accept(**event)
        return counter

    def test_two_boars_and_two_dark_axe_stumps(self):
        # Visible births at frames 10,15,17,24: 43,46,46,43.
        counter=self.replay('20261106-001349-060242')
        self.assertEqual(dict(counter.counts),{'Dark Axe Stump':2,'Wild Boar':2})
        self.assertEqual(counter.personal_exp,178)
        self.assertEqual(counter.unresolved,0)
        self.assertEqual(sum(counter.estimated_counts.values()),0)

    def test_43_scrolls_as_3_without_duplicate_and_fast_rows_confirm_fire_boar(self):
        # Visible births at frames 4,7,16: 43,21,60. No second 43.
        counter=self.replay('20261106-001425-922630')
        self.assertEqual(dict(counter.counts),{'Dark Axe Stump':1,'Dark Stump':1,'Fire Boar [Lv32, ID30]':1})
        # Tight row crops now read +60 in both frames 17 and 18, with
        # weakest-digit scores .918 and .846. Its one kill is confirmed.
        self.assertEqual(counter.personal_exp,124)
        self.assertEqual(counter.estimated_exp,0)
        self.assertEqual(sum(counter.estimated_counts.values()),0)
        self.assertEqual(counter.unresolved,0)
