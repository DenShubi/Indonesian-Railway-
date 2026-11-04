"""Build data/stations.csv: one row per station called at, with OpenStreetMap coordinates.

Stations are matched on OSM's railway:ref, which is the KAI station code the
timetable prints, so there is no name guessing. Where OSM has not tagged a
station with a ref, the printed name is used instead. Anything that fails both
falls back to the previous stations.csv and is reported loudly.

Each region is searched in its own OSM cache, and a station used by two regions
keeps one row.

Usage:  python scripts/build_stations.py
"""
import csv, json, pathlib, re, unicodedata

ROOT = pathlib.Path(__file__).resolve().parents[1]
D = ROOT / 'data'


def norm(s: str) -> str:
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().upper()
    s = re.sub(r'^STASIUN\s+', '', s)
    return re.sub(r'[^A-Z0-9]', '', s)


def main() -> None:
    regions = json.load(open(D / 'regions.json', encoding='utf-8'))
    parsed = json.load(open(D / 'trips_parsed.json', encoding='utf-8'))
    pdf_names = parsed['names']

    # A station belongs to the first region whose trips call at it.
    region_of = {}
    for trip in parsed['trips']:
        for stop in trip['stops']:
            region_of.setdefault(stop['code'], trip['region'])
    codes = sorted(region_of)

    by_ref, by_name = {}, {}
    for region in regions:
        path = D / 'osm' / region['id'] / 'stations.csv'
        if not path.exists():
            print(f'  !! no OSM cache for {region["id"]} - run scripts/fetch_osm.py')
            continue
        for r in csv.DictReader(open(path, encoding='utf-8')):
            if r['ref']:
                by_ref.setdefault(r['ref'], r)
            if r['norm']:
                by_name.setdefault(r['norm'], r)

    previous = {}
    old_path = D / 'stations.csv'
    if old_path.exists():
        previous = {r['code']: r for r in csv.DictReader(open(old_path, encoding='utf-8'))}

    rows, fallbacks, moved = [], [], []
    for code in codes:
        hit = by_ref.get(code) or by_name.get(norm(pdf_names.get(code, '')))
        if hit:
            rows.append({'code': code, 'name': hit['name'], 'lat': hit['lat'],
                         'lon': hit['lon'], 'region': region_of[code], 'source': 'osm'})
            was = previous.get(code)
            if was:
                dlat = float(hit['lat']) - float(was['lat'])
                dlon = float(hit['lon']) - float(was['lon'])
                metres = ((dlat * 111320) ** 2 + (dlon * 110570) ** 2) ** 0.5
                if metres > 300:
                    moved.append((code, hit['name'], metres))
        elif code in previous:
            was = previous[code]
            rows.append({'code': code, 'name': was['name'], 'lat': was['lat'],
                         'lon': was['lon'], 'region': region_of[code], 'source': 'previous'})
            fallbacks.append(code)
        else:
            fallbacks.append(code)
            print(f'  !! {code} ({pdf_names.get(code, "?")}) has no coordinate at all')

    with open(old_path, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=['code', 'name', 'lat', 'lon', 'region', 'source'])
        writer.writeheader()
        writer.writerows(rows)

    print(f'{len(rows)} stations -> data/stations.csv '
          f'({sum(1 for r in rows if r["source"] == "osm")} from OpenStreetMap)')
    if moved:
        print(f'\n{len(moved)} coordinates moved more than 300 m:')
        for code, name, metres in sorted(moved, key=lambda m: -m[2]):
            print(f'  {code:<5} {name:<24} {metres / 1000:6.2f} km')
    if fallbacks:
        print(f'\nnot matched in OpenStreetMap: {fallbacks}')


if __name__ == '__main__':
    main()
