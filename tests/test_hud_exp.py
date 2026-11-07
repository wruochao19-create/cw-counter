import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock,patch
from PIL import Image
from hud_exp import ExpReading,parse_exp,HudReader,read_crop,unique_monsters,ExpLedger,HudSampler
from counter import CounterSession

PROFILE={'Stump':21,'Axe':32,'Dark Axe':43,'Boar':46,'Fire Boar':60}


class HudTests(unittest.TestCase):
    def test_user_screenshot_discovery_and_cached_crop(self):
        image=Image.open(Path(__file__).parent/'data/user-exp-bar.png').convert('RGB')
        reader=HudReader()
        self.assertEqual(reader.read(image,(0,0,image.width,image.height),0),ExpReading(26617,11.07))
        self.assertEqual(reader.read(image.crop(reader.box),reader.box,1),ExpReading(26617,11.07))

    def test_parser_rejects_bad_grouping_and_incomplete_percentage(self):
        self.assertEqual(parse_exp('EXP 26.617[11.07%]'),ExpReading(26617,11.07))
        for text in ('EXP26.61[11.07%]','EXP26617[11.07%','HP26617[11.07%]',
                     'EXP26617[111.07%]','EXP26B17[11.07%]'):
            self.assertIsNone(parse_exp(text))

    def test_fixed_crop_retries_scale_without_lowering_numeric_threshold(self):
        def result(score):
            text='EXP 26,617[11.07%]'
            return ([(text,.99,[None,None,None,None,[score]*len(text)])]*2,0)
        engine=Mock();engine.text_rec.side_effect=[result(.5),result(.99)]
        evidence={}
        with patch('hud_exp.model',return_value=engine):
            found=read_crop(Image.new('RGB',(250,30)),debug=evidence)
        self.assertEqual(found,ExpReading(26617,11.07))
        self.assertEqual([r['height']for r in evidence['attempts']],[48,32])

    def test_hud_diagnostic_pixels_and_metadata_share_size_budget(self):
        from diagnostics import DiagnosticRecorder
        with tempfile.TemporaryDirectory() as directory:
            recorder=DiagnosticRecorder(directory,max_bytes=10000)
            recorder.add(Image.new('RGB',(40,40)),0,(0,0,40,40),[],[],
                         hud=(Image.new('RGB',(30,10)),{'amount':26617,'percent':11.07}))
            self.assertTrue((recorder.path/'000-hud.png').exists())
            row=json.loads((recorder.path/'frames.jsonl').read_text(encoding='utf-8'))
            self.assertEqual(row['hud']['amount'],26617)
            self.assertEqual(recorder.bytes,sum(p.stat().st_size for p in recorder.path.iterdir()))

    def test_wide_bottom_bar_locates_supplied_pixels_without_shrinking_text(self):
        image=Image.open(Path(__file__).parent/'data/user-exp-bar.png').convert('RGB')
        canvas=Image.new('RGB',(2560,192),'#444444');canvas.paste(image,(1300,140))
        reader=HudReader()
        self.assertEqual(reader.read(canvas,(0,1408,2560,1600),0),ExpReading(26617,11.07))
        self.assertTrue(1250<=reader.box[0]<=1320) # includes left padding for EXP prefix
        self.assertGreater(reader.box[2],1530)
        self.assertGreater(reader.box[1],1408)

    def test_multi_kill_ambiguity_and_same_exp_species(self):
        self.assertEqual(unique_monsters(46,PROFILE),{'Boar':1})
        self.assertEqual(unique_monsters(42,PROFILE),{'Stump':2})
        self.assertIsNone(unique_monsters(64,PROFILE)) # 21+43 or 32+32
        self.assertIsNone(unique_monsters(46,{'A':46,'B':46}))
        self.assertIsNone(unique_monsters(999999,PROFILE))

    def ledger(self):
        ledger=ExpLedger()
        ledger.observe(ExpReading(1000,10),0,PROFILE)
        ledger.observe(ExpReading(1000,10),.15,PROFILE)
        self.assertIsNotNone(ledger.last)
        return ledger

    def point(self,ledger,amount,at,**kwargs):
        result=ledger.observe(ExpReading(amount,amount/100),at,PROFILE,**kwargs)
        result+=ledger.observe(ExpReading(amount,amount/100),at+.15,PROFILE,**kwargs)
        return result

    def test_baseline_does_not_require_idle_seconds(self):
        ledger=self.ledger()
        self.point(ledger,1046,.3)
        events=ledger.finish(7)
        self.assertEqual([e['amount'] for e in events],[46])

    def test_continuous_fighting_settles_without_waiting_for_idle(self):
        ledger=self.ledger();events=[]
        for t in range(1,16):events+=self.point(ledger,1000+46*t,t)
        self.assertGreaterEqual(len(events),8)
        events+=ledger.finish(16,force=True)
        self.assertEqual(len(events),15)
        self.assertEqual(ledger.finish(20,force=True),[])

    def test_already_counted_notification_pairs_instead_of_double_count(self):
        ledger=self.ledger();counter=CounterSession(PROFILE)
        self.point(ledger,1046,1)
        counter.accept('notice','exp',46,'white',observed_at=1.4)
        for e in ledger.finish(7):counter.accept(**e)
        self.assertEqual(counter.counts['Boar'],1)
        self.assertEqual(counter.events[-1]['status'],'hud_checked')

    def test_neighbouring_same_exp_kills_pair_once_each_in_both_orders(self):
        ledger=self.ledger();counter=CounterSession(PROFILE)
        self.point(ledger,1046,1);self.point(ledger,1092,2)
        counter.accept('first','exp',46,'white',observed_at=1.3)
        for e in ledger.finish(8):counter.accept(**e)
        self.assertEqual(counter.counts['Boar'],2)
        counter.accept('second','exp',46,'white',observed_at=2.2)
        self.assertEqual(counter.counts['Boar'],2)
        self.assertEqual(counter.estimated_exp,0)
        counter.accept('third','exp',46,'white',observed_at=4)
        self.assertEqual(counter.counts['Boar'],3)

    def test_old_notification_outside_interval_cannot_consume_new_increment(self):
        ledger=self.ledger();counter=CounterSession(PROFILE)
        counter.accept('old','exp',46,'white',observed_at=-2)
        self.point(ledger,1046,1)
        for e in ledger.finish(7):counter.accept(**e)
        self.assertEqual(counter.counts['Boar'],2)

    def test_ambiguous_delta_not_forced(self):
        ledger=self.ledger();self.point(ledger,1064,1)
        self.assertEqual(ledger.finish(7),[])

    def test_brief_ocr_dropout_recovers_unique_two_kill_increment(self):
        ledger=self.ledger();ledger.observe(None,.4,PROFILE)
        self.point(ledger,1081,.7)
        self.assertEqual(sorted(e['amount'] for e in ledger.finish(7)),[21,60])

    def test_long_dropout_never_bridges_but_keeps_verified_earlier_step(self):
        ledger=self.ledger();self.point(ledger,1046,1)
        ledger.observe(None,2.5,PROFILE)
        self.assertIsNone(ledger.last)
        self.point(ledger,1106,2.7)
        self.assertEqual([e['amount'] for e in ledger.finish(8)],[46])

    def test_two_samples_required_for_new_hud_amount(self):
        ledger=self.ledger()
        ledger.observe(ExpReading(1046,10.46),1,PROFILE)
        self.assertEqual(ledger.finish(2,force=True),[])

    def test_high_frequency_steps_disambiguate_total(self):
        ledger=self.ledger();self.point(ledger,1043,1);self.point(ledger,1064,1.3)
        self.assertEqual(sorted(e['amount'] for e in ledger.finish(8)),[21,43])

    def test_party_and_disabled_do_not_top_up(self):
        ledger=self.ledger();self.point(ledger,1046,1)
        self.assertEqual(ledger.finish(7,allow_topup=False),[])
        ledger=self.ledger();self.point(ledger,1046,1)
        self.assertEqual(ledger.observe(ExpReading(1046,10.46),2,PROFILE,party=True),[])
        self.assertEqual(ledger.finish(7,force=True),[])

    def test_levelup_death_percentage_conflict_and_gap_never_inferred(self):
        for reading,t in ((ExpReading(20,.2),1),(ExpReading(1046,40),1),(ExpReading(1046,10.46),4)):
            ledger=self.ledger()
            ledger.observe(reading,t,PROFILE);ledger.observe(reading,t+.15,PROFILE)
            self.assertEqual(ledger.finish(12),[])

    def test_pause_flushes_verified_increment_once_without_more_pixels(self):
        ledger=self.ledger();self.point(ledger,1046,1)
        self.assertEqual([e['amount'] for e in ledger.finish(1.2,force=True)],[46])
        self.assertEqual(ledger.finish(1.3,force=True),[])

    def test_app_flush_matches_finished_hint_and_hud_before_reset(self):
        import app
        ui=app.App.__new__(app.App);ui.running=True;ui.hud_sampler=None
        ui.session=CounterSession(PROFILE);ui.exp_ledger=self.ledger()
        self.point(ui.exp_ledger,1046,1)
        ui.hud_topup=Mock();ui.hud_topup.get.return_value=True
        ui.reader=Mock();ui.reader.finish.return_value=[dict(event_id='late',kind='exp',
            amount=46,color='white',observed_at=1.3)]
        ui.append_log=Mock();ui.update_stats=Mock()
        with patch.object(app.capture,'grab_region') as capture:
            ui.flush_observed();ui.flush_observed()
        capture.assert_not_called()
        self.assertEqual(ui.session.counts['Boar'],1)
        self.assertEqual(ui.session.events[-1]['status'],'hud_checked')

    def test_latest_saved_hud_pixels_reproduce_valid_and_failed_reads(self):
        root=Path(__file__).resolve().parents[1]/'diagnostics'
        directories=[root/name for name in ('20261106-113601-233167',
            '20261106-113626-208918','20261106-113723-211161')]
        if not all((p/'frames.jsonl').exists() for p in directories):self.skipTest('Local diagnostic absent')
        verified=missing=0
        for directory in directories:
            for row in map(json.loads,(directory/'frames.jsonl').read_text(encoding='utf-8').splitlines()):
                h=row.get('hud')
                if not h:continue
                with Image.open(directory/f'{row["frame"]:03d}-hud.png') as image:
                    result=read_crop(image)
                expected=ExpReading(h['amount'],h['percent']) if h['amount'] is not None else None
                self.assertEqual(result,expected)
                verified+=result is not None;missing+=result is None
        self.assertEqual((verified,missing),(72,1))

    def test_late_notification_replaces_credit_but_new_kill_is_counted(self):
        counter=CounterSession(PROFILE)
        counter.accept('hud','exp',46,'white',estimated=True,source='hud_difference',observed_at=10)
        counter.accept('late','exp',46,'white',observed_at=7)
        self.assertEqual(counter.counts['Boar'],1);self.assertEqual(counter.personal_exp,46)
        self.assertEqual(counter.estimated_exp,0)
        counter.accept('new','exp',46,'white',observed_at=11)
        self.assertEqual(counter.counts['Boar'],2)
        counter.accept('hud2','exp',46,'white',estimated=True,source='hud_difference',observed_at=20)
        counter.accept('new2','exp',46,'white',observed_at=21)
        self.assertEqual(counter.counts['Boar'],4)

    def test_worker_never_captures_background_or_moved_window(self):
        capture=Mock();capture.foreground.return_value=False
        worker=HudSampler(1,(0,0,800,600),(100,550,300,580),capture)
        self.assertIsNone(worker.sample_once()[0][1]);capture.grab_region.assert_not_called()
        self.assertFalse(worker.sample_once()[0][4])
        capture.foreground.return_value=True;capture.client_rect.return_value=(1,0,800,600)
        self.assertIsNone(worker.sample_once()[0][1]);capture.grab_region.assert_not_called()

    def test_worker_bounds_queue_and_reuses_identical_pixels(self):
        capture=Mock();capture.foreground.return_value=True;capture.client_rect.return_value=(0,0,800,600)
        capture.region_on_screen.return_value=True;capture.grab_region.return_value=Image.new('RGB',(200,30))
        recognizer=Mock(return_value=ExpReading(1000,10))
        worker=HudSampler(1,(0,0,800,600),(100,550,300,580),capture,recognizer=recognizer)
        result,key,reading=worker.sample_once();result,key,reading=worker.sample_once(key,reading)
        self.assertTrue(result[3]);self.assertEqual(recognizer.call_count,1)
        self.assertTrue(result[4])
        for _ in range(140):worker.push(result)
        rows,dropped=worker.drain();self.assertEqual(len(rows),128);self.assertEqual(dropped,12)

    def test_failed_ocr_result_is_not_cached(self):
        capture=Mock();capture.foreground.return_value=True;capture.client_rect.return_value=(0,0,800,600)
        capture.region_on_screen.return_value=True;capture.grab_region.return_value=Image.new('RGB',(200,30))
        recognizer=Mock(side_effect=[None,ExpReading(1000,10)])
        worker=HudSampler(1,(0,0,800,600),(100,550,300,580),capture,recognizer=recognizer)
        result,key,reading=worker.sample_once();result,key,reading=worker.sample_once(key,reading)
        self.assertEqual(recognizer.call_count,2);self.assertEqual(reading,ExpReading(1000,10))

    def test_app_keeps_worker_on_ocr_miss_but_resets_on_window_change(self):
        import app
        ui=app.App.__new__(app.App);rect=(0,0,800,600)
        ui.hud_sampler=Mock();ui.hud_sampler.rect=rect;ui.hud_missing_since=None
        ui.reset_hud=Mock();ui.apply_hud_reading=Mock()
        ui.hud_sampler.drain.return_value=([(99.8,None,40,False,True),
            (100,ExpReading(1046,10.46),40,False,True)],0)
        with patch.object(app.time,'monotonic',return_value=100):ui.probe_hud(rect,[])
        ui.reset_hud.assert_not_called();self.assertIsNone(ui.hud_missing_since)
        ui.hud_sampler.drain.return_value=([(100.1,None,0,False,False)],0)
        with patch.object(app.time,'monotonic',return_value=100.2):ui.probe_hud(rect,[])
        ui.reset_hud.assert_called_once()
