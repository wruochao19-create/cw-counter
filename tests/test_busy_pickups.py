"""Busy notification stacks with known pickup amounts and ordinary pixel OCR."""
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image,ImageDraw,ImageFont

from counter import CounterSession
from pixel_ocr import RapidReader,NotificationStrips,scan


class BusyPickupTests(unittest.TestCase):
    def test_real_coin_crops_keep_same_amount_across_fast_frames(self):
        data=Path(__file__).parent/'data'
        first=Image.open(data/'coin-23-a.png').convert('RGB')
        second=Image.open(data/'coin-23-b.png').convert('RGB')
        layout=NotificationStrips()
        layout.learn(scan(first))
        lines=layout.read(second,None)
        coins=[r for r in lines if r['said'][0]=='mesos']
        self.assertEqual(len(coins),1)
        self.assertEqual(coins[0]['said'][1],23)
        self.assertTrue(coins[0]['digit_verified'])

    @staticmethod
    def frame(schedule,now):
        image=Image.new('RGB',(520,300),(40,65,75))
        draw=ImageDraw.Draw(image)
        font=ImageFont.truetype(os.path.join(os.environ.get('WINDIR',r'C:\Windows'),'Fonts','arial.ttf'),21)
        for index,(born,kind,amount) in enumerate([r for r in reversed(schedule) if 0<=now-r[0]<3][:8]):
            value=round(255-(now-born)*35)
            text=f'You have gained mesos (+{amount})' if kind=='mesos' else f'Bonus EXP for PARTY (+{amount})'
            color=(value,)*3 if kind=='mesos' else (value,round(value*.9),0)
            draw.text((514-draw.textlength(text,font=font),255-index*29),text,font=font,
                      fill=color,stroke_width=1,stroke_fill=(0,0,0))
        return image

    def test_fast_rows_count_busy_party_and_identical_bags_without_duplicates(self):
        expected=[23,23,52,23,52,52,23,23,52,23,23,52]
        schedule=[]
        for i,value in enumerate(expected):
            at=1+i*.24
            schedule.extend(((at,'mesos',value),(at+.12,'bonus',3)))
        for interval in (.1,.2):
            with self.subTest(interval=interval):
                reader=RapidReader()
                session=CounterSession()
                modes=[]
                for n in range(round(6.5/interval)):
                    now=n*interval
                    events,_=reader.read(self.frame(schedule,now),now)
                    modes.append(reader.last_diagnostics['ocr_mode'])
                    for event in events:session.accept(**event)
                for event in reader.finish():session.accept(**event)
                coins=[r for r in session.events if r['type']=='mesos' and r['status']=='counted']
                self.assertEqual([r['mesos'] for r in coins],expected)
                self.assertEqual(session.coin_total,sum(expected))
                self.assertIn('strips',modes)
                self.assertEqual(len({r['event_id'] for r in coins}),len(expected))

    def test_empty_fast_rows_eventually_search_again_and_rebase_discards_old_layout(self):
        reader=RapidReader()
        image=self.frame([(0,'mesos',23)],0)
        reader.read(image,0)
        self.assertIsNotNone(reader.strips.height)
        empty=Image.new('RGB',image.size,'black')
        reader.read(empty,.3)
        with patch('pixel_ocr.scan',return_value=[]) as detector:
            changed=empty.copy();changed.putpixel((0,0),(255,255,255))
            reader.read(changed,1.5)
            self.assertEqual(detector.call_count,1)
        reader.rebase((0,0,520,300),(0,20,520,300))
        self.assertIsNone(reader.strips.height)
