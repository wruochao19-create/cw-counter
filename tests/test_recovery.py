import csv
import json
import tempfile
import tkinter as tk
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch,Mock
from PIL import Image
import app
from auto_calibration import AutoRegion,search_box
from map_reader import MapMonitor
from pixel_ocr import NotificationTracker,RapidReader
from windows_capture import covered_by_monitors,visible_region
from character_reader import CharacterMonitor


def notification(x=850,y=550,amount=15):
    return dict(text=f'You received EXP (+{amount})',score=.99,box=(x,y,x+140,y+20),
                said=('exp',amount),color='white',digit_verified=True,map_verified=True)


class AutoRegionTests(unittest.TestCase):
    def test_slow_ocr_frames_still_confirm_once_instead_of_stalling(self):
        tracker=NotificationTracker();tracker.update([],0)
        events=[]
        for t in (.9,1.8,2.7,3.6):
            new,gap=tracker.update([notification()],t)
            self.assertFalse(gap)
            events.extend(new)
        self.assertEqual(len(events),1)
        _,gap=tracker.update([notification()],6.)
        self.assertTrue(gap)

    def test_search_includes_right_edge_and_rolling_rows(self):
        box=search_box(2560,1600)
        self.assertEqual(box[2],2560)
        self.assertLess(box[1],1100)
        self.assertGreater(box[3],1300)

    def test_two_frames_locate_and_preserve_old_row_context(self):
        region=AutoRegion(1000,700)
        x,y=region.box[:2]
        row=notification(x=850-x,y=550-y)
        self.assertIsNone(region.observe([row],0))
        change=region.observe([row],.3)
        self.assertIsNotNone(change)
        left,top,right,bottom=region.box
        self.assertEqual(region.phase,'ready')
        self.assertLessEqual(top,550-7*35)
        self.assertEqual(right,1000)
        self.assertGreater(bottom,570)
        self.assertEqual(AutoRegion(1000,700,region.settings()).box,region.box)

    def test_old_manual_small_region_is_not_trusted(self):
        bad=dict(width=2560,height=1600,region=[2112,1240,2560,1600])
        self.assertEqual(AutoRegion(2560,1600,bad).box,search_box(2560,1600))

    def test_mismatched_size_invalid_cache_and_idle_wider_search(self):
        saved=dict(version=1,width=800,height=600,region=[500,300,800,500])
        region=AutoRegion(1000,700,saved)
        self.assertEqual(region.box,region.search)
        region.expand_if_idle(0)
        change=region.expand_if_idle(6.1)
        self.assertIsNotNone(change)
        self.assertEqual(region.box,region.wide)
        self.assertIsNone(region.expand_if_idle(6.2))

    def test_rebase_keeps_pending_and_baseline_message_identity(self):
        reader=RapidReader.__new__(RapidReader)
        reader.tracker=NotificationTracker()
        reader.tracker.update([],0)
        reader.tracker.update([notification(x=1,y=100)],.2)
        reader.rebase((0,400,300,600),(0,300,300,600))
        events,_=reader.tracker.update([notification(x=1,y=200)],.4)
        self.assertEqual(len(events),1)


class ScreenGeometryTests(unittest.TestCase):
    def test_visible_clip_allows_bottom_crop_but_keeps_numeric_edge(self):
        rect=(0,30,2560,1600)
        monitors=[(0,0,2560,1440)]
        self.assertEqual(visible_region(rect,(1800,800,2560,1550),monitors),(1800,800,2560,1410))
        self.assertFalse(covered_by_monitors((0,0,300,100),[(0,0,100,100),(200,0,300,100)]))
        self.assertTrue(covered_by_monitors((0,0,300,100),[(0,0,100,100),(100,0,300,100)]))


class RealAutomaticRegionTests(unittest.TestCase):
    def test_user_picture_auto_locates_and_counts_35_without_a_manual_box(self):
        from catalog import Catalog
        from counter import CounterSession
        image=Image.new('RGB',(917,574))
        patch_image=Image.open(Path(__file__).parent/'data/auto-search-exp35.png').convert('RGB')
        image.paste(patch_image,(458,172))
        region=AutoRegion(*image.size)
        reader=RapidReader(Catalog().profile('The Road to the Dungeon'))
        counter=CounterSession(reader.profile)
        reader.read(Image.new('RGB',(region.box[2]-region.box[0],region.box[3]-region.box[1])),0)
        for n in range(1,5):
            events,_=reader.read(image.crop(region.box),n*.3)
            relocation=region.observe(reader.last_lines,n*.3)
            if relocation:reader.rebase(*relocation)
            for event in events:counter.accept(**event)
        self.assertEqual(region.phase,'ready')
        self.assertEqual(sum(counter.counts.values()),1)
        self.assertEqual(counter.personal_exp,35)

    def test_auto_search_does_not_force_faded_17_into_an_orange_mushroom(self):
        from catalog import Catalog
        from counter import CounterSession
        image=Image.new('RGB',(908,566))
        patch_image=Image.open(Path(__file__).parent/'data/auto-search-faded.png').convert('RGB')
        image.paste(patch_image,(454,170))
        region=AutoRegion(*image.size)
        reader=RapidReader(Catalog().profile('The Road to the Dungeon'))
        counter=CounterSession(reader.profile)
        reader.read(Image.new('RGB',(region.box[2]-region.box[0],region.box[3]-region.box[1])),0)
        for n in range(1,5):
            events,_=reader.read(image.crop(region.box),n*.3)
            relocation=region.observe(reader.last_lines,n*.3)
            if relocation:reader.rebase(*relocation)
            for event in events:counter.accept(**event)
        self.assertEqual(counter.counts['Orange Mushroom'],0)
        for event in reader.finish():counter.accept(**event)
        self.assertGreater(counter.unresolved,0)


class FakeWorld:
    def __init__(self):
        self.now=0.;self.hwnd=11;self.exists=True;self.focus=False
        self.rect=(0,0,1000,700);self.specs=[];self.grabs=0
        self.map_name='The Road to the Dungeon';self.map_valid=True
        self.extras=[]

    def windows(self):
        return ([(self.hwnd,'MapleStory')] if self.exists else [])+self.extras

    def grab(self,hwnd,box):
        self.grabs+=1
        image=Image.new('RGB',(box[2]-box[0],box[3]-box[1]),
                        'black' if self.map_name=='The Road to the Dungeon' else 'white')
        image.info['region']=box
        return image

    def recognize_map(self,image):
        return dict(name=self.map_name,box=(2,2,100,22)) if self.map_valid else None


class FakeReader:
    def __init__(self,world,profile=None):
        self.world=world;self.profile=profile;self.tracker=NotificationTracker();self.last_lines=[]
        self.reset_count=0

    def reset(self):
        self.reset_count+=1;self.tracker.reset();self.last_lines=[]

    def set_profile(self,profile):
        self.profile=dict(profile);self.reset()

    def rebase(self,old,new):
        RapidReader.rebase(self,old,new)

    def read(self,image,timestamp):
        l,t,r,b=image.info['region'];rows=[]
        for source in self.world.specs:
            x,y,right,bottom=source['box']
            if x>=l and y>=t and right<=r and bottom<=b:
                row=dict(source,box=(x-l,y-t,right-l,bottom-t))
                row['map_verified']=source['said'][1] in set((self.profile or {}).values())
                rows.append(row)
        self.last_lines=rows
        return self.tracker.update(rows,timestamp)


class RecoveryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)
        self.world=FakeWorld()
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        patches=[patch.object(app,'CONFIG',self.path/'settings.json'),patch.object(app,'OUTPUT',self.path),
                 patch.object(app.capture,'enumerate_windows',side_effect=self.world.windows),
                 patch.object(app.capture,'window_exists',side_effect=lambda h:self.world.exists and h==self.world.hwnd),
                 patch.object(app.capture,'client_rect',side_effect=lambda h:self.world.rect if self.world.exists else None),
                 patch.object(app.capture,'foreground',side_effect=lambda h:self.world.focus),
                 patch.object(app.capture,'grab_region',side_effect=self.world.grab),
                 patch.object(app.capture,'monitor_rectangles',return_value=[(0,0,1920,1080)]),
                 patch.object(app.time,'monotonic',side_effect=lambda:self.world.now),
                 patch.object(app,'RapidReader',side_effect=lambda p=None:FakeReader(self.world,p)),
                 patch.object(app,'MapMonitor',side_effect=lambda c:MapMonitor(c,self.world.recognize_map)),
                 patch.object(app,'CharacterMonitor',side_effect=lambda:CharacterMonitor(lambda image:None))]
        for item in patches:self.stack.enter_context(item)
        self.root=tk.Tk();self.root.withdraw()
        self.ui=app.App(self.root)
        self.addCleanup(self.finish)

    def finish(self):
        self.ui.stop()
        self.root.destroy()

    def cancel_tick(self):
        if self.ui.tick_job:self.root.after_cancel(self.ui.tick_job);self.ui.tick_job=None

    def step(self,t):
        self.world.now=t;self.ui.capture_step(t)

    def begin(self):
        self.ui.start();self.cancel_tick()
        self.world.focus=True
        for t in (.1,.4,.9):self.step(t)

    def test_our_overlay_pauses_then_resumes_without_losing_session(self):
        self.begin()
        session=self.ui.session
        before=self.world.grabs
        with patch.object(app.capture,'overlay_occludes',return_value=True):
            self.step(1.2)
        self.assertEqual(self.world.grabs,before)
        self.assertIn('面板遮住',self.ui.status.get())
        self.assertTrue(self.ui.needs_resume)
        with patch.object(app.capture,'overlay_occludes',return_value=False):
            for t in (1.5,2.,2.5):self.step(t)
        self.assertIs(self.ui.session,session)
        self.assertTrue(self.ui.was_valid)

    def test_no_manual_calibration_and_browser_return_continues_same_session(self):
        self.assertFalse(hasattr(self.ui,'cal_button'))
        self.ui.start();self.cancel_tick()
        self.assertTrue(self.ui.running)
        self.assertEqual(self.world.grabs,0)
        self.world.focus=True
        for t in (.1,.4,.9):self.step(t)
        self.world.specs=[notification()]
        self.step(1.2);self.step(1.5)
        self.assertEqual(sum(self.ui.session.counts.values()),1)
        self.assertEqual(self.ui.auto_region.phase,'ready')
        path=self.ui.session.path
        self.world.focus=False
        captures=self.world.grabs
        self.step(1.8);resets=self.ui.reader.reset_count;self.step(2.1)
        self.assertEqual(self.world.grabs,captures)
        self.assertEqual(self.ui.reader.reset_count,resets)
        self.world.focus=True;self.world.rect=(150,80,1000,700)
        self.step(3.2);self.step(3.7);self.step(4.)
        self.assertEqual(sum(self.ui.session.counts.values()),1)  # old visible message suppressed
        self.world.specs=[notification(),notification(y=520)]
        self.step(4.3);self.step(4.6)
        self.assertEqual(sum(self.ui.session.counts.values()),2)
        self.assertEqual(self.ui.session.path,path)
        self.assertTrue(self.ui.running)

    def test_resize_and_closed_window_reconnect_without_manual_action(self):
        self.begin()
        self.world.specs=[notification()];self.step(1.2);self.step(1.5)
        self.world.rect=(10,10,1200,800);self.world.specs=[]
        for t in (1.8,2.1,2.6):self.step(t)
        self.assertTrue(self.ui.running)
        self.assertEqual((self.ui.calibration.width,self.ui.calibration.height),(1200,800))
        self.world.specs=[notification(x=1050,y=650)]
        self.step(2.9);self.step(3.2)
        self.assertEqual(sum(self.ui.session.counts.values()),2)
        self.world.exists=False;self.step(3.5)
        self.assertTrue(self.ui.running)
        self.world.exists=True;self.world.hwnd=22;self.world.specs=[]
        for t in (5.6,5.9,6.4):self.step(t)
        self.assertEqual(self.ui.hwnd,22)
        self.assertTrue(self.ui.was_valid)
        self.assertEqual(sum(self.ui.session.counts.values()),2)

    def test_map_failure_recovers_without_losing_existing_total(self):
        self.begin();self.world.specs=[notification()];self.step(1.2);self.step(1.5)
        self.world.focus=False;self.step(1.8)
        self.world.focus=True;self.world.map_valid=False
        self.step(3.);self.step(3.6)
        self.assertIn('地图确认中',self.ui.status.get())
        self.assertEqual(sum(self.ui.session.counts.values()),1)
        self.world.map_valid=True
        self.step(4.2);self.step(4.7)
        self.world.specs=[notification(),notification(y=520)]
        self.step(5.);self.step(5.3)
        self.assertEqual(sum(self.ui.session.counts.values()),2)

    def test_refresh_preserves_target_and_shows_offscreen_reason(self):
        self.begin()
        self.world.extras=[(99,'Other window')]
        self.ui.refresh_windows()
        self.assertEqual(self.ui.selected_window(),11)
        self.world.rect=(1500,0,1000,700)
        self.step(1.2)
        self.assertIn('移出屏幕',self.ui.status.get())
        self.world.rect=(100,0,1000,700)
        self.step(1.5);self.step(2.)
        self.assertTrue(self.ui.was_valid)

    def test_focus_change_during_capture_discards_frame_and_then_recovers(self):
        self.begin()
        self.world.specs=[notification()]
        def switch_during_grab(hwnd,box):
            result=self.world.grab(hwnd,box)
            self.world.focus=False
            return result
        with patch.object(app.capture,'grab_region',side_effect=switch_during_grab):
            self.step(1.2)
        self.assertTrue(self.ui.needs_resume)
        self.assertEqual(sum(self.ui.session.counts.values()),0)
        self.world.focus=True;self.world.specs=[]
        self.step(1.5);self.step(2.)
        self.world.specs=[notification()]
        self.step(2.3);self.step(2.6)
        self.assertEqual(sum(self.ui.session.counts.values()),1)

    def test_capture_error_is_retryable_without_ending_session(self):
        self.begin()
        self.world.now=1.2
        with patch.object(app.capture,'grab_region',side_effect=RuntimeError('temporary capture failure')):
            self.ui.tick();self.cancel_tick()
        self.assertTrue(self.ui.running)
        self.assertIn('读取暂时失败',self.ui.status.get())
        self.step(1.5);self.step(2.)
        self.world.specs=[notification()]
        self.step(2.3);self.step(2.6)
        self.assertEqual(sum(self.ui.session.counts.values()),1)

    def test_window_taller_than_monitor_can_use_visible_exp_and_map(self):
        self.world.rect=(0,30,1000,1200)
        self.begin()
        self.world.specs=[notification(y=960)]
        self.step(1.2);self.step(1.5)
        self.assertTrue(self.ui.running)
        self.assertEqual(sum(self.ui.session.counts.values()),1)

    def test_restart_reuses_verified_region_without_calibration_dialog(self):
        self.begin();self.world.specs=[notification()];self.step(1.2);self.step(1.5)
        saved=tuple(json.loads((self.path/'settings.json').read_text('utf-8'))['auto_region']['region'])
        self.ui.stop()
        root=tk.Tk();root.withdraw()
        second=app.App(root)
        try:
            self.world.now=2.;second.start()
            if second.tick_job:root.after_cancel(second.tick_job);second.tick_job=None
            self.assertTrue(second.running)
            self.assertEqual(second.auto_region.box,saved)
            self.assertFalse(hasattr(second,'cal_button'))
        finally:second.stop();root.destroy()
