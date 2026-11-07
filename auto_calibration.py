"""Automatic notification search, geometry confirmation, and bounded recovery."""
import math
import re


def search_box(width,height):
    # Keep the complete right edge and the rows above the newest notification.
    return (max(0,width-max(360,round(width*.32))),max(0,round(height*.52)),
            width,min(height,round(height*.94)))


def valid_box(box,width,height):
    return (isinstance(box,(list,tuple)) and len(box)==4 and
            all(isinstance(v,(int,float)) and math.isfinite(v) for v in box) and
            0<=box[0]<box[2]<=width and 0<=box[1]<box[3]<=height and
            box[2]-box[0]>=100 and box[3]-box[1]>=60)


class AutoRegion:
    def __init__(self,width,height,saved=None):
        self.width,self.height=width,height
        self.search=search_box(width,height)
        self.wide=(max(0,width-max(420,round(width*.45))),max(0,round(height*.35)),width,height)
        reusable=(isinstance(saved,dict) and saved.get('version')==1 and
                  saved.get('width')==width and saved.get('height')==height and
                  valid_box(saved.get('region'),width,height))
        self.box=tuple(round(v) for v in saved['region']) if reusable else self.search
        self.phase='verifying' if reusable else 'searching'
        self.has_location=bool(reusable)
        self.probe_backup=None
        self.probe_frames=0
        self.change_reason='提示文字已连续定位，自动保留上方滚动空间'
        self.pending=None
        self.hits=0
        self.last_evidence=None
        self.last_expand=float('-inf')

    def resume(self):
        self.phase='verifying'
        self.pending=None;self.hits=0;self.last_evidence=None

    def expand_if_idle(self,now):
        if self.last_evidence is None:
            self.last_evidence=now
        # No messages can simply mean idle. A slow wider search is harmless and
        # does not reset message identities or repeatedly seed a new baseline.
        wait=15 if self.has_location else 6
        cooldown=30 if self.has_location else 6
        if now-self.last_evidence>=wait and now-self.last_expand>=cooldown and self.box!=self.wide:
            if self.has_location:
                self.probe_backup=(self.box,self.phase)
                self.probe_frames=0
            old=self.box;self.box=self.wide
            self.phase='probing' if self.has_location else 'searching'
            self.pending=None;self.hits=0
            self.last_expand=now
            return old,self.box
        return None

    def observe(self,lines,now):
        if self.probe_backup:self.probe_frames+=1
        candidates=[]
        for line in lines:
            compact=re.sub(r'\s+','',line.get('text','')).lower()
            said=line.get('said')
            notification=(said and said[0] in ('exp','bonus','mesos')) or ('receivedexp' in compact)
            if not notification or line.get('score',0)<.7:
                continue
            x,y,right,bottom=line['box']
            if bottom-y<3 or x<0 or right>self.box[2]-self.box[0]+3:
                continue
            candidates.append((x,y,right,bottom))
        if not candidates:
            if self.probe_backup and self.probe_frames>=2:
                return self.restore_probe()
            return None
        self.last_evidence=now
        height=max(bottom-y for x,y,right,bottom in candidates)
        bottom=max((y+end)/2+self.box[1] for x,y,right,end in candidates)
        # Generous vertical context prevents identical consecutive EXP messages
        # being merged when their older rows scroll upward.
        left=max(0,min(round(min(x for x,y,r,b in candidates)+self.box[0]-height*2),
                       self.width-max(360,round(self.width*.20))))
        top=max(0,round(bottom-height*14))
        end=min(self.height,round(bottom+height*2))
        candidate=(left,top,self.width,end)
        if not valid_box(candidate,self.width,self.height):
            return None
        if self.pending and abs(candidate[3]-self.pending[3])<=max(5,height):
            self.hits+=1
        else:
            self.pending=candidate;self.hits=1
        if self.hits<2:
            if self.probe_backup and self.probe_frames>=3:
                return self.restore_probe()
            return None
        if self.phase=='ready':
            return None
        self.phase='ready'
        self.has_location=True
        self.probe_backup=None
        self.change_reason='提示文字已连续定位，自动保留上方滚动空间'
        old=self.box
        self.box=candidate
        return (old,self.box) if old!=self.box else None

    def restore_probe(self):
        old=self.box
        self.box,self.phase=self.probe_backup
        self.probe_backup=None
        self.pending=None;self.hits=0
        self.change_reason='空闲探测未发现新位置，恢复已验证的小区域'
        return old,self.box

    def settings(self):
        return dict(version=1,width=self.width,height=self.height,region=list(self.box))
