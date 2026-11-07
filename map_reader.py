"""Read the minimap title with the shared OCR; use cheap image comparison per frame."""
import re
from difflib import SequenceMatcher
import numpy as np
from PIL import Image
from pixel_ocr import scan


def title_box(width,height):
    return (0,0,min(width,max(220,min(720,round(width*.25)))),
            min(height,max(80,min(240,round(height*.13)))))


def key(text):
    return re.sub(r'[^a-z0-9]','',text.casefold())


def variant_suffix(text):
    match=re.search(r'\b([ivx]+|\d+)\s*$',text.casefold())
    return match.group(1) if match else ''


def identify_map(image,catalog):
    lines=scan(image)
    candidates={}
    for line in lines:
        if line['score']<.7:
            continue
        observed=key(line['text'])
        if len(observed)<5:
            continue
        for name in catalog.maps:
            canonical=key(name)
            if observed!=canonical and variant_suffix(line['text'])!=variant_suffix(name):
                continue
            similarity=SequenceMatcher(None,observed,canonical).ratio()
            if similarity<.88:
                continue
            score=similarity  # OCR score is a separate gate, not a map-name probability.
            if name not in candidates or score>candidates[name]['match']:
                candidates[name]=dict(name=name,match=score,ocr_score=line['score'],box=line['box'],raw=line['text'])
    ranked=sorted(candidates.values(),key=lambda row:row['match'],reverse=True)
    if not ranked or (len(ranked)>1 and ranked[0]['match']-ranked[1]['match']<.07):
        return None
    return ranked[0]


class MapMonitor:
    def __init__(self,catalog,recognizer=None):
        self.recognize=recognizer or (lambda image:identify_map(image,catalog))
        self.confirmed=None
        self.pending=None
        self.hits=0
        self.signature=None
        self.box=None
        self.last_ocr=-100
        self.ocr_reads=0

    def invalidate(self):
        self.confirmed=self.pending=None
        self.hits=0
        self.signature=self.box=None
        self.last_ocr=-100

    @staticmethod
    def fingerprint(image,box):
        return np.asarray(image.crop(box).convert('RGB').resize((256,32),Image.Resampling.BILINEAR)).astype(np.int16)

    def observe(self,image,timestamp):
        if self.confirmed and self.box:
            signature=self.fingerprint(image,self.box)
            difference=np.abs(signature-self.signature)
            # A single Roman numeral may change only a small part of the title.
            changed=float(difference.mean())>1.5 or float((difference.max(axis=2)>18).mean())>.002
            if not changed and timestamp-self.last_ocr<5:
                return self.confirmed
            if changed:
                # Never use the old map after the visible title changes.
                self.confirmed=None
                self.pending=None
                self.hits=0
        if timestamp-self.last_ocr<.45:
            return self.confirmed
        self.last_ocr=timestamp
        self.ocr_reads+=1
        found=self.recognize(image)
        if found is None:
            self.confirmed=self.pending=None
            self.hits=0
            return None
        if self.confirmed==found['name']:
            self.box=self._box(found['box'],image)
            self.signature=self.fingerprint(image,self.box)
            return self.confirmed
        if self.pending==found['name']:
            self.hits+=1
        else:
            self.pending=found['name'];self.hits=1
        if self.hits>=2:
            self.confirmed=found['name']
            self.box=self._box(found['box'],image)
            self.signature=self.fingerprint(image,self.box)
        return self.confirmed

    @staticmethod
    def _box(box,image):
        left,top,right,bottom=box
        return (max(0,int(left)-2),max(0,int(top)-2),min(image.width,round(right)+2),min(image.height,round(bottom)+2))
