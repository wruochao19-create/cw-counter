"""Map-session EXP efficiency from verified HUD samples, independent of kills."""
import math
from collections import deque


class ExperienceProgress:
    FRESH_SECONDS = 1.2
    RATE_WINDOW_SECONDS = 600.
    RATE_WARMUP_SECONDS = 60.

    def __init__(self):
        self.gained=0
        self.seconds=0.
        self.rate_intervals=deque()
        self.rate_seconds=0.
        self.rate_gain=0.
        self.current=None
        self.capacity_range=None
        self.last_sample_at=None
        self.last_confirmed_at=None
        self.rejected_readings=0
        self.reading_status='waiting'
        self.break_interval()

    def break_interval(self):
        # A pause drops the subtractable interval, not the trusted level/EXP
        # capacity. Otherwise the first two bad OCR frames after recovery can
        # replace the last trustworthy level with an impossible one.
        self.baseline=None
        self.baseline_at=None
        self.candidate=None
        self.samples=0
        self.last_input=None
        self.last_valid=None
        self.missing_since=None
        self.level_candidate=None
        self.reading_status='paused' if self.current is not None else 'waiting'

    @staticmethod
    def capacity(reading):
        if reading.amount<=0 or not .01<reading.percent<100:return None
        return (100*reading.amount/(reading.percent+.011),
                100*reading.amount/max(.001,reading.percent-.011))

    @staticmethod
    def overlap(a,b):
        return a is not None and b is not None and max(a[0],b[0])<=min(a[1],b[1])

    @staticmethod
    def compatible(a,b):
        return (b.amount>=a.amount and b.percent>=a.percent and
                ExperienceProgress.overlap(ExperienceProgress.capacity(a),ExperienceProgress.capacity(b)))

    def _accept(self,reading,now,capacity,rebase=False):
        if not rebase and self.baseline is not None and self.compatible(self.baseline,reading):
            gain=reading.amount-self.baseline.amount
            duration=now-self.baseline_at
            self.gained+=gain
            self.seconds+=duration
            self._append_rate_interval(duration,gain)
        if capacity is not None:
            if self.overlap(self.capacity_range,capacity):
                self.capacity_range=(max(self.capacity_range[0],capacity[0]),min(self.capacity_range[1],capacity[1]))
            else:self.capacity_range=capacity
        self.current=reading;self.baseline=reading;self.baseline_at=now
        self.last_confirmed_at=now
        self.level_candidate=None
        self.reading_status='live'

    def _append_rate_interval(self,duration,gain):
        # Matched gain/time intervals only, including idle (zero-gain) samples.
        # Pauses and rebases never enter either side of the rate calculation.
        if duration<=0:return
        self.rate_intervals.append((duration,float(gain)))
        self.rate_seconds+=duration
        self.rate_gain+=gain
        excess=self.rate_seconds-self.RATE_WINDOW_SECONDS
        while excess>0 and self.rate_intervals:
            seconds,amount=self.rate_intervals.popleft()
            removed=min(excess,seconds)
            removed_gain=amount*(removed/seconds)
            self.rate_seconds-=removed
            self.rate_gain-=removed_gain
            excess-=removed
            if removed<seconds:
                # Interpolate only the tiny interval crossing the window edge;
                # dropping a whole sample would introduce a periodic step.
                self.rate_intervals.appendleft((seconds-removed,amount-removed_gain))
        # Fractional eviction may leave roundoff after all earned EXP expires.
        # Treat sub-millionth EXP residue as zero, including for ETA division.
        self.rate_gain=0. if self.rate_gain<1e-6 else self.rate_gain

    def observe(self,reading,now):
        # Preserve the high-water sample timestamp through pauses so queued old
        # samples cannot rewind the model when a new interval starts.
        if self.last_sample_at is not None and now<=self.last_sample_at:return
        if self.last_sample_at is not None and now-self.last_sample_at>3:self.break_interval()
        self.last_sample_at=now;self.last_input=now
        if reading is None:
            missing_since=self.missing_since if self.missing_since is not None else now
            if self.last_valid is not None and now-self.last_valid>self.FRESH_SECONDS:self.break_interval()
            self.missing_since=missing_since
            expired=(self.last_confirmed_at is not None and now-self.last_confirmed_at>self.FRESH_SECONDS)
            self.reading_status='stale' if expired or now-missing_since>self.FRESH_SECONDS else 'confirming'
            return
        if self.last_valid is not None and now-self.last_valid>self.FRESH_SECONDS:
            self.break_interval()
        self.last_valid=now
        self.missing_since=None
        if reading==self.candidate:self.samples+=1
        else:self.candidate=reading;self.samples=1
        if self.samples<2:
            self.reading_status='confirming';return
        capacity=self.capacity(reading)
        if self.current is None or self.capacity_range is None:
            if capacity is not None or reading.amount==reading.percent==0:
                self._accept(reading,now,capacity)
                return
        elif self.overlap(self.capacity_range,capacity):
            if reading.amount>=self.current.amount and reading.percent>=self.current.percent:
                self._accept(reading,now,capacity);return
            if reading.amount<=self.current.amount and reading.percent<=self.current.percent:
                # Same-level loss (death), not positive income. The crossing is
                # not included in the reliable rate denominator either.
                self._accept(reading,now,capacity,rebase=True);return
        elif capacity is not None and capacity[0]>self.capacity_range[1]:
            # Near 0%, display rounding can make a new level overlap the old
            # capacity and get accepted as an EXP loss. Later new-level samples
            # must still be able to recover, even after their percent has risen
            # above that accepted sample or a pause hid the percentage wrap.
            # A larger level capacity is only a proposal.
            # Two copies of the same contradictory read do not prove a level-up.
            # Require a second distinct, stable endpoint in that new capacity;
            # then only its verified post-level increment is retained.
            if self.level_candidate is not None:
                previous,at=self.level_candidate
                if reading!=previous and self.compatible(previous,reading):
                    self.capacity_range=self.capacity(previous)
                    self.baseline=previous;self.baseline_at=at
                    self._accept(reading,now,capacity);return
                if reading==previous:
                    self.reading_status='level_change_pending';return
            self.level_candidate=(reading,now)
            self.reading_status='level_change_pending'
            return
        self.rejected_readings+=1
        self.reading_status='rejected'
        # Do not let rejected OCR extend a subtractable interval indefinitely.
        if self.last_confirmed_at is not None and now-self.last_confirmed_at>self.FRESH_SECONDS:
            self.baseline=None;self.baseline_at=None

    def snapshot(self,now=None,unit='小时'):
        rolling_ready=self.rate_seconds>=self.RATE_WARMUP_SECONDS-1e-7
        rolling_rate=self.rate_gain*3600/self.rate_seconds if rolling_ready else None
        session_ready=self.seconds>=30
        session_rate=self.gained*3600/self.seconds if session_ready else None
        rolling=unit=='分钟'
        ready=rolling_ready if rolling else session_ready
        rate=rolling_rate if rolling else session_rate
        remaining=None
        if self.current and self.current.amount>0 and .1<=self.current.percent<100:
            remaining=self.current.amount*(100-self.current.percent)/self.current.percent
        eta=remaining/rate*3600 if remaining is not None and rate is not None and rate>0 else None
        # No argument keeps deterministic export/synthetic-test compatibility.
        # The UI supplies its monotonic clock to detect an absent/stuck worker.
        point=self.last_sample_at if now is None else now
        sample_age=max(0.,point-self.last_sample_at) if point is not None and self.last_sample_at is not None else None
        confirmed_age=max(0.,point-self.last_confirmed_at) if point is not None and self.last_confirmed_at is not None else None
        fresh=(sample_age is not None and sample_age<=self.FRESH_SECONDS and
               confirmed_age is not None and confirmed_age<=self.FRESH_SECONDS)
        status=self.reading_status
        if sample_age is not None and sample_age>self.FRESH_SECONDS:status='stale'
        elif status=='confirming' and confirmed_age is not None and confirmed_age>self.FRESH_SECONDS:status='stale'
        elif status=='live' and not fresh:status='confirming'
        return dict(hud_exp_gained=self.gained,hud_observed_seconds=round(self.seconds,2),
            exp_per_hour=round(rate,1) if rate is not None else None,
            exp_rate_basis='rolling_valid_600s' if rolling else 'session_valid',
            exp_rate_window_seconds=self.RATE_WINDOW_SECONDS,
            exp_rate_observed_seconds=round(self.rate_seconds,2),
            exp_rate_window_gain=round(self.rate_gain,3),
            exp_rate_window_full=self.rate_seconds>=self.RATE_WINDOW_SECONDS-1e-7,
            exp_session_per_hour=round(session_rate,1) if session_rate is not None else None,
            exp_rolling_per_hour=round(rolling_rate,1) if rolling_rate is not None else None,
            exp_rolling_per_minute=round(rolling_rate/60,3) if rolling_rate is not None else None,
            exp_rolling_eta_seconds=round(remaining/rolling_rate*3600,1) if remaining is not None and rolling_rate is not None and rolling_rate>0 else None,
            remaining_exp_estimate=round(remaining) if remaining is not None else None,
            level_eta_seconds=round(eta,1) if eta is not None else None,
            current_hud_exp=self.current.amount if self.current else None,
            current_hud_percent=self.current.percent if self.current else None,
            exp_rate_ready=ready,exp_reading_live=self.baseline is not None and fresh and status not in ('rejected','level_change_pending','paused'),
            exp_reading_status=status,exp_sample_age_seconds=round(sample_age,2) if sample_age is not None else None,
            exp_confirmed_age_seconds=round(confirmed_age,2) if confirmed_age is not None else None,
            exp_rejected_readings=self.rejected_readings)

    def display(self,running=False,now=None,unit='小时'):
        s=self.snapshot(now,unit=unit);rate=s['exp_per_hour'];eta=s['level_eta_seconds']
        if unit=='分钟' and rate is not None:rate/=60
        warmup='积累1分钟有效数据中' if unit=='分钟' else '收集30秒数据中'
        speed=f"{rate:,.0f} EXP" if rate is not None else warmup if running else '—'
        if eta is not None:
            minutes=max(1,math.ceil(eta/60));hours,minutes=divmod(minutes,60)
            duration=(f'{hours}小时' if hours else '')+(f'{minutes}分钟' if minutes else '')
            estimate=f'约 {duration}'
        elif rate==0:estimate='暂无经验增长'
        else:estimate='等待有效读数与经验增长'
        basis='最近10分钟' if unit=='分钟' else '本图整场平均'
        title=f'{basis}经验／{unit}：{speed}    按此速度升级：{estimate}'
        seconds=int(self.seconds);minutes,seconds=divmod(seconds,60)
        state=' · 读取暂停，保留上次估算' if running and not s['exp_reading_live'] else ''
        window='已满10分钟' if s['exp_rate_window_full'] else f"已积累 {s['exp_rate_observed_seconds']:.0f}/600 秒，未满10分钟"
        window_note=f' · 滚动窗口{window}' if unit=='分钟' else ''
        detail=f'本图已记录经验 +{self.gained:,} · 经验条观察时长 {minutes}分{seconds:02d}秒{window_note} · 切窗暂停计时{state}'
        return title,detail
