"""Offline coverage check against the dated, sourced map reference snapshot."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from catalog import Catalog


def audit(catalog=None):
    catalog=catalog or Catalog()
    reference=json.loads((ROOT/'assets/catalog_reference.json').read_text('utf-8'))
    missing=[]
    for location in reference['maps']:
        try:name=catalog.canonical_map(location['game_name'])
        except ValueError:
            missing.append(f"Missing map: {location['name']}");continue
        actual={(m['name'],m['level'],m['exp']) for m in catalog.records if name in m['maps']}
        for row in location['monsters']:
            if tuple(row) not in actual:missing.append(f"{location['name']}: missing/different {row}")
    return reference['source'],missing


if __name__=='__main__':
    source,missing=audit()
    print(f"Reference checked {source['checked_at']}: {source['index_rows_checked']} index rows, {source['rows_with_monster_tables']} monster tables")
    for error in missing:print(error)
    print(f'{len(missing)} missing map/monster/EXP entries in this reference scope.')
    raise SystemExit(bool(missing))
