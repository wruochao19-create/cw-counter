import unittest
from pathlib import Path
from PIL import Image
from pixel_ocr import scan,parse_notification,number_evidence,NotificationTracker,RapidReader
from counter import CounterSession
from catalog import Catalog


def line(amount=35,y=90,color='white',kind='exp',score=.95):
    return dict(text='',score=score,box=(5,y,190,y+12),said=(kind,amount),color=color,digit_verified=True)


class TrackingTests(unittest.TestCase):
    def test_high_line_score_does_not_override_failed_digit_check(self):
        tracker=NotificationTracker();counter=CounterSession({'A':15})
        tracker.update([],0)
        wrong=line(15,score=.97);wrong['digit_verified']=False
        for t in (.2,.4,.6,.8):
            for event in tracker.update([wrong],t)[0]:counter.accept(**event)
        self.assertEqual(sum(counter.counts.values()),0)
        for event in tracker.finish():counter.accept(**event)
        self.assertEqual(counter.unresolved,1)

    def test_digit_score_uses_weakest_digit_not_sentence_average(self):
        text='You received EXP (+17)'
        probabilities=[.99]*len(text)
        probabilities[text.index('7')]=.42
        self.assertEqual(number_evidence(text,probabilities),(17,.42))
        self.assertEqual(number_evidence('You received EXP (+1S)',[.99]*22),(None,0))

    def test_static_message_once_and_identical_next_kill_separately(self):
        tracker=NotificationTracker();events=[]
        frames=[[],[line()],[line()],[line()], [line(),line(y=65)], [line(),line(y=65)]]
        for n,rows in enumerate(frames):
            events.extend(tracker.update(rows,n*.2)[0])
        self.assertEqual([e['amount'] for e in events],[35,35])
        self.assertEqual(len({e['event_id'] for e in events}),2)

    def test_dropout_does_not_recount_existing_message(self):
        tracker=NotificationTracker();events=[]
        for n,rows in enumerate([[],[line()],[line()],[],[line()],[line()]]):
            events.extend(tracker.update(rows,n*.1)[0])
        self.assertEqual(len(events),1)

    def test_baseline_and_pause_do_not_recount(self):
        tracker=NotificationTracker()
        self.assertEqual(tracker.update([line()],0)[0],[])
        self.assertEqual(tracker.update([line()],.3)[0],[])
        events,gap=tracker.update([line()],3)
        self.assertTrue(gap);self.assertEqual(events,[])

    def test_party_and_bonus_do_not_become_personal_kills(self):
        tracker=NotificationTracker();counter=CounterSession({'A':35})
        tracker.update([],0)
        lines=[line(color='yellow'),line(7,65,'yellow','bonus')]
        for t in (.2,.4,.6):
            for event in tracker.update(lines,t)[0]:counter.accept(**event)
        self.assertEqual(sum(counter.counts.values()),0)
        self.assertEqual(counter.party_exp,42)

    def test_low_score_and_inconsistent_colors_never_count(self):
        tracker=NotificationTracker();tracker.update([],0)
        for n,color in enumerate(('white','yellow','white','yellow'),1):
            self.assertEqual(tracker.update([line(color=color),line(99,65,score=.6)],n*.2)[0],[])

    def test_parser_tolerates_prefix_not_guessed_digits(self):
        self.assertEqual(parse_notification('Youreceiveu ExPG35'),('exp',35))
        self.assertEqual(parse_notification('Bonus EXP for PARTY (+7)'),('bonus',7))
        self.assertEqual(parse_notification('You have gained mesos (+1,234)'),('mesos',1234))
        for text in ('You received EXP (+3S)','You received EXP (-35)','HP 35','You received EXP (+1,2)'):
            self.assertIsNone(parse_notification(text))


class RealScreenshotTests(unittest.TestCase):
    def test_faded_three_line_sample_is_not_claimed_fully_accurate(self):
        image=Image.open(Path(__file__).parent/'data/user-exp17-13-15.png').convert('RGB')
        rows=scan(image)
        # Faded first line is not reliably recovered from this reduced screenshot.
        top=[row for row in rows if row['box'][1]<8]
        self.assertTrue(top)
        self.assertFalse(any(row['said'] and row['digit_verified'] for row in top),top)
        # Whole-line recognition can be plausible while a digit has weak evidence.
        low=[row for row in rows if row['said'] and not row['digit_verified']]
        self.assertTrue(low,rows)

    def test_calibration_ui_uses_same_real_ocr_pipeline(self):
        import tkinter as tk
        from calibration_ui import CalibrationDialog
        from recognition import Calibration
        image=Image.open(Path(__file__).parent/'data/user-exp35.png').convert('RGB')
        root=tk.Tk();root.withdraw()
        dialog=CalibrationDialog(root,image,Calibration(image.width,image.height,region=[0,0,image.width,image.height]),lambda c:None)
        dialog.window.withdraw()
        try:
            dialog.inspect()
            text=dialog.result.get('1.0','end')
            self.assertIn('exp +35',text)
            self.assertIn('white',text)
            self.assertNotIn('识别失败',text)
        finally:dialog.window.destroy();root.destroy()

    def test_user_screenshot_exp35_ocr_and_end_to_end_once(self):
        image=Image.open(Path(__file__).parent/'data/user-exp35.png').convert('RGB')
        lines=scan(image)
        found=[row for row in lines if row['said']==('exp',35) and row['score']>=.8]
        self.assertTrue(found,lines)
        self.assertEqual(found[0]['color'],'white')
        # This fixture is from The Road to the Dungeon. Ghost Stump now also
        # gives 35 EXP, so a global profile cannot identify it as Blue Mushroom.
        profile=Catalog().profile('The Road to the Dungeon')
        session=CounterSession(profile)
        reader=RapidReader()
        frames=[Image.new('RGB',image.size),image,image,image]
        for n,frame in enumerate(frames):
            for event in reader.read(frame,n*.3)[0]:session.accept(**event)
        self.assertEqual(sum(session.counts.values()),1)
        self.assertEqual(session.personal_exp,35)
        self.assertTrue(next(iter(session.counts)).startswith('Blue Mushroom'))

