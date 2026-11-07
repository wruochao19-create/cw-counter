"""Visible HUD EXP reader and time-bounded increment reconciliation."""
import bootstrap
import re
import uuid
import threading
import time
import hashlib
from collections import deque
from dataclasses import dataclass
import numpy as np
import cv2
from PIL import Image
from pixel_ocr import model,scan


@dataclass(frozen=True)
class ExpReading:
    amount:int
    percent:float


def parse_exp(text,discovery=False):
    prefix=r'E?XP' if discovery else 'EXP'
    match=re.search(r'\b'+prefix+r'\s*[:.]?\s*(\d[\d,.]*)\s*[\[(]\s*(\d{1,3}\.\d{2})\s*%\s*[\])]',text,re.I)
    if not match:return None
    number=match[1]
    # The fixed HUD uses integer EXP. OCR often renders its comma as a dot;
    # only groups of exactly three digits qualify as thousands separators.
    if (','in number or '.'in number) and not re.fullmatch(r'\d{1,3}([,.]\d{3})+',number):return None
    amount=int(number.replace(',','').replace('.',''));percent=float(match[2])
    if not 0<=amount<100000000 or not 0<=percent<100:return None
    return ExpReading(amount,percent)


def search_box(width,height):
    return (0,max(0,height-max(90,round(height*.12))),width,height)


def read_crop(image,debug=None):
    if image.height<5:return None
    original=image.convert('RGB')
    for height in (48,32,64):
        scaled=original.resize((max(1,round(original.width*height/original.height)),height),Image.Resampling.BICUBIC)
        bgr=np.asarray(scaled)[:,:,::-1].copy()
        results,_=model().text_rec([bgr,cv2.convertScaleAbs(bgr,alpha=1.1,beta=-8)],return_word_box=True)
        readings=[];evidence=[]
        for text,score,details in results:
            reading=parse_exp(text)
            digit_scores=[float(p) for c,p in zip(text,details[4]) if c.isdigit()]
            valid=reading is not None and score>=.85 and bool(digit_scores) and min(digit_scores)>=.8
            evidence.append(dict(raw=text,score=round(float(score),4),
                                 weakest_digit=round(min(digit_scores),4) if digit_scores else None,valid=bool(valid)))
            readings.append(reading if valid else None)
        if debug is not None:debug.setdefault('attempts',[]).append(dict(height=height,reads=evidence))
        if len(readings)==2 and readings[0] is not None and readings[0]==readings[1]:return readings[0]
    return None


class HudReader:
    def __init__(self):self.box=None;self.next_read=0.

    def read(self,image,origin,now):
        self.next_read=now+.8
        if self.box:
            result=read_crop(image)
            if result is not None:return result
            self.box=None;self.next_read=now+1.;return None
        if image.width>1024:
            # Avoid shrinking the whole 2560/4K bottom bar into one detector
            # image. Overlap keeps EXP fields intact at tile boundaries.
            starts=set(range(0,max(1,image.width-1024+1),768))
            starts.add(image.width-1024)
            starts.add(max(0,(image.width-1024)//2))
            for x in sorted(starts,key=lambda n:abs(n+512-image.width/2)):
                tile=HudReader()
                result=tile.read(image.crop((x,0,x+1024,image.height)),
                                 (origin[0]+x,origin[1],origin[0]+x+1024,origin[3]),now)
                if result:self.box=tile.box;return result
            self.next_read=now+5.;return None
        # Discovery only. Stable operation recognizes one short HUD line.
        rows=scan(image)
        for row in rows:
            if not re.search(r'\bE?XP',row['text'],re.I):continue
            x,y,r,b=row['box'];height=b-y
            aligned=[p for p in rows if abs((p['box'][1]+p['box'][3]-y-b)/2)<height*.6
                     and p['box'][0]>=x-2]
            aligned.sort(key=lambda p:p['box'][0])
            # Grow only until the percentage ends, avoiding unrelated buttons.
            for count in range(1,min(4,len(aligned))+1):
                group=aligned[:count]
                if not parse_exp(' '.join(p['text'] for p in group),discovery=True):continue
                box=(max(0,int(x-height*.8)),max(0,int(min(p['box'][1]for p in group))-3),
                     min(image.width,int(max(p['box'][2]for p in group))+4),
                     min(image.height,int(max(p['box'][3]for p in group))+3))
                result=read_crop(image.crop(box))
                if result:
                    self.box=(origin[0]+box[0],origin[1]+box[1],origin[0]+box[2],origin[1]+box[3])
                    return result
        self.next_read=now+5.;return None


def compatible_level(a,b):
    if b.amount<a.amount or b.percent<a.percent:return False
    if a.percent<=.01 or b.percent<=.01:return False
    # Allow display rounding/truncation uncertainty; never infer a level-up total.
    def capacity(r):return (100*r.amount/(r.percent+.011),100*r.amount/max(.001,r.percent-.011))
    alo,ahi=capacity(a);blo,bhi=capacity(b)
    return max(alo,blo)<=min(ahi,bhi)


def unique_monsters(amount,profile):
    """All unordered decompositions, capped at two; duplicate EXP species matter."""
    choices=[(name,int(exp)) for name,exp in profile.items() if 0<exp<=amount]
    if amount<=0 or not choices or len(choices)>20:return None
    # Bounds limit work, never truncate the search and call an answer unique.
    if amount>20000 or amount//min(v for _,v in choices)>12:return None
    ways=[[] for _ in range(amount+1)];ways[0]=[{}]
    for name,value in choices:
        for total in range(value,amount+1):
            for prior in ways[total-value]:
                if len(ways[total])>=2:break
                combo=dict(prior);combo[name]=combo.get(name,0)+1
                ways[total].append(combo)
    return ways[amount][0] if len(ways[amount])==1 else None


class ExpLedger:
    """Confirm HUD samples, then reconcile each increment after a bounded delay.

    No idle requirement. Only two agreeing pixel reads establish a point; missing
    frames, level changes and pauses are never bridged. CounterSession pairs the
    resulting intervals with notification evidence in either arrival order.
    """
    def __init__(self):self.reset()

    def reset(self):
        self.last=None;self.last_time=None;self.last_confirmed_time=None
        self.candidate=None;self.candidate_at=None;self.samples=0
        self.steps=deque();self.party_blocked=False
        self.status='经验条：等待两帧一致读数'

    def finish(self,now,allow_topup=True,force=False):
        events=[]
        while self.steps and (force or now-self.steps[0]['at']>=6):
            step=self.steps.popleft()
            if not allow_topup or self.party_blocked:continue
            combo=step['combo']
            if combo is None:
                self.status=f"经验条：增量 {step['delta']} 有多种解释，未补计";continue
            for name,count in combo.items():
                for _ in range(count):
                    events.append(dict(event_id='hud-'+uuid.uuid4().hex,kind='exp',
                        amount=step['profile'][name],color='white',confident=True,estimated=True,
                        source='hud_difference',observed_at=step['at'],
                        interval_start=step['start']-.4,interval_end=step['at']+1.2,
                        note=f"经验条已确认增量 {step['delta']}：与同时间提示配对，缺失时估计补计"))
        return events

    def observe(self,reading,now,profile,party=False,allow_topup=True):
        if party or self.party_blocked:
            self.party_blocked=True;self.steps.clear();self.last=None
            self.status='经验条：检测到队伍经验，本会话仅保留提示计数';return []
        events=self.finish(now,allow_topup)
        if reading is None:
            self.candidate=None;self.samples=0
            if self.last_time is None or now-self.last_time>1.2:
                # Keep already verified increments, discard only the uncertain gap.
                self.last=None;self.last_confirmed_time=None
            self.status='经验条：短暂未读清，继续重读';return events
        if self.last_time is not None and now-self.last_time>3:
            self.last=None;self.candidate=None;self.samples=0
        self.last_time=now
        if reading==self.candidate:self.samples+=1
        else:self.candidate=reading;self.candidate_at=now;self.samples=1
        if self.samples<2:
            self.status=f'经验条：{reading.amount:,}，验证下一帧';return events
        if self.last is None:
            self.last=reading;self.last_confirmed_time=now
            self.status=f'经验条：基线 {reading.amount:,}，连续增量对账中';return events
        if reading==self.last:
            # Narrow the time interval to the last unchanged visible sample.
            self.last_confirmed_time=now
            self.status=f'经验条：{reading.amount:,}；待配对增量 {len(self.steps)} 段';return events
        if not compatible_level(self.last,reading):
            self.last=reading;self.last_confirmed_time=now
            self.status='经验条：升级、经验减少或读数冲突，重建基线';return events
        delta=reading.amount-self.last.amount
        if delta>0:
            self.steps.append(dict(delta=delta,combo=unique_monsters(delta,profile),
                profile=dict(profile),start=self.last_confirmed_time,at=self.candidate_at))
        self.last=reading;self.last_confirmed_time=now
        # Six seconds of delayed matching normally holds only a few increments.
        # If a caller cannot keep up, settle verified data instead of growing memory.
        if len(self.steps)>128:events+=self.finish(now,allow_topup,force=True)
        self.status=f'经验条：已验证 +{delta}；连续打怪也会自动配对补计'
        return events


class HudSampler:
    """One small, bounded worker. No UI, game memory, input or disk images.

    Capture+recognition is independent of notification OCR. Queue holds numeric
    results only; overflow invalidates reconciliation instead of hiding gaps.
    """
    def __init__(self,hwnd,rect,box,capture,period=.15,recognizer=read_crop):
        self.hwnd=hwnd;self.rect=rect;self.box=box;self.capture=capture
        self.period=max(.1,period);self.recognizer=recognizer
        self.results=deque(maxlen=128);self.lock=threading.Lock();self.stop_event=threading.Event()
        self.dropped=0;self.thread=None
        self.latest=None

    def snapshot(self):
        with self.lock:
            if self.latest is None:return None
            image,details=self.latest
            return image.copy(),dict(details)

    def start(self):
        self.thread=threading.Thread(target=self.run,name='CW-HUD-EXP',daemon=True);self.thread.start()

    def push(self,value):
        with self.lock:
            if len(self.results)==self.results.maxlen:self.dropped+=1
            self.results.append(value)

    def drain(self):
        with self.lock:
            result=list(self.results);self.results.clear();dropped=self.dropped;self.dropped=0
        return result,dropped

    def sample_once(self,previous_key=None,previous_reading=None):
        started=time.monotonic();c=self.capture
        if not c.foreground(self.hwnd) or c.client_rect(self.hwnd)!=self.rect or not c.region_on_screen(self.rect,self.box):
            return (started,None,0.,False,False),None,None
        image=c.grab_region(self.hwnd,self.box).convert('RGB')
        if not c.foreground(self.hwnd) or c.client_rect(self.hwnd)!=self.rect:
            return (started,None,0.,False,False),None,None
        key=hashlib.sha256(image.tobytes()).digest()
        reused=key==previous_key and previous_reading is not None
        debug={}
        if reused:reading=previous_reading
        elif self.recognizer is read_crop:reading=self.recognizer(image,debug=debug)
        else:reading=self.recognizer(image)
        # Switching away during OCR also invalidates this result.
        if not c.foreground(self.hwnd) or c.client_rect(self.hwnd)!=self.rect:
            return (started,None,0.,False,False),None,None
        with self.lock:
            self.latest=(image,dict(sample_time=started,box=self.box,
                amount=reading.amount if reading else None,percent=reading.percent if reading else None,
                reused=reused,evidence=debug))
        return (started,reading,(time.monotonic()-started)*1000,reused,True),key,reading

    def run(self):
        key=reading=None
        while not self.stop_event.is_set():
            started=time.monotonic()
            try:result,key,reading=self.sample_once(key,reading)
            except Exception:result=(started,None,0.,False,False);key=reading=None
            self.push(result)
            self.stop_event.wait(max(.02,self.period-(time.monotonic()-started)))

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=.5)
