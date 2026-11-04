"""Parse the KAI Commuter timetable PDFs into trips.

One region per PDF, listed in data/regions.json. Three layouts turn up across them:

  station_rows  one row per station, one column per train   (Surabaya p1-2, Bandung p3)
  train_rows    one row per train, one column per station   (Surabaya p3-5, Bandung p1-2)
  flat_text     one line per train, station codes in the header line  (Yogyakarta)

The two geometric layouts are read from rebuilt words rather than extracted text,
because these PDFs lose their column structure in plain extraction.

Station codes printed in the PDFs are not trustworthy - on the Surabaya pages
Wonokromo is printed (WR), the same code as Waru, and Mojokerto appears as
(SDA) - so wherever a station NAME is printed it wins, resolved against
OpenStreetMap's railway:ref. Disagreements are reported.

Every trip carries the line name from its own "NAMA KA" cell, or from the page
entry in regions.json where the page has no such column.

Output: data/trips_parsed.json
Usage:  python scripts/parse_timetable.py [region-id ...]
"""
import csv, json, pathlib, re, statistics, sys, unicodedata
from collections import defaultdict

import pdfplumber

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from words import build_words, CODE, TIME  # noqa: E402

REGIONS = json.load(open(ROOT / 'data' / 'regions.json', encoding='utf-8'))
OUT = ROOT / 'data' / 'trips_parsed.json'

# "Bandung Raya" is the only two-word service name in these feeds; everything
# after a one-word name is the relasi, so the second word is matched explicitly.
LINE_RE = re.compile(r'Commuter\s*Line\s*(\w+(?:\s+Raya)?)', re.I)
TRAIN_NO = re.compile(r'^\(?(\d{3,4}[A-Z]?(?:-\d{3,4}[A-Z]?)?)\)?$')
# "PADALARANG(PDL)", "(GRM) GARUM", "MALANG (MLK) KOTA LAMA" all appear.
NAME_CODE = re.compile(r'\(([A-Z]{2,4})\)')

# Service names the PDFs abbreviate.
LINE_ALIASES = {'Yk': 'Yogyakarta'}

# Station names the PDFs spell differently from OpenStreetMap.
NAME_ALIASES = {
    'SURABAYAPASARTURI': 'SBI',
    'SURABAYAPASARTURII': 'SBI',
    'SURABAYAKOTA': 'SB',
    'SURABAYAGUBENG': 'SGU',
    'HAUPUGUR': 'HRP',
    'SUMBEREJO': 'SRJ',
    'MALANGKOTALAMA': 'MLK',
    'MALANGKOTABARU': 'ML',
}


def norm(s: str) -> str:
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().upper()
    s = re.sub(r'^STASIUN\s+', '', s)
    return re.sub(r'[^A-Z0-9]', '', s)


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


class Resolver:
    """Turns a printed name and/or printed code into one trusted station code."""

    def __init__(self, region_id: str):
        path = ROOT / 'data' / 'osm' / region_id / 'stations.csv'
        if not path.exists():
            raise SystemExit(f'missing {path} - run scripts/fetch_osm.py {region_id} first')
        self.index = dict(NAME_ALIASES)
        self.known = set()
        for row in csv.DictReader(open(path, encoding='utf-8')):
            if row['ref']:
                self.known.add(row['ref'])
                if row['norm']:
                    self.index.setdefault(row['norm'], row['ref'])
        self.conflicts = []
        self.unmatched = []
        self.unknown = []
        self.names = {}

    def resolve(self, name: str, printed: str, where: str) -> str:
        code = self.index.get(norm(name)) if name else None
        if code is None:
            if name:
                self.unmatched.append((where, name, printed))
                # Keep the printed name anyway: build_stations can still find the
                # station by name for codes OSM has not tagged with a railway:ref.
                self.names.setdefault(printed, name.title())
            if printed and printed not in self.known:
                self.unknown.append((where, printed))
            return printed
        if printed and code != printed:
            self.conflicts.append((where, name, printed, code))
        self.names.setdefault(code, name.title())
        return code


def split_name_code(text: str):
    """Pull the bracketed code out of a label, wherever it sits in the line.

    'PADALARANG(PDL)' -> ('PADALARANG', 'PDL')
    '(GRM) GARUM'     -> ('GARUM', 'GRM')
    'MALANG (MLK) KOTA LAMA' -> ('MALANG KOTA LAMA', 'MLK')
    """
    m = NAME_CODE.search(text)
    if not m:
        return text.strip(), ''
    name = f'{text[:m.start()]} {text[m.end():]}'
    return re.sub(r'\s+', ' ', name).strip(), m.group(1)


# A table's column headers - the train numbers - sit above its "NO." heading row,
# so each band starts this far above it.
BAND_LOOKBACK = 42.0


def table_bands(W, page_height):
    """Split a page into tables on its 'NO.' heading rows."""
    tops = sorted(w['top'] for w in W if w['text'].rstrip('.').upper() == 'NO'
                  and w['x0'] < 130)
    if not tops:
        return [(0.0, page_height)]
    merged = [tops[0]]
    for t in tops[1:]:
        if t - merged[-1] > 20:
            merged.append(t)
    starts = [max(0.0, t - BAND_LOOKBACK) for t in merged]
    return [(starts[i], starts[i + 1] if i + 1 < len(starts) else page_height)
            for i in range(len(starts))]


def read_label(W, code_x0, row_top, spec):
    """Read a trip row's leading cells: train number, line name, relasi.

    Read by content, not by column position: the heading row is glued together on
    some pages ("NO.NOMOR KA NAMA KA RELASI" arrives as one token), so there are
    no reliable column edges to measure. Every row reads
    "<index> <number> Commuter Line <Name> <relasi>", but how the words are glued
    varies by page - "Commuter LineWalahar", "CommuterLineGarut" - so the label is
    re-split on lowercase-to-uppercase joins before being read.
    """
    own = sorted((w for w in W if w['x0'] < code_x0 and abs(w['top'] - row_top) <= 2.5
                  and not TIME.match(w['text'])),
                 key=lambda w: w['x0'])
    blob = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', ' '.join(w['text'] for w in own))
    toks = blob.split()
    at = next((i for i, t in enumerate(toks) if t.lower() == 'commuter'), None)
    if at is None:
        return None, spec.get('line'), blob

    left = toks[:at]
    if left and re.fullmatch(r'\d{1,2}', left[0]):      # the "NO." index column
        left = left[1:]
    number = ''.join(left) or None

    m = LINE_RE.search(blob)
    line = (m.group(1) if m else spec.get('line') or '').title()
    line = LINE_ALIASES.get(line, line) or spec.get('line')
    relasi = ' '.join(toks[at + 3:])
    return number, line, relasi


# ------------------------------------------------------------- station rows

def parse_station_rows(page, region, spec, resolver):
    """Stations down the left edge, one column per train. May hold several tables."""
    W = build_words(page)
    line = spec.get('line')
    trips = []

    for band_no, (top, bottom) in enumerate(table_bands(W, page.height), 1):
        inside = [w for w in W if top <= w['top'] < bottom]
        times = [w for w in inside if TIME.match(w['text'])]
        if len(times) < 6:
            continue

        label_x = min(w['x0'] for w in times) - 4
        centres = cluster([w['mid'] for w in times])
        row_tops = cluster([w['top'] for w in times], gap=4)
        first_row = min(row_tops)

        # One station per row: read its name and code from the label column.
        codes = []
        for ri, rtop in enumerate(row_tops):
            label = sorted((w['x0'], w['text']) for w in inside
                           if w['x0'] < label_x and abs(w['top'] - rtop) <= 5
                           and not w['text'].isdigit())
            name, printed = split_name_code(' '.join(t for _, t in label))
            codes.append(resolver.resolve(
                name, printed, f'{region["id"]} p{page.page_number} row {ri + 1}'))

        # Train numbers sit above the first station row, one per time column.
        trains = {}
        for w in inside:
            m = TRAIN_NO.match(w['text'])
            if m and w['x0'] >= label_x and w['top'] < first_row - 4:
                trains[nearest(w['mid'], centres)] = m.group(1)
        if len(trains) != len(centres):
            print(f'  ! {region["id"]} p{page.page_number} table {band_no}: '
                  f'{len(centres)} time columns but {len(trains)} train numbers')

        columns = defaultdict(list)
        dropped = 0
        for w in times:
            ri = nearest(w['top'], row_tops)
            if abs(row_tops[ri] - w['top']) > 6:
                dropped += 1
                continue
            columns[nearest(w['mid'], centres)].append((row_tops[ri], codes[ri], w['text']))

        for ci in sorted(columns):
            stops = [{'code': c, 'time': t} for _, c, t in sorted(columns[ci])]
            if len(stops) < 3:
                continue
            trips.append({'region': region['id'], 'line': line, 'number': trains.get(ci),
                          'relasi': '', 'page': page.page_number, 'stops': stops})
        if dropped:
            print(f'  ! {region["id"]} p{page.page_number}: {dropped} times did not '
                  f'line up with a station row')
    return trips


# --------------------------------------------------------------- train rows

def parse_train_rows(page, region, spec, resolver):
    """One row per train, one column per station; several tables per page."""
    W = build_words(page)
    heads = sorted(w['top'] for w in W if w['text'] == 'NO.' and w['x0'] < 130)
    if not heads:
        return []

    code_x0 = min((w['x0'] for w in W if CODE.match(w['text'])), default=10 ** 6)

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
        # Names sit just above the MAIN code row. Use the median code top, not the
        # minimum: a merged arrival/departure cell puts one code higher than the
        # rest and would drag the name band off the names entirely.
        band_top = statistics.median(sorted(t for _, t, _ in header))

        centres = [m for m, _, _ in header]
        pitch = min((b - a for a, b in zip(centres, centres[1:])), default=24)

        # Assign every word in the name band to its nearest column, then read each
        # column's words in printed order so wrapped names come back right.
        parts = defaultdict(list)
        for w in W:
            if CODE.match(w['text']) or not (band_top - 10 < w['top'] < band_top - 0.3):
                continue
            ci = nearest(w['mid'], centres)
            if abs(centres[ci] - w['mid']) < pitch / 2:
                parts[ci].append((w['top'], w['x0'], w['text']))

        codes = []
        for ci, (m, _, printed) in enumerate(header):
            name = ' '.join(t for _, _, t in sorted(parts.get(ci, [])))
            codes.append(resolver.resolve(
                name, printed, f'{region["id"]} p{page.page_number} col x={m:.0f}'))

        rows = defaultdict(list)
        for w in W:
            if TIME.match(w['text']) and band_top + 4 < w['top'] < nxt - 4:
                rows[round(w['top'] / 3)].append(w)

        for key in sorted(rows):
            tw = sorted(rows[key], key=lambda a: a['x0'])
            top = tw[0]['top']
            number, line, relasi = read_label(W, code_x0, top, spec)

            # Floor the tolerance: a station split into arrival/departure columns
            # widens the gap around it, and half of that gap is narrower than the
            # offset of its own two sub-columns.
            tol = max(pitch / 2, 17.0)
            stops = []
            for w in tw:
                ci = nearest(w['mid'], centres)
                if abs(centres[ci] - w['mid']) < tol:
                    stops.append({'code': codes[ci], 'time': w['text']})
            if len(stops) >= 3 and line:
                trips.append({'region': region['id'], 'line': line, 'number': number,
                              'relasi': relasi, 'page': page.page_number, 'stops': stops})
    return trips


# ----------------------------------------------------------------- flat text

FLAT_HEADER = re.compile(r'\bLINTAS\s+(.+?)\s+WP\s+KETERANGAN\s*$', re.I)
FLAT_ROW = re.compile(
    r'^\d+\s+(\d{3,4}[A-Z]?)\s+COMMUTER\s+LINE\s+(\w+)\s+\d+\s+(\S+)\s*-\s*(\S+)\s+(.+)$', re.I)


def parse_flat_text(page, region, spec, resolver):
    """Yogyakarta: plain text, station codes listed in each table's header line.

    "Ls" marks a station the train passes without stopping, and the last value on
    a row is the journey time rather than a call, so both are dropped while the
    remaining values stay aligned with the header codes.
    """
    trips = []
    header = None
    for raw in (page.extract_text() or '').split('\n'):
        line = raw.strip()
        m = FLAT_HEADER.search(line)
        if m:
            header = [resolver.resolve('', c, f'{region["id"]} header')
                      for c in m.group(1).split()]
            continue
        m = FLAT_ROW.match(line)
        if not (m and header):
            continue
        number, service, origin, destination, rest = m.groups()
        values = rest.split()
        if len(values) == len(header) + 1:      # trailing journey time
            values = values[:-1]
        if len(values) != len(header):
            print(f'  ! {region["id"]} KA {number}: {len(values)} values for '
                  f'{len(header)} stations, skipped')
            continue
        stops = [{'code': code, 'time': value}
                 for code, value in zip(header, values) if TIME.match(value)]
        if len(stops) < 3:
            continue
        service = LINE_ALIASES.get(service.title(), service.title())
        trips.append({'region': region['id'], 'line': service, 'number': number,
                      'relasi': f'{origin}-{destination}', 'page': page.page_number,
                      'stops': stops})
    return trips


LAYOUTS = {'station_rows': parse_station_rows,
           'train_rows': parse_train_rows,
           'flat_text': parse_flat_text}


def main() -> None:
    wanted = [r for r in REGIONS if not sys.argv[1:] or r['id'] in sys.argv[1:]]
    if not wanted:
        raise SystemExit(f'no such region; known ids: {[r["id"] for r in REGIONS]}')

    all_trips, all_names = [], {}
    for region in wanted:
        resolver = Resolver(region['id'])
        pdf = pdfplumber.open(ROOT / 'Train Timetables' / region['pdf'])
        trips = []
        for page, spec in zip(pdf.pages, region['pages']):
            trips += LAYOUTS[spec['layout']](page, region, spec, resolver)

        by_line = defaultdict(list)
        for t in trips:
            by_line[t['line']].append(t)
        print(f'{region["id"]}: {len(trips)} trips across {len(by_line)} lines')
        for line, group in sorted(by_line.items()):
            calls = sum(len(t['stops']) for t in group)
            print(f'  {line:<14} {len(group):>3} trips  {calls:>4} calls   '
                  f'{", ".join(str(t["number"]) for t in group)}'[:150])

        for label, items in (('printed code disagreed with the station name', resolver.conflicts),
                             ('no OSM match for the printed name', resolver.unmatched),
                             ('code is not a station in this region', resolver.unknown)):
            if not items:
                continue
            seen = sorted({tuple(i[1:]) for i in items})
            print(f'  {label} ({len(seen)} distinct):')
            for item in seen[:12]:
                print(f'    {item}')

        all_trips += trips
        all_names.update(resolver.names)
        print()

    json.dump({'trips': all_trips, 'names': all_names},
              open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print(f'{len(all_trips)} trips total -> {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
