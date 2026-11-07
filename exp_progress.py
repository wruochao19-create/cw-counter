"""Map-session EXP efficiency from verified HUD samples, independent of kills."""
import math


class ExperienceProgress:
    def __init__(self):
        self.gained=0
        self.seconds=0.
        self.current=None
        self.break_interval()

    def break_interval(self):
        # Keep map-session totals, but never subtract across invisible periods.
        self.baseline=None
        self.baseline_at=None
        self.candidate=None
        self.samples=0
        self.last_input=None
        self.last_valid=None

    @staticmethod
    def compatible(a,b):
        if b.amount<a.amount or b.percent<a.percent:return False
        if a.percent<=.01 or b.percent<=.01:return False
        def capacity(r):
            return (100*r.amount/(r.percent+.011),100*r.amount/max(.001,r.percent-.011))
        lo,hi=capacity(a);other_lo,other_hi=capacity(b)
        return max(lo,other_lo)<=min(hi,other_hi)

    def observe(self,reading,now):
        if self.last_input is not None and now<=self.last_input:return
        if self.last_input is not None and now-self.last_input>3:self.break_interval()
        self.last_input=now
        if reading is None:
            self.candidate=None;self.samples=0
            if self.last_valid is not None and now-self.last_valid>1.2:self.break_interval()
            return
        self.last_valid=now
        if reading==self.candidate:self.samples+=1
        else:self.candidate=reading;self.samples=1
        if self.samples<2:return
        if self.baseline is not None and self.compatible(self.baseline,reading):
            self.gained+=reading.amount-self.baseline.amount
            self.seconds+=now-self.baseline_at
        # Level-up, loss or inconsistent percentage starts a fresh interval.
        # Earlier verified gains remain; the crossing itself is not guessed.
        self.current=reading;self.baseline=reading;self.baseline_at=now

    def snapshot(self):
        ready=self.seconds>=30
        rate=self.gained*3600/self.seconds if ready else None
        remaining=None
        if self.current and self.current.amount>0 and .1<=self.current.percent<100:
            remaining=self.current.amount*(100-self.current.percent)/self.current.percent
        eta=remaining/rate*3600 if remaining is not None and rate is not None and rate>0 else None
        return dict(hud_exp_gained=self.gained,hud_observed_seconds=round(self.seconds,2),
            exp_per_hour=round(rate,1) if rate is not None else None,
            remaining_exp_estimate=round(remaining) if remaining is not None else None,
            level_eta_seconds=round(eta,1) if eta is not None else None,
            current_hud_exp=self.current.amount if self.current else None,
            current_hud_percent=self.current.percent if self.current else None,
            exp_rate_ready=ready,exp_reading_live=self.baseline is not None)

    def display(self,running=False):
        s=self.snapshot();rate=s['exp_per_hour'];eta=s['level_eta_seconds']
        speed=f"{rate:,.0f} EXP" if rate is not None else '收集30秒数据中' if running else '—'
        if eta is not None:
            minutes=max(1,math.ceil(eta/60));hours,minutes=divmod(minutes,60)
            duration=(f'{hours}小时' if hours else '')+(f'{minutes}分钟' if minutes else '')
            estimate=f'约 {duration}'
        elif rate==0:estimate='暂无经验增长'
        else:estimate='等待有效读数与经验增长'
        title=f'本图平均经验／小时：{speed}    按此速度升级：{estimate}'
        seconds=int(self.seconds);minutes,seconds=divmod(seconds,60)
        state=' · 读取暂停，保留上次估算' if running and not s['exp_reading_live'] else ''
        detail=f'本图已记录经验 +{self.gained:,} · 经验条观察时长 {minutes}分{seconds:02d}秒 · 切窗暂停计时{state}'
        return title,detail
