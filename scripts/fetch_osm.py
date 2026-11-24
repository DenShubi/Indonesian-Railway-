"""Fetch each region's rail network and stations from OpenStreetMap via Overpass.

Writes a local cache under data/osm/<region>/ that the rest of the pipeline reads:
  rail.geojson   LineString per rail way, for routing trip shapes
  stations.csv   ref,name,lat,lon,norm - ref is OSM's railway:ref, the KAI station code

Regions and their bounding boxes come from data/regions.json. The cache is
refetched only when missing or when --force is passed; Overpass is a donated
public service, so do not hammer it.

The `java` pseudo-region covers the whole island, which is too large for one
query: a bbox wider than WIDE degrees is fetched tile by tile and the tiles are
merged on OSM id. Overpass returns a way intersecting the bbox with its whole
geometry, so adjacent tiles overlap in content rather than leaving seams, and
merging on id is what removes the duplicates instead of stitching them.

Tiling the island guarantees tiles that are open sea, and a tile of open sea
legitimately answers with zero elements. The empty answer that means failure is
the one from a bbox that should hold track -- a regional mirror with no
Indonesian data answers that way -- so emptiness is tolerated per call, with
allow_empty, and not globally. Without that, every sea tile would walk all
three endpoints, sleep between each, and abort the island fetch at the first
stretch of Java Sea.

Tiles go one at a time with a pause between them, and no larger than a bbox
already known to answer in one query. There is no concurrency here on purpose.

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

# A bbox with a side longer than this is fetched tile by tile. The three
# published regions are all inside it, so their caches stay byte-identical and
# nothing refetches them; Java's 9.7 degrees of longitude are not.
WIDE = 2.0
# Tile side in degrees. It is WIDE on purpose: a tile should be no larger than
# the largest bbox this repo already knows Overpass answers in one query, and
# Surabaya's is two degrees wide. Smaller tiles are not kinder. Overpass is
# queue-bound, not bandwidth-bound -- a trivial one-street query waited 31
# seconds the day this was written -- so the cost of a fetch is the number of
# requests, and one-degree tiles would put 80 of them in the queue instead of
# 20 for the same data.
TILE = WIDE
# Between tiles, on top of however long the server itself took.
PAUSE = 2.0

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


def tiles(bbox, step: float = TILE) -> list[tuple[float, float, float, float]]:
    """`bbox` cut into tiles of at most `step` degrees a side, (s, w, n, e).

    Tiles abut exactly and the last row and column are short rather than
    overhanging, so the tiles cover the bbox and nothing outside it. Edges are
    rounded to six places, which is a tenth of a metre, because walking a float
    up by 1.0 forty times is how a tile edge ends up at 113.99999999999999 and
    a query asks for a sliver of sea of its own.
    """
    s, w, n, e = bbox
    out, south = [], s
    while south < n:
        north = round(min(south + step, n), 6)
        west = w
        while west < e:
            east = round(min(west + step, e), 6)
            out.append((south, west, north, east))
            west = east
        south = north
    return out


def overpass(query: str, bbox, allow_empty: bool = False) -> dict:
    """One Overpass query, trying each endpoint in turn.

    A zero-element answer is a failure by default, because a mirror with no
    Indonesian data answers exactly that way and it looks like success. Pass
    allow_empty for a bbox that may genuinely hold nothing -- a sea tile -- or
    every one of those walks all three endpoints and then aborts the fetch.
    """
    s, w, n, e = bbox
    body = query.format(s=s, w=w, n=n, e=e)
    last = None
    for endpoint in ENDPOINTS:
        try:
            r = requests.post(endpoint, data={'data': body},
                              headers={'User-Agent': UA}, timeout=300)
            if r.ok and r.text.lstrip().startswith('{'):
                payload = r.json()
                if payload.get('elements') or allow_empty:
                    print(f'  [ok] {endpoint}  {len(r.content) / 1e6:.1f} MB'
                          f'  {len(payload.get("elements", []))} elements')
                    return payload
                last = f'{endpoint}: answered with zero elements'
            else:
                last = f'{endpoint}: HTTP {r.status_code} {r.text[:120]!r}'
        except requests.RequestException as exc:
            last = f'{endpoint}: {exc}'
        print(f'  [retry] {last}')
        time.sleep(8)
    raise SystemExit(f'All Overpass endpoints failed. Last: {last}')


def gather(query: str, bbox, tiled: bool = True) -> list[dict]:
    """Every Overpass answer for this bbox: one, or one per tile.

    A bbox inside WIDE degrees goes as a single query and must not come back
    empty. A wider one is tiled, and then a tile may be empty sea -- but not
    all of them: a whole island answering with nothing is the mirror failure
    the single-query rule guards against, so it is caught here instead.

    `tiled=False` sends even a wide bbox as one query, for a query too light to
    need splitting. Tiling exists because the railway is heavy; it is not free.
    Overpass is queue-bound, so every tile is another wait in a queue that was
    answering 502 and 504 the week this was written, and another chance to fail
    the whole fetch. A single query still must not come back empty.
    """
    s, w, n, e = bbox
    # Rounded, because Surabaya's bbox is exactly two degrees wide and
    # 113.2 - 111.2 is the kind of subtraction that comes out at 2.0000000000001
    # and tiles a region that has a perfectly good single-query cache already.
    if not tiled or max(round(n - s, 6), round(e - w, 6)) <= WIDE:
        return [overpass(query, bbox)]
    boxes = tiles(bbox)
    print(f'    {len(boxes)} tiles of {TILE} degree')
    payloads = []
    for at, box in enumerate(boxes, 1):
        print(f'    tile {at}/{len(boxes)} {box}')
        payloads.append(overpass(query, box, allow_empty=True))
        if at < len(boxes):
            time.sleep(PAUSE)
    if not any(p.get('elements') for p in payloads):
        raise SystemExit(f'all {len(boxes)} tiles answered with zero elements')
    return payloads


def merge_rail(payloads: list[dict]) -> dict:
    """The rail ways from every tile as one FeatureCollection, deduplicated.

    Overpass hands back a way that merely touches the bbox with its whole
    geometry, so a way crossing a tile edge arrives twice, identically. The OSM
    id is what says they are one way.
    """
    features = {}
    for payload in payloads:
        for el in payload.get('elements', []):
            geom = el.get('geometry')
            if not geom or len(geom) < 2 or el['id'] in features:
                continue
            tags = el.get('tags', {})
            features[el['id']] = {
                'type': 'Feature',
                'properties': {
                    'id': el['id'],
                    'railway': tags.get('railway'),
                    'usage': tags.get('usage'),
                    'name': tags.get('name'),
                },
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [[round(p['lon'], 7), round(p['lat'], 7)]
                                    for p in geom],
                },
            }
    return {'type': 'FeatureCollection',
            'features': [features[at] for at in sorted(features)]}


def merge_stations(payloads: list[dict]) -> list[dict]:
    """The station elements from every tile, deduplicated on type and id.

    A node carries one id space and a way another, so the pair is the key; a
    station mapped as an area sits in both lists under the same number.
    """
    out = {}
    for payload in payloads:
        for el in payload.get('elements', []):
            out.setdefault((el['type'], el['id']), el)
    return [out[key] for key in sorted(out)]


def fetch_rail(out: pathlib.Path, bbox) -> None:
    print('  rail ways...')
    data = merge_rail(gather(RAIL_QUERY, bbox))
    features = data['features']
    path = out / 'rail.geojson'
    json.dump(data, open(path, 'w'), separators=(',', ':'))
    print(f'    {len(features)} ways -> {path.relative_to(ROOT)} '
          f'({path.stat().st_size / 1e6:.1f} MB)')


def fetch_stations(out: pathlib.Path, bbox) -> None:
    print('  stations...')
    rows = []
    # One query for any bbox: Java's stations are about a thousand points, less
    # than a single railway tile, so tiling them would only multiply the waits.
    for el in merge_stations(gather(STATION_QUERY, bbox, tiled=False)):
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
