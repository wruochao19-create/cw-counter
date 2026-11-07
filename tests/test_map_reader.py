import csv
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
from PIL import Image
from catalog import Catalog
from counter import CounterSession
from map_reader import MapMonitor,identify_map,title_box
from pixel_ocr import apply_map_constraint,retry_with_map,NotificationTracker,RapidReader
from test_pixel_ocr import line


class MapTests(unittest.TestCase):
    def test_candidate_retry_uses_pixels_and_does_not_force_nearest_number(self):
        profile={'Pig':13,'Orange Mushroom':15,'Ribbon Pig':19}
        def detail(value):
            text=f'You received EXP (+{value})'
            return (text,.99,[None,None,None,None,[.99]*len(text)])
        image=Image.new('RGB',(220,140))
        for original,verified,reads,expected in [(17,True,(15,15),17), # strong out-of-table EXP is preserved
                                                (15,False,(19,19),15), # two in-map possibilities remain ambiguous
                                                (None,False,(19,19),19), # missing digits recovered from two actual rereads
                                                (None,False,(15,19),None),
                                                (None,False,(22,22),None)]:
            row=line(original or 1)
            row.update(text='You received EXP' if original is None else f'You received EXP (+{original})',
                       said=None if original is None else ('exp',original),digit_verified=verified)
            fake=Mock()
            fake.text_rec.return_value=([detail(value) for value in reads],0)
            with patch('pixel_ocr.model',return_value=fake):
                retry_with_map(image,[row],profile)
            self.assertEqual(row['said'][1] if row['said'] else None,expected)

    def test_single_character_change_invalidates_cached_map(self):
        image=Image.new('RGB',(200,40),'black')
        recognizer=Mock(return_value=dict(name='Map I',box=(0,0,200,40)))
        monitor=MapMonitor(Catalog(),recognizer)
        monitor.observe(image,0);self.assertEqual(monitor.observe(image,.5),'Map I')
        changed=image.copy()
        for y in range(8,28):
            for x in range(150,153):changed.putpixel((x,y),(255,255,255))
        self.assertIsNone(monitor.observe(changed,.6))

    def test_real_minimap_title_matches_database(self):
        image=Image.open(Path(__file__).parent/'data/user-map-road.png').convert('RGB')
        found=identify_map(image,Catalog())
        self.assertIsNotNone(found)
        self.assertEqual(found['name'],'The Road to the Dungeon')

    def test_roman_variants_and_unknown_titles_are_not_guessed(self):
        catalog=SimpleNamespace(maps=['Test Path I','Test Path II'])
        for text,expected in [('Test Path I','Test Path I'),('Test Path II','Test Path II'),
                              ('Test Path',None),('Test Path 1',None),('Warning Street',None)]:
            with patch('map_reader.scan',return_value=[dict(text=text,score=.99,box=(1,1,90,15))]):
                result=identify_map(Image.new('RGB',(100,30)),catalog)
                self.assertEqual(result['name'] if result else None,expected)

    def test_per_frame_cache_and_immediate_pause_on_title_change(self):
        black=Image.new('RGB',(100,40),'black')
        white=Image.new('RGB',(100,40),'white')
        def recognize(image):
            return dict(name='A' if image.getpixel((5,5))[0]==0 else 'B',box=(2,2,90,20))
        recognizer=Mock(side_effect=recognize)
        monitor=MapMonitor(Catalog(),recognizer)
        self.assertIsNone(monitor.observe(black,0))
        self.assertEqual(monitor.observe(black,.5),'A')
        self.assertEqual(monitor.observe(black,.6),'A')
        self.assertEqual(recognizer.call_count,2)
        self.assertIsNone(monitor.observe(white,.7))  # no stale A allowed
        self.assertIsNone(monitor.observe(white,1.0))
        self.assertEqual(monitor.observe(white,1.5),'B')
        self.assertEqual(recognizer.call_count,4)

    def test_unreadable_map_blocks_old_profile(self):
        found=dict(name='A',box=(0,0,100,40))
        recognizer=Mock(side_effect=[found,found,None])
        monitor=MapMonitor(Catalog(),recognizer)
        image=Image.new('RGB',(100,40))
        monitor.observe(image,0);self.assertEqual(monitor.observe(image,.5),'A')
        self.assertIsNone(monitor.observe(Image.new('RGB',(100,40),'white'),1))

    def test_map_filter_does_not_round_17_to_an_expected_15(self):
        profile={'Pig':13,'Orange Mushroom':15}
        row=line(17)
        apply_map_constraint([row],profile)
        self.assertEqual(row['said'],('exp',17))
        self.assertFalse(row['map_verified'])
        tracker=NotificationTracker();tracker.update([],0)
        session=CounterSession(profile)
        for t in (.2,.4,.6,.8):
            for event in tracker.update([row],t)[0]:session.accept(**event)
        self.assertEqual(sum(session.counts.values()),0)
        for event in tracker.finish():session.accept(**event)
        self.assertEqual(session.unresolved,1)

    def test_party_exp_is_excluded_even_when_not_in_map_exp_set(self):
        row=line(7,color='yellow')
        apply_map_constraint([row],{'A':35})
        self.assertNotIn('map_verified',row)

    def test_real_map_and_notification_pipeline(self):
        root=Path(__file__).parent/'data'
        found=identify_map(Image.open(root/'user-map-road.png'),Catalog())
        profile=Catalog().profile(found['name'])
        image=Image.open(root/'user-exp35.png').convert('RGB')
        reader=RapidReader(profile);session=CounterSession(profile,map_name=found['name'])
        for n,frame in enumerate([Image.new('RGB',image.size),image,image,image]):
            for event in reader.read(frame,n*.3)[0]:session.accept(**event)
        self.assertEqual(session.personal_exp,35)
        self.assertEqual(sum(session.counts.values()),1)

    def test_title_region_remains_inside_client(self):
        self.assertEqual(title_box(2560,1600),(0,0,640,208))
        self.assertEqual(title_box(200,50),(0,0,200,50))


class SessionSwitchTests(unittest.TestCase):
    def test_map_switch_saves_separate_counts(self):
        import app
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            with patch.object(app,'CONFIG',base/'missing.json'),patch.object(app,'OUTPUT',base),\
                 patch.object(app.capture,'enumerate_windows',return_value=[]):
                root=tk.Tk();root.withdraw()
                ui=app.App(root)
                ui.reader=Mock()
                ui.reader.finish.return_value=[]
                ui.session.open_log(base)
                ui.running=True
                try:
                    ui.apply_detected_map('The Road to the Dungeon')
                    ui.session.accept('1','exp',15,'white')
                    ui.apply_detected_map('Ant Tunnel I')
                    self.assertEqual(sum(ui.session.counts.values()),0)
                    ui.session.accept('2','exp',41,'white')
                    ui.stop()
                    summaries=list(base.glob('*-summary.csv'))
                    self.assertEqual(len(summaries),2)
                    maps=set()
                    for path in summaries:
                        with path.open(encoding='utf-8-sig',newline='') as handle:
                            rows=list(csv.reader(handle))
                        counted=[row for row in rows[1:] if len(row)==7 and row[3]=='1']
                        self.assertEqual(len(counted),1)
                        maps.add(counted[0][1])
                    self.assertEqual(maps,{'The Road to the Dungeon','Ant Tunnel I'})
                finally:
                    ui.session.close();ui.close()
