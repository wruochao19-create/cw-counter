import tempfile
import unittest
from pathlib import Path
from PIL import Image
from pixel_ocr import parse_notification,number_evidence,NotificationTracker
from tests.test_stress import line
from counter import CounterSession
from diagnostics import DiagnosticRecorder


class RealFailureTests(unittest.TestCase):
    def test_logged_ep_typo_preserves_digit_evidence(self):
        text='You recelved EP (+43)'
        self.assertEqual(parse_notification(text),('exp',43))
        self.assertEqual(number_evidence(text,[.99]*len(text)),(43,.99))
        self.assertIsNone(parse_notification('You received EP (+B0)'))

    def test_same_hint_46_40_4_becomes_one_labelled_estimate(self):
        t=NotificationTracker();t.update([],0);events=[]
        for n,amount in enumerate((46,40,4),1):
            row=line(amount);row['digit_verified']=n==1
            events.extend(t.update([row],n*.3)[0])
        events+=t.finish()
        self.assertEqual(len(events),1);self.assertEqual(events[0]['amount'],46)
        self.assertTrue(events[0]['estimated'])
        c=CounterSession({'Wild Boar':46,'Blue Snail':4})
        c.accept(**events[0]);self.assertEqual(c.counts['Wild Boar'],1)
        self.assertEqual(c.estimated_counts['Wild Boar'],1);self.assertEqual(c.personal_exp,0)

    def test_two_strong_different_values_are_not_fused(self):
        t=NotificationTracker();t.update([],0)
        t.update([line(46)],.3);t.update([line(4)],.6)
        self.assertEqual(len(t.tracks),2)

    def test_diagnostics_are_opt_in_bounded_and_preserve_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'diagnostic';r=DiagnosticRecorder(root,max_frames=2)
            self.assertFalse(root.exists())
            image=Image.new('RGB',(100,50),'white')
            for n in range(4):r.add(image,n,(0,0,100,50),[],[])
            self.assertTrue(r.done);self.assertEqual(len(list(root.rglob('*.png'))),2)
            self.assertEqual(Image.open(next(root.rglob('*.png'))).tobytes(),image.tobytes())
            capped=DiagnosticRecorder(root,max_bytes=1)
            capped.add(image,0,(0,0,100,50),[],[])
            self.assertTrue(capped.done);self.assertIsNone(capped.path)
