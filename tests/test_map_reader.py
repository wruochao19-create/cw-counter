import csv
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
from PIL import Image
import numpy as np
from catalog import Catalog
from counter import CounterSession
from map_reader import MapMonitor,identify_map,title_box,glyph_mask,verify_title,vertical_roman
from pixel_ocr import apply_map_constraint,retry_with_map,NotificationTracker,RapidReader
from test_pixel_ocr import line


class MapTests(unittest.TestCase):
    def test_user_decayed_tunnel_iii_original_font_across_capture_sizes(self):
        with Image.open(Path(__file__).parent/'data/user-map-decayed-iii.png') as image:
            original=image.convert('RGB')
        for scale in (.75,1,1.25,1.5,2):
            sample=original.resize((round(original.width*scale),round(original.height*scale)),Image.Resampling.BICUBIC)
            for size in (sample.size,(1024,260)):
                canvas=Image.new('RGB',size,(80,100,70));canvas.paste(sample)
                with self.subTest(scale=scale,size=size):
                    found=identify_map(canvas,Catalog())
                    self.assertIsNotNone(found)
                    self.assertEqual(found['name'],'Decayed Tunnel III')
                    self.assertEqual(found.get('roman_glyphs'),'III')

    def test_counted_strokes_keep_i_ii_iii_separate_and_reject_v(self):
        with Image.open(Path(__file__).parent/'data/user-map-decayed-iii.png') as image:
            original=image.convert('RGB')
        for count in (1,2,3):
            image=original.copy()
            image.paste(original.getpixel((300,90)),(273,77,310,104))
            for i in range(count):image.paste(original.crop((275,77,279,104)),(275+i*6,77))
            self.assertEqual(vertical_roman(image.crop((95,77,310,104))),'I'*count)
            self.assertEqual(identify_map(image,Catalog())['name'],'Decayed Tunnel '+'I'*count)
        self.assertIsNone(vertical_roman(self.roman_title('V').crop((96,83,380,111))))

    def test_stroke_recovery_abstains_on_confident_conflict_or_clipped_stems(self):
        with Image.open(Path(__file__).parent/'data/user-map-decayed-iii.png') as image:
            original=image.convert('RGB')
        found=dict(name='Decayed Tunnel II',raw='Decayed Tunnel II',box=(99,79,293,102))
        text='Decayed Tunnel II'
        reading=(text,.99,[None,None,None,None,[.99]*len(text)])
        with patch('map_reader.model') as model:
            model.return_value.text_rec.return_value=([reading]*3,0)
            self.assertIsNone(verify_title(original,found,Catalog()))
        self.assertIsNone(vertical_roman(original.crop((95,85,310,104))))

    def test_forgotten_hollow_region_heading_does_not_conflict_with_field(self):
        rows=[dict(text='Forgotten Hollow',score=.99,box=(20,15,200,35)),
              dict(text='Primeval Forest II',score=.99,box=(20,40,230,60))]
        with patch('map_reader.scan',return_value=rows):
            self.assertEqual(identify_map(Image.new('RGB',(300,90)),Catalog(),verify=False)['name'],'Primeval Forest II')
        with patch('map_reader.scan',return_value=rows[:1]):
            self.assertEqual(identify_map(Image.new('RGB',(300,90)),Catalog(),verify=False)['name'],'Forgotten Hollow')

    @staticmethod
    def roman_title(numeral):
        # Derived test image: reassemble actual I/V glyphs from the supplied IV
        # screenshot. These are synthetic variants, not captured V/VI/VII maps.
        with Image.open(Path(__file__).parent/'data/user-map-west-iv.png') as original:
            image=original.convert('RGB')
        result=Image.new('RGB',(420,128),image.getpixel((330,83)))
        result.paste(image.crop((0,0,338,128)))
        x=342
        for char in numeral:
            glyph=image.crop((340,82,349,113) if char=='I' else (349,82,366,113))
            result.paste(glyph,(x,82));x+=glyph.width
        return result

    def test_real_font_v_and_vi_at_six_scales(self):
        catalog=SimpleNamespace(maps=['West Rocky Mountain '+s for s in ('IV','V','VI','VII')])
        for numeral in ('V','VI'):
            original=self.roman_title(numeral)
            for scale in (.5,.75,1,1.25,1.5,2):
                image=original.resize((round(original.width*scale),round(original.height*scale)),Image.Resampling.BICUBIC)
                with self.subTest(numeral=numeral,scale=scale):
                    found=identify_map(image,catalog)
                    self.assertIsNotNone(found)
                    self.assertEqual(found['name'],'West Rocky Mountain '+numeral)

    def test_clipped_detector_box_is_repaired_using_actual_pixels(self):
        image=self.roman_title('VI')
        catalog=SimpleNamespace(maps=['West Rocky Mountain V','West Rocky Mountain VI'])
        # Detector omitted the final I. A name-only test would accept V.
        with patch('map_reader.scan',return_value=[dict(text='West Rocky Mountain V',score=.99,box=(99,85,359,109))]):
            self.assertEqual(identify_map(image,catalog)['name'],'West Rocky Mountain VI')

    def test_numbered_map_can_return_to_its_unnumbered_neighbour(self):
        image=Image.new('RGB',(200,50))
        found=dict(name='Pig Park',raw='Pig Park',box=(5,5,100,30))
        catalog=SimpleNamespace(maps=['Pig Park','Pig Park II'])
        reading=('Pig Park',.99,[None,None,None,None,[.99]*8])
        with patch('map_reader.model') as model:
            model.return_value.text_rec.return_value=([reading]*3,0)
            result=verify_title(image,found,catalog)
        self.assertEqual(result['name'],'Pig Park')
        self.assertTrue(result['verified'])

    def test_actual_font_vii_at_native_size_and_upscaled(self):
        catalog=SimpleNamespace(maps=['West Rocky Mountain '+s for s in ('V','VI','VII')])
        for scale in (1,1.25,2):
            original=self.roman_title('VII')
            image=original.resize((round(original.width*scale),round(original.height*scale)),Image.Resampling.BICUBIC)
            self.assertEqual(identify_map(image,catalog)['name'],'West Rocky Mountain VII')

    def test_background_colour_changes_cannot_accept_two_wrong_reads(self):
        original=self.roman_title('VI')
        box=(99,85,370,110)
        recognizer=Mock(return_value=dict(name='East Rocky Mountain VI',box=box,verified=True))
        monitor=MapMonitor(Catalog(),recognizer)
        monitor.observe(original,0);monitor.observe(original,.5)
        ref_box=monitor.box
        for n in range(1,25):
            array=np.asarray(original).copy()
            # Change blue background by enough to bypass the 0.30 RGB gate.
            mask=~glyph_mask(original).astype(bool)
            array[mask]=np.clip(array[mask].astype(int)+[0,0,(n%3)*12],0,255)
            recognizer.return_value=dict(name='East Rocky Mountain V',box=box,verified=True)
            self.assertEqual(monitor.observe(Image.fromarray(array),.5+n*.5),'East Rocky Mountain VI')
        self.assertEqual(monitor.box,ref_box)

    def test_unverified_or_brief_neighbour_reads_do_not_commit_a_switch(self):
        image=self.roman_title('VI')
        recognizer=Mock(return_value=dict(name='East Rocky Mountain VI',box=(99,85,370,110),verified=True))
        monitor=MapMonitor(Catalog(),recognizer)
        monitor.observe(image,0);monitor.observe(image,.5)
        other=self.roman_title('V')
        recognizer.return_value=dict(name='East Rocky Mountain V',box=(99,85,363,110))
        for t in (1,1.5,2,2.5,3):self.assertIsNone(monitor.observe(other,t))
        self.assertEqual(monitor.trusted,'East Rocky Mountain VI')
        recognizer.return_value['verified']=True
        for t in (3.5,4,4.5):self.assertIsNone(monitor.observe(other,t))
        self.assertEqual(monitor.observe(other,5),'East Rocky Mountain V')

    def test_title_fits_common_resolutions_at_multiple_ui_scales(self):
        for width,height in ((800,600),(1280,720),(1920,1080),(2560,1440),(3840,2160)):
            box=title_box(width,height)
            self.assertLessEqual(box[2],width)
            self.assertLessEqual(box[3],height)
            for scale in (1,1.25,1.5,2):
                if width>=1280 or scale==1:
                    self.assertGreaterEqual(box[2],380*scale)
                    self.assertGreaterEqual(box[3],110*scale)

    def test_v_vi_real_ocr_in_full_capture_regions_including_2560_borderless(self):
        catalog=SimpleNamespace(maps=['West Rocky Mountain V','West Rocky Mountain VI'])
        cases=[(800,600,1),(1280,720,1),(1920,1080,1),(3840,2160,2)]
        cases.extend((2560,1440,scale) for scale in (.5,1,1.25,1.5,2))
        for width,height,scale in cases:
            for numeral in ('V','VI'):
                sample=self.roman_title(numeral)
                sample=sample.resize((round(sample.width*scale),round(sample.height*scale)),Image.Resampling.BICUBIC)
                box=title_box(width,height)
                captured=Image.new('RGB',(box[2],box[3]),(80,100,70))
                captured.paste(sample)
                with self.subTest(client=(width,height),scale=scale,numeral=numeral):
                    found=identify_map(captured,catalog)
                    self.assertIsNotNone(found)
                    self.assertEqual(found['name'],'West Rocky Mountain '+numeral)

    def test_map_diagnostic_records_waiting_frames_with_shared_size_and_time_limits(self):
        from diagnostics import DiagnosticRecorder
        image=self.roman_title('VI')
        with tempfile.TemporaryDirectory() as directory:
            recorder=DiagnosticRecorder(directory,max_bytes=100000,duration=20)
            recorder.add_map(image,1,dict(result=None))
            self.assertTrue((recorder.path/'map-000.png').exists())
            self.assertTrue((recorder.path/'maps.jsonl').exists())
            recorder.add_map(image,21,dict(result=None))
            self.assertTrue(recorder.done)
            self.assertEqual(recorder.map_frames,1)
            capped=DiagnosticRecorder(directory,max_bytes=1)
            capped.add_map(image,1,{})
            self.assertTrue(capped.done)
            self.assertIsNone(capped.path)

    def test_east_west_neighbours_require_a_distinguishable_title(self):
        image=Image.new('RGB',(640,187))
        catalog=Catalog()
        for titles,expected in [
            (['Victoria Road','West Rocky Mountain IV'],'West Rocky Mountain IV'),
            (['East Rocky Mountain IV'],'East Rocky Mountain IV'),
            (['est Rocky Mountain IV'],None),
            (['East Rocky Mountain IV','West Rocky Mountain IV'],None),
        ]:
            with self.subTest(titles=titles), patch('map_reader.scan',return_value=[
                    dict(text=t,score=.92,box=(10,20,370,45)) for t in titles]):
                found=identify_map(image,catalog,verify=False)
                self.assertEqual(found['name'] if found else None,expected)

    def test_excavation_titles_and_angle_brackets_match_without_mixing_variants(self):
        for text,expected in [('Excavation Site II','Excavation Site II'),
                              ('Remains <Tomb> IV','Remains (Tomb) IV'),
                              ('Remains <Cliff>','Remains (Cliff)'),('Camp 2','Camp 2'),('Camp 4',None)]:
            with patch('map_reader.scan',return_value=[dict(text=text,score=.99,box=(0,0,220,24))]):
                found=identify_map(Image.new('RGB',(250,40)),Catalog(),verify=False)
                self.assertEqual(found['name'] if found else None,expected)

    def test_hidden_street_murky_swamp_titles_keep_roman_variants_separate(self):
        for title in ('The Murky Swamp I','The Murky Swamp II'):
            lines=[dict(text='Hidden Street',score=.99,box=(0,0,120,15)),
                   dict(text=title,score=.99,box=(0,16,210,34))]
            with patch('map_reader.scan',return_value=lines):
                result=identify_map(Image.new('RGB',(250,80)),Catalog(),verify=False)
                self.assertEqual(result['name'],title)

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
                result=identify_map(Image.new('RGB',(100,30)),catalog,verify=False)
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

    def test_unchanged_vi_title_cannot_switch_to_v_on_periodic_ocr(self):
        image=Image.new('RGB',(220,45),'black')
        image.paste('white',(184,10,188,30))  # The trailing I remains visible.
        recognizer=Mock(return_value=dict(name='East Rocky Mountain VI',box=(2,2,190,35),verified=True))
        monitor=MapMonitor(Catalog(),recognizer)
        monitor.observe(image,0)
        self.assertEqual(monitor.observe(image,.5),'East Rocky Mountain VI')
        for n in range(1,121):
            # Two matching mistakes used to accumulate across the five-second
            # refreshes and replace the session despite identical title pixels.
            recognizer.return_value=dict(name='East Rocky Mountain V' if n%4 in (1,2)
                                         else 'East Rocky Mountain VI',box=(2,2,182,35))
            self.assertEqual(monitor.observe(image,.5+n*5.1),'East Rocky Mountain VI')

    def test_same_title_is_preserved_after_focus_invalidation_and_failed_read(self):
        image=Image.new('RGB',(220,45),'black')
        recognizer=Mock(return_value=dict(name='East Rocky Mountain VI',box=(2,2,190,35),verified=True))
        monitor=MapMonitor(Catalog(),recognizer)
        monitor.observe(image,0);monitor.observe(image,.5)
        monitor.invalidate()
        recognizer.return_value=None
        self.assertIsNone(monitor.observe(image,1))
        recognizer.return_value=dict(name='East Rocky Mountain V',box=(2,2,180,35))
        self.assertIsNone(monitor.observe(image,1.5))
        self.assertEqual(monitor.observe(image,2),'East Rocky Mountain VI')

    def test_real_trailing_numeral_change_still_switches_maps(self):
        vi=Image.new('RGB',(220,45),'black')
        vi.paste('white',(184,10,188,30))
        v=Image.new('RGB',vi.size,'black')
        recognizer=Mock(return_value=dict(name='East Rocky Mountain VI',box=(2,2,190,35),verified=True))
        monitor=MapMonitor(Catalog(),recognizer)
        monitor.observe(vi,0);monitor.observe(vi,.5)
        recognizer.return_value=dict(name='East Rocky Mountain V',box=(2,2,182,35),verified=True)
        self.assertIsNone(monitor.observe(v,.7))
        self.assertIsNone(monitor.observe(v,1))
        self.assertIsNone(monitor.observe(v,1.5))
        self.assertIsNone(monitor.observe(v,2))
        self.assertEqual(monitor.observe(v,2.5),'East Rocky Mountain V')
        recognizer.return_value=dict(name='East Rocky Mountain VI',box=(2,2,190,35),verified=True)
        for t in (3,3.5,4):self.assertIsNone(monitor.observe(vi,t))
        self.assertEqual(monitor.observe(vi,4.5),'East Rocky Mountain VI')

    def test_changed_title_after_pause_is_not_pinned_to_previous_map(self):
        vi=Image.new('RGB',(220,45),'black')
        vi.paste('white',(184,10,188,30))
        v=Image.new('RGB',vi.size,'black')
        recognizer=Mock(return_value=dict(name='East Rocky Mountain VI',box=(2,2,190,35),verified=True))
        monitor=MapMonitor(Catalog(),recognizer)
        monitor.observe(vi,0);monitor.observe(vi,.5)
        monitor.invalidate()
        recognizer.return_value=dict(name='East Rocky Mountain V',box=(2,2,182,35),verified=True)
        self.assertIsNone(monitor.observe(v,10))
        self.assertIsNone(monitor.observe(v,10.5))
        self.assertIsNone(monitor.observe(v,11))
        self.assertEqual(monitor.observe(v,11.5),'East Rocky Mountain V')

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
        self.assertEqual(title_box(2560,1600),(0,0,1024,288))
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
