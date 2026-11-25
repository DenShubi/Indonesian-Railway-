"""Parse the register's train rows: every train on Java, one line of text each.

Pages 4-31 of the register are the train tables. A row prints, in this order:
sequence number within its section, train number, REGULER or FAKULTATIF, the
service name, the service name a second time (the "NAMA IDENTITAS" column
repeats it), that identity's number, the relasi, the operator, the distance in
km, the same distance rounded to a whole number, departure, arrival, and the
duration as HH.MM. 1,775 rows parse this way.

GAPEKA 2026 prints its register on pages 1828-1863 in the same layout: 1,815
rows in nineteen train sections, every one tallying with its banner, its
JUMLAH line and its footer, which also prints the section's km to the metre.
Three things differ from 2025 and are handled where they bite: times drop
their seconds, counts and the rounded km group thousands with ".", and the
identity column is not always spelled as the name column is. One banner
contradicts its own rows; see BANNER_ERRATA.

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
# Proven against both registers: this matches all 1,775 rows of 2025 and all
# 1,815 of 2026, and nothing else. 2026 prints times without their seconds
# ("08:15"), and its rounded km groups thousands like any other number: the six
# runs over 1,000 km print "1.002,375 1.002", so km_int is [\d.]+, not \d+ --
# with \d+ those six rows, Sangkuriang, Blambangan and Ketandan, vanish.
TIME = r'\d{2}:\d{2}(?::\d{2})?'
ROW = re.compile(
    r'^(\d+)\s+(\S+)\s+(REGULER|FAKULTATIF)\s+(.+?)\s+(\d+)\s+(.+?)\s+(PT\.\s*\w+)\s+'
    rf'([\d.,]+)\s+([\d.]+)\s+({TIME})\s+({TIME})\s+([\d.]+)\s*$')

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

    Split it only where the two halves name the same thing; a cell that is not
    a doubling is a row this parser has not seen, and silently keeping part of
    it would invent a service name. 2026 does not always spell the identity
    column exactly as the name column: "Commuter Line BST Commuter Line Bst"
    (68 rows), "Bandara SMO Bandara Smo" (10) and "Sri Tanjung Sritanjung"
    (2). So the halves are compared ignoring case and spaces, and the first --
    the NAMA KERETA API column -- is the one kept.
    """
    words = cell.split()
    for at in range(1, len(words)):
        if ''.join(words[:at]).lower() == ''.join(words[at:]).lower():
            return ' '.join(words[:at])
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
# to tally with what the banner claims, and over the 2025 edition all eighteen
# train sections do, 1,775 rows in total.
#
# Counts group thousands with "." like every other number in the register.
# 2026's Commuter Line Daop 1 Jak claims "REGULER : 1.055 FAKULTATIF : 24": a
# banner pattern of \d+ misses it, and with it 1,079 trains. The 1,274 the
# 2026 banners first seemed to claim was every banner but that one: 736 in
# the train sections and 538 in the duty rosters. Read whole, the nineteen
# train sections claim 1,815, which is exactly the rows under them.
BANNER = re.compile(r'KELAS KERETA API\s*:\s*(.+?)'
                    r'\s+REGULER\s*:\s*([\d.]+)\s+FAKULTATIF\s*:\s*([\d.]+)\s*$')
# The line under each banner, "WILAYAH : JAWA JUMLAH : 70": the section's total.
JUMLAH = re.compile(r'^WILAYAH\s*:.*\bJUMLAH\s*:\s*([\d.]+)\s*$')
# The line closing each section, "70 JUMLAH KERETA API DAN KM-KERETA API
# 2.907,470 2.907": its row count again, then the sum of its rows' km.
FOOTER = re.compile(r'^(\d+)\s+JUMLAH KERETA API DAN K\S*-KERETA API\s+([\d.,]+)\s+[\d.]+\s*$')
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
    # 2026 renames one section and adds two. Lokal Ekonomi is 2025's Ekonomi
    # Lokal, the same 150 trains. Barang Ternak (livestock) is the two Ketandan
    # runs, Surabaya Pasarturi to Ketapang. Barang Dinas (EJEK) is the four
    # empty-stock moves R951-R954 round Sidotopo, which have no timetable and
    # are not drawn; they keep a category of their own rather than borrow
    # freight's colour.
    'LOKAL EKONOMI': 'Ekonomi Lokal',
    'BARANG TERNAK': 'Barang',
    'BARANG DINAS (EJEK)': 'Barang Dinas',
}


@dataclass(frozen=True)
class Section:
    """One "KELAS KERETA API" section of the register, with its rows.

    `name` is the banner's own wording; `category` is what that collapses to.
    `reguler` and `fakultatif` are what the banner CLAIMS, so comparing them
    against `trains` is the check, not a restatement of it. `jumlah` is the
    total the line under the banner prints, and `footer_rows` and `footer_km`
    the row count and km sum the section's closing line prints -- each None
    when the register prints no such line for the section.
    """
    name: str
    category: str
    klasifikasi: str
    page: int
    reguler: int
    fakultatif: int
    trains: tuple[dict, ...]
    jumlah: int | None = None
    footer_rows: int | None = None
    footer_km: float | None = None

    @property
    def tally(self) -> tuple[int, int]:
        """The REGULER and FAKULTATIF rows actually found in this section."""
        return (sum(1 for t in self.trains if t['jenis'] == 'REGULER'),
                sum(1 for t in self.trains if t['jenis'] == 'FAKULTATIF'))

    @property
    def claimed(self) -> tuple[int, int]:
        return (self.reguler, self.fakultatif)


@dataclass(frozen=True)
class BannerErratum:
    """A banner whose REGULER/FAKULTATIF split its own rows contradict.

    `printed` is what the banner claims and `rows` what the rows under it are.
    Every other count the register prints for the section has to agree with
    the rows, so an erratum is only ever about the split, never the total.
    """
    page: int
    section: str
    printed: tuple[int, int]
    rows: tuple[int, int]


BANNER_ERRATA = (
    # Page 1837 claims "REGULER : 70 FAKULTATIF : 0" for Commuter Line Bandara
    # Soetta, but six of its 70 rows print FAKULTATIF: 805F-806F, 807F-808F,
    # 925F-926F, 927F-928F, 933F-934F and 935F-936F. The rows are right
    # and the banner is not:
    #   * the total agrees everywhere -- the banner's 70 + 0, the "JUMLAH : 70"
    #     beneath it, the "70 JUMLAH KERETA API" footer and the 70 rows;
    #   * every one of the six carries the "F" suffix, and over all 1,815 rows
    #     of the 2026 register a number carries an F exactly when its row says
    #     FAKULTATIF -- 101 of 101, and 1,714 REGULER rows without one.
    BannerErratum(1837, 'COMMUTER LINE BANDARA SOETTA', (70, 0), (64, 6)),
)


def banner_disagreements(sections: list[Section],
                         errata: tuple[BannerErratum, ...] = BANNER_ERRATA) -> list[str]:
    """The train sections whose rows do not tally with their own printed counts.

    A section tallies when its rows meet the banner's REGULER and FAKULTATIF
    counts, the JUMLAH and footer counts where it prints them, and the km sum
    its footer prints, to the metre. A section
    an erratum names tallies only if its banner prints exactly the erratum's
    `printed` split and its rows exactly its `rows` split, and every total
    agrees: the erratum explains one known disagreement, not any.

    Raises ValueError for an erratum whose section is not there, or not once,
    or whose banner and rows have changed under it: it would then be excusing
    a disagreement nobody has looked at.
    """
    by_name: dict[str, list[Section]] = {}
    for section in sections:
        by_name.setdefault(section.name, []).append(section)
    excused = {}
    for erratum in errata:
        found = by_name.get(erratum.section, [])
        if len(found) != 1:
            raise ValueError(f'banner erratum for page {erratum.page}: expected one '
                             f'section {erratum.section!r}, found {len(found)}')
        section, = found
        if (section.claimed, section.tally) != (erratum.printed, erratum.rows):
            raise ValueError(f'banner erratum for page {erratum.page}: '
                             f'{erratum.section} claims {section.claimed} over rows '
                             f'{section.tally}, not the {erratum.printed} over '
                             f'{erratum.rows} it explains')
        excused[erratum.section] = erratum
    off = []
    for section in sections:
        if not section.trains:
            continue
        rows = len(section.trains)
        totals = [sum(section.claimed)] + [n for n in (section.jumlah, section.footer_rows)
                                           if n is not None]
        split_ok = section.tally == section.claimed or section.name in excused
        km = sum(t['km'] for t in section.trains)
        km_ok = section.footer_km is None or abs(km - section.footer_km) < 0.0005
        if not split_ok or not km_ok or any(n != rows for n in totals):
            off.append(section.name)
    return off


def scan_sections(pages: dict) -> list[Section]:
    """Every section of the register, in print order, with the rows under it.

    `pages` is a cached extraction: page index as a string -> its text, either
    as {"text": ...} (the 2025 cache, data/gapeka/2025/pages.json) or as the
    text itself (the 2026 cache, data/gapeka/2026/pages.json). Pages are walked
    in page order and lines in print order, so a section runs from its banner
    to the next one wherever the page happens to break -- which is the whole
    point of reading the banner instead of mapping pages to categories.

    The register's last pages are duty rosters, and they carry banners of the
    same shape. Their rows print no NAMA IDENTITAS column, so parse_train_row()
    does not match them and those sections come back with no trains and a count
    they do not meet. That is the honest answer: they are not trains. A caller
    that wants only the trains takes the sections that have some, and the
    movements the DINAS banners claim -- 464 in 2025, 538 in 2026 -- stay out.

    Raises ValueError for a train row above the first banner, which would mean
    a layout where the category of a row cannot be known.
    """
    found: list[dict] = []
    klasifikasi = ''
    for page in sorted(pages, key=int):
        text = pages[page] if isinstance(pages[page], str) else pages[page]['text']
        for line in text.split('\n'):
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
                    'reguler': _count(banner.group(2)),
                    'fakultatif': _count(banner.group(3)),
                    'trains': [],
                })
                continue
            total = JUMLAH.match(line.strip())
            if total and found and found[-1]['trains'] == [] \
                    and 'jumlah' not in found[-1]:
                found[-1]['jumlah'] = _count(total.group(1))
                continue
            footer = FOOTER.match(line.strip())
            if footer and found and 'footer_rows' not in found[-1]:
                found[-1]['footer_rows'] = int(footer.group(1))
                found[-1]['footer_km'] = float(
                    footer.group(2).replace('.', '').replace(',', '.'))
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


def _count(text: str) -> int:
    """A register count, thousands grouped with ".": "1.055" is 1055."""
    return int(text.replace('.', ''))


def scan_categories(pages: dict) -> dict[str, str]:
    """Train number -> category, taken from the banner above each row.

    This is what `category_for_page` should have been. All 1,775 train numbers
    in the 2025 edition are distinct, and all 1,815 in 2026, including the
    paired ones the register prints as a single cell ("2501-2504-2505-2508"),
    so nothing collapses.
    """
    return {train['no']: section.category
            for section in scan_sections(pages)
            for train in section.trains}


def match_runs(runs, register) -> dict[str, str]:
    """Timetabled run number -> the register number it belongs to.

    GAPEKA 2026 prints a timetable per run, and a register row per train, and
    a train may be several runs: register row "32-33" is KA 32 Gambir to
    Yogyakarta and KA 33 onward. So a run belongs to the register number that
    IS its number, or that has its number as one of the parts between the
    dashes -- whole parts only, so run 3 is not claimed by "32-33".

    `runs` is any iterable of objects with a `.no` (timetables.Run), and
    `register` any iterable of register numbers (a dict of rows keyed on them
    will do). A run that belongs to no register row is left out of the result,
    for the caller to list; a run two register numbers would both claim raises
    ValueError, because which train it is would then be a guess.
    """
    claims: dict[str, list[str]] = {}
    for no in register:
        for part in {no, *no.split('-')}:
            claims.setdefault(part, []).append(no)
    out = {}
    for run in runs:
        found = sorted(set(claims.get(run.no, [])))
        if len(found) > 1:
            raise ValueError(f'run {run.no} belongs to register rows {found}')
        if found:
            out[run.no] = found[0]
    return out
