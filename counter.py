"""Pure event accounting. No capture, OS hooks or network."""
import csv
from collections import Counter
from datetime import datetime
from pathlib import Path
from exp_progress import ExperienceProgress
from session_clock import MapClock


def parse_monsters(text):
    """Each line: monster name, observed personal EXP. Duplicate EXP is ambiguous."""
    result = {}
    for number, raw in enumerate(text.splitlines(), 1):
        raw = raw.strip()
        if not raw or raw.startswith('#'):
            continue
        try:
            name, value = raw.rsplit(',', 1)
            name, value = name.strip(), int(value.strip())
            if not name or value <= 0 or name in result:
                raise ValueError()
        except ValueError:
            raise ValueError(f'第 {number} 行格式错误：怪物名称,单只实际经验（正整数）；名称不能重复') from None
        result[name] = value
    return result


class CounterSession:
    FIELDS = ['time', 'event_id', 'elapsed_s', 'type', 'color', 'exp', 'monster', 'status', 'note',
              'source', 'observed_at', 'interval_start', 'interval_end']

    def __init__(self, monsters=None, character='', map_name=''):
        self.monsters = dict(monsters or {})
        self.character = character
        self.map_name = map_name
        self.counts = Counter()
        self.estimated_counts=Counter()
        self.estimated_exp=0
        self.hud_estimated_counts=Counter()
        self.hud_credits=[]
        self.notification_evidence=[]
        self.seen = set()
        self.events = []
        self.personal_exp = self.party_exp = self.unresolved = 0
        self.active_seconds = 0.0
        self.exp_progress=ExperienceProgress()
        self.map_clock=MapClock()
        self.writer = self.file = None
        self.path = None

    def open_log(self, directory):
        Path(directory).mkdir(parents=True, exist_ok=True)
        self.path = Path(directory) / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-events.csv')
        self.file = self.path.open('w', newline='', encoding='utf-8-sig')
        self.writer = csv.DictWriter(self.file, fieldnames=self.FIELDS)
        self.writer.writeheader()
        self.note('session_start', f'角色={self.character}; 地图={self.map_name}; 经验表={self.monsters}')

    @staticmethod
    def safe_cell(value):
        # Prevent spreadsheet formula execution from user-supplied labels.
        return "'" + value if isinstance(value, str) and value[:1] in ('=', '+', '-', '@') else value

    def _record(self, **values):
        row = dict.fromkeys(self.FIELDS, '')
        row.update(time=datetime.now().astimezone().isoformat(timespec='milliseconds'),
                   elapsed_s=round(self.active_seconds, 2), **values)
        self.events.append(row)
        # Keep the UI history bounded; full history is on disk.
        if len(self.events) > 500:
            del self.events[:100]
        if self.writer:
            self.writer.writerow({k: self.safe_cell(v) for k, v in row.items()})
            self.file.flush()
        return row

    def note(self, kind, note):
        return self._record(type=kind, status='notice', note=note)

    def accept(self, event_id, kind, amount, color, confident=True, note='',estimated=False,
               source='notification',observed_at=None,interval_start=None,interval_end=None):
        if event_id in self.seen:
            return None
        self.seen.add(event_id)
        def record(**values):
            return self._record(source=source,observed_at=observed_at,
                interval_start=interval_start,interval_end=interval_end,**values)
        monster = ''
        # Identifying a possible species is separate from confirming a new kill.
        if kind=='exp' and isinstance(amount,int):
            candidates=[name for name,exp in self.monsters.items() if exp==amount]
            if len(candidates)==1:monster=candidates[0]
        if kind == 'mesos' or kind == 'text':
            return None
        if source=='hud_difference' and interval_start is not None:
            # Match individual HUD increments to hints in the same time interval,
            # regardless of which channel finishes recognition first.
            candidates=[e for e in self.notification_evidence if not e['used']
                and e['amount']==amount and e['monster']==monster
                and interval_start<=e['time']<=interval_end]
            if candidates:
                evidence=min(candidates,key=lambda e:abs(e['time']-observed_at));evidence['used']=True
                return record(event_id=event_id,type=kind,exp=amount,color=color,monster=monster,
                              status='hud_checked',note='经验条增量与已计提示配对，未增加击杀数')
        if source=='notification' and confident and kind=='exp' and color=='white' and observed_at is not None:
            # Late hints replace only a matching credit from their own interval.
            candidates=[(i,c) for i,c in enumerate(self.hud_credits)
                        if c['value']==amount and c['start']<=observed_at<=c['end']]
            if candidates:
                i,credit=min(candidates,key=lambda pair:abs(pair[1]['at']-observed_at))
                name=credit['name']
                self.hud_credits.pop(i)
                self.hud_estimated_counts[name]-=1
                if not estimated:
                    self.estimated_counts[name]-=1;self.estimated_exp-=amount;self.personal_exp+=amount
                return record(event_id=event_id,type=kind,exp=amount,color=color,monster=name,
                              status='reconciled_hud',note='提示迟到：与经验条补计合并，未增加击杀数')
        if not confident or kind not in ('exp', 'bonus') or not isinstance(amount, int) or amount <= 0:
            status = 'uncertain'
            self.unresolved += 1
        elif kind == 'bonus':
            status = 'excluded_party_bonus'
            self.party_exp += amount
        elif color == 'yellow':
            status = 'excluded_party_share'
            self.party_exp += amount
        elif color != 'white':
            status = 'uncertain_color'
            self.unresolved += 1
        else:
            if not estimated:self.personal_exp += amount
            matches = [name for name, exp in self.monsters.items() if exp == amount]
            if len(matches) == 1:
                monster = matches[0]
                self.counts[monster] += 1
                if estimated:
                    self.estimated_counts[monster]+=1;self.estimated_exp+=amount
                    if source=='hud_difference':
                        self.hud_estimated_counts[monster]+=1
                        self.hud_credits.append(dict(value=amount,name=monster,at=observed_at,
                            start=interval_start if interval_start is not None else float('-inf'),
                            end=interval_end if interval_end is not None else observed_at))
                        self.hud_credits=self.hud_credits[-200:]
                if source=='notification' and observed_at is not None:
                    self.notification_evidence.append(dict(amount=amount,time=observed_at,monster=monster,used=False))
                    self.notification_evidence=self.notification_evidence[-512:]
                status = 'estimated_candidate' if estimated else 'matched_candidate'
            else:
                status = 'ambiguous_exp' if matches else 'unmapped_exp'
                monster = ' / '.join(matches)
                self.unresolved += 1
        return record(event_id=event_id, type=kind or 'unreadable', exp=amount if amount is not None else '',
                            color=color, monster=monster, status=status, note=note)

    def export_summary(self, destination):
        with open(destination, 'w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.writer(handle)
            writer.writerow(['character', 'map', 'monster', 'candidate_kills', 'exp_each', 'active_seconds', 'kills_per_hour'])
            for name, exp in self.monsters.items():
                count = self.counts[name]
                rate = round(count * 3600 / self.active_seconds, 1) if self.active_seconds else 0
                writer.writerow([self.safe_cell(self.character), self.safe_cell(self.map_name), self.safe_cell(name),
                                 count, exp, round(self.active_seconds, 2), rate])
            writer.writerow([])
            writer.writerow(['personal_exp_observed', self.personal_exp])
            writer.writerow(['party_exp_observed', self.party_exp])
            writer.writerow(['unresolved_events', self.unresolved])
            writer.writerow(['estimated_kills',sum(self.estimated_counts.values())])
            writer.writerow(['estimated_exp',self.estimated_exp])
            writer.writerow(['hud_estimated_kills',sum(self.hud_estimated_counts.values())])
            for name,count in self.estimated_counts.items():writer.writerow(['estimated_monster',self.safe_cell(name),count])
            for key,value in self.exp_progress.snapshot().items():writer.writerow([key,value])
            writer.writerow(['map_active_seconds',round(self.map_clock.seconds,2)])

    def close(self):
        if self.file:
            self.file.close()
            self.file = self.writer = None

