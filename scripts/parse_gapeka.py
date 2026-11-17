"""Extract the GAPEKA 2025 register once, and keep what it says.

"Train Timetables/GAPEKA Jadwal Kereta.pdf" is Lampiran II of DJKA decree
KP-DJKA 224/2024 and it is the primary source for every train on Java. This
script is the only thing in the pipeline that opens it: every page's text goes
once into data/gapeka/pages.json and later runs read that back unless --force
is passed, so nothing downstream -- and no test -- needs pdfplumber at all.
Three files come out of it:

  pages.json     the extraction itself, text per page, plus the per-word
                 coordinates for the twelve pages that print a distance matrix
  trains.json    1,775 trains, each with the category of the section it is in
  network.json   37 corridor chains and 6 inline branch pairs, 396 stations

pages.json keeps word coordinates only for the matrix pages because those are
the only pages any parser reads them on -- tables.recover_vertical_codes()
de-interleaves the two wrecked headers from them -- and all 64 pages of
coordinates would triple the file for nothing. The whole extraction takes about
half a minute, measured, and is deterministic: a --force re-run writes the same
656 kB byte for byte.

Which pages hold what is read off the register rather than hardcoded. A train
section starts at a "KELAS KERETA API" banner, so rows.scan_sections() finds
the train tables wherever they are. The distance tables are the pages that
print a matrix row; a page's inline branch pairs ("KEN-CGD 6,439") are taken
only from those pages, because the register's duty rosters on pages 32-40 put
a station pair next to a distance in every row -- "R1100 ... KRL DP-BOO 22,126"
-- and reading those as branches would wire Solo to Yogyakarta direct and
short-circuit half the island.

Usage:  python scripts/parse_gapeka.py [--force]
"""
import json
import pathlib
import sys

import pdfplumber

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from gapeka.rows import SECTION_CATEGORIES, scan_sections            # noqa: E402
from gapeka.tables import (parse_corridor_block, parse_inline_pairs,  # noqa: E402
                           parse_matrix_rows, recover_vertical_codes)

PDF = ROOT / 'Train Timetables' / 'GAPEKA Jadwal Kereta.pdf'
OUT = ROOT / 'data' / 'gapeka'

# What this edition holds. Asserted rather than merely printed: the page roles
# are discovered, so a discovery that goes wrong has to fail loudly instead of
# quietly writing a smaller network for the rest of the pipeline to build on.
TRAINS = 1775
SECTIONS = 18
CORRIDORS = 37
CODES = 396


def extract(path: pathlib.Path) -> dict[str, dict]:
    """Every page of the register as {"<page>": {"text", "words"?}}.

    Keyed on the page index as a string, because that is what JSON gives back
    and sorting on int(key) is the only thing that reads it. Coordinates are
    rounded to a tenth of a point, which is finer than any gap tables.py
    measures and halves the file.
    """
    pages = {}
    with pdfplumber.open(path) as pdf:
        for at, page in enumerate(pdf.pages):
            text = page.extract_text() or ''
            pages[str(at)] = {'text': text}
            if any(parse_matrix_rows(line) for line in text.split('\n')):
                pages[str(at)]['words'] = [
                    [round(w['x0'], 1), round(w['top'], 1), w['text']]
                    for w in page.extract_words()]
            print(f'  page {at + 1}/{len(pdf.pages)}', end='\r', flush=True)
    print()
    return pages


def read_pages(force: bool) -> dict[str, dict]:
    """The cached extraction, extracting it first if it is missing or stale."""
    path = OUT / 'pages.json'
    if path.exists() and not force:
        pages = json.loads(path.read_text(encoding='utf-8'))
        print(f'{path.relative_to(ROOT)}: {len(pages)} pages cached '
              f'({path.stat().st_size / 1e6:.1f} MB) - pass --force to re-extract')
        return pages
    if not PDF.exists():
        raise SystemExit(f'missing {PDF.relative_to(ROOT)}')
    print(f'extracting {PDF.name}...')
    pages = extract(PDF)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pages, separators=(',', ':')), encoding='utf-8')
    print(f'  -> {path.relative_to(ROOT)} '
          f'({path.stat().st_size / 1e6:.1f} MB, {len(pages)} pages)')
    return pages


def read_network(pages: dict[str, dict]) -> tuple[list, list]:
    """The corridor chains and inline branch pairs, from the matrix pages."""
    corridors, pairs = [], []
    for page in sorted(pages, key=int):
        lines = [line for line in pages[page]['text'].split('\n') if line.strip()]
        if not any(parse_matrix_rows(line) for line in lines):
            continue
        words = pages[page].get('words', [])
        found = parse_corridor_block(lines, recover_vertical_codes(words, int(page)))
        corridors.extend(found)
        for line in lines:
            pairs.extend(parse_inline_pairs(line))
    return corridors, pairs


def main() -> None:
    force = '--force' in sys.argv[1:]
    OUT.mkdir(parents=True, exist_ok=True)
    pages = read_pages(force)

    sections = scan_sections(pages)
    trains = [dict(train, category=section.category, section=section.name)
              for section in sections for train in section.trains]
    counted = [section for section in sections if section.trains]
    duty = [section for section in sections if not section.trains]
    print(f'\n{len(trains)} trains in {len(counted)} sections '
          f'({len(duty)} duty-roster sections hold no train rows)')
    for section in counted:
        flag = '' if section.tally == section.claimed else '   !! banner says ' \
            f'{section.claimed[0]}/{section.claimed[1]}'
        print(f'  p{section.page:<3d} {section.name:<30s} {section.category:<30s}'
              f' {section.tally[0]:>4d} reguler {section.tally[1]:>3d} fakultatif{flag}')
    off = [s.name for s in counted if s.tally != s.claimed]
    if off:
        raise SystemExit(f'sections disagreeing with their own banner: {off}')

    corridors, pairs = read_network(pages)
    codes = sorted({code for c in corridors for code, _ in c.stations}
                   | {code for pair in pairs for code in pair[:2]})
    relasi = {(t['relasi'][0], t['relasi'][1], t['via']) for t in trains}
    print(f'\n{len(corridors)} corridors, {len(pairs)} inline pairs, '
          f'{len(codes)} station codes, {len(relasi)} distinct relasi')
    guessed = sorted(s.name for s in counted if s.name not in SECTION_CATEGORIES)
    if guessed:
        print(f'  !! sections whose category had to be guessed at: {guessed}')

    (OUT / 'trains.json').write_text(json.dumps({
        'trains': trains,
        'sections': [{'name': s.name, 'category': s.category,
                      'klasifikasi': s.klasifikasi, 'page': s.page,
                      'reguler': s.reguler, 'fakultatif': s.fakultatif,
                      'rows': len(s.trains)} for s in sections],
    }, separators=(',', ':')), encoding='utf-8')
    (OUT / 'network.json').write_text(json.dumps({
        'corridors': [{'name': c.name, 'stations': [[code, km]
                                                    for code, km in c.stations]}
                      for c in corridors],
        'pairs': [[a, b, km] for a, b, km in pairs],
        'codes': codes,
    }, separators=(',', ':')), encoding='utf-8')
    for name in ('trains.json', 'network.json'):
        path = OUT / name
        print(f'  -> {path.relative_to(ROOT)} ({path.stat().st_size / 1e3:.0f} kB)')

    if (len(trains), len(counted), len(corridors), len(codes)) != \
            (TRAINS, SECTIONS, CORRIDORS, CODES):
        raise SystemExit(
            f'expected {TRAINS} trains in {SECTIONS} sections and {CORRIDORS} '
            f'corridors over {CODES} codes; got {len(trains)}, {len(counted)}, '
            f'{len(corridors)}, {len(codes)}')


if __name__ == '__main__':
    main()
