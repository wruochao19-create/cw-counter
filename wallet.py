"""Read the visible inventory balance, anchored to the white field and coin."""
import re
from difflib import SequenceMatcher

import cv2
import numpy as np

from pixel_ocr import model


def wallet_balance(image,details=None):
    """Return (field visible, verified amount). Ambiguous fields are unreadable."""
    rgb = np.asarray(image.convert('RGB'))
    scale = min(1, 1100 / image.width)
    small = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    mask = cv2.inRange(small, (243, 243, 243), (255, 255, 255))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    values = []
    visible = False
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if h < 6 or not 6 <= w / h <= 28 or cv2.contourArea(contour) < .7*w*h:
            continue
        coin = small[y:y+h, max(0, x-2*h):x]
        if not coin.size:
            continue
        gold = cv2.inRange(coin, (150, 95, 0), (255, 240, 100))
        if cv2.countNonZero(gold) < .025*h*h:
            continue
        left, top, right, bottom = [round(v/scale) for v in (x,y,x+w,y+h)]
        unit = rgb[top:bottom, right:min(image.width,right+round(4*h/scale))]
        field = rgb[top:bottom,left:right]
        if not unit.size or not field.size:
            continue
        # MESOS appears immediately to the right of the number in inventory.
        # Read the digits at their natural aspect ratio. A wide, almost empty
        # balance field otherwise gets compressed by the recognition model.
        margin = max(1, field.shape[0]//12)
        inner = field[margin:-margin, margin:-margin]
        ink = np.where(inner.max(axis=2) < 150)
        if not ink[0].size:
            continue
        field = inner[:, max(0,int(ink[1].min())-margin):int(ink[1].max())+margin+1]
        crops = [cv2.resize(crop[:,:,::-1], None, fx=40/field.shape[0],
                            fy=40/field.shape[0], interpolation=cv2.INTER_CUBIC)
                 for crop in (unit,field)]
        crops.append(cv2.convertScaleAbs(crops[1],alpha=1.1,beta=-8))
        reads, _ = model().text_rec(crops,return_word_box=True)
        if details is not None and len(details.setdefault('attempts',[]))<4:
            details['attempts'].append([dict(text=r[0],score=round(float(r[1]),4)) for r in reads])
        unit_text=reads[0][0].strip().upper() if reads else ''
        if (len(reads)!=3 or not 4<=len(unit_text)<=6 or reads[0][1]<.7 or
                SequenceMatcher(None,unit_text,'MESOS').ratio()<.75):
            continue
        visible = True
        if details is not None:
            details['box']=(max(0,round((x-2*h)/scale)),max(0,top-3),
                            min(image.width,right+round(4*h/scale)),min(image.height,bottom+3))
        amounts=[]
        for text,confidence,evidence in reads[1:]:
            digits=text.strip()
            scores=[float(p) for c,p in zip(text,evidence[4]) if c.isdigit()]
            if (confidence>=.9 and scores and min(scores)>=.9 and
                    re.fullmatch(r'(?:[0-9]+|[0-9]{1,3}(?:[,.][0-9]{3})+)',digits)):
                amounts.append(int(digits.replace(',','').replace('.','')))
        if len(amounts)==2 and amounts[0]==amounts[1]:
            values.append(amounts[0])
    return visible, values[0] if len(values)==1 else None


class WalletCheck:
    def __init__(self):
        self.phase = 'start'
        self.start = self.end = None
        self.previous = None
        self.absent = 0
        self.next_scan = 0.
        self.last_lines = None
        self.last_scan = None
        self.total = 0
        self.uncertain = 0

    def observe(self, visible, amount, now):
        if self.phase == 'done':
            return None
        if self.phase == 'close':
            self.absent = 0 if visible else self.absent + 1
            if self.absent >= 2:
                self.phase = 'end'
            return None
        if not visible or amount is None or amount != self.previous:
            self.previous = amount if visible else None
            return None
        self.previous = None
        if self.phase == 'start':
            self.start = now, amount
            self.phase = 'close'
            return 'wallet_start'
        self.end = now, amount
        self.phase = 'done'
        return 'wallet_end'

    def count_event(self, at, amount, valid):
        if not self.start or at <= self.start[0] or (self.end and at > self.end[0]):
            return
        if valid:
            self.total += amount
        else:
            self.uncertain += 1


class LiveWalletCheck:
    """Compare one live balance interval with hints born in that same interval."""
    def __init__(self):
        self.phase='live'
        self.start=self.end=self.current=self.previous=None
        self.next_scan=0.
        self.last_lines=self.last_scan=None
        self.total=self.uncertain=0
        self.pending=[]
        self.last_read_at=None
        self.segment_start=None
        self.closed_intervals=[]
        self.saved_seconds=0.
        self.saved_gain=0

    def observe(self,visible,amount,now):
        if self.phase=='done':return None
        if self.last_read_at is not None and now<=self.last_read_at:return None
        self.last_read_at=now
        if not visible or amount is None:
            self.previous=None
            return None
        previous=self.previous
        self.previous=(now,amount)
        if previous is None or now-previous[0]>2:return None
        # A new, increasing balance need not remain unchanged while party loot
        # arrives. Confirm the preceding two-route OCR point with the next one.
        # A lone high spike followed by a lower value is never committed.
        if amount<previous[1]:return None
        self.current=previous
        self.phase='live'
        if self.start is None:
            self.start=previous
            marker='wallet_live_start'
        else:
            marker='wallet_live_sample'
        if self.segment_start is None:self.segment_start=previous
        pending,self.pending=self.pending,[]
        for at,value,valid in pending:self.count_event(at,value,valid)
        return marker

    def count_event(self,at,amount,valid):
        past=any(start<at<=end for start,end in self.closed_intervals)
        if past:
            if valid:self.total+=amount
            else:self.uncertain+=1
            return
        if self.segment_start is None:
            if self.previous and at>self.previous[0]:
                self.pending.append((at,amount,valid))
            return
        if at<=self.segment_start[0]:return
        if at>self.current[0]:
            if self.phase!='done':self.pending.append((at,amount,valid))
        elif valid:
            self.total+=amount
        else:
            self.uncertain+=1

    def break_interval(self):
        if self.segment_start is not None:
            self.saved_seconds+=self.current[0]-self.segment_start[0]
            self.saved_gain+=self.current[1]-self.segment_start[1]
            self.closed_intervals.append((self.segment_start[0],self.current[0]))
        self.segment_start=None
        self.previous=None
        self.pending.clear()
        if self.phase!='done':self.phase='paused'

    def finish(self):
        self.phase='done'
        self.end=self.current
        self.pending.clear()

    def snapshot(self,now=None):
        elapsed=self.saved_seconds
        gain=self.saved_gain if self.start else None
        if self.segment_start:
            elapsed+=self.current[0]-self.segment_start[0]
            gain+=self.current[1]-self.segment_start[1]
        ready=elapsed>=30
        fresh=bool(self.phase=='live' and self.current and (now is None or now-self.current[0]<=2))
        return dict(start=self.start,current=self.current,seconds=round(elapsed,3),
                    wallet_gain=gain,notification_gain=self.total,uncertain=self.uncertain,
                    difference=gain-self.total if gain is not None else None,
                    wallet_per_hour=round(gain*3600/elapsed) if ready else None,
                    notification_per_hour=round(self.total*3600/elapsed) if ready else None,
                    live=fresh,segments=list(self.closed_intervals),
                    current_segment_start=self.segment_start)
