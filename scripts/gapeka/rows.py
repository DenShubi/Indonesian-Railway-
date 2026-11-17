"""Parse the register's train rows: every train on Java, one line of text each.

Pages 4-31 of the register are the train tables. A row prints, in this order:
sequence number within its section, train number, REGULER or FAKULTATIF, the
service name, the service name a second time (the "NAMA IDENTITAS" column
repeats it), that identity's number, the relasi, the operator, the distance in
km, the same distance rounded to a whole number, departure, arrival, and the
duration as HH.MM. 1,775 rows parse this way.

Two things the layout does that a reader's eye fixes silently:

  * the service name arrives doubled, because two adjacent columns hold the same
    text and extract_text() runs them together. Halving it is only safe when the
    cell really is one name twice, so the halves are compared before trusting it.
  * a relasi naming intermediate points is printed with spaces around its dashes
    ("GMR - SBI - JR") where a plain origin-destination pair has none
    ("SBI-GMR") -- and one row, Sancaka Utara 236F, has it both ways in the same
    cell ("CP - SLO -GBN - SBI"). So the split is on a dash with optional space
    either side, not on " - ".

Distances are Indonesian-formatted: "," is the decimal point, so "720,109" is
720.109 km. A "." would group thousands, and the code strips it, but no row in
this edition needs it -- the longest run prints "1030,306", not "1.030,306".

Times are left as the register prints them, HH:MM truncated from HH:MM:SS; every
time cell in the register ends ":00", so nothing is lost. `duration` is the
authoritative elapsed time, and it is HH.MM, NOT a decimal: "26.50" is 26 h
50 min, not 26.5 h. Reach for it rather than subtracting the two clock times,
because one row needs it -- Kenlimas Cargo 2501-2504-2505-2508 runs 23:25 to
02:15 over 26 h 50 min, so the obvious "arrival before departure means add a
day" rule puts it 24 h short. It is the only run over 24 h in this edition, and
the only row where that rule and `duration` disagree.

A relasi is identified by `relasi` AND `via`, never `relasi` alone: there are
316 distinct (relasi, via) combinations but only 304 distinct origin-destination
pairs, so twelve differ by via point only. 32 rows are circular, with
origin == destination -- the Dhoho and Penataran runs out of Surabaya, the
circular Cikarang workings, and Joglosemarkerto.

A train's CATEGORY comes from the section banner above its row, which
scan_sections() walks to. See the note on SECTIONS below for why a page map
cannot do it.
"""
import re
from dataclasses import dataclass

# urut, no, jenis, nama(+identitas), ident, lintas, operator, km, km_int, dep, arr, duration
# Proven against the whole register: this matches all 1,775 rows and nothing else.
ROW = re.compile(
    r'^(\d+)\s+(\S+)\s+(REGULER|FAKULTATIF)\s+(.+?)\s+(\d+)\s+(.+?)\s+(PT\.\s*\w+)\s+'
    r'([\d.,]+)\s+(\d+)\s+(\d{2}:\d{2}:\d{2})\s+(\d{2}:\d{2}:\d{2})\s+([\d.]+)\s*$')

DASH = re.compile(r'\s*-\s*')

# The register's sections in print order, each with the page its first row is on,
# from the table of contents on page 1 and the "KELAS KERETA API" banner each
# section carries. The seven freight sections on pages 29-31 collapse to one
# category; the spec treats freight as a single class.
#
# SUPERSEDED by scan_categories(), which switches category at each section's
# "KELAS KERETA API" banner instead. Do not wire category_for_page() into
# anything: a page is not a clean category boundary, because a page can hold the
# end of one section and the start of the next, and measured against the banners
# 232 of the 1,775 rows -- 13%, across twelve section pairs -- come out in a
# sibling's category. Category drives the line panel's groups and the track
# colour priority, so that is not a rounding error. Kept, unused, only so the
# task that introduced it stays closed.
SECTIONS = [
    (4, 'Argo'),
    (4, 'Eksekutif'),
    (5, 'Eksekutif Campuran'),
    (7, 'Ekonomi Jarak Jauh'),
    (8, 'Ekonomi Lokal'),
    (10, 'Bandara YIA'),
    (11, 'Bandara SMO'),
    (11, 'Ekonomi Lokal (Feeder)'),
    (12, 'Commuter Line Daop 6 YK'),
    (13, 'Commuter Line Bandara Soetta'),
    (14, 'Commuter Line Daop 1 Jak'),
    (29, 'Barang'),
]
LAST_ROW_PAGE = 31      # page 32 starts the stock and crew diagrams


def _categories() -> dict[int, str]:
    out = {}
    for page, name in SECTIONS:
        out.setdefault(page, name)
    for page in range(SECTIONS[0][0] + 1, LAST_ROW_PAGE + 1):
        out.setdefault(page, out[page - 1])
    return out


CATEGORIES = _categories()


def category_for_page(page: int) -> str:
    """The register section a train row on this page belongs to."""
    return CATEGORIES[page]


def _service(cell: str) -> str:
    """The service name, from the cell that holds it twice.

    Halve it only if the halves agree; a cell that is not a clean doubling is a
    row this parser has not seen, and silently keeping its first half would
    invent a service name.
    """
    words = cell.split()
    half = len(words) // 2
    if len(words) % 2 == 0 and words[:half] == words[half:]:
        return ' '.join(words[:half])
    return ' '.join(words)


def parse_train_row(line: str) -> dict | None:
    """One register train, or None when the line is not a train row."""
    m = ROW.match(line.strip())
    if not m:
        return None
    _, no, jenis, name, ident, relasi, operator, km, _, dep, arr, duration = m.groups()
    stops = [s for s in DASH.split(relasi.strip()) if s]
    return {
        'no': no,
        'jenis': jenis,
        'service': _service(name),
        'ident': ident,
        'relasi': (stops[0], stops[-1]),
        'via': tuple(stops[1:-1]),
        'operator': ' '.join(operator.split()),
        'km': float(km.replace('.', '').replace(',', '.')),
        'dep': dep[:5],
        'arr': arr[:5],
        'duration': duration,
    }


# The banner the register prints above every section: the section's own name,
# and how many REGULER and FAKULTATIF trains it contains. Both counts are a
# free end-to-end check -- the rows walked between one banner and the next have
# to tally with what the banner claims, and over this edition all eighteen
# train sections do, 1,775 rows in total.
BANNER = re.compile(r'KELAS KERETA API\s*:\s*(.+?)'
                    r'\s+REGULER\s*:\s*(\d+)\s+FAKULTATIF\s*:\s*(\d+)\s*$')
# The line above each banner, which says what KIND of working the section
# holds: ANTAR KOTA (intercity), PERKOTAAN (urban) or DINAS (duty roster).
KLASIFIKASI = re.compile(r'KLASIFIKASI KERETA API\s*:\s*KERETA API\s+(.+?)\s*$')

# Section name -> the category the app groups and colours by. The seven freight
# sections collapse to one: the spec treats freight as a single class, and the
# commodity a wagon carries is not a thing the map can show. Everything else
# keeps its own name, spelled as the register's contents page spells it.
#
# A section this map has not seen is title-cased rather than refused, so a
# re-typeset register still parses; the CLI prints any section it had to guess
# at, because an unknown category is one the line panel has no colour for.
SECTION_CATEGORIES = {
    'ARGO': 'Argo',
    'EKSEKUTIF': 'Eksekutif',
    'EKSEKUTIF CAMPURAN': 'Eksekutif Campuran',
    'EKONOMI JARAK JAUH': 'Ekonomi Jarak Jauh',
    'EKONOMI LOKAL': 'Ekonomi Lokal',
    'BANDARA YIA': 'Bandara YIA',
    'BANDARA SMO': 'Bandara SMO',
    'EKONOMI LOKAL (FEEDER)': 'Ekonomi Lokal (Feeder)',
    'COMMUTER LINE DAOP 6 YK': 'Commuter Line Daop 6 YK',
    'COMMUTER LINE BANDARA SOETTA': 'Commuter Line Bandara Soetta',
    'COMMUTER LINE DAOP 1 JAK': 'Commuter Line Daop 1 Jak',
    'BARANG HANTARAN PARCEL (BHP)': 'Barang',
    'BARANG PETIKEMAS': 'Barang',
    'BARANG BBM': 'Barang',
    'BARANG BATUBARA': 'Barang',
    'BARANG SEMEN': 'Barang',
    'BARANG PUPUK': 'Barang',
    'ANTAR KOTA BARANG': 'Barang',
}


@dataclass(frozen=True)
class Section:
    """One "KELAS KERETA API" section of the register, with its rows.

    `name` is the banner's own wording; `category` is what that collapses to.
    `reguler` and `fakultatif` are what the banner CLAIMS, so comparing them
    against `trains` is the check, not a restatement of it.
    """
    name: str
    category: str
    klasifikasi: str
    page: int
    reguler: int
    fakultatif: int
    trains: tuple[dict, ...]

    @property
    def tally(self) -> tuple[int, int]:
        """The REGULER and FAKULTATIF rows actually found in this section."""
        return (sum(1 for t in self.trains if t['jenis'] == 'REGULER'),
                sum(1 for t in self.trains if t['jenis'] == 'FAKULTATIF'))

    @property
    def claimed(self) -> tuple[int, int]:
        return (self.reguler, self.fakultatif)


def scan_sections(pages: dict[str, dict]) -> list[Section]:
    """Every section of the register, in print order, with the rows under it.

    `pages` is the cached extraction: page index as a string -> {"text": ...},
    which parse_gapeka.py writes to data/gapeka/pages.json. Pages are walked in
    page order and lines in print order, so a section runs from its banner to
    the next one wherever the page happens to break -- which is the whole point
    of reading the banner instead of mapping pages to categories.

    The register's last eight pages are duty rosters, and they carry banners of
    the same shape. Their rows print no NAMA IDENTITAS column, so
    parse_train_row() does not match them and those sections come back with no
    trains and a count they do not meet. That is the honest answer: they are
    not trains. A caller that wants only the trains takes the sections that
    have some, and the 464 duty movements the thirteen DINAS banners claim stay
    out of the 1,775.

    Raises ValueError for a train row above the first banner, which would mean
    a layout where the category of a row cannot be known.
    """
    found: list[dict] = []
    klasifikasi = ''
    for page in sorted(pages, key=int):
        for line in pages[page]['text'].split('\n'):
            marked = KLASIFIKASI.search(line)
            if marked:
                klasifikasi = marked.group(1).strip()
                continue
            banner = BANNER.search(line)
            if banner:
                name = ' '.join(banner.group(1).split())
                found.append({
                    'name': name,
                    'category': SECTION_CATEGORIES.get(name, name.title()),
                    'klasifikasi': klasifikasi,
                    'page': int(page),
                    'reguler': int(banner.group(2)),
                    'fakultatif': int(banner.group(3)),
                    'trains': [],
                })
                continue
            row = parse_train_row(line)
            if row is None:
                continue
            if not found:
                raise ValueError(f'page {page} prints a train row above the '
                                 f'first KELAS KERETA API banner: {line!r}')
            found[-1]['trains'].append(dict(row, page=int(page)))
    return [Section(**dict(section, trains=tuple(section['trains'])))
            for section in found]


def scan_categories(pages: dict[str, dict]) -> dict[str, str]:
    """Train number -> category, taken from the banner above each row.

    This is what `category_for_page` should have been. All 1,775 train numbers
    in this edition are distinct, including the 234 paired ones the register
    prints as a single cell ("2501-2504-2505-2508"), so nothing collapses.
    """
    return {train['no']: section.category
            for section in scan_sections(pages)
            for train in section.trains}
