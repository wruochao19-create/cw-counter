"""Offline CW reference data. No network or screen access at runtime."""
import json
from collections import Counter
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from pathlib import Path

ALL_MAPS = '全部已记录地图（自动匹配）'
BUILTIN = '内置资料：自动匹配'
CUSTOM = '手动表：实测覆盖'


class Catalog:
    def __init__(self, path=None):
        bundled = path is None
        path = path or Path(__file__).parent / 'assets' / 'monsters.json'
        data = json.loads(Path(path).read_text('utf-8'))
        self.metadata = data['source']
        # Entries with no recorded location may be unreleased/test content.
        self.records = [m for m in data['monsters'] if m['exp'] > 0 and m['maps']]
        self.aliases = {}
        if bundled:
            corrections=json.loads(Path(path).with_name('map_overrides.json').read_text('utf-8'))
            self.aliases=corrections['renames']
            by_id={m['id']:m for m in self.records}
            for monster in self.records:
                monster['maps']=[self.aliases.get(place,place) for place in monster['maps']]
            for location in corrections['additional_locations']:
                for monster_id in location['monster_ids']:
                    if monster_id not in by_id:raise ValueError(f'Map correction references missing monster ID {monster_id}')
                    if location['map'] not in by_id[monster_id]['maps']:
                        by_id[monster_id]['maps'].append(location['map'])
            self.metadata={**self.metadata,'map_corrections':corrections['source']}
        self.maps = sorted({place for m in self.records for place in m['maps']})
        names = Counter(m['name'] for m in self.records)
        self.labels = {m['id']: m['name'] if names[m['name']] == 1 else
                       f"{m['name']} [Lv{m['level']}, ID{m['id']}]" for m in self.records}

    def canonical_map(self, name):
        name = name.strip()
        if not name or name == ALL_MAPS:
            return ''
        name=next((target for old,target in self.aliases.items() if old.casefold()==name.casefold()),name)
        matches = [place for place in self.maps if place.casefold() == name.casefold()]
        if len(matches) != 1:
            raise ValueError('请从下拉列表选择地图，或选择“全部已记录地图”；可以先输入部分英文筛选。')
        return matches[0]

    def profile(self, map_name='', multiplier='1'):
        map_name = self.canonical_map(map_name)
        try:
            factor = Decimal(str(multiplier))
            if not factor.is_finite() or not Decimal('.1') <= factor <= 10:
                raise ValueError()
        except (ValueError, InvalidOperation):
            raise ValueError('经验倍率应为 0.1 到 10 之间的数字；普通单人测试用 1。') from None
        records = [m for m in self.records if not map_name or map_name in m['maps']]
        return {self.labels[m['id']]: int((Decimal(m['exp']) * factor).to_integral_value(rounding=ROUND_FLOOR))
                for m in records if Decimal(m['exp']) * factor >= 1}


def settings_profile(settings, catalog=None):
    # Old custom settings remain readable by offline replay.
    from counter import parse_monsters
    if settings.get('catalog_mode', CUSTOM) == CUSTOM:
        return parse_monsters(settings.get('monsters', ''))
    return (catalog or Catalog()).profile(settings.get('map', ''), settings.get('exp_multiplier', '1'))
