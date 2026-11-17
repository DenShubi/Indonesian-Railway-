"""Parse the register's JARAK ANTAR STASIUN corridor matrices. No IO.

Pages 52-63 print the official distance between every pair of stations on a
corridor, one symmetric matrix per corridor. A block reads:

    TANAH ABANG - KRENCENG - MERAK          one or more full-name title lines
    THB - KEN - MER                         the same corridor in station codes
    THB PLM KBY PDJ ... KEN MER             the header row of codes, in order
    O/D
    1 2 3 ... 22 23                         the index row
    THB 1 3,191 6,928 ... 141,190           the matrix, one row per station
    PLM 2 3,191 3,737 ... 137,999

The diagonal is not printed, so row *i* holds n-1 values: the distance to every
station but itself, in index order. That makes the FIRST value of row *i* its
distance to station 1 -- its cumulative km from the head of the corridor -- for
every row but the first, where it is d(1,2) instead. Station 1's own cumulative
km is 0, and row 1's first value cross-checks station 2's.

Four things the layout does that make the obvious reading wrong:

  * The header row is unusable on a narrow page. It arrives interleaved with
    the index row, character by character -- page 55 gives
    "O/D C 1KP C 2BR PW 3K C 4A SU 5T ..." for CKP, CBR, PWK, CA, SUT -- and
    the code boundaries are only recoverable from the x coordinates, which
    extract_text() has already thrown away. So the ordered station list comes
    from the matrix ROW LABELS, the first token of each row, which print
    cleanly on every page.
  * The page truncates the right-hand columns, never the left. Row 1 of the
    42-station Cikampek - Banjar matrix runs off the page mid-number, ending in
    a bare "177" that is the head of "177,378". Cumulative km therefore come
    from each row's own first value, and a numeric token that is not a whole
    Indonesian-formatted number is discarded.
  * Two tables are often printed side by side, so one text line holds a row
    from each: "SBE 1 5,740 7,786 9,246 10,176 TRK 1 14,593 22,147". Rows are
    read left to right off the line and handed to their own column, because a
    second "index 1" is a second corridor, not a continuation.
  * Where the page is tightest, adjacent columns run together into one token
    ("104,830117,217120,796"), so a token is read as a run of numbers rather
    than as one.

Numbers are Indonesian-formatted: "." groups thousands, "," is the decimal
point, so "9,241" is 9.241 km and "141,190" is 141.190 km. Most print three
decimals, but page 63 prints some with one or two ("102,1" where row 1 of the
same matrix says "102,098"), which costs a few metres and nothing more.

Two corridors lose rows to the register's own typesetting: pages 55 and 58 each
print a stretch of one matrix as wrecked vertical text, which takes rows 7-8 of
Padalarang - Sukabumi and rows 8-12 of Banjar - Kroya with it. Because every km
is measured from the head rather than from the row above, the stations that do
print keep their true distances and the corridor simply has a hole in it; four
station codes -- CBB, LP, JRL, LBG -- are lost with those rows and have to come
from somewhere else.

The short branches are not printed as matrices at all but as inline pairs, two
codes and a distance tucked onto whatever line had room -- "KEN-CGD 6,439" at
the end of a code route, "TPK-KMO 8,624" at the end of an index row,
"JAKK-TPK 8,115" at the end of a matrix row. parse_inline_pairs() picks those
up; five station codes exist only there.

A junction belongs to several corridors at different cumulative km, because
each corridor measures from its own head: Bandung is at km 89.727 on
Cikampek - Banjar and km 2.729 on Andir - Ciroyom - Bandung. Nothing here
merges or rebases them. That is the topology layer's job, and it needs both
numbers to do it.
"""
import re
from dataclasses import dataclass

# An Indonesian-formatted distance, whole: thousands grouped with ".", three
# decimals at most after the ",". Anything else the page edge chopped in half.
NUMBER = re.compile(r'\d{1,3}(?:\.\d{3})*,\d{1,3}')
# A station code: the register's are 2-4 characters, all of them upper case.
CODE = re.compile(r'[A-Z][A-Z0-9]{0,4}\Z')
INDEX = re.compile(r'\d{1,2}\Z')
# A corridor's route in station codes, as the line above each block prints it.
# Full-name title lines never match: every code is five characters at most, and
# a route needs two of them, so "DURI - TANGERANG" cannot qualify.
ROUTE = re.compile(r'(?<![A-Z0-9])[A-Z][A-Z0-9]{0,4}(?:\s*-\s*[A-Z][A-Z0-9]{0,4})+'
                   r'(?![A-Z0-9])')
# One short branch printed inline, "KEN-CGD 6,439". The distance has to follow
# on the same line for the pair to be a pair; "THB - KEN - MER" is a route.
PAIR = re.compile(r'(?<![A-Z0-9])([A-Z][A-Z0-9]{0,4})\s*-\s*([A-Z][A-Z0-9]{0,4})'
                  r'\s+(\d{1,3}(?:\.\d{3})*,\d{1,3})(?![\d,.])')


@dataclass(frozen=True)
class Row:
    """One matrix row: its station, its index in the corridor, its distances."""
    code: str
    index: int
    values: tuple[float, ...]

    @property
    def km(self) -> float:
        """This station's cumulative km from the head of its corridor."""
        return 0.0 if self.index == 1 else self.values[0]


@dataclass(frozen=True)
class Corridor:
    name: str
    stations: list[tuple[str, float]]


def _km(text: str) -> float:
    """One Indonesian-formatted distance as kilometres."""
    return float(text.replace('.', '').replace(',', '.'))


def _numbers(token: str) -> list[float]:
    """Every whole distance in a token, which may hold several run together.

    Stops at the first thing that is not one, so a number the page edge cut in
    half is dropped rather than read as a smaller distance.
    """
    out, at = [], 0
    while at < len(token):
        match = NUMBER.match(token, at)
        if not match:
            break
        out.append(_km(match.group()))
        at = match.end()
    return out


def parse_matrix_rows(line: str) -> list[Row]:
    """Every matrix row on one line of text, left to right.

    A line usually holds one row, but holds two where the register prints two
    corridors side by side, and none at all for a title, a header, an index row
    or the vertical-text wreckage between blocks. A row is a station code, then
    its index, then at least one distance; the header rows that survive as
    "... PB 7" with nothing after them are rejected on that last count.
    """
    tokens = line.split()
    rows, at = [], 0
    while at < len(tokens):
        if not (CODE.match(tokens[at]) and at + 1 < len(tokens)
                and INDEX.match(tokens[at + 1])):
            at += 1
            continue
        values, end = [], at + 2
        while end < len(tokens):
            found = _numbers(tokens[end])
            if not found:
                break
            values.extend(found)
            end += 1
        if not values:
            at += 1
            continue
        rows.append(Row(tokens[at], int(tokens[at + 1]), tuple(values)))
        at = end
    return rows


def split_side_by_side(rows: list[Row]) -> list[list[Row]]:
    """Group rows read off a page into one list per corridor, in index order.

    An index of 1 opens a corridor. Any other row joins the corridor whose
    first row says where it belongs: row *i*'s first value is d(i,1), which row
    1 also prints as its (i-1)th value, so the matrix checks itself. Where row
    1 ran off the page before reaching that column the check is unavailable,
    and the row falls back to the open corridor it extends -- the one with the
    highest index below its own and a smaller cumulative km.
    """
    columns: list[dict[int, Row]] = []
    for row in rows:
        if row.index == 1:
            columns.append({1: row})
            continue
        column = _column_for(columns, row)
        if column is None:
            columns.append({row.index: row})
        else:
            column[row.index] = row
    return [[column[index] for index in sorted(column)] for column in columns]


def _column_for(columns: list[dict[int, Row]], row: Row) -> dict[int, Row] | None:
    free = [column for column in columns if row.index not in column]
    for column in free:
        head = column.get(1)
        if head and row.index - 2 < len(head.values) \
                and abs(head.values[row.index - 2] - row.values[0]) < 1e-9:
            return column
    extends = [column for column in free
               if max(column) < row.index and column[max(column)].km < row.values[0]]
    return max(extends, key=max) if extends else None


def _routes(lines: list[str]) -> list[str]:
    """The code routes printed above the blocks, in print order.

    A route followed by a distance is an inline pair instead -- a corridor of
    two stations with no matrix of its own -- and belongs to
    parse_inline_pairs(), so it is left out here.
    """
    out = []
    for line in lines:
        for match in ROUTE.finditer(line):
            if not re.match(r'\s*\d{1,3}(?:\.\d{3})*,\d{1,3}', line[match.end():]):
                out.append(re.sub(r'\s*-\s*', ' - ', match.group()))
    return out


def parse_inline_pairs(line: str) -> list[tuple[str, str, float]]:
    """The short branches printed as "CTA-NMO 13,267" rather than as a matrix."""
    return [(m.group(1), m.group(2), _km(m.group(3))) for m in PAIR.finditer(line)]


def parse_corridor_block(lines: list[str]) -> list[Corridor]:
    """The corridors on these lines, which may be one block or a whole page.

    Each corridor is named for the code route printed above its block, matched
    on the head station because the full-name title lines are not printed in
    the same order as the routes and are in the wrong alphabet to check. A
    corridor with no route of its own is named for its own two ends.

    A group of rows that does not start at index 1 has no head to measure from,
    so there is nothing to anchor its cumulative km to and it is dropped.
    """
    rows = [row for line in lines for row in parse_matrix_rows(line)]
    routes = _routes(lines)
    out = []
    for group in split_side_by_side(rows):
        if len(group) < 2 or group[0].index != 1:
            continue
        stations = [(row.code, row.km) for row in group]
        out.append(Corridor(_name(stations, routes), stations))
    return out


def _name(stations: list[tuple[str, float]], routes: list[str]) -> str:
    head, tail = stations[0][0], stations[-1][0]
    for at, route in enumerate(routes):
        if route.split(' - ')[0] == head:
            return routes.pop(at)
    return f'{head} - {tail}'
