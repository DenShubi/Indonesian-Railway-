"""Cross-check the feed against the official GAPEKA 2025 register.

"Train Timetables/GAPEKA Jadwal Kereta.pdf" is Lampiran II of DJKA decree
KP-DJKA 224/2024: every train in Java with its number, service name, relasi,
distance and end-to-end times. That makes it an independent authority for three
questions the per-line timetable PDF cannot answer on its own:

  * which Commuter Line services exist in Wilayah 8 at all
  * whether we parsed every train
  * whether our OSM-routed shapes are the right length

The register splits some through runs into their two legs (Arjonegoro 444 + 445
is the single run the timetable prints as 444-445), so a trip is matched either
by its own number or by the numbers either side of the dash.

Usage:  python scripts/validate_gapeka.py
"""
import json, pathlib, re, sys
from collections import defaultdict

import pdfplumber

ROOT = pathlib.Path(__file__).resolve().parents[1]
PDF = ROOT / 'Train Timetables' / 'GAPEKA Jadwal Kereta.pdf'
BUNDLE = ROOT / 'data' / 'bundle.json'

WILAYAH_8 = {'DHOHO', 'PENATARAN', 'SUPAS', 'ARJONEGORO', 'JENGGALA', 'BLORASURA'}

# urut, no, jenis, nama(+identitas), ident, lintas, operator, km, km_int, dep, arr, duration
ROW = re.compile(
    r'^(\d+)\s+(\S+)\s+(REGULER|FAKULTATIF)\s+(.+?)\s+(\d+)\s+(.+?)\s+(PT\.\s*\w+)\s+'
    r'([\d.,]+)\s+(\d+)\s+(\d{2}:\d{2}:\d{2})\s+(\d{2}:\d{2}:\d{2})\s+([\d.]+)\s*$')

# A routed shape follows curves the register measures along the line, so allow a
# little slack before calling a length wrong.
KM_TOLERANCE = 0.03      # fraction
KM_FLOOR = 3.0           # km


def read_register() -> dict:
    """KA number -> record, for Wilayah 8 Commuter Line services only."""
    out = {}
    with pdfplumber.open(PDF) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or '').split('\n'):
                m = ROW.match(line.strip())
                if not m:
                    continue
                _, number, _, name, _, lintas, _, km, _, dep, arr, _ = m.groups()
                words = name.upper().replace('COMMUTER LINE ', '').split()
                if not words or words[0] not in WILAYAH_8:
                    continue
                out[number] = {
                    'line': words[0],
                    'lintas': lintas.strip(),
                    'km': float(km.replace('.', '').replace(',', '.')),
                    'dep': dep[:5],
                    'arr': arr[:5],
                }
    return out


def hhmm(seconds: int) -> str:
    return f'{seconds // 3600 % 24:02d}:{seconds % 3600 // 60:02d}'


def main() -> None:
    if not PDF.exists():
        raise SystemExit(f'missing {PDF}')
    register = read_register()
    bundle = json.load(open(BUNDLE, encoding='utf-8'))

    counts = defaultdict(int)
    for rec in register.values():
        counts[rec['line']] += 1

    print(f'GAPEKA 2025 lists {len(register)} Wilayah 8 Commuter Line trains:')
    for line in sorted(counts):
        print(f'  {line.title():<12} {counts[line]:>3}')
    print('  (no Tumapel and no Sindro: they are not in the register)')

    problems = []
    matched = set()
    print(f'\n{"trip":<10} {"ours km":>8} {"gapeka":>8} {"diff":>7}  window')
    for trip in sorted(bundle['trips'], key=lambda t: (t['r'], t['n'])):
        keys = [trip['n']] if trip['n'] in register else trip['n'].split('-')
        refs = [register[k] for k in keys if k in register]
        if not refs:
            problems.append(f'{trip["n"]}: no GAPEKA entry')
            continue
        matched.update(k for k in keys if k in register)

        ours_km = trip['k'][-1][2]
        their_km = sum(r['km'] for r in refs)
        window = f'{hhmm(trip["k"][0][1])}-{hhmm(trip["k"][-1][0])}'
        their_window = f'{min(r["dep"] for r in refs)}-{max(r["arr"] for r in refs)}'

        flags = ''
        if abs(ours_km - their_km) > max(KM_FLOOR, KM_TOLERANCE * their_km):
            flags += '  LENGTH'
            problems.append(f'{trip["n"]}: routed {ours_km:.1f} km vs GAPEKA {their_km:.1f} km')
        if window != their_window:
            flags += '  TIMES'
            problems.append(f'{trip["n"]}: runs {window} vs GAPEKA {their_window}')
        print(f'{trip["n"]:<10} {ours_km:8.2f} {their_km:8.2f} {ours_km - their_km:+7.2f}  '
              f'{window}{flags}')

    missing = sorted(set(register) - matched)
    if missing:
        print(f'\nin GAPEKA but not in the feed: {missing}')
        problems += [f'{n}: in GAPEKA, missing from the feed' for n in missing]

    if problems:
        print(f'\n{len(problems)} disagreement(s) with the register:')
        for line in problems:
            print(f'  - {line}')
        sys.exit(1)
    print(f'\nall {len(bundle["trips"])} trips agree with the register '
          f'on length and end-to-end times')


if __name__ == '__main__':
    main()
