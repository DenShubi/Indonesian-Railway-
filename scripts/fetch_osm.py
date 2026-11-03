"""Fetch the East Java rail network and its stations from OpenStreetMap via Overpass.

Writes a local cache under data/osm/ that the rest of the pipeline reads:
  rail.geojson   LineString per rail way, for routing trip shapes
  stations.csv   ref,name,lat,lon,norm - ref is OSM's railway:ref, the KAI station code

The cache is refetched only when missing or when --force is passed; Overpass is a
donated public service, so do not hammer it.

Usage:  python scripts/fetch_osm.py [--force]
"""
import csv, json, pathlib, re, sys, time, unicodedata

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'osm'

# East Java plus Cepu in the west: covers Bojonegoro, Babat, Surabaya, Gresik,
# Mojokerto, Kertosono, Kediri, Blitar, Malang and Pasuruan.
BBOX = (-8.45, 111.20, -6.80, 113.20)

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


def overpass(query: str) -> dict:
    s, w, n, e = BBOX
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


def fetch_rail() -> None:
    print('rail ways...')
    data = overpass(RAIL_QUERY)
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
    path = OUT / 'rail.geojson'
    json.dump({'type': 'FeatureCollection', 'features': features},
              open(path, 'w'), separators=(',', ':'))
    print(f'  {len(features)} ways -> {path.relative_to(ROOT)} '
          f'({path.stat().st_size / 1e6:.1f} MB)')


def fetch_stations() -> None:
    print('stations...')
    data = overpass(STATION_QUERY)
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
    path = OUT / 'stations.csv'
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=['ref', 'name', 'railway', 'lat', 'lon', 'norm'])
        writer.writeheader()
        writer.writerows(rows)
    with_ref = sum(1 for r in rows if r['ref'])
    print(f'  {len(rows)} stations ({with_ref} with a railway:ref code) '
          f'-> {path.relative_to(ROOT)}')


def main() -> None:
    force = '--force' in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    rail, stations = OUT / 'rail.geojson', OUT / 'stations.csv'

    if force or not rail.exists():
        fetch_rail()
    else:
        print(f'rail.geojson cached ({rail.stat().st_size / 1e6:.1f} MB) - pass --force to refetch')
    if force or not stations.exists():
        fetch_stations()
    else:
        print('stations.csv cached - pass --force to refetch')


if __name__ == '__main__':
    main()
