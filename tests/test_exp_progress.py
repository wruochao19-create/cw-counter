import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from exp_progress import ExperienceProgress
from hud_exp import ExpReading,ExpLedger
from counter import CounterSession


class ProgressTests(unittest.TestCase):
    def test_real_mismatched_8196_222_read_never_poison_current_or_capacity(self):
        p=ExperienceProgress()
        self.point(p,8196,0,3.07)
        trusted=p.capacity_range
        self.point(p,222,.4,3.08)
        self.assertEqual(p.current,ExpReading(8196,3.07))
        self.assertEqual(p.capacity_range,trusted)
        self.assertEqual(p.gained,0)
        self.assertEqual(p.snapshot()['exp_reading_status'],'rejected')
        self.point(p,8222,.8,3.08)
        self.assertEqual(p.current,ExpReading(8222,3.08))
        self.assertEqual(p.gained,26)

    def test_capacity_survives_pause_and_rejects_two_bad_recovery_frames(self):
        p=ExperienceProgress();self.point(p,8196,0,3.07)
        p.break_interval()
        self.point(p,222,20,3.08)
        self.assertEqual(p.current,ExpReading(8196,3.07))
        self.assertIsNone(p.baseline)
        self.point(p,8222,21,3.08)
        self.assertEqual(p.current,ExpReading(8222,3.08))
        self.assertEqual(p.gained,0)  # No subtraction across the pause.

    def test_larger_capacity_needs_two_distinct_stable_level_endpoints(self):
        p=self.sixty_seconds()
        self.point(p,200,61,1)
        self.assertEqual(p.current,ExpReading(1600,16))
        self.assertEqual(p.snapshot()['exp_reading_status'],'level_change_pending')
        self.point(p,200,61.5,1)
        self.assertEqual(p.current,ExpReading(1600,16))
        self.point(p,220,62,1.1)
        self.assertEqual(p.current,ExpReading(220,1.1))
        self.assertEqual(p.gained,620)

    def test_watchdog_separates_sample_and_confirmed_freshness_without_extrapolation(self):
        p=self.baseline();before=p.snapshot()
        self.assertTrue(p.snapshot(.5)['exp_reading_live'])
        stale=p.snapshot(5)
        self.assertFalse(stale['exp_reading_live'])
        self.assertEqual(stale['exp_reading_status'],'stale')
        self.assertEqual(stale['hud_observed_seconds'],before['hud_observed_seconds'])
        self.assertEqual(stale['hud_exp_gained'],before['hud_exp_gained'])
        for n in range(1,21):
            p.observe(ExpReading(1000+n,10+n*.01),n*.15+.15)
        waiting=p.snapshot(3.2)
        self.assertFalse(waiting['exp_reading_live'])
        self.assertEqual(waiting['exp_reading_status'],'stale')
        self.assertLess(waiting['exp_sample_age_seconds'],.1)
        self.assertGreater(waiting['exp_confirmed_age_seconds'],3)

    def test_levelup_recovers_after_low_percent_overlaps_old_capacity(self):
        p=ExperienceProgress()
        self.point(p,324232,0,99.99)
        # Real session pattern: the tiny post-level percentage still admits
        # the old level's capacity, so it initially looks like an EXP loss.
        self.point(p,521,1,.15)
        self.assertEqual(p.current,ExpReading(521,.15))
        self.point(p,575,2,.16)
        self.assertEqual(p.reading_status,'level_change_pending')
        self.point(p,649,3,.18)
        self.assertEqual(p.current,ExpReading(649,.18))
        self.assertTrue(p.snapshot()['exp_reading_live'])
        self.assertEqual(p.gained,74)
        self.assertGreater(p.capacity_range[0],324260)
        for t in range(4,36):
            amount=649+(t-3)*100
            self.point(p,amount,t,round(amount/356706*100,2))
        s=p.snapshot()
        self.assertTrue(s['exp_rate_ready'])
        self.assertTrue(s['exp_reading_live'])
        self.assertIsNotNone(s['level_eta_seconds'])
        self.assertEqual(s['hud_exp_gained'],3274)

    def test_levelup_during_pause_recovers_when_new_percent_is_higher(self):
        p=self.sixty_seconds()
        p.break_interval()
        self.point(p,4000,600,20)
        self.assertEqual(p.reading_status,'level_change_pending')
        self.point(p,4020,601,20.1)
        self.assertEqual(p.current,ExpReading(4020,20.1))
        self.assertEqual(p.gained,620)
        self.assertEqual(p.snapshot()['hud_observed_seconds'],61)
        self.assertTrue(p.snapshot()['exp_reading_live'])

    def test_levelup_at_zero_resumes_after_two_new_stable_endpoints(self):
        p=self.sixty_seconds()
        self.point(p,0,61,0)
        self.point(p,200,62,1)
        self.point(p,220,63,1.1)
        self.assertEqual(p.current,ExpReading(220,1.1))
        self.assertTrue(p.snapshot()['exp_reading_live'])
        self.assertIsNotNone(p.snapshot()['level_eta_seconds'])
        self.assertEqual(p.gained,620)

    def test_continuous_missing_samples_stay_stale_until_confirmed_recovery(self):
        p=self.baseline();before=p.snapshot()
        for n in range(1,31):
            now=.15+n*.15
            p.observe(None,now)
            if now>1.35:
                self.assertEqual(p.reading_status,'stale')
                self.assertEqual(p.snapshot(now)['exp_reading_status'],'stale')
                self.assertFalse(p.snapshot(now)['exp_reading_live'])
        self.assertEqual(p.snapshot()['hud_exp_gained'],before['hud_exp_gained'])
        self.assertEqual(p.snapshot()['hud_observed_seconds'],before['hud_observed_seconds'])
        p.observe(ExpReading(1010,10.1),4.8)
        self.assertEqual(p.snapshot(4.8)['exp_reading_status'],'stale')
        p.observe(ExpReading(1010,10.1),4.95)
        self.assertTrue(p.snapshot(4.95)['exp_reading_live'])
        self.assertEqual(p.gained,0)

    def test_startup_without_any_readable_sample_reports_continuous_stale(self):
        p=ExperienceProgress()
        for n in range(20):
            now=n*.2
            p.observe(None,now)
            if now>1.2:
                self.assertEqual(p.reading_status,'stale')
                self.assertEqual(p.snapshot(now)['exp_reading_status'],'stale')
        self.assertIsNone(p.current)
        self.assertEqual(p.snapshot()['hud_observed_seconds'],0)

    def test_short_missing_frame_keeps_candidate_but_long_gap_drops_it(self):
        p=self.baseline()
        p.observe(ExpReading(1010,10.1),.3);p.observe(None,.45)
        p.observe(ExpReading(1010,10.1),.6)
        self.assertEqual(p.gained,10)
        p.observe(ExpReading(1020,10.2),.75);p.observe(None,.9)
        p.observe(ExpReading(1020,10.2),2.5)
        self.assertEqual(p.gained,10)
        self.assertIsNone(p.baseline)

    def test_old_queued_sample_after_break_cannot_rewind_current(self):
        p=self.baseline();p.break_interval()
        p.observe(ExpReading(900,9),.1)
        p.observe(ExpReading(900,9),.11)
        self.assertEqual(p.current,ExpReading(1000,10))

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
