import unittest

from exp_progress import ExperienceProgress
from hud_exp import ExpReading


class RollingExperienceTests(unittest.TestCase):
    def point(self,p,amount,at):
        reading=ExpReading(amount,round(amount/10000,2))
        p.observe(reading,at)
        p.observe(reading,at+.15)

    def run_phase(self,p,amount,start,seconds,gain):
        for t in range(start+1,start+seconds+1):
            amount+=gain
            self.point(p,amount,t)
        return amount

    def test_old_fast_or_slow_period_leaves_window_and_eta_uses_recent_rate(self):
        for first,last in ((10,1),(1,10)):
            with self.subTest(first=first,last=last):
                p=ExperienceProgress();self.point(p,100000,0)
                amount=self.run_phase(p,100000,0,300,first)
                amount=self.run_phase(p,amount,300,600,last)
                s=p.snapshot(unit='分钟')
                self.assertEqual(s['exp_rate_observed_seconds'],600)
                self.assertTrue(s['exp_rate_window_full'])
                self.assertEqual(s['exp_rate_window_gain'],600*last)
                self.assertEqual(s['exp_per_hour'],3600*last)
                self.assertEqual(s['hud_exp_gained'],300*first+600*last)
                self.assertNotEqual(s['exp_per_hour'],s['exp_session_per_hour'])
                expected_remaining=p.current.amount*(100-p.current.percent)/p.current.percent
                self.assertAlmostEqual(s['level_eta_seconds'],expected_remaining/last,delta=.1)
                self.assertLessEqual(len(p.rate_intervals),1202)

    def test_idle_is_included_and_short_burst_is_diluted_over_ten_minutes(self):
        p=ExperienceProgress();self.point(p,100000,0)
        amount=self.run_phase(p,100000,0,600,10)
        self.run_phase(p,amount,600,300,0)
        self.assertEqual(p.snapshot(unit='分钟')['exp_per_hour'],18000)
        self.run_phase(p,amount,900,300,0)
        self.assertEqual(p.snapshot(unit='分钟')['exp_per_hour'],0)
        self.assertIsNone(p.snapshot(unit='分钟')['level_eta_seconds'])
        self.point(p,amount+100,1201)
        self.assertEqual(p.snapshot(unit='分钟')['exp_per_hour'],600)

    def test_pause_gap_excludes_both_gain_and_time_and_preserves_window(self):
        p=ExperienceProgress();self.point(p,100000,0)
        amount=self.run_phase(p,100000,0,600,10)
        before=p.snapshot(unit='分钟')
        p.break_interval()
        self.point(p,amount+50000,5000)
        after=p.snapshot(unit='分钟')
        for key in ('exp_rate_window_gain','exp_rate_observed_seconds','exp_per_hour'):
            self.assertEqual(after[key],before[key])
        self.run_phase(p,amount+50000,5000,600,1)
        self.assertEqual(p.snapshot(unit='分钟')['exp_per_hour'],3600)
        self.assertEqual(p.gained,6600)

    def test_missing_or_rejected_reads_do_not_become_zero_income_or_catchup_spike(self):
        p=ExperienceProgress();self.point(p,100000,0)
        amount=self.run_phase(p,100000,0,600,10)
        for t in range(601,611):p.observe(None,t)
        self.point(p,amount+10000,611)
        self.assertEqual(p.gained,6000)
        self.assertEqual(p.snapshot(unit='分钟')['exp_per_hour'],36000)
        for t in (612,612.15):p.observe(ExpReading(123,12),t)
        self.assertEqual(p.snapshot(unit='分钟')['exp_per_hour'],36000)
        self.assertGreater(p.rejected_readings,0)
        self.point(p,amount+10010,613)
        self.assertEqual(p.gained,6010)
        self.assertAlmostEqual(p.snapshot(unit='分钟')['exp_rate_observed_seconds'],600)

    def test_sampling_frequency_and_partial_window_boundary_do_not_bias_rate(self):
        for step in (.3,1.):
            with self.subTest(step=step):
                p=ExperienceProgress();self.point(p,100000,0)
                for index in range(1,round(901/step)+1):
                    at=index*step
                    self.point(p,100000+round(at*10),at)
                s=p.snapshot(unit='分钟')
                self.assertAlmostEqual(s['exp_per_hour'],36000,delta=1)
                self.assertAlmostEqual(s['exp_rate_window_gain'],6000,delta=.1)

    def test_warmup_uses_actual_duration_and_units_do_not_change_estimate(self):
        p=ExperienceProgress();self.point(p,100000,0)
        amount=self.run_phase(p,100000,0,59,10)
        self.assertIsNone(p.snapshot(unit='分钟')['exp_per_hour'])
        self.point(p,amount+10,60)
        s=p.snapshot(unit='分钟')
        self.assertFalse(s['exp_rate_window_full'])
        self.assertEqual(s['exp_per_hour'],36000)
        hour=p.display(unit='小时')[0]
        minute=p.display(unit='分钟')[0]
        self.assertIn('36,000 EXP',hour)
        self.assertIn('600 EXP',minute)
        self.assertEqual(hour.split('按此速度升级：')[1],minute.split('按此速度升级：')[1])
        self.assertIn('未满10分钟',p.display(unit='分钟')[1])

    def test_hour_preserves_original_30_second_warmup_and_session_mean(self):
        p=ExperienceProgress();self.point(p,100000,0)
        self.run_phase(p,100000,0,30,10)
        hour=p.snapshot()
        minute=p.snapshot(unit='分钟')
        self.assertEqual(hour['exp_per_hour'],36000)
        self.assertEqual(hour['exp_rate_basis'],'session_valid')
        self.assertIsNone(minute['exp_per_hour'])
        self.assertEqual(minute['exp_rate_basis'],'rolling_valid_600s')
        self.assertIn('本图整场平均',p.display()[0])
