"""Explicit developer refresh; normal application never calls this script."""
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

URL = 'https://jcsoutherland.github.io/maple-exp-tracker/data/osms/monsters.json'


def main():
    with urllib.request.urlopen(URL, timeout=30) as response:
        raw = response.read()
        modified = response.headers.get('Last-Modified')
    records = json.loads(raw)
    if not isinstance(records, list) or len(records) < 50:
        raise ValueError('Unexpected catalogue format; refusing to replace snapshot')
    clean, ids = [], set()
    for m in records:
        if not isinstance(m['id'], int) or m['id'] in ids or not isinstance(m['exp'], int) or m['exp'] < 0:
            raise ValueError('Invalid or duplicate record')
        if not isinstance(m['name'], str) or not m['name'].strip() or not isinstance(m['maps'], list):
            raise ValueError('Invalid name or locations')
        if not all(isinstance(place, str) for place in m['maps']):
            raise ValueError('Invalid location')
        ids.add(m['id'])
        clean.append({k: m[k] for k in ('id', 'name', 'level', 'exp', 'boss', 'maps')})
    data = {'source': {'author': 'OSMS Data Explorer by @ohmi',
                      'origin': 'https://osmsdataexplorer.com/data/current/monsters.json',
                      'mirror': URL, 'mirror_last_modified': modified,
                      'fetched_at': datetime.now(timezone.utc).isoformat(),
                      'raw_sha256': hashlib.sha256(raw).hexdigest(),
                      'note': 'Public reference snapshot, not a complete or authoritative live-server list. No images/code copied.'},
            'monsters': clean}
    destination = Path(__file__).resolve().parents[1] / 'assets' / 'monsters.json'
    destination.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8')
    print(f'Saved {len(clean)} reference records to {destination}')


if __name__ == '__main__':
    main()
