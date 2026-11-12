import csv
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from counter import CounterSession
from wallet import wallet_balance, WalletCheck, LiveWalletCheck
from pixel_ocr import NotificationTracker
from tests.test_notification_mix import coin


class WalletTests(unittest.TestCase):
    def test_real_wallet_dot_separator_and_meso_label(self):
        image=Image.open(Path(__file__).parent/'data/user-wallet-real.png').convert('RGB')
        for scale in (1,1.5):
            resized=image.resize((round(image.width*scale),round(image.height*scale)))
            self.assertEqual(wallet_balance(resized),(True,627949))

    def test_pause_excludes_shopping_balance_changes_and_time_but_keeps_totals(self):
        check=LiveWalletCheck()
        for t,balance in enumerate((1000,1010,1020)):check.observe(True,balance,t)
        check.count_event(.5,10,True)
        check.break_interval()
        before=check.snapshot()
        check.count_event(50,999,True)
        self.assertEqual(check.snapshot()['wallet_gain'],10)
        self.assertEqual(check.snapshot()['notification_gain'],10)
        self.assertFalse(check.snapshot()['live'])
        # A much lower wallet after buying supplies starts a new interval.
        for t,balance in ((100,50),(101,60),(102,70)):
            check.observe(True,balance,t)
        check.count_event(100.5,10,True)
        after=check.snapshot()
        self.assertEqual(before['seconds'],1)
        self.assertEqual(after['seconds'],2)
        self.assertEqual(after['wallet_gain'],20)
        self.assertEqual(after['notification_gain'],20)
        self.assertEqual(after['difference'],0)
        self.assertEqual(after['segments'],[(0,1)])

    def test_continuously_changing_party_balance_and_late_hints_share_one_interval(self):
        check=LiveWalletCheck()
        check.observe(True,1000,0)
        check.count_event(.5,10,True)
        check.observe(True,1010,1)
        check.observe(True,1020,2)
        self.assertEqual(check.start,(0,1000))
        self.assertEqual(check.snapshot()['wallet_gain'],10)
        self.assertEqual(check.total,10)
        check.count_event(1.5,10,True)  # Arrives ahead of the wallet watermark.
        self.assertEqual(check.total,10)
        for t in range(3,33):check.observe(True,1000+t*10,t)
        check.count_event(20,50,True)  # Late OCR still reconciles its own time.
        check.count_event(33,999,True)  # Future hints never inflate this interval.
        sample=check.snapshot()
        self.assertEqual(sample['seconds'],31)
        self.assertEqual(sample['wallet_gain'],310)
        self.assertEqual(sample['notification_gain'],70)
        self.assertEqual(sample['difference'],240)
        self.assertEqual(sample['wallet_per_hour'],36000)
        self.assertEqual(sample['notification_per_hour'],8129)

    def test_wallet_spike_missing_frame_and_old_timestamp_cannot_poison_baseline(self):
        check=LiveWalletCheck()
        for t,balance in enumerate((1000,1001,19000,1002,1003)):
            check.observe(True,balance,t)
        self.assertEqual(check.current,(3,1002))
        check.observe(True,99999,2)
        self.assertEqual(check.current,(3,1002))
        check.observe(False,None,5)
        self.assertFalse(check.snapshot(8)['live'])
        check.observe(True,1020,8)
        self.assertEqual(check.current,(3,1002))
        check.observe(True,1021,8.5)
        self.assertEqual(check.current,(8,1020))

    def test_live_comparison_is_exported_with_its_last_wallet_endpoint(self):
        session=CounterSession()
        check=LiveWalletCheck()
        session.wallet_checks.append(check)
        check.observe(True,1000,0)
        check.observe(True,1010,1)
        session.accept('coin','mesos',10,'white',True,observed_at=.5)
        check.observe(True,1020,2)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'summary.csv'
            session.export_summary(path)
            with path.open(encoding='utf-8-sig') as handle:
                data=next(r[1] for r in csv.reader(handle) if r and r[0]=='wallet_live_check')
            sample=json.loads(data)
            self.assertEqual(sample['difference'],0)
            self.assertEqual(sample['current'],[1,1010])

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
