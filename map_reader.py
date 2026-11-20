"""Read the minimap title with the shared OCR; use cheap image comparison per frame."""
import re
from difflib import SequenceMatcher
import numpy as np
from PIL import Image
from pixel_ocr import scan,model


def title_box(width,height):
    # Game UI size is not a fixed fraction of the client resolution. In a
    # small client the old 25% crop cut off the title and its Roman suffix.
    return (0,0,min(width,max(800,min(1200,round(width*.4)))),
            min(height,max(260,min(400,round(height*.18)))))


def key(text):
    return re.sub(r'[^a-z0-9]','',text.casefold())


def variant_suffix(text):
    match=re.search(r'\b([ivx]+|\d+)\s*$',text.casefold())
    return match.group(1) if match else ''


def identify_map(image,catalog,verify=True):
    # Large clients can still use a small minimap font. The shared detector
    # downsizes large search images, losing a thin I. Try a small native-pixel
    # search first, then expand for larger UI scales or longer titles.
    if verify and (image.width>320 or image.height>100):
        compact=image.crop((0,0,min(320,image.width),min(100,image.height)))
        found=identify_map(compact,catalog,verify=True)
        if found is not None and found['name'] not in getattr(catalog,'region_labels',set()):return found
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
    # Forgotten Hollow is both a region heading and its town name. A complete
    # title below that heading identifies the field, not two conflicting maps.
    regions=getattr(catalog,'region_labels',set())
    for name,row in list(candidates.items()):
        if name in regions and any(other['match']==1 and other['name'] not in regions
                and other['box'][1]>=row['box'][3] for other in candidates.values()):
            del candidates[name]
    ranked=sorted(candidates.values(),key=lambda row:row['match'],reverse=True)
    # A fully read title can differ from its neighbour by just one letter
    # (East/West Rocky Mountain IV). Apply the margin only to fuzzy matches.
    if ranked and ranked[0]['match']==1:
        if len(ranked)>1 and ranked[1]['match']==1:
            return None
        return verify_title(image,ranked[0],catalog) if verify else ranked[0]
    if not ranked or (len(ranked)>1 and ranked[0]['match']-ranked[1]['match']<.07):
        return None
    return verify_title(image,ranked[0],catalog) if verify else ranked[0]


def title_stem(name):
    return key(re.sub(r'\s+(?:[IVX]+|\d+)\s*$','',name))


def verify_title(image,found,catalog):
    """Read the padded title directly, without detector truncation of the I.

    Require two agreeing resamplings and individual suffix confidence, not the average
    confidence of the much longer words preceding a one-character suffix.
    """
    l,t,r,b=found['box'];h=b-t
    if r>=image.width-2 or b>=image.height-2:return None
    names={key(name):name for name in catalog.maps if title_stem(name)==title_stem(found['name'])}
    if not variant_suffix(found['name']) and len(names)==1:return found
    box=(max(0,int(l)-3),max(0,int(t)-2),min(image.width,round(r+h*.7)),min(image.height,round(b)+2))
    crop=image.crop(box)
    # A minimap's white vertical frame is not a final I. Stop the padded crop
    # before that frame, while retaining detached narrow text glyphs.
    a=np.asarray(crop.convert('RGB')).min(axis=2)
    borders=np.where((a>190).mean(axis=0)>.85)[0]
    borders=borders[borders>=round(r-box[0])]
    if len(borders):
        box=(box[0],box[1],box[0]+int(borders[0]),box[3])
        crop=image.crop(box)
    variants=[]
    for interpolation in (Image.Resampling.NEAREST,Image.Resampling.BICUBIC,Image.Resampling.LANCZOS):
        scale=64/crop.height
        enlarged=crop.resize((max(1,round(crop.width*scale)),64),interpolation)
        variants.append(np.asarray(enlarged)[:,:,::-1].copy())
    details,_=model().text_rec(variants,return_word_box=True)
    reads=[]
    for text,score,chars in details:
        name=names.get(key(text))
        if name is None:return None
        suffix=re.search(r'\b([IVX]+|\d+)\W*$',text.upper())
        scores=chars[4]
        if variant_suffix(name):
            if not suffix or len(scores)!=len(text) or min(scores[suffix.start(1):suffix.end(1)])<.7:
                continue
        elif score<.85:continue
        reads.append(name)
    if len(reads)<2 or len(set(reads))!=1:return None
    return dict(found,name=reads[0],raw=found['raw'],verified=True,
                title_reads=[row[0] for row in details],box=box)


def glyph_mask(image):
    pixels=np.asarray(image.convert('RGB'))
    low=pixels.min(axis=2);high=pixels.max(axis=2)
    return ((low>175)&((high.astype(np.int16)-low)<65)).astype(np.uint8)


class MapMonitor:
    def __init__(self,catalog,recognizer=None):
        self.recognize=recognizer or (lambda image:identify_map(image,catalog))
        self.confirmed=None
        self.pending=None
        self.hits=0
        self.signature=None
        self.box=None
        self.trusted=None
        self.image_size=None
        self.disagreement=None
        self.pending_since=None
        self.glyphs=None
        self.last_read=None
        self.last_ocr=-100
        self.ocr_reads=0

    def invalidate(self):
        self.confirmed=self.pending=None
        self.hits=0
        self.pending_since=None
        # A focus/geometry pause requires fresh readable frames, but must not
        # discard the evidence that this exact title was already confirmed.
        # A new session creates a new monitor and therefore a fresh reference.
        self.last_ocr=-100

    @staticmethod
    def fingerprint(image,box):
        return np.asarray(image.crop(box).convert('RGB').resize((256,32),Image.Resampling.BILINEAR)).astype(np.int16)

    def same_glyphs(self,image):
        if self.glyphs is None:return False
        current=glyph_mask(image.crop(self.box))
        if current.shape!=self.glyphs.shape:return False
        # Compare text strokes separately from the blue/translucent background.
        # The final quarter has its own threshold so one lost I is not diluted
        # by the many unchanged letters in "East Rocky Mountain".
        for old,new in ((self.glyphs,current),(self.glyphs[:,-max(1,current.shape[1]//4):],current[:,-max(1,current.shape[1]//4):])):
            union=np.count_nonzero(old|new)
            if union<8 or np.count_nonzero(old^new)/union>.08:return False
        return True

    def observe(self,image,timestamp):
        self.disagreement=None
        self.last_read=None
        unchanged=False
        if self.trusted and self.box and image.size==self.image_size:
            signature=self.fingerprint(image,self.box)
            difference=np.abs(signature-self.signature)
            # A single Roman numeral may change only a small part of the title.
            changed=float(difference.mean())>1.5 or float((difference.max(axis=2)>18).mean())>.002
            unchanged=not changed or self.same_glyphs(image)
        if self.confirmed:
            if unchanged and timestamp-self.last_ocr<5:
                return self.confirmed
            if not unchanged:
                # Never use the old map after the visible title changes.
                self.confirmed=None
                self.pending=None
                self.hits=0
                self.pending_since=None
        if timestamp-self.last_ocr<.45:
            return self.confirmed
        self.last_ocr=timestamp
        self.ocr_reads+=1
        found=self.recognize(image)
        self.last_read=dict(timestamp=timestamp,image_size=image.size,trusted=self.trusted,
            unchanged=unchanged,found=found)
        if found is None:
            self.confirmed=self.pending=None
            self.hits=0
            self.pending_since=None
            return None
        name=found['name']
        if unchanged:
            # Periodic OCR can drop a trailing I (VI -> V) even on identical
            # pixels. Repeated readings of that mistake are not a map change.
            # Keep the original box too, so a shorter OCR box cannot erase the I
            # from the image reference used to detect a genuine later change.
            if name!=self.trusted:
                self.disagreement=dict(kept_map=self.trusted,ocr_map=name,
                    raw=found.get('raw',name),ocr_score=found.get('ocr_score'),
                    reason='unchanged_title')
            name=self.trusted
        if self.confirmed==name:
            return self.confirmed
        neighbour=(self.trusted is not None and self.trusted!=name and title_stem(self.trusted)==title_stem(name))
        if neighbour and not found.get('verified',False):
            self.pending=None;self.hits=0;self.pending_since=None
            return None
        if self.pending==name:
            self.hits+=1
        else:
            self.pending=name;self.hits=1;self.pending_since=timestamp
        ready=self.hits>=2
        if neighbour:
            ready=self.hits>=4 and timestamp-self.pending_since>=1.5 and found.get('verified',False)
        if ready:
            self.confirmed=name
            if not unchanged:
                self.trusted=name
                self.box=self._box(found['box'],image)
                self.signature=self.fingerprint(image,self.box)
                self.image_size=image.size
                self.glyphs=glyph_mask(image.crop(self.box))
        return self.confirmed

    @staticmethod
    def _box(box,image):
        left,top,right,bottom=box
        # Include detached narrow suffix glyphs just beyond the detector box.
        padding=max(6,round((bottom-top)*.5))
        return (max(0,int(left)-2),max(0,int(top)-2),min(image.width,round(right)+padding),min(image.height,round(bottom)+2))
