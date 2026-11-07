import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from exp_progress import ExperienceProgress
from hud_exp import ExpReading,ExpLedger
from counter import CounterSession


class ProgressTests(unittest.TestCase):
    def baseline(self):
        p=ExperienceProgress()
        p.observe(ExpReading(1000,10),0)
        p.observe(ExpReading(1000,10),.15)
        return p

    def point(self,p,amount,t,percent=None):
        r=ExpReading(amount,percent if percent is not None else amount/100)
        p.observe(r,t);p.observe(r,t+.15)

    def sixty_seconds(self):
        p=self.baseline()
        for t in range(1,61):self.point(p,1000+t*10,t)
        return p

    def test_rate_and_eta_use_hud_gain_not_kills(self):
        p=self.sixty_seconds();s=p.snapshot()
        self.assertEqual(s['hud_exp_gained'],600)
        self.assertEqual(s['hud_observed_seconds'],60)
        self.assertEqual(s['exp_per_hour'],36000)
        self.assertEqual(s['remaining_exp_estimate'],8400)
        self.assertEqual(s['level_eta_seconds'],840)
        self.assertIn('14分钟',p.display(True)[0])

    def test_idle_visible_time_reduces_average_rate(self):
        p=self.sixty_seconds()
        for t in range(61,121):self.point(p,1600,t)
        self.assertEqual(p.snapshot()['exp_per_hour'],18000)
        self.assertEqual(p.snapshot()['level_eta_seconds'],1680)

    def test_warmup_and_zero_gain_have_no_misleading_eta(self):
        p=self.baseline()
        for t in range(1,30):self.point(p,1000,t)
        self.assertIsNone(p.snapshot()['exp_per_hour'])
        self.point(p,1000,30)
        self.assertEqual(p.snapshot()['exp_per_hour'],0)
        self.assertIsNone(p.snapshot()['level_eta_seconds'])

    def test_switching_away_excludes_background_time_and_gain(self):
        p=self.sixty_seconds();before=p.snapshot()
        p.break_interval();self.assertFalse(p.snapshot()['exp_reading_live'])
        self.point(p,5000,600)
        self.assertEqual(p.snapshot()['hud_exp_gained'],600)
        self.assertEqual(p.snapshot()['hud_observed_seconds'],before['hud_observed_seconds'])
        self.point(p,5010,601)
        self.assertEqual(p.snapshot()['hud_exp_gained'],610)
        self.assertEqual(p.snapshot()['hud_observed_seconds'],61)

    def test_short_miss_bridges_but_long_miss_and_queue_gap_do_not(self):
        p=self.baseline();p.observe(None,.3);self.point(p,1046,.5)
        self.assertEqual(p.gained,46)
        p.observe(None,2);self.point(p,1106,2.5)
        self.assertEqual(p.gained,46)
        self.point(p,1166,10)
        self.assertEqual(p.gained,46)

    def test_level_change_and_exp_loss_rebase_without_false_gain(self):
        p=self.sixty_seconds();self.point(p,200,61,1)
        self.assertEqual(p.gained,600)
        self.point(p,220,62,1.1)
        self.assertEqual(p.gained,620)
        self.point(p,100,63,.5)
        self.assertEqual(p.gained,620)
        self.assertEqual(p.snapshot()['remaining_exp_estimate'],19900)

    def test_single_frame_spike_and_duplicate_timestamp_do_not_count(self):
        p=self.baseline()
        p.observe(ExpReading(5000,50),1)
        p.observe(ExpReading(5000,50),1)
        self.assertEqual(p.gained,0)
        self.point(p,1000,1.5)
        self.assertEqual(p.gained,0)

    def test_zero_percent_does_not_divide_by_zero(self):
        p=ExperienceProgress();self.point(p,0,0,0)
        self.assertIsNone(p.snapshot()['remaining_exp_estimate'])
        self.assertIsNone(p.snapshot()['level_eta_seconds'])

    def test_export_contains_metrics_and_new_map_has_separate_totals(self):
        s=CounterSession({'Boar':46});s.exp_progress=self.sixty_seconds()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'summary.csv';s.export_summary(path)
            with path.open(encoding='utf-8-sig') as handle:rows=list(csv.reader(handle))
        values={r[0]:r[1]for r in rows if len(r)==2}
        self.assertEqual(values['hud_exp_gained'],'600')
        self.assertEqual(values['level_eta_seconds'],'840.0')
        self.assertEqual(CounterSession({'Boar':46}).exp_progress.gained,0)

    def test_app_records_progress_even_when_kill_topup_off_or_party_detected(self):
        import app
        ui=app.App.__new__(app.App);ui.session=CounterSession({'Boar':46})
        ui.session.party_exp=100;ui.exp_ledger=ExpLedger()
        ui.hud_topup=Mock();ui.hud_topup.get.return_value=False
        ui.hud_status=Mock();ui.append_log=Mock()
        ui.hud_sample_count=0;ui.hud_log_at=-100;ui.hud_log_reading=None
        for t in range(32):
            reading=ExpReading(1000+t*10,10+t*.1)
            ui.apply_hud_reading(reading,t,(0,0,200,30))
            ui.apply_hud_reading(reading,t+.15,(0,0,200,30))
        self.assertEqual(ui.session.exp_progress.gained,310)
        self.assertEqual(ui.session.exp_progress.snapshot()['exp_per_hour'],36000)
        self.assertEqual(sum(ui.session.counts.values()),0)
