"""Compare map EXP strings against the existing recognizer's pixel probabilities.

No model, training data, game access, or numeric-nearest substitution is added.
Scores describe model evidence, not calibrated probabilities of a correct kill.
"""
import bootstrap
import math
import re
import numpy as np
import cv2
from PIL import Image


def ctc_log_score(probabilities, labels):
    """Sum CTC paths for an exact string; column 0 is blank. No renormalization."""
    if not labels or len(probabilities)==0:return -math.inf
    states=[0]
    for label in labels:states.extend((label,0))
    previous=np.full(len(states),-np.inf);previous[0]=0.
    logp=np.log(np.maximum(probabilities,1e-30))
    for frame in logp:
        current=previous.copy()
        current[1:]=np.logaddexp(current[1:],previous[:-1])
        for k in range(2,len(states)):
            if states[k]!=0 and states[k]!=states[k-2]:
                current[k]=np.logaddexp(current[k],previous[k-2])
        previous=current+frame[states]
    return float(np.logaddexp(previous[-1],previous[-2]))


def rank_pixels(probabilities,characters,values):
    """Locate the bounded (+...) suffix and score all map values against it.

    A missing '+' or closing bracket, strong out-of-map value, weak absolute
    support, or close runner-up causes rejection even with only one map value.
    """
    if probabilities.ndim!=2 or not len(probabilities):
        return dict(raw='',accepted=False,reason='no_pixels',ranking=[])
    ids=probabilities.argmax(axis=1)
    runs=[]
    for t,index in enumerate(ids):
        if t==0 or index!=ids[t-1]:runs.append([int(index),t,t+1])
        else:runs[-1][2]=t+1
    nonblank=[r for r in runs if r[0]!=0]
    text=''.join(characters[r[0]] for r in nonblank)
    result=dict(raw=text,accepted=False,reason='missing_boundary',ranking=[])
    plus=[i for i,r in enumerate(nonblank) if characters[r[0]]=='+']
    if not plus:return result
    start=plus[-1]
    closes=[i for i in range(start+1,len(nonblank)) if characters[nonblank[i][0]] in ')]}']
    if not closes:return result
    stop=closes[0]
    left,right=nonblank[start],nonblank[stop]
    if min(float(probabilities[r[1]:r[2],r[0]].max()) for r in (left,right))<.65:
        result['reason']='weak_boundary';return result
    # A second field or trailing digits are not a complete amount suffix.
    if any(characters[r[0]].isdigit() for r in nonblank[stop+1:]):return result
    interior=nonblank[start+1:stop]
    raw=''.join(characters[r[0]] for r in interior).replace(' ','')
    if not raw or len(raw)>8 or not re.fullmatch('[0-9A-Za-z]+',raw):return result
    digit_values=sorted(set(int(v) for v in values if 0<int(v)<100000000))
    if not digit_values or len(digit_values)>64:return result
    observed=int(raw) if raw.isdecimal() else None
    strength=min((float(probabilities[r[1]:r[2],r[0]].max()) for r in interior
                  if characters[r[0]]!=' '),default=0.)
    result.update(observed=observed,raw_min_score=round(strength,4))
    if observed is not None and observed not in digit_values and strength>=.85:
        result['reason']='strong_outside_map';return result
    segment=probabilities[left[2]:right[1]].copy()
    if not len(segment):return result
    if ' ' in characters:
        space=characters.index(' ');segment[:,0]+=segment[:,space];segment[:,space]=0
    lookup={char:i for i,char in enumerate(characters)}
    scores=sorted(((ctc_log_score(segment,[lookup[c] for c in str(v)]),v)
                   for v in digit_values),reverse=True)
    top,value=scores[0]
    runner=scores[1][0] if len(scores)>1 else -math.inf
    # Keep evidence outside the catalog in competition. Without this, any noise
    # would become the only value in a one-monster map.
    baseline=float(np.log(np.maximum(segment.max(axis=1),1e-30)).sum())
    if observed is not None:
        baseline=max(baseline,ctc_log_score(segment,[lookup[c] for c in str(observed)]))
    relative=math.exp(min(0,top-baseline))
    margin=math.exp(min(20,top-runner))
    support=math.exp(min(0,top/max(1,len(str(value)))))
    result.update(value=value,relative=round(relative,4),margin=round(margin,3),support=round(support,4),
                  inferred=observed!=value,
                  ranking=[dict(value=v,log_score=round(s,3)) for s,v in scores[:3]])
    result['accepted']=bool(relative>=.25 and margin>=3 and support>=.35)
    result['reason']='accepted' if result['accepted'] else 'insufficient_margin_or_support'
    return result


def compare_crop(crop,recognizer,values):
    """Use local RapidOCR 1.4.4 preprocessing and its existing ONNX session."""
    bgr=np.asarray(crop.convert('RGB'))[:,:,::-1].copy()
    variants=[bgr,cv2.convertScaleAbs(bgr,alpha=1.2,beta=-15)]
    c,h,w=recognizer.rec_image_shape
    ratio=max(w/h,bgr.shape[1]/bgr.shape[0])
    batch=np.stack([recognizer.resize_norm_img(v,ratio) for v in variants]).astype(np.float32)
    probabilities=recognizer.session(batch)[0]
    chars=recognizer.postprocess_op.character
    results=[rank_pixels(p,chars,values) for p in probabilities]
    accepted=all(r['accepted'] for r in results) and results[0].get('value')==results[1].get('value')
    return dict(accepted=accepted,value=results[0].get('value') if accepted else None,
                inferred=accepted and any(r.get('inferred',False) for r in results),variants=results)


def enhance_lines(image,lines,profile,recognizer,parse_prefix):
    if not profile:return
    values=set(profile.values())
    for line in lines:
        old=line.get('said')
        if line['color']=='yellow' or line['score']<.7:continue
        if old and (old[0]!='exp' or line.get('digit_verified',False)):continue
        prefix=parse_prefix(re.sub(r'\s+','',line['text']).lower())
        if not prefix or prefix[0]!='exp':continue
        left,top,right,bottom=line['box'];height=bottom-top
        if height<6:continue
        # Include EXP context plus the longest map amount; normalize scale from
        # detected line height, not hard-coded window coordinates.
        width=max(96,(max(len(str(v)) for v in values)+4)*.65*height)
        crop=image.crop((max(0,int(right-width)),max(0,int(top)-2),
                         min(image.width,int(right)+4),min(image.height,int(bottom)+2)))
        crop=crop.resize((max(1,round(crop.width*48/crop.height)),48),Image.Resampling.BICUBIC)
        decision=compare_crop(crop,recognizer,values)
        line['candidate_comparison']=decision
        if not decision['accepted']:continue
        value=decision['value']
        # A complete in-map original amount conflicting with the suffix remains
        # unresolved. Map evidence cannot silently override it.
        if old and old[1]!=value and old[1] in values:continue
        inferred=decision['inferred'] or bool(old and old[1]!=value)
        line.update(said=('exp',value),candidate_verified=True,candidate_inferred=inferred)
