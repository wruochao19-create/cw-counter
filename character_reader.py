"""Bounded startup OCR of the visible HUD name; no game data access."""
import re
from pixel_ocr import scan

JOBS={'beginner','warrior','fighter','page','spearman','magician','wizard','cleric',
      'bowman','hunter','crossbowman','thief','rogue','assassin','bandit'}


def character_box(width,height):
    return (round(width*.12),max(0,height-max(90,round(height*.12))),round(width*.45),height)


def identify_character(image):
    rows=scan(image)
    jobs=[r for r in rows if re.sub('[^a-z]','',r['text'].lower()) in JOBS and r['score']>=.85]
    candidates=set()
    for job in jobs:
        x,y,right,bottom=job['box'];height=bottom-y
        for row in rows:
            left,top,end,low=row['box'];name=row['text'].strip()
            if (row['score']>=.9 and re.fullmatch('[A-Za-z][A-Za-z0-9]{2,15}',name)
                and name.lower() not in JOBS and abs(left-x)<=max(10,height*2)
                and y+height*.5<=top<=bottom+height*1.7):
                candidates.add(name)
    return next(iter(candidates)) if len(candidates)==1 else None


class CharacterMonitor:
    def __init__(self,recognizer=None):
        self.recognizer=recognizer or identify_character
        self.pending=None;self.hits=0;self.attempts=0;self.done=False

    def observe(self,image):
        self.attempts+=1
        name=self.recognizer(image)
        if name and name==self.pending:self.hits+=1
        else:self.pending=name;self.hits=int(bool(name))
        if self.hits>=2:
            self.done=True;return name
        if self.attempts>=3:self.done=True
        return None
