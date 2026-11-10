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

Distances are Indonesian-formatted: "." groups thousands, "," is the decimal
point, so "720,109" is 720.109 km.

Times are left as the register prints them, HH:MM truncated from HH:MM:SS. An
arrival earlier than its departure means the run crosses midnight; that is the
GTFS layer's problem, not this one's.
"""
import re

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
# Four pages hold the end of one section and the start of the next, so a page is
# not a clean category boundary: the section that starts highest on the page wins
# the page, which is the order the contents page reads them in. The two sections
# that never win one are Eksekutif (it starts halfway down page 4, under Argo)
# and Ekonomi Lokal (Feeder) (under Bandara SMO on page 11); their trains are
# tagged with the sibling that owns the page.
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
