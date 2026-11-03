"""Build a GTFS feed for KAI Commuter Wilayah 8 (Surabaya) from the parsed timetable.

Reads data/trips_parsed.json (scripts/parse_timetable.py) and data/stations.csv
(scripts/build_stations.py), and writes gtfs/*.txt plus a zipped copy.
"""
import csv, json, pathlib, sys, zipfile
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
D = ROOT / 'data'
G = ROOT / 'gtfs'
G.mkdir(parents=True, exist_ok=True)

# One colour per line, in the order they appear on the network map.
LINE_COLORS = {
    'Dhoho': 'E4572E',
    'Penataran': '2E9BD6',
    'Supas': '27A567',
    'Arjonegoro': '9B6BC9',
    'Jenggala': 'E9A13B',
    'Blorasura': 'C2456E',
}
FALLBACK_COLOR = '7A8A94'

parsed = json.load(open(D / 'trips_parsed.json', encoding='utf-8'))
stations = {r['code']: r for r in csv.DictReader(open(D / 'stations.csv', encoding='utf-8'))}


def hhmmss(t: str, roll: int) -> str:
    h, m = map(int, t.split(':'))
    return f'{h + 24 * roll:02d}:{m:02d}:00'


def trip_stop_times(stops):
    """Merge a repeated stop into one arrival/departure pair and roll past midnight."""
    merged = []
    for s in stops:
        if merged and merged[-1]['code'] == s['code'] and len(merged[-1]['t']) == 1:
            merged[-1]['t'].append(s['time'])
        else:
            merged.append({'code': s['code'], 't': [s['time']]})

    rows = []
    prev = -1
    roll = 0
    for i, m in enumerate(merged, 1):
        arr, dep = m['t'][0], m['t'][-1]
        for t in (arr, dep):
            h, mi = map(int, t.split(':'))
            v = (h + 24 * roll) * 60 + mi
            if v < prev:
                roll += 1
                v = (h + 24 * roll) * 60 + mi
            prev = max(prev, v)
        rows.append((i, hhmmss(arr, roll), hhmmss(dep, roll), m['code']))
    return rows


def route_id(line: str) -> str:
    return 'CL_' + line.upper()


# Group trips by line, keeping the order they were parsed in.
by_line = defaultdict(list)
for t in parsed['trips']:
    by_line[t['line']].append(t)

stops_used = set()
trips = []
stop_times = []
seen_ids = set()

for line in sorted(by_line, key=lambda l: list(LINE_COLORS).index(l) if l in LINE_COLORS else 99):
    rid = route_id(line)
    for t in by_line[line]:
        number = t.get('number')
        if not number:
            continue
        tid = f'{rid}_{number}'
        if tid in seen_ids:                      # same train number in both directions
            tid = f'{tid}_{len(seen_ids)}'
        seen_ids.add(tid)

        rows = trip_stop_times(t['stops'])
        last = rows[-1][3]
        first = rows[0][3]
        head = stations.get(last, {}).get('name', last)
        # direction 0 runs towards Surabaya, 1 away from it; SB/SBI/SGU are the
        # three Surabaya termini.
        direction = 0 if last in ('SB', 'SBI', 'SGU') else 1

        trips.append({'route_id': rid, 'service_id': 'DAILY', 'trip_id': tid,
                      'trip_short_name': number, 'trip_headsign': head,
                      'direction_id': direction})

        for seq, arr, dep, code in rows:
            if code not in stations:
                print(f'  !! no coordinate for {code} (trip {tid}) - stop dropped', file=sys.stderr)
                continue
            stops_used.add(code)
            stop_times.append({'trip_id': tid, 'arrival_time': arr, 'departure_time': dep,
                               'stop_id': code, 'stop_sequence': seq})
        if first == last:
            print(f'  note: {tid} starts and ends at {first}')


def write(name, fields, rows):
    with open(G / name, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


write('agency.txt', ['agency_id', 'agency_name', 'agency_url', 'agency_timezone', 'agency_lang'],
      [{'agency_id': 'KAIC', 'agency_name': 'KAI Commuter', 'agency_url': 'https://commuterline.id',
        'agency_timezone': 'Asia/Jakarta', 'agency_lang': 'id'}])

write('stops.txt', ['stop_id', 'stop_name', 'stop_lat', 'stop_lon'],
      [{'stop_id': c, 'stop_name': stations[c]['name'],
        'stop_lat': stations[c]['lat'], 'stop_lon': stations[c]['lon']}
       for c in sorted(stops_used)])

write('routes.txt',
      ['route_id', 'agency_id', 'route_short_name', 'route_long_name', 'route_type', 'route_color'],
      [{'route_id': route_id(line), 'agency_id': 'KAIC', 'route_short_name': line,
        'route_long_name': f'Commuter Line {line}', 'route_type': 2,
        'route_color': LINE_COLORS.get(line, FALLBACK_COLOR)}
       for line in sorted(by_line, key=lambda l: list(LINE_COLORS).index(l)
                          if l in LINE_COLORS else 99)])

write('trips.txt',
      ['route_id', 'service_id', 'trip_id', 'trip_short_name', 'trip_headsign', 'direction_id'],
      trips)
write('stop_times.txt',
      ['trip_id', 'arrival_time', 'departure_time', 'stop_id', 'stop_sequence'], stop_times)
write('calendar.txt',
      ['service_id', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
       'start_date', 'end_date'],
      [{'service_id': 'DAILY', 'monday': 1, 'tuesday': 1, 'wednesday': 1, 'thursday': 1,
        'friday': 1, 'saturday': 1, 'sunday': 1, 'start_date': '20260101', 'end_date': '20271231'}])

zp = D / 'gtfs_wilayah8_surabaya.zip'
with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in sorted(G.glob('*.txt')):
        z.write(f, f.name)

print(f'routes={len(by_line)} trips={len(trips)} stops={len(stops_used)} '
      f'stop_times={len(stop_times)}')
for line in sorted(by_line):
    print(f'  {line:<12} {len(by_line[line]):>3} trips')
print(f'zip: {zp.relative_to(ROOT)} {zp.stat().st_size} bytes')
