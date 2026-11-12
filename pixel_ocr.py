"""Small English OCR model plus conservative, multi-frame notification tracking."""
import bootstrap
import re
import uuid
import hashlib
from difflib import SequenceMatcher
from dataclasses import dataclass,field
import numpy as np
import cv2
from PIL import Image
from candidate_ocr import enhance_lines

_model=None


def model():
    global _model
    if _model is None:
        from rapidocr_onnxruntime import RapidOCR
        _model=RapidOCR(rec_model_path=str(bootstrap.ROOT/'assets/en-rec.onnx'),
                        det_limit_type='max',det_limit_side_len=960,
                        intra_op_num_threads=1,inter_op_num_threads=1)
    return _model


def notification_parts(s):
    # OCR can split the m into rn or confuse one currency letter. Match the
    # fixed sentence and unit together, keeping the amount outside this match.
    boundary=re.search(r'[\(\[\{+]',s)
    if boundary:
        end=boundary.start()
        for length in range(4,8):
            start=end-length
            if start<=0:continue
            unit=s[start:end]
            if (unit.isalnum() and SequenceMatcher(None,unit,'mesos').ratio()>=.7 and
                    SequenceMatcher(None,s[:start],'youhavegained').ratio()>=.8):
                return 'mesos',end,s[end:]
    for match in re.finditer(r'exp|ep|xp|rnesos|mesos|nesos',s):
        marker=match.group();prefix=s[:match.start()];start=match.end()
        if marker in ('mesos','rnesos','nesos') and SequenceMatcher(None,prefix,'youhavegained').ratio()>=.8:
            return 'mesos',start,s[start:]
        if marker=='exp' and prefix.endswith('bonus') and s[start:].startswith('forparty'):
            return 'bonus',start+8,s[start+8:]
        if marker!='mesos' and SequenceMatcher(None,prefix,'youreceived').ratio()>=.8:
            return 'exp',start,s[start:]
    return None


def complete_number(text):
    return bool(re.search(r'\d\s*[)\]}][.!]*\s*$',text))


def parse_notification(text):
    s=re.sub(r'\s+','',text).lower()
    parts=notification_parts(s)
    if not parts:return None
    kind,_,tail=parts
    # Parentheses/+ sometimes become C/G in this outlined font. Never replace a digit.
    match=re.fullmatch(r'[\(\[\{+cg]*([0-9][0-9,]*)[\)\]\}.!]*',tail)
    if not match:
        return None
    digits=match.group(1)
    if ',' in digits and not re.fullmatch(r'\d{1,3}(,\d{3})+',digits):
        return None
    amount=int(digits.replace(',',''))
    return (kind,amount) if 0<amount<100000000 else None


def text_color(image,box):
    x0,y0,x1,y1=map(round,box)
    a=np.asarray(image.convert('RGB'))[max(0,y0):max(0,y1),max(0,x0):max(0,x1)]
    if not a.size:
        return 'unknown'
    light=np.minimum(a[:,:,0],a[:,:,1])
    # Prefer bright letter cores rather than green scenery and the dark outline.
    mask=(light>=max(140,float(np.percentile(light,92))))
    if mask.sum()<5:
        return 'unknown'
    ratio=float(np.median(a[:,:,2][mask]/np.maximum(1,a[:,:,0][mask].astype(float))))
    return 'white' if ratio>.72 else 'yellow' if ratio<.48 else 'unknown'


def text_metrics(image,box,color):
    x,y,right,bottom=map(round,box)
    a=np.asarray(image.convert('RGB'))[max(0,y):max(0,bottom),max(0,x):max(0,right)]
    if not a.size:return None,None
    light=np.minimum(a[:,:,0],a[:,:,1])
    shade=cv2.erode(light,np.ones((3,3),np.uint8))
    edges=(light.astype(np.int16)-shade.astype(np.int16)>35)&(light>70)
    if color=='white':edges&=(a[:,:,2]>.65*a[:,:,0])
    elif color=='yellow':edges&=(a[:,:,2]<.65*a[:,:,0])
    else:return None,None
    if edges.sum()<8:return None,None
    contrast=light.astype(np.int16)-shade.astype(np.int16)
    return float(np.percentile(light[edges],80)),float(np.percentile(contrast[edges],80))


def number_evidence(text,confidences):
    """Extract suffix digits and their individual scores; never fix a digit using a mob table."""
    chars=[(char.lower(),float(prob)) for char,prob in zip(text,confidences) if not char.isspace()]
    compact=''.join(char for char,prob in chars)
    parts=notification_parts(compact)
    if not parts:return None,0.0
    _,start,tail=parts
    match=re.fullmatch(r'[\(\[\{+cg]*([0-9][0-9,]*)[\)\]\}.!]*',tail)
    if not match:
        return None,0.0
    digits=match.group(1)
    if ',' in digits and not re.fullmatch(r'\d{1,3}(,\d{3})+',digits):
        return None,0.0
    amount=int(digits.replace(',',''))
    scores=[prob for char,prob in chars[start+match.start(1):start+match.end(1)] if char.isdigit()]
    return (amount,min(scores)) if scores and 0<amount<100000000 else (None,0.0)


def verify_numbers(bgr,raw_lines,lines,first_reads=None):
    indices=[i for i,line in enumerate(lines) if line['said']]
    if not indices:
        return
    crops=model().get_crop_img_list(bgr,[np.asarray(raw_lines[i][0],dtype=np.float32) for i in indices])
    variants=[]
    for crop in crops:
        if first_reads is None:variants.append(crop)
        variants.append(cv2.convertScaleAbs(crop,alpha=1.2,beta=-15))
    details,_=model().text_rec(variants,return_word_box=True)
    for n,index in enumerate(indices):
        first,second=(details[2*n:2*n+2] if first_reads is None else (first_reads[index],details[n]))
        evidence=[number_evidence(result[0],result[2][4]) for result in (first,second)]
        expected=lines[index]['said'][1]
        verified=(all(amount==expected and score>=.7 for amount,score in evidence)
                  and all(complete_number(result[0]) for result in (first,second)))
        lines[index].update(digit_verified=verified,digit_reads=[amount for amount,score in evidence],
                            digit_min_score=min(score for amount,score in evidence),
                            digit_scores=[score for amount,score in evidence],
                            digit_texts=[result[0] for result in (first,second)],
                            digit_complete=[complete_number(result[0]) for result in (first,second)])


def apply_map_constraint(lines,profile):
    if profile is None:
        return lines
    for line in lines:
        if line['said'] and line['said'][0]=='exp' and line['color']!='yellow':
            matches=[name for name,exp in profile.items() if exp==line['said'][1]]
            line.update(map_matches=matches,map_verified=bool(matches))
    return lines


def retry_with_map(image,lines,profile):
    """Map narrows admissible rereads; it never supplies a replacement number by distance."""
    if not profile:
        return
    expected=set(profile.values())
    targets=[];variants=[]
    for i,line in enumerate(lines):
        parsed=line['said']
        if parsed and (parsed[0]!='exp' or (line['digit_verified'] and parsed[1] in expected)):
            continue
        compact=re.sub(r'\s+','',line['text']).lower()
        parts=notification_parts(compact)
        if not parts or parts[0]!='exp':
            continue
        left,top,right,bottom=line['box']
        # Include a detached numeric block at the same row's right end.
        crop=image.crop((max(0,int(left)-1),max(0,int(top)-1),image.width,min(image.height,round(bottom)+1)))
        factor=min(4,max(1,48/crop.height))
        size=(max(1,round(crop.width*factor)),max(1,round(crop.height*factor)))
        for interpolation in (Image.Resampling.NEAREST,Image.Resampling.BICUBIC):
            variants.append(np.asarray(crop.resize(size,interpolation))[:,:,::-1].copy())
        targets.append(i)
    if not targets:
        return
    details,_=model().text_rec(variants,return_word_box=True)
    for n,index in enumerate(targets):
        pair=details[2*n:2*n+2]
        evidence=[number_evidence(row[0],row[2][4]) for row in pair]
        line=lines[index]
        line['map_rereads']=[value for value,score in evidence]
        value=evidence[0][0]
        if value not in expected or not all(v==value and score>=.7 for v,score in evidence) or not all(complete_number(row[0]) for row in pair):
            continue
        old=line['said']
        # Two plausible values already in the map remain ambiguous. Strong original
        # evidence for an out-of-catalog value may be real partial EXP; do not replace it.
        if old and old[1]!=value and (line['digit_verified'] or (old[1] in expected and complete_number(line['text']))):
            continue
        line.update(said=('exp',value),digit_verified=True,digit_reads=[v for v,s in evidence],
                    digit_min_score=min(s for v,s in evidence),score=min(float(row[1]) for row in pair),
                    map_reread_used=True)


def scan(image,profile=None):
    factor=3 if image.width<650 else 2
    factor=min(factor,1800/max(image.size))
    scaled=image.resize((max(1,round(image.width*factor)),max(1,round(image.height*factor))),Image.Resampling.LANCZOS)
    bgr=np.asarray(scaled)[:,:,::-1].copy()
    # Keep the first recognition's character evidence. The previous path read
    # every notification three times, discarding the first pass's digit scores.
    # Bound detection cost without shrinking the crops used to read digits.
    # This RapidOCR version chooses an adaptive maximum internally; resize the
    # detector input explicitly rather than assuming its config is a hard cap.
    detector_factor=min(960/max(bgr.shape[:2]),max(1,736/min(bgr.shape[:2])))
    dw,dh=max(1,round(bgr.shape[1]*detector_factor)),max(1,round(bgr.shape[0]*detector_factor))
    detector=cv2.resize(bgr,(dw,dh),interpolation=cv2.INTER_CUBIC if detector_factor>1 else cv2.INTER_AREA)
    boxes,_=model()(detector,use_cls=False,use_rec=False)
    if not boxes:return []
    boxes=[np.asarray(q,dtype=np.float32)*np.array([bgr.shape[1]/dw,bgr.shape[0]/dh]) for q in boxes]
    crops=model().get_crop_img_list(bgr,[np.asarray(q,dtype=np.float32) for q in boxes])
    details,_=model().text_rec(crops,return_word_box=True)
    selected=[(quad,detail) for quad,detail in zip(boxes,details) if detail[1]>=.5 and detail[0]]
    lines=[];result=[];first_reads=[]
    for quad,detail in selected:
        text,score=detail[:2]
        result.append((quad,text,score));first_reads.append(detail)
        points=np.array(quad)/factor
        box=(float(points[:,0].min()),float(points[:,1].min()),float(points[:,0].max()),float(points[:,1].max()))
        color=text_color(image,box)
        brightness,contrast=text_metrics(image,box,color)
        lines.append(dict(text=text,score=float(score),box=box,said=parse_notification(text),color=color,
                          brightness=brightness,contrast=contrast,digit_verified=False))
    verify_numbers(bgr,result,lines,first_reads)
    enhance_lines(image,lines,profile,model().text_rec,notification_parts)
    retry_with_map(image,lines,profile)
    apply_map_constraint(lines,profile)
    return sorted(lines,key=lambda line:line['box'][1],reverse=True)


@dataclass
class Track:
    key: tuple
    center: float
    height: float
    last_seen: float
    colors: list
    digit_checks: list
    hits: int=1
    done: bool=False
    brightness: float | None=None
    contrast: float | None=None
    born: float=0.0
    absent: bool=False
    observations: list=field(default_factory=list)
    candidate_votes: list=field(default_factory=list)


class NotificationTracker:
    def __init__(self):
        self.reset()

    def reset(self):
        self.tracks=[]
        self.baseline=True
        self.last_time=None
        self.generation=uuid.uuid4().hex[:12]
        self.sequence=0

    def update(self,lines,timestamp):
        interval=timestamp-self.last_time if self.last_time is not None else 0
        gap=interval>2
        if gap:
            self.reset()
        self.last_time=timestamp
        # A typo in the fixed English prefix must not discard clearly read digits.
        # Weak lines can be tracked as uncertain; counting still needs independent
        # numeric evidence in both frames and a recognized notification prefix.
        items=[line for line in lines if line['said'] and line['score']>=.7]
        # Slow OCR must still be able to confirm two consecutive frames. With a
        # fixed .8s lifetime, ~1s frames continually threw away their first look.
        retention=min(4,max(3,interval*2))
        old=[t for t in self.tracks if timestamp-t.last_seen<retention]
        expired=[t for t in self.tracks if timestamp-t.last_seen>=retention and not t.done and t.key[0] in ('exp','bonus','mesos')]
        if self.baseline:
            self.tracks=[self.make_track(line,timestamp,True) for line in items]
            self.baseline=False
            return [],gap
        # Find the upward movement explaining existing messages. Unmatched text above
        # the stack is evidence of a missed OCR line, never evidence of a new kill.
        deltas={0.0}
        for track in old:
            for line in items:
                center=(line['box'][1]+line['box'][3])/2
                # A scrolling hint can lose a digit in this frame. Use the same
                # guarded compatibility rule as association so its motion is
                # still considered; otherwise the recovered text counts twice.
                if self.compatible(track,line,timestamp) and track.center-center>track.height*.6:
                    deltas.add(round(track.center-center,1))
        best=None
        for delta in deltas:
            pairs=[]; used=set()
            for i,line in enumerate(items):
                center=(line['box'][1]+line['box'][3])/2
                candidates=[(abs(track.center-delta-center),j) for j,track in enumerate(old)
                            if j not in used and self.compatible(track,line,timestamp) and
                            abs(track.center-delta-center)<=max(3,track.height*.5) and
                            not (delta==0 and track.absent and timestamp-track.born>=2.5 and self.brightness_rise(track,line))]
                if candidates:
                    distance,j=min(candidates);pairs.append((i,j));used.add(j)
            matched={i for i,j in pairs}
            floor=max((t.center-delta for t in old),default=-1)
            score=len(pairs)*3-delta*.001
            # At a steady stack size, all strings can be identical. Their fresh
            # brightness explains a scroll that text/position alone cannot see.
            rises=sum(self.brightness_rise(old[j],items[i]) for i,j in pairs)
            if rises>=2:score-=4*rises
            for i,line in enumerate(items):
                if i not in matched:
                    center=(line['box'][1]+line['box'][3])/2
                    score+=.5 if center>=floor-3 else -2
            if best is None or score>best[0]:
                best=(score,delta,pairs)
        _,delta,pairs=best
        matched={i:j for i,j in pairs}
        used={j for i,j in pairs}
        updated=[];events=[self.uncertain_event(track,'提示消失前未取得两帧有效证据，不计为击杀') for track in expired]
        for i,line in enumerate(items):
            if i in matched:
                track=old[matched[i]]
                track.center=(line['box'][1]+line['box'][3])/2
                track.last_seen=timestamp
                track.brightness=line.get('brightness')
                track.contrast=line.get('contrast')
                track.absent=False
                track.hits+=1
                track.observations.append((line['said'][1],self.valid_evidence(line),line['color']))
                track.observations=track.observations[-8:]
                track.candidate_votes.append(line['said'][1] if line.get('candidate_verified') else None)
                track.candidate_votes=track.candidate_votes[-8:]
                if self.valid_evidence(line) and not any(track.digit_checks):track.key=line['said']
                track.colors.append(line['color'])
                track.colors=track.colors[-4:]
                track.digit_checks.append(self.valid_evidence(line))
                track.digit_checks=track.digit_checks[-2:]
            else:
                center=(line['box'][1]+line['box'][3])/2
                # EXP can first be visible above newer coin/item messages. Its
                # vertical position alone is not evidence that it predates us.
                # Retained tracks handle short OCR dropouts; only a real capture
                # baseline seeds all visible lines as already counted.
                track=self.make_track(line,timestamp)
            if not track.done and track.hits>=2:
                known_colors={color for value,strong,color in track.observations if color in ('white','yellow')}
                same=len(known_colors)==1
                resolved_color=next(iter(known_colors)) if same else 'unknown'
                # Fading can obscure color and individual intermediate frames.
                # Accumulate independent numeric evidence for this tracked hint;
                # unknown color is missing evidence, not a conflicting color.
                verified=sum(value==track.key[1] and strong for value,strong,color in track.observations)>=2
                if verified and (same or track.key[0]=='mesos'):
                    self.sequence+=1
                    events.append(dict(event_id=f'{self.generation}-{self.sequence}',kind=track.key[0],amount=track.key[1],
                                       observed_at=track.born,
                                       color=resolved_color,confident=verified,
                                       note='两帧金币金额一致' if track.key[0]=='mesos' else '同条提示两帧数字/地图验证通过，已知颜色一致'))
                    track.done=True
            updated.append(track)
        for j,track in enumerate(old):
            if j not in used:
                track.center-=delta
                track.absent=not any(abs((row['box'][1]+row['box'][3])/2-track.center)<=max(3,track.height*.5) for row in lines)
                updated.append(track)
        self.tracks=updated[:24]
        return events,gap

    def uncertain_event(self,track,note):
        self.sequence+=1;track.done=True
        if track.key[0]=='mesos':
            note='金币提示结束时，未取得两帧一致金额'
        votes=[v for v in track.candidate_votes if v is not None]
        known={color for value,strong,color in track.observations if color in ('white','yellow')}
        strong_values={v for v,strong,color in track.observations if strong}
        if (track.key[0]=='exp' and known=={'white'} and len(votes)>=2 and len(set(votes))==1
                and (not strong_values or strong_values=={votes[0]})):
            return dict(event_id=f'{self.generation}-{self.sequence}',kind='exp',amount=votes[0],
                        observed_at=track.born,
                        color='white',confident=True,estimated=True,
                        note='地图图像候选估计：至少两帧行尾概率比较支持同一经验，保留估计标签')
        anchors={v for v,strong,color in track.observations if strong and color=='white'}
        if track.key[0]=='exp' and len(anchors)==1 and len(track.observations)>=3:
            value=next(iter(anchors))
            supporting=sum(color=='white' and SequenceMatcher(None,str(v),str(value)).ratio()>=.5
                           for v,strong,color in track.observations)
            if supporting>=3 and all(color=='white' for v,strong,color in track.observations):
                return dict(event_id=f'{self.generation}-{self.sequence}',kind='exp',amount=value,
                            observed_at=track.born,
                            color='white',confident=True,estimated=True,
                            note='估计：同一位置连续提示，至少一帧数字与地图验证通过，另两帧相似；不等同两帧精确确认')
        return dict(event_id=f'{self.generation}-{self.sequence}',kind=track.key[0],amount=track.key[1],
                    observed_at=track.born,
                    color=track.colors[-1],confident=False,note=note)

    def finish(self):
        return [self.uncertain_event(t,'会话结束时提示尚未确认，不计为击杀')
                for t in self.tracks if not t.done and t.key[0] in ('exp','bonus','mesos')]

    @staticmethod
    def compatible(track,line,timestamp):
        if track.key==line['said']:return True
        if track.key[0]!='exp' or line['said'][0]!='exp':return False
        if track.absent or timestamp-track.last_seen>1 or NotificationTracker.brightness_rise(track,line):return False
        if any(strong for value,strong,color in track.observations) and NotificationTracker.valid_evidence(line):return False
        return SequenceMatcher(None,str(track.key[1]),str(line['said'][1])).ratio()>=.5

    @staticmethod
    def brightness_rise(track,line):
        before,after=track.brightness,line.get('brightness')
        if before is None or after is None or after-before<max(12,before*.07):return False
        previous,current=track.contrast,line.get('contrast')
        return previous is None or current is None or current-previous>=max(10,previous*.08)

    @staticmethod
    def valid_evidence(line):
        return bool(line.get('digit_verified',False) and line.get('map_verified',True) and
                    (line['score']>=.8 or line.get('digit_min_score',0)>=.85))

    @staticmethod
    def make_track(line,timestamp,done=False):
        _,y,_,bottom=line['box']
        return Track(line['said'],(y+bottom)/2,bottom-y,timestamp,[line['color']],
                     [NotificationTracker.valid_evidence(line)],done=done,
                     brightness=line.get('brightness'),contrast=line.get('contrast'),born=timestamp,
                     observations=[(line['said'][1],NotificationTracker.valid_evidence(line),line['color'])],
                     candidate_votes=[line['said'][1] if line.get('candidate_verified') else None])


class NotificationStrips:
    """Locate outlined text rows near the learned right edge, without a detector."""
    def __init__(self):
        self.height=None
        self.right=None

    def learn(self,lines):
        hints=[line for line in lines if line.get('said') and line['score']>=.8]
        if hints:
            self.height=float(np.median([r['box'][3]-r['box'][1] for r in hints]))
            self.right=max(r['box'][2] for r in hints)

    def boxes(self,image):
        if self.height is None:return []
        rgb=np.asarray(image.convert('RGB'))
        light=np.minimum(rgb[:,:,0],rgb[:,:,1])
        shade=cv2.erode(light,np.ones((3,3),np.uint8))
        # White/yellow letter cores with a dark outline. Scenery can also pass,
        # so OCR still has to identify a complete system notification.
        high=rgb.max(axis=2).astype(np.int16)
        low=rgb.min(axis=2).astype(np.int16)
        white=high-low<high*.15
        yellow=(rgb[:,:,1]>.85*rgb[:,:,0])&(rgb[:,:,2]<.4*rgb[:,:,0])
        glyph=((light.astype(np.int16)-shade.astype(np.int16))>45)&(light>125)&(white|yellow)
        right=min(image.width,round(self.right+4))
        tail=max(0,right-round(self.height*1.7))
        present=(glyph[:,tail:right].sum(axis=1)>=3).astype(np.uint8)
        present=cv2.morphologyEx(present[:,None],cv2.MORPH_CLOSE,np.ones((3,1),np.uint8))[:,0]
        edges=np.diff(np.pad(present,(1,1)).astype(np.int16))
        boxes=[]
        for top,bottom in zip(np.flatnonzero(edges==1),np.flatnonzero(edges==-1)):
            if not self.height*.35<=bottom-top<=self.height*1.6:continue
            columns=np.flatnonzero(glyph[top:bottom,:right].sum(axis=0)>0)
            if not len(columns) or columns[-1]<right-self.height*.6:continue
            gaps=np.flatnonzero(np.diff(columns)>self.height*.8)
            left=int(columns[gaps[-1]+1] if len(gaps) else columns[0])
            boxes.append((max(0,left-3),max(0,int(top)-3),right,min(image.height,int(bottom)+3)))
        return boxes[-16:]

    def read(self,image,profile):
        boxes=self.boxes(image)
        if not boxes:return []
        crops=[]
        for box in boxes:
            crop=image.crop(box)
            crop=crop.resize((max(1,round(crop.width*40/crop.height)),40),Image.Resampling.BICUBIC)
            bgr=np.asarray(crop)[:,:,::-1].copy()
            crops.extend((bgr,cv2.convertScaleAbs(bgr,alpha=1.2,beta=-15)))
        details,_=model().text_rec(crops,return_word_box=True)
        lines=[]
        for index,box in enumerate(boxes):
            pair=details[index*2:index*2+2]
            text,score=pair[0][:2]
            said=parse_notification(text)
            if not said:continue
            evidence=[number_evidence(r[0],r[2][4]) for r in pair]
            complete=[complete_number(r[0]) for r in pair]
            verified=all(value==said[1] and strength>=.7 for value,strength in evidence) and all(complete)
            color=text_color(image,box)
            brightness,contrast=text_metrics(image,box,color)
            lines.append(dict(text=text,score=float(score),box=box,said=said,color=color,
                              brightness=brightness,contrast=contrast,digit_verified=verified,
                              digit_reads=[v for v,s in evidence],digit_scores=[s for v,s in evidence],
                              digit_min_score=min(s for v,s in evidence),digit_complete=complete,
                              digit_texts=[r[0] for r in pair]))
        apply_map_constraint(lines,profile)
        return sorted(lines,key=lambda line:line['box'][1],reverse=True)


class RapidReader:
    def __init__(self,profile=None):
        model()
        self.profile=profile
        self.tracker=NotificationTracker()
        self.last_lines=[]
        self.last_diagnostics={}
        self.frame_key=None
        self.strips=NotificationStrips()
        self.last_search=float('-inf')
        self.last_text=float('-inf')

    def set_profile(self,profile):
        self.profile=dict(profile)
        self.reset()

    def reset(self):
        self.tracker.reset()
        self.last_lines=[]
        self.last_diagnostics={}
        self.frame_key=None
        self.strips=NotificationStrips()
        self.last_search=float('-inf')
        self.last_text=float('-inf')

    def rebase(self,old_box,new_box):
        # Crop movement changes line coordinates, not message identity.
        shift=old_box[1]-new_box[1]
        for track in self.tracker.tracks:
            track.center+=shift
        self.frame_key=None
        self.strips=NotificationStrips()
        self.last_search=float('-inf')

    def read(self,image,timestamp):
        baseline=self.tracker.baseline
        frame_key=(image.size,image.mode,hashlib.sha256(image.tobytes()).digest())
        cached=frame_key==getattr(self,'frame_key',None)
        mode='cached'
        if not cached:
            search=(self.strips.height is None or timestamp-self.last_search>=4 or
                    timestamp-self.last_text>1 and timestamp-self.last_search>=1)
            if search:
                self.last_lines=scan(image,self.profile)
                self.strips.learn(self.last_lines)
                self.last_search=timestamp
                mode='detector'
            else:
                self.last_lines=self.strips.read(image,self.profile)
                mode='strips'
            if any(row.get('said') for row in self.last_lines):self.last_text=timestamp
            self.frame_key=frame_key
        events,gap=self.tracker.update(self.last_lines,timestamp)
        self.last_diagnostics=dict(baseline=bool(baseline or gap),ocr_cache_hit=cached,ocr_mode=mode,
            pending_tracks=sum(not track.done for track in self.tracker.tracks),
            completed_tracks=sum(track.done for track in self.tracker.tracks),
            confirmed_events=sum(event['confident'] for event in events),
            uncertain_events=sum(not event['confident'] for event in events))
        return events,gap

    def inspect(self,image):
        return scan(image,self.profile)

    def finish(self):
        return self.tracker.finish()
