"""Cross-check the feed against the official GAPEKA 2025 register.

"Train Timetables/GAPEKA Jadwal Kereta.pdf" is Lampiran II of DJKA decree
KP-DJKA 224/2024: every train in Java with its number, service name, relasi,
distance and end-to-end times. That makes it an independent authority for three
questions the per-region timetable PDFs cannot answer on their own:

  * which Commuter Line services exist in a region at all
  * whether we parsed every train
  * whether our OSM-routed shapes are the right length

The register splits some through runs into their two legs (Arjonegoro 444 + 445
is the single run the timetable prints as 444-445), so a trip is matched either
by its own number or by the numbers either side of the dash.

A region whose PDF predates GAPEKA 2025 is marked "gapekaNumbering": false in
data/regions.json. Its train numbers cannot line up with the register, so only
the per-line route lengths are compared there.

Usage:  python scripts/validate_gapeka.py
"""
import json, pathlib, re, sys
from collections import defaultdict

import pdfplumber

ROOT = pathlib.Path(__file__).resolve().parents[1]
PDF = ROOT / 'Train Timetables' / 'GAPEKA Jadwal Kereta.pdf'
BUNDLE = ROOT / 'data' / 'bundle.json'

REGIONS = json.load(open(ROOT / 'data' / 'regions.json', encoding='utf-8'))
# Our line name -> the name the register prints, where they differ.
SERVICE_ALIASES = {'PRAMEKS': 'PRAMEKS KUTOARJO'}
LINES = {line.upper(): region['id'] for region in REGIONS for line in region.get('colors', {})}
SERVICES = {SERVICE_ALIASES.get(line, line): line for line in LINES}

# urut, no, jenis, nama(+identitas), ident, lintas, operator, km, km_int, dep, arr, duration
ROW = re.compile(
    r'^(\d+)\s+(\S+)\s+(REGULER|FAKULTATIF)\s+(.+?)\s+(\d+)\s+(.+?)\s+(PT\.\s*\w+)\s+'
    r'([\d.,]+)\s+(\d+)\s+(\d{2}:\d{2}:\d{2})\s+(\d{2}:\d{2}:\d{2})\s+([\d.]+)\s*$')

# A routed shape follows curves the register measures along the line, so allow a
# little slack before calling a length wrong.
KM_TOLERANCE = 0.03      # fraction
KM_FLOOR = 3.0           # km


def read_register() -> dict:
    """KA number -> record, for the Commuter Line services our regions cover."""
    out = {}
    with pdfplumber.open(PDF) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or '').split('\n'):
                m = ROW.match(line.strip())
                if not m:
                    continue
                _, number, _, name, _, lintas, _, km, _, dep, arr, _ = m.groups()
                # The register repeats the service name twice in the same cell.
                text = name.upper().replace('COMMUTER LINE ', '')
                hit = next((s for s in SERVICES if text.startswith(s)), None)
                if not hit:
                    continue
                ours = SERVICES[hit]
                out[number] = {
                    'line': ours,
                    'region': LINES[ours],
                    'lintas': lintas.strip(),
                    'km': float(km.replace('.', '').replace(',', '.')),
                    'dep': dep[:5],
                    'arr': arr[:5],
                }
    return out


def hhmm(seconds: int) -> str:
    return f'{seconds // 3600 % 24:02d}:{seconds % 3600 // 60:02d}'


def off_by_too_much(ours: float, theirs: float) -> bool:
    return abs(ours - theirs) > max(KM_FLOOR, KM_TOLERANCE * theirs)


def main() -> None:
    if not PDF.exists():
        raise SystemExit(f'missing {PDF}')
    register = read_register()
    bundle = json.load(open(BUNDLE, encoding='utf-8'))
    route_region = {rid: r.get('g', '') for rid, r in bundle['routes'].items()}
    route_line = {rid: r['name'].upper() for rid, r in bundle['routes'].items()}

    counts = defaultdict(lambda: defaultdict(int))
    for rec in register.values():
        counts[rec['region']][rec['line']] += 1

    problems = []

    for region in REGIONS:
        rid = region['id']
        trips = [t for t in bundle['trips'] if route_region.get(t['r']) == rid]
        print(f'== {region["name"]}: register {sum(counts[rid].values())} trains, '
              f'feed {len(trips)}')
        for line in sorted(counts[rid]):
            ours = sum(1 for t in trips if route_line[t['r']] == line)
            print(f'   {line:<16} register {counts[rid][line]:>3}   feed {ours:>3}')

        if not region.get('gapekaNumbering', True):
            print(f'   note: {region.get("timetableNote", "")}')
            for line in sorted(counts[rid]):
                theirs = max((r['km'] for r in register.values()
                              if r['region'] == rid and r['line'] == line), default=0.0)
                mine = max((t['k'][-1][2] for t in trips if route_line[t['r']] == line),
                           default=0.0)
                bad = off_by_too_much(mine, theirs)
                print(f'   {line:<16} longest run {mine:7.2f} km vs register {theirs:7.2f} km'
                      f'{"  LENGTH" if bad else ""}')
                if bad:
                    problems.append(f'{rid}/{line}: {mine:.1f} km vs register {theirs:.1f} km')
            print()
            continue

        matched = set()
        for trip in sorted(trips, key=lambda t: (t['r'], t['n'])):
            keys = [trip['n']] if trip['n'] in register else trip['n'].split('-')
            refs = [register[k] for k in keys if k in register]
            if not refs:
                problems.append(f'{trip["n"]}: no GAPEKA entry')
                continue
            matched.update(k for k in keys if k in register)

            ours_km = trip['k'][-1][2]
            their_km = sum(r['km'] for r in refs)
            if off_by_too_much(ours_km, their_km):
                problems.append(
                    f'{trip["n"]}: routed {ours_km:.1f} km vs register {their_km:.1f} km')
            window = f'{hhmm(trip["k"][0][1])}-{hhmm(trip["k"][-1][0])}'
            their_window = f'{min(r["dep"] for r in refs)}-{max(r["arr"] for r in refs)}'
            if window != their_window:
                problems.append(f'{trip["n"]}: runs {window} vs register {their_window}')

        missing = sorted(n for n, r in register.items()
                         if r['region'] == rid and n not in matched)
        if missing:
            print(f'   in the register but not in the feed: {missing}')
            problems += [f'{n}: in the register, missing from the feed' for n in missing]
        print()

    if problems:
        print(f'{len(problems)} disagreement(s) with the register:')
        for line in problems:
            print(f'  - {line}')
        sys.exit(1)
    print(f'all {len(bundle["trips"])} trips agree with the register')


if __name__ == '__main__':
    main()
