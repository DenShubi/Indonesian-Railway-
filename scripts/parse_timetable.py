"""Parse the KAI Commuter Wilayah 8 timetable PDF into trips.

The PDF uses two layouts:
  A "station rows"  pages 1-2: one row per station, one column per train
  B "train rows"    pages 3-5: one row per train, one column per station

Station codes printed in the PDF are not trustworthy - Wonokromo is printed as
(WR), the same code as Waru, and Mojokerto appears as (SDA) on page 4 - so each
column/row is resolved by its station NAME, using OpenStreetMap's railway:ref as
the authority, and only falls back to the printed code. Mismatches are reported.

Every trip carries the line name from its own "NAMA KA" cell (layout B) or the
page title (layout A), which is what separates Arjonegoro from Blorasura on
page 5 and picks up Jenggala on page 4.

Output: data/trips_parsed.json
Usage:  python scripts/parse_timetable.py
"""
import csv, json, pathlib, re, statistics, sys, unicodedata
from collections import defaultdict

import pdfplumber

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from words import build_words, CODE, TIME  # noqa: E402

PDF = ROOT / 'Train Timetables' / 'Jadwal Commuter Line Wilayah 8 Surabaya.pdf'
OSM_STATIONS = ROOT / 'data' / 'osm' / 'stations.csv'
OUT = ROOT / 'data' / 'trips_parsed.json'

# Pages 1-2 carry one line each; pages 3-5 name their line per trip row.
PAGE_LINES = {0: 'Dhoho', 1: 'Penataran'}

LINE_RE = re.compile(r'Commuter\s*Line\s*(\w+)', re.I)

# Names the PDF spells differently from OpenStreetMap.
NAME_ALIASES = {
    'SURABAYAPASARTURI': 'SBI',
    'SURABAYAPASARTURII': 'SBI',
    'SURABAYAKOTA': 'SB',
    'SURABAYAGUBENG': 'SGU',
    'MALANGKOTALAMA': 'MLK',
    'MALANGKOTABARU': 'ML',
}


def norm(s: str) -> str:
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().upper()
    s = re.sub(r'^STASIUN\s+', '', s)
    return re.sub(r'[^A-Z0-9]', '', s)


def load_name_index() -> dict:
    """norm(station name) -> KAI code, from OpenStreetMap's railway:ref."""
    index = dict(NAME_ALIASES)
    if not OSM_STATIONS.exists():
        raise SystemExit(f'missing {OSM_STATIONS} - run scripts/fetch_osm.py first')
    for row in csv.DictReader(open(OSM_STATIONS, encoding='utf-8')):
        if row['ref'] and row['norm']:
            index.setdefault(row['norm'], row['ref'])
    return index


class Resolver:
    """Turns a printed name + printed code into one trusted station code."""

    def __init__(self, index: dict):
        self.index = index
        self.conflicts = []
        self.unmatched = []
        self.names = {}

    def resolve(self, name: str, printed: str, where: str) -> str:
        key = norm(name)
        code = self.index.get(key)
        if code is None:
            if name:
                self.unmatched.append((where, name, printed))
            return printed
        if printed and code != printed:
            self.conflicts.append((where, name, printed, code))
        self.names.setdefault(code, name.title())
        return code


def cluster(values, gap=10):
    values = sorted(values)
    out, cur = [], [values[0]]
    for v in values[1:]:
        if v - cur[-1] <= gap:
            cur.append(v)
        else:
            out.append(sum(cur) / len(cur))
            cur = [v]
    out.append(sum(cur) / len(cur))
    return out


def nearest(value, centres):
    return min(range(len(centres)), key=lambda i: abs(centres[i] - value))


# --------------------------------------------------------------------------- A

def parse_station_rows(page, line, resolver):
    """Pages 1-2: stations down the left edge, one column per train."""
    W = build_words(page)
    anchors = sorted((w['top'], CODE.match(w['text']).group(1))
                     for w in W if CODE.match(w['text']) and w['x0'] < 90)

    # Each left-column text token belongs to its nearest code anchor.
    buckets = defaultdict(list)
    for w in W:
        if (w['x0'] < 90 and not CODE.match(w['text']) and not TIME.match(w['text'])
                and not w['text'].isdigit()):
            i = min(range(len(anchors)), key=lambda k: abs(anchors[k][0] - w['top']))
            if abs(anchors[i][0] - w['top']) <= 6:
                buckets[i].append((w['x0'], w['text']))

    codes = []
    for i, (top, printed) in enumerate(anchors):
        name = ' '.join(t for _, t in sorted(buckets[i]))
        codes.append(resolver.resolve(name, printed, f'{line} p{page.page_number} row {i + 1}'))

    trains = sorted((w['mid'], w['text'].strip('()')) for w in W
                    if re.fullmatch(r'\(?\d{3}(-\d{3})?\)?', w['text']) and w['top'] < 140)
    times = [w for w in W if TIME.match(w['text'])]
    centres = cluster([w['mid'] for w in times])
    if len(centres) != len(trains):
        raise SystemExit(f'p{page.page_number}: {len(centres)} time columns but {len(trains)} trains')

    columns = defaultdict(list)
    dropped = 0
    for w in times:
        ci = nearest(w['mid'], centres)
        ri = min(range(len(anchors)), key=lambda k: abs(anchors[k][0] - w['top']))
        if abs(anchors[ri][0] - w['top']) > 11:
            dropped += 1
            continue
        columns[ci].append((anchors[ri][0], codes[ri], w['text']))

    trips = []
    for ci in sorted(columns):
        stops = [{'code': c, 'time': t} for _, c, t in sorted(columns[ci])]
        trips.append({'line': line, 'number': trains[ci][1], 'relasi': '',
                      'page': page.page_number, 'stops': stops})
    if dropped:
        print(f'  ! p{page.page_number}: {dropped} time tokens did not line up with a station row')
    return trips


# --------------------------------------------------------------------------- B

def parse_train_rows(page, resolver):
    """Pages 3-5: one row per train, one column per station, several tables."""
    W = build_words(page)
    heads = sorted(w['top'] for w in W if w['text'] == 'NO.' and w['x0'] < 115)
    if not heads:
        return []

    code_x0 = min((w['x0'] for w in W if CODE.match(w['text'])), default=10 ** 6)
    heading = {}
    for key, token in (('no', 'NO.'), ('nomor', 'NOMOR'), ('nama', 'NAMA'), ('relasi', 'RELASI')):
        xs = [w['x0'] for w in W if w['text'] == token and w['x0'] < code_x0]
        if xs:
            heading[key] = min(xs)
    # A cell's contents can start left of its heading, so split on the midpoints.
    mid = lambda a, b: (heading[a] + heading[b]) / 2
    bounds = {
        'number': (mid('no', 'nomor'), mid('nomor', 'nama')),
        'name': (mid('nomor', 'nama'), mid('nama', 'relasi')),
        'relasi': (mid('nama', 'relasi'), code_x0),
    }

    trips = []
    for hi, htop in enumerate(heads):
        nxt = heads[hi + 1] if hi + 1 < len(heads) else 10 ** 6

        # Station header: codes around this table's NO. row. The window reaches a
        # little ABOVE that row because a station split into arrival/departure
        # columns (Surabaya Pasarturi on page 5) carries its code in a merged cell
        # that sits higher than the rest of the header.
        header = sorted((w['mid'], w['top'], CODE.match(w['text']).group(1)) for w in W
                        if CODE.match(w['text']) and w['x0'] >= code_x0
                        and htop - 9 < w['top'] < htop + 20)
        if len(header) < 3:
            continue
        # Station names sit just above the MAIN code row. Use the median code top,
        # not the minimum: a merged arrival/departure cell puts one code higher
        # than the rest and would drag the name band off the names entirely.
        band_top = statistics.median(sorted(t for _, t, _ in header))

        centres = [mid for mid, _, _ in header]
        pitch = min((b - a for a, b in zip(centres, centres[1:])), default=24)

        # Station names sit in one band just above the code row, each centred on
        # its column. Assign every word to its nearest column, then read each
        # column's words in printed order so wrapped names ("SURABAYA PASAR
        # TURI") come back in the right order.
        parts = defaultdict(list)
        for w in W:
            if CODE.match(w['text']) or not (band_top - 10 < w['top'] < band_top - 0.3):
                continue
            ci = nearest(w['mid'], centres)
            if abs(centres[ci] - w['mid']) < pitch / 2:
                parts[ci].append((w['top'], w['x0'], w['text']))

        codes = []
        for ci, (mid, _, printed) in enumerate(header):
            name = ' '.join(t for _, _, t in sorted(parts.get(ci, [])))
            codes.append(resolver.resolve(name, printed, f'p{page.page_number} col x={mid:.0f}'))

        # Trip rows between this station header and the next table.
        rows = defaultdict(list)
        for w in W:
            if TIME.match(w['text']) and band_top + 4 < w['top'] < nxt - 4:
                rows[round(w['top'] / 3)].append(w)

        for key in sorted(rows):
            tw = sorted(rows[key], key=lambda a: a['x0'])
            top = tw[0]['top']
            label = [w for w in W if w['x0'] < code_x0 and top - 3.5 <= w['top'] < top + 4.5]

            def cell(start, end):
                return ' '.join(w['text'] for w in sorted(label, key=lambda a: a['x0'])
                                if start <= w['x0'] < end)

            number = cell(*bounds['number']).replace(' ', '')
            name_cell = cell(*bounds['name'])
            relasi = cell(*bounds['relasi'])
            match = LINE_RE.search(name_cell)
            line = match.group(1).title() if match else None

            stops = []
            for w in tw:
                ci = nearest(w['mid'], centres)
                if abs(centres[ci] - w['mid']) < 17:
                    stops.append({'code': codes[ci], 'time': w['text']})
            if len(stops) >= 3 and line:
                trips.append({'line': line, 'number': number or None, 'relasi': relasi,
                              'page': page.page_number, 'stops': stops})
    return trips


def main() -> None:
    resolver = Resolver(load_name_index())
    pdf = pdfplumber.open(PDF)
    trips = []
    for pi, page in enumerate(pdf.pages):
        if pi in PAGE_LINES:
            trips += parse_station_rows(page, PAGE_LINES[pi], resolver)
        else:
            trips += parse_train_rows(page, resolver)

    by_line = defaultdict(list)
    for t in trips:
        by_line[t['line']].append(t)

    print(f'{len(trips)} trips across {len(by_line)} lines')
    for line, group in sorted(by_line.items()):
        calls = sum(len(t['stops']) for t in group)
        numbers = ', '.join(str(t['number']) for t in group)
        print(f'  {line:<12} {len(group):>3} trips  {calls:>4} calls   {numbers}')

    if resolver.conflicts:
        print(f'\nprinted code disagreed with the station name in {len(resolver.conflicts)} cells '
              f'(name wins):')
        seen = set()
        for where, name, printed, code in resolver.conflicts:
            key = (name, printed, code)
            if key in seen:
                continue
            seen.add(key)
            print(f'  {name:<24} printed ({printed}) -> ({code})   {where}')
    if resolver.unmatched:
        print(f'\n{len(resolver.unmatched)} cells had no OSM match, keeping the printed code:')
        for where, name, printed in sorted(set(resolver.unmatched))[:20]:
            print(f'  {name!r:<30} ({printed})  {where}')

    json.dump({'trips': trips, 'names': resolver.names},
              open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(f'\n-> {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
