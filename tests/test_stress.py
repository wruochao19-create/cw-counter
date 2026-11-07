import random
import os
import unittest
from unittest.mock import patch,Mock
from PIL import Image,ImageDraw,ImageFont
from auto_calibration import AutoRegion
from pixel_ocr import NotificationTracker,RapidReader,text_metrics


def line(amount=12,y=300,brightness=240,contrast=220,verified=True):
    return dict(text=f'You received EXP (+{amount})',score=.99,box=(5,y,220,y+12),
                said=('exp',amount),color='white',digit_verified=verified,map_verified=True,
                brightness=brightness,contrast=contrast)


def simulate(amounts,spacing=.9,sample=.3,weak_initial=False):
    schedule=[];timestamp=1.
    for i,amount in enumerate(amounts):
        schedule.append((timestamp,amount))
        timestamp+=spacing[i%len(spacing)] if isinstance(spacing,list) else spacing
    tracker=NotificationTracker();events=[]
    for n in range(int((schedule[-1][0]+4)/sample)+1):
        now=n*sample
        active=[(born,amount) for born,amount in reversed(schedule) if 0<=now-born<2.8]
        rows=[line(amount,300-index*25,255-(now-born)*45,230-(now-born)*45,
                   verified=not weak_initial or now-born>=.4)
              for index,(born,amount) in enumerate(active)]
        events.extend(tracker.update(rows,now)[0])
    return [event for event in events if event['confident']]


class SustainedTrackingTests(unittest.TestCase):
    def test_same_monster_20_kills_at_five_speeds(self):
        for spacing in (.6,.9,1.2,2.,3.):
            with self.subTest(spacing=spacing):
                events=simulate([12]*20,spacing)
                self.assertEqual(len(events),20)
                self.assertEqual(len({row['event_id'] for row in events}),20)

    def test_mixed_monsters_with_irregular_intervals(self):
        expected=[12,21,26,41]*10
        events=simulate(expected,[.8,1.1,1.5])
        self.assertEqual([row['amount'] for row in events],expected)

    def test_slow_sampling_does_not_lock_two_frame_confirmation(self):
        events=simulate([12,21,26,41]*5,2.5,.9)
        self.assertEqual(len(events),20)

    def test_initial_weak_digits_can_recover_before_uncertain_is_final(self):
        events=simulate([12,21,26,41]*5,1.3,.3,weak_initial=True)
        self.assertEqual(len(events),20)

    def test_stationary_text_brightness_noise_and_scene_flash_do_not_count(self):
        tracker=NotificationTracker()
        base=[line(y=300-index*25,brightness=220-index*35,contrast=200-index*35) for index in range(3)]
        tracker.update(base,0)
        rng=random.Random(97);events=[]
        for n in range(1,120):
            rows=[]
            for index,original in enumerate(base):
                row=dict(original)
                row['brightness']+=rng.uniform(-4,4)
                row['contrast']+=rng.uniform(-4,4)
                # Whole-scene flashes raise luminance without increasing text contrast.
                if n in (20,21,70):row['brightness']+=30
                # One changed row alone does not establish a stack scroll.
                if n in (40,41) and index==0:
                    row['brightness']+=25;row['contrast']+=25
                rows.append(row)
            events.extend(tracker.update(rows,n*.3)[0])
        self.assertEqual(events,[])


class RenderedFrameTests(unittest.TestCase):
    def test_small_exp_with_interleaved_coins_on_a_changing_brown_background(self):
        from counter import CounterSession
        font=ImageFont.truetype(os.path.join(os.environ.get('WINDIR',r'C:\Windows'),'Fonts','arial.ttf'),14)
        profile={'Dark Stump':21,'Axe Stump':32,'Dark Axe Stump':43,'Wild Boar':46,'Fire Boar':60}
        reader=RapidReader(profile);counter=CounterSession(profile)
        amounts=[21,32,43,46,60,21];schedule=[]
        for i,amount in enumerate(amounts):
            birth=1+i*1.6;schedule.append((birth,'exp',amount))
            schedule.extend((birth+d,'mesos',100+i*3+j) for j,d in enumerate((.18,.45,.7)))
        schedule.sort()
        for n in range(37):
            now=n*.4
            image=Image.new('RGB',(512,300),(60,42,28));draw=ImageDraw.Draw(image)
            for x in range(0,512,13):draw.line((x+round(now)%5,0,x+30,300),fill=(70,50,30),width=3)
            active=[v for v in reversed(schedule) if 0<=now-v[0]<4][:8]
            for index,(birth,kind,amount) in enumerate(active):
                value=round(255-(now-birth)*25)
                text=f'You received EXP (+{amount})' if kind=='exp' else f'You have gained mesos (+{amount})'
                color=(value,)*3 if kind=='exp' else (value,round(value*.85),0)
                draw.text((505-draw.textlength(text,font=font),250-index*25),text,font=font,
                          fill=color,stroke_width=1,stroke_fill=(0,0,0))
            for event in reader.read(image,now)[0]:counter.accept(**event)
        self.assertEqual(sum(counter.counts.values()),6)
        self.assertEqual(counter.personal_exp,sum(amounts))
        self.assertEqual(counter.unresolved,0)

    def test_real_ocr_on_fading_same_value_stack(self):
        from counter import CounterSession
        font=ImageFont.truetype(os.path.join(os.environ.get('WINDIR',r'C:\Windows'),'Fonts','arial.ttf'),24)
        reader=RapidReader({'Slime':12});counter=CounterSession({'Slime':12})
        births=[1+i*.9 for i in range(6)]
        for n in range(int((births[-1]+3.5)/.3)+1):
            now=n*.3
            image=Image.new('RGB',(480,230),(40,65,75));draw=ImageDraw.Draw(image)
            active=[born for born in reversed(births) if 0<=now-born<2.8]
            for index,born in enumerate(active):
                value=round(255-(now-born)*45);text='You received EXP (+12)'
                draw.text((475-draw.textlength(text,font=font),180-index*32),text,font=font,
                          fill=(value,)*3,stroke_width=1,stroke_fill=(0,0,0))
            for event in reader.read(image,now)[0]:counter.accept(**event)
        self.assertEqual(sum(counter.counts.values()),6)
        self.assertEqual(counter.personal_exp,72)


class IdleAndCacheTests(unittest.TestCase):
    def test_five_minute_idle_probes_return_to_small_region(self):
        region=AutoRegion(1000,700,dict(version=1,width=1000,height=700,region=[640,250,1000,610]))
        small=region.box
        region.phase='ready';region.last_evidence=0
        wide_frames=0;probes=0
        for n in range(1,601):
            now=n*.5
            if region.expand_if_idle(now):probes+=1
            wide_frames+=region.box==region.wide
            region.observe([],now)
        self.assertEqual(region.box,small)
        self.assertLessEqual(probes,10)
        self.assertLessEqual(wide_frames,22)

    def test_static_frames_reuse_ocr_but_confirm_only_one_message(self):
        with patch('pixel_ocr.model',return_value=Mock()),patch('pixel_ocr.scan',return_value=[]) as scan:
            reader=RapidReader()
            reader.read(Image.new('RGB',(240,320),'black'),0)
            picture=Image.new('RGB',(240,320),'white')
            scan.return_value=[line()]
            events=[]
            for n in range(1,6):events.extend(reader.read(picture,n*.2)[0])
            self.assertEqual(len(events),1)
            self.assertEqual(scan.call_count,2)
            self.assertTrue(reader.last_diagnostics['ocr_cache_hit'])
            changed=picture.copy();changed.putpixel((0,0),(0,0,0))
            reader.read(changed,1.2)
            self.assertEqual(scan.call_count,3)
            reader.reset();reader.read(picture,1.4)
            self.assertEqual(scan.call_count,4)

    def test_text_contrast_distinguishes_scene_lighting_from_new_text(self):
        def image(foreground,background):
            canvas=Image.new('RGB',(100,20),(background,)*3)
            draw=ImageDraw.Draw(canvas)
            for x in range(5,90,8):draw.rectangle((x,4,x+2,15),fill=(foreground,)*3)
            return canvas
        first=text_metrics(image(180,0),(0,0,100,20),'white')
        lit=text_metrics(image(210,30),(0,0,100,20),'white')
        fresh=text_metrics(image(240,0),(0,0,100,20),'white')
        self.assertGreater(lit[0],first[0]);self.assertEqual(lit[1],first[1])
        self.assertGreater(fresh[1],first[1])
