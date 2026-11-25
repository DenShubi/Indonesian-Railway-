"""Read GAPEKA 2026 from its committed cache, and keep what it says.

GAPEKA 2026 (decree KP-DJKA 116/2026, valid from 1 December 2026) is the
source for every train on Java. Its 61 MB PDF is not in the repository:
scripts/cache_gapeka_2026.py extracts it once, by hand, into
data/gapeka/2026/pages.json (page text) and words.json (the word coordinates
of the twelve distance-table pages), and this script reads only those. Three
files come out of it:

  timetables.json  2,089 timetabled runs, one record per run:
                   {no, service, origin, destination,
                    rows: [[code, name, max_kmh, arr, dep, kind, note]]}
                   times as printed, in seconds from midnight, rolled past
                   86,400 where a run crosses midnight, null where a row
                   prints none. Estimated times are not stored: they need
                   routed distances, which only exist at bundle time.
  trains.json      the register, pages 1828-1863: 1,815 trains in nineteen
                   sections, each with its category and the timetabled runs
                   that make it up
  network.json     the distance tables, pages 1875-1886: 37 corridors, each
                   with the edition and page it was read from, and 6 inline
                   branch pairs

The register and the distance tables are no longer sources of times; they are
the independent checks on distance. Two corrections are applied to the 2026
tables, both named in tables.py with their evidence: Benteng's BET is read as
SBE (ALIASES_2026), and the Tegal - Cepu main line, whose matrix page 1880
does not print, is carried forward from 2025 (CARRIED_2026). The Wates /
Kedundang transposition is corrected in 2026 as it was in 2025 (ERRATA_2026).

GAPEKA 2025, "Train Timetables/GAPEKA Jadwal Kereta.pdf" (KP-DJKA 224/2024), is
read for that carried corridor only. Its cache, data/gapeka/2025/pages.json,
is committed; --force re-extracts it from the PDF, which takes about half a
minute and writes the same 656 kB byte for byte. That cache keeps word
coordinates only for its matrix pages, the only pages any parser reads them on.

Which pages hold what is read off the document rather than hardcoded, except
the distance tables' twelve pages, which are the only pages words.json holds:
a train section starts at a "KELAS KERETA API" banner, so rows.scan_sections()
finds the register wherever it is. Inline branch pairs ("KEN-CGD 6,439") are
taken only from distance-table pages, because the register's duty rosters
put a station pair next to a distance in every row -- "R1100 ... KRL DP-BOO
22,126" -- and reading those as branches would wire Solo to Yogyakarta direct.

Every count below is asserted before anything is written, so a parse that went
wrong leaves the last good files in place.

Usage:  python scripts/parse_gapeka.py [--force]
"""
import json
import pathlib
import sys

import networkx as nx

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from gapeka.rows import (SECTION_CATEGORIES, banner_disagreements,   # noqa: E402
                         match_runs, scan_sections)
from gapeka.tables import (ALIASES_2026, ERRATA, ERRATA_2026,        # noqa: E402
                           apply_errata, carry_forward, compare_editions,
                           parse_corridor_block, parse_inline_pairs,
                           parse_matrix_rows, recover_vertical_codes)
from gapeka.timetables import DAY, KINDS, parse_runs, run_record     # noqa: E402
from gapeka.topology import JUNCTIONS, build_topology, station       # noqa: E402

OUT = ROOT / 'data' / 'gapeka'
PDF_2025 = ROOT / 'Train Timetables' / 'GAPEKA Jadwal Kereta.pdf'
PAGES_2025 = OUT / '2025' / 'pages.json'
PAGES_2026 = OUT / '2026' / 'pages.json'
WORDS_2026 = OUT / '2026' / 'words.json'

# What GAPEKA 2026 holds. Asserted rather than merely printed: the page roles
# are discovered, so a discovery that goes wrong has to fail loudly instead of
# quietly writing less for the rest of the pipeline to build on. The timetable
# parser cross-checks each run's numbering and ends itself; these catch a cache
# that has lost or gained pages.
RUNS = 2089
ROWS = 48685
TIMETABLE_CODES = 466
TRAINS = 1815
SECTIONS = 19
CORRIDORS = 37                  # 36 printed, 1 carried forward from 2025
NETWORK_CODES = 396
# The register rows no timetable belongs to: the four empty-stock moves round
# Sidotopo, Barang Dinas (EJEK), which no passenger rides and nobody draws.
UNTIMETABLED = ['R951', 'R952', 'R953', 'R954']


def extract_2025(path: pathlib.Path) -> dict[str, dict]:
    """Every page of the 2025 register as {"<page>": {"text", "words"?}}."""
    import pdfplumber           # only --force needs it
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


def read_2025(force: bool) -> dict[str, dict]:
    """The cached 2025 extraction, extracting it first if asked to."""
    if PAGES_2025.exists() and not force:
        return json.loads(PAGES_2025.read_text(encoding='utf-8'))
    if not PDF_2025.exists():
        raise SystemExit(f'missing {PDF_2025.relative_to(ROOT)}')
    print(f'extracting {PDF_2025.name}...')
    pages = extract_2025(PDF_2025)
    PAGES_2025.parent.mkdir(parents=True, exist_ok=True)
    PAGES_2025.write_text(json.dumps(pages, separators=(',', ':')), encoding='utf-8')
    print(f'  -> {PAGES_2025.relative_to(ROOT)} ({PAGES_2025.stat().st_size / 1e6:.1f} MB)')
    return pages


def read_2026() -> tuple[dict[str, str], dict[str, list]]:
    for path in (PAGES_2026, WORDS_2026):
        if not path.exists():
            raise SystemExit(f'missing {path.relative_to(ROOT)} - run '
                             f'scripts/cache_gapeka_2026.py <pdf> first')
    return (json.loads(PAGES_2026.read_text(encoding='utf-8')),
            json.loads(WORDS_2026.read_text(encoding='utf-8')))


def _text(page) -> str:
    return page if isinstance(page, str) else page['text']


def read_network(pages: dict, words: dict | None = None, errata=ERRATA,
                 aliases=(), edition: str = '2025') -> tuple[list, list]:
    """The corridor chains and inline branch pairs, from the matrix pages.

    `pages` is either cache shape; `words` is 2026's separate words.json, and
    when it is left out each page's own "words" are read, as 2025 caches them.
    Each corridor's `source` names the edition and page it was read from.

    The known misprints are corrected after parsing, by tables.apply_errata(),
    so that the parse reads what the page prints and the correction is one
    named table rather than a special case inside a parser. An alias whose
    printed code no matrix row carries raises ValueError: it is out of date.
    """
    alias = {a.printed: a.code for a in aliases}
    corridors, pairs, printed = [], [], set()
    for page in sorted(pages, key=int):
        lines = [line for line in _text(pages[page]).split('\n') if line.strip()]
        rows = [row for line in lines for row in parse_matrix_rows(line)]
        if not rows:
            continue
        printed |= {row.code for row in rows}
        found = words.get(page, []) if words is not None else pages[page].get('words', [])
        for corridor in parse_corridor_block(
                lines, recover_vertical_codes(found, int(page)), alias):
            corridors.append(type(corridor)(corridor.name, corridor.stations,
                                            f'GAPEKA {edition} page {page}'))
        for line in lines:
            pairs.extend((alias.get(a, a), alias.get(b, b), km)
                         for a, b, km in parse_inline_pairs(line))
    stale = sorted(a.printed for a in aliases if a.printed not in printed)
    if stale:
        raise ValueError(f'aliases for codes no matrix row prints: {stale}')
    return apply_errata(corridors, errata), pairs


def recovered_pages(pages: dict, words: dict) -> dict[str, dict[int, str]]:
    """Each page on which vertical-text recovery found codes, and what it found."""
    out = {}
    for page in sorted(words, key=int):
        codes = recover_vertical_codes(words[page], int(page))
        if codes:
            out[page] = codes
    return out


def network_2026(pages: dict, words: dict, pages_2025: dict) -> tuple[list, list]:
    """2026's corridors with the carried one added, and its inline pairs."""
    tables = {page: pages[page] for page in words}
    printed, pairs = read_network(tables, words, ERRATA_2026, ALIASES_2026, '2026')
    previous, _ = read_network(pages_2025)
    return carry_forward(printed, previous), pairs


def timetables(pages: dict) -> list:
    runs = parse_runs(pages)
    rows = [row for run in runs for row in run.rows]
    codes = {row.code for row in rows}
    print(f'{len(runs)} timetabled runs, {len(rows)} station rows, {len(codes)} codes')
    for kind in KINDS:
        print(f'  {kind:<13s} {sum(1 for row in rows if row.kind == kind):>6d}')

    def printed(run):
        return [t for row in run.rows for t in (row.arr, row.dep) if t is not None]

    def span(run):
        return printed(run)[-1] - printed(run)[0]
    longest = max(runs, key=span)
    crossing = sum(1 for run in runs if printed(run)[-1] >= DAY)
    print(f'  {crossing} runs cross midnight; the longest, KA {longest.no} '
          f'{longest.service}, takes {span(longest) // 3600} h {span(longest) % 3600 // 60} min')
    if (len(runs), len(rows), len(codes)) != (RUNS, ROWS, TIMETABLE_CODES):
        raise SystemExit(f'expected {RUNS} runs, {ROWS} rows and {TIMETABLE_CODES} '
                         f'codes; got {len(runs)}, {len(rows)}, {len(codes)}')
    return runs


def register(pages: dict, runs: list) -> tuple[list, list]:
    """The register's trains, each with its runs, and its sections."""
    sections = scan_sections(pages)
    counted = [s for s in sections if s.trains]
    duty = [s for s in sections if not s.trains]
    print(f'\n{sum(len(s.trains) for s in counted)} trains in {len(counted)} sections '
          f'({len(duty)} duty-roster sections hold no train rows)')
    for s in counted:
        note = '' if s.tally == s.claimed else \
            f'   banner says {s.claimed[0]}/{s.claimed[1]} (BANNER_ERRATA)'
        print(f'  p{s.page:<4d} {s.name:<30s} {s.category:<24s}'
              f' {s.tally[0]:>4d} reguler {s.tally[1]:>3d} fakultatif{note}')
    off = banner_disagreements(sections)
    if off:
        raise SystemExit(f'sections disagreeing with their own printed counts: {off}')
    guessed = sorted(s.name for s in counted if s.name not in SECTION_CATEGORIES)
    if guessed:
        raise SystemExit(f'sections with no category in SECTION_CATEGORIES: {guessed}')

    trains = [dict(t, category=s.category, section=s.name) for s in counted for t in s.trains]
    belongs = match_runs(runs, [t['no'] for t in trains])
    orphans = [run.no for run in runs if run.no not in belongs]
    if orphans:
        # None in 2026. A run with no register row has no category but the
        # one its timetable section implies, and choosing that is a decision
        # for a person, not a default for this script.
        raise SystemExit(f'timetabled runs with no register row: {orphans}')
    legs: dict[str, list[str]] = {}
    for run in runs:
        legs.setdefault(belongs[run.no], []).append(run.no)
    for train in trains:
        train['runs'] = legs.get(train['no'], [])
    untimed = sorted(t['no'] for t in trains if not t['runs'])
    print(f'  {len(runs)} runs belong to {len(legs)} register rows; '
          f'{len(untimed)} rows have no timetable: {untimed}')
    if (len(trains), len(counted), untimed) != (TRAINS, SECTIONS, UNTIMETABLED):
        raise SystemExit(f'expected {TRAINS} trains in {SECTIONS} sections, untimetabled '
                         f'{UNTIMETABLED}; got {len(trains)}, {len(counted)}, {untimed}')
    return trains, sections


def network(pages: dict, words: dict, pages_2025: dict) -> tuple[list, list, list]:
    recovered = recovered_pages(pages, words)
    print(f'\nvertical-text recovery: '
          f'{"needed on pages " + str(sorted(recovered)) if recovered else "needed on no page"}')
    corridors, pairs = network_2026(pages, words, pages_2025)
    previous, _ = read_network(pages_2025)
    changed = {name: diff for name, diff in compare_editions(corridors, previous).items()
               if diff}
    codes = sorted({code for c in corridors for code, _ in c.stations}
                   | {code for pair in pairs for code in pair[:2]})
    print(f'{len(corridors)} corridors, {len(pairs)} inline pairs, {len(codes)} codes')
    for c in corridors:
        print(f'  {c.name:<40s} {len(c.stations):>3d} stations  {c.source}')
    for name, diff in changed.items():
        print(f'  changed since 2025: {name}: {diff}')
    graph = build_topology(corridors, pairs, JUNCTIONS)
    if graph.graph['conflicts']:
        raise SystemExit(f'edges measured two ways: {graph.graph["conflicts"]}')
    if nx.number_connected_components(graph) != 1:
        raise SystemExit(f'the network falls into {nx.number_connected_components(graph)} '
                         f'pieces')
    if (len(corridors), len(codes)) != (CORRIDORS, NETWORK_CODES):
        raise SystemExit(f'expected {CORRIDORS} corridors over {NETWORK_CODES} codes; '
                         f'got {len(corridors)}, {len(codes)}')
    print(f'  one graph: {len({station(n) for n in graph})} stations, '
          f'{graph.number_of_edges()} edges, junctions split at '
          f'{", ".join(s.code for s in graph.graph["splits"])}')
    return corridors, pairs, codes


def main() -> None:
    force = '--force' in sys.argv[1:]
    pages, words = read_2026()
    pages_2025 = read_2025(force)
    runs = timetables(pages)
    trains, sections = register(pages, runs)
    corridors, pairs, codes = network(pages, words, pages_2025)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'timetables.json').write_text(json.dumps(
        {'runs': [run_record(run) for run in runs]}, separators=(',', ':')),
        encoding='utf-8')
    (OUT / 'trains.json').write_text(json.dumps({
        'trains': trains,
        'sections': [{'name': s.name, 'category': s.category,
                      'klasifikasi': s.klasifikasi, 'page': s.page,
                      'reguler': s.reguler, 'fakultatif': s.fakultatif,
                      'rows': len(s.trains)} for s in sections],
    }, separators=(',', ':')), encoding='utf-8')
    (OUT / 'network.json').write_text(json.dumps({
        'corridors': [{'name': c.name, 'source': c.source,
                       'stations': [[code, km] for code, km in c.stations]}
                      for c in corridors],
        'pairs': [[a, b, km] for a, b, km in pairs],
        'codes': codes,
    }, separators=(',', ':')), encoding='utf-8')
    print()
    for name in ('timetables.json', 'trains.json', 'network.json'):
        path = OUT / name
        print(f'  -> {path.relative_to(ROOT)} ({path.stat().st_size / 1e3:.0f} kB)')


if __name__ == '__main__':
    main()
