"""Fetch each region's rail network and stations from OpenStreetMap via Overpass.

Writes a local cache under data/osm/<region>/ that the rest of the pipeline reads:
  rail.geojson   LineString per rail way, for routing trip shapes
  stations.csv   ref,name,lat,lon,norm - ref is OSM's railway:ref, the KAI station code

Regions and their bounding boxes come from data/regions.json. The cache is
refetched only when missing or when --force is passed; Overpass is a donated
public service, so do not hammer it.

Usage:  python scripts/fetch_osm.py [region-id ...] [--force]
"""
import csv, json, pathlib, re, sys, time, unicodedata

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGIONS = json.load(open(ROOT / 'data' / 'regions.json', encoding='utf-8'))

# Global instances only: regional mirrors answer happily with zero elements for
# an Indonesian bounding box, which looks like success and is not.
ENDPOINTS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
]
UA = 'IndonesianRailwayVisualizer/0.1 (https://github.com/DenShubi/Indonesian-Railway-)'

RAIL_QUERY = """[out:json][timeout:240];
(
  way["railway"~"^(rail|narrow_gauge|light_rail)$"]["service"!~"^(yard|siding|spur)$"]({s},{w},{n},{e});
);
out geom;"""

STATION_QUERY = """[out:json][timeout:180];
(
  node["railway"~"^(station|halt)$"]({s},{w},{n},{e});
  way["railway"~"^(station|halt)$"]({s},{w},{n},{e});
  relation["railway"~"^(station|halt)$"]({s},{w},{n},{e});
);
out tags center;"""


def norm(s: str) -> str:
    """Station name reduced to letters and digits, for fuzzy comparison."""
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().upper()
    s = re.sub(r'^STASIUN\s+', '', s)
    return re.sub(r'[^A-Z0-9]', '', s)


def overpass(query: str, bbox) -> dict:
    s, w, n, e = bbox
    body = query.format(s=s, w=w, n=n, e=e)
    last = None
    for endpoint in ENDPOINTS:
        try:
            r = requests.post(endpoint, data={'data': body},
                              headers={'User-Agent': UA}, timeout=300)
            if r.ok and r.text.lstrip().startswith('{'):
                payload = r.json()
                if payload.get('elements'):
                    print(f'  [ok] {endpoint}  {len(r.content) / 1e6:.1f} MB')
                    return payload
                last = f'{endpoint}: answered with zero elements'
            else:
                last = f'{endpoint}: HTTP {r.status_code} {r.text[:120]!r}'
        except requests.RequestException as exc:
            last = f'{endpoint}: {exc}'
        print(f'  [retry] {last}')
        time.sleep(8)
    raise SystemExit(f'All Overpass endpoints failed. Last: {last}')


def fetch_rail(out: pathlib.Path, bbox) -> None:
    print('  rail ways...')
    data = overpass(RAIL_QUERY, bbox)
    features = []
    for el in data['elements']:
        geom = el.get('geometry')
        if not geom or len(geom) < 2:
            continue
        tags = el.get('tags', {})
        features.append({
            'type': 'Feature',
            'properties': {
                'id': el['id'],
                'railway': tags.get('railway'),
                'usage': tags.get('usage'),
                'name': tags.get('name'),
            },
            'geometry': {
                'type': 'LineString',
                'coordinates': [[round(p['lon'], 7), round(p['lat'], 7)] for p in geom],
            },
        })
    path = out / 'rail.geojson'
    json.dump({'type': 'FeatureCollection', 'features': features},
              open(path, 'w'), separators=(',', ':'))
    print(f'    {len(features)} ways -> {path.relative_to(ROOT)} '
          f'({path.stat().st_size / 1e6:.1f} MB)')


def fetch_stations(out: pathlib.Path, bbox) -> None:
    print('  stations...')
    data = overpass(STATION_QUERY, bbox)
    rows = []
    for el in data['elements']:
        tags = el.get('tags', {})
        if el['type'] == 'node':
            lat, lon = el.get('lat'), el.get('lon')
        else:
            centre = el.get('center') or {}
            lat, lon = centre.get('lat'), centre.get('lon')
        if lat is None or lon is None:
            continue
        name = tags.get('name') or ''
        rows.append({
            'ref': (tags.get('railway:ref') or tags.get('ref') or '').strip().upper(),
            'name': name,
            'railway': tags.get('railway'),
            'lat': round(lat, 7),
            'lon': round(lon, 7),
            'norm': norm(name),
        })
    rows.sort(key=lambda r: (r['ref'] == '', r['ref'], r['name']))
    path = out / 'stations.csv'
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=['ref', 'name', 'railway', 'lat', 'lon', 'norm'])
        writer.writeheader()
        writer.writerows(rows)
    with_ref = sum(1 for r in rows if r['ref'])
    print(f'    {len(rows)} stations ({with_ref} with a railway:ref code) '
          f'-> {path.relative_to(ROOT)}')


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    force = '--force' in sys.argv
    wanted = [r for r in REGIONS if not args or r['id'] in args]
    if not wanted:
        raise SystemExit(f'no such region; known ids: {[r["id"] for r in REGIONS]}')

    for region in wanted:
        print(f'{region["id"]}:')
        out = ROOT / 'data' / 'osm' / region['id']
        out.mkdir(parents=True, exist_ok=True)
        rail, stations = out / 'rail.geojson', out / 'stations.csv'
        bbox = region['bbox']

        if force or not rail.exists():
            fetch_rail(out, bbox)
        else:
            print(f'  rail.geojson cached ({rail.stat().st_size / 1e6:.1f} MB)'
                  ' - pass --force to refetch')
        if force or not stations.exists():
            fetch_stations(out, bbox)
        else:
            print('  stations.csv cached - pass --force to refetch')


if __name__ == '__main__':
    main()
