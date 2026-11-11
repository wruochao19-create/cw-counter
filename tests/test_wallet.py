import csv
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from counter import CounterSession
from wallet import wallet_balance, WalletCheck
from pixel_ocr import NotificationTracker
from tests.test_notification_mix import coin


class WalletTests(unittest.TestCase):
    def test_reads_inventory_field_in_window_at_two_scales(self):
        image = Image.new('RGB',(1280,800),'#404040')
        draw = ImageDraw.Draw(image)
        draw.rectangle((30,470,424,502),fill='#8593a6')
        draw.rectangle((60,473,355,499),fill='white')
        draw.ellipse((36,477,54,495),fill='gold',outline='black')
        draw.text((274,475),'461,026',font=ImageFont.truetype('arial.ttf',21),fill='black')
        draw.text((362,481),'MESOS',font=ImageFont.truetype('arial.ttf',12),fill='white')
        for size in (image.size,(2560,1600)):
            self.assertEqual(wallet_balance(image.resize(size)),(True,461026))
        draw.rectangle((30,470,59,502),fill='#8593a6')
        self.assertEqual(wallet_balance(image),(False,None))

    def test_late_events_wallet_boundaries_and_export(self):
        with tempfile.TemporaryDirectory() as directory:
            s=CounterSession()
            s.open_log(directory)
            check=WalletCheck()
            s.wallet_checks.append(check)
            for t in (1,2):check.observe(True,1000,t)
            for t in (3,4):check.observe(False,None,t)
            for t in (8,9):check.observe(True,1114,t)
            self.assertEqual(check.phase,'done')
            for event,at,ok in [('a',1,True),('b',3,True),('b',3,True),
                                ('c',8,True),('d',5,False),('e',10,True)]:
                s.accept(event,'mesos',57,'unknown',ok,observed_at=at)
            self.assertEqual((check.total,check.uncertain),(114,1))
            self.assertEqual(s.coin_total,228)
            self.assertEqual(s.unresolved,0)
            s.map_clock.seconds=120
            self.assertEqual(s.coin_rate(),6840)
            s.close()
            path=Path(directory)/'summary.csv'
            s.export_summary(path)
            with path.open(encoding='utf-8-sig') as handle:
                audit=next(row for row in csv.reader(handle) if row and row[0]=='wallet_check')
            self.assertEqual(json.loads(audit[1])['difference'],0)

    def test_separate_identical_pickups_and_uncertain_coin(self):
        tracker=NotificationTracker()
        tracker.update([],0)
        events=[]
        for t,rows in ((.2,[coin(57)]),(.4,[coin(57)]),
                       (.6,[coin(57,275),coin(57)]),(.8,[coin(57,275),coin(57)]),
                       (1,[coin(33,300),coin(57,275),coin(57,250)])):
            events.extend(tracker.update(rows,t)[0])
        events.extend(tracker.finish())
        self.assertEqual(sorted((e['amount'],e['confident']) for e in events),[(33,False),(57,True),(57,True)])
