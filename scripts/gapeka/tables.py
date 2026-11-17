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
  * That header is the only line extract_text() truncates; the matrix rows
    themselves are complete. Every row on pages 52-63 carries all n-1 of its
    values, the 42-station Cikampek - Banjar row 1 included. So each row's own
    first value -- d(i,1), its distance to the head -- is the one anchor every
    row carries whatever the header did to itself, and that is where cumulative
    km come from. A numeric token with no comma in it is not a distance and is
    rejected, which is the only thing standing between the vertical-text
    wreckage on page 58 ("LJ BR GL 98 76 25 ,, 15 90 ...") and a station
    called GL at km 76.
  * Two tables are often printed side by side, so one text line holds a row
    from each: "SBE 1 5,740 7,786 9,246 10,176 TRK 1 14,593 22,147". Rows are
    read left to right off the line and handed to their own column, because a
    second "index 1" is a second corridor, not a continuation.
  * Where the page is tightest, adjacent columns run together into one token
    ("104,830117,217120,796"), so a token is read as a run of numbers rather
    than as one.

Numbers are Indonesian-formatted: "." groups thousands, "," is the decimal
point, so "9,241" is 9.241 km and "141,190" is 141.190 km. Most print three
decimals, but page 63 prints some with one or two -- its KTK row says "102,1"
where row 1 of the same matrix says "102,098" for the same cell. So a cell is
matched at the precision the register printed it, within SAME_CELL: page 63's
roundings are at most 5 m wide, and the nearest pair of genuinely different
cells on these pages is 15 m apart, so 10 m of slack separates the two.

Two corridors lose rows to the register's own typesetting: pages 55 and 58 each
print a stretch of one matrix as wrecked vertical text, which takes rows 7 and
8 of Padalarang - Sukabumi and rows 8, 9, 11 and 12 of Banjar - Kroya with it
(row 10, KH at km 77.386, survives in the middle of that hole). Because every
km is measured from the head rather than from the row above, the stations that
do print keep their true distances and the corridor simply has a hole in it;
four station codes -- CBB, LP, JRL, LBG -- are lost with those rows and have to
come from somewhere else. Their km are not lost: they are still in row 1 of
their own matrix, which is why nothing here throws a short chain away.

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

# An Indonesian-formatted distance: thousands grouped with ".", one to three
# decimals after the ",". The "," is required, because the only tokens that
# reach here without one are the loose digits of a vertical-text column.
NUMBER = re.compile(r'\d{1,3}(?:\.\d{3})*,\d{1,3}')
# A station code: the register's are 2-4 characters, all of them upper case.
CODE = re.compile(r'[A-Z][A-Z0-9]{0,4}\Z')
INDEX = re.compile(r'\d{1,2}\Z')
# How far apart two readings of one matrix cell may be and still be that cell.
SAME_CELL = 0.01
# A corridor's route in station codes, as the line above each block prints it.
# A full-name title line can match too -- page 58's "BANJAR - MAOS - KROYA"
# yields "MAOS - KROYA" -- so a route is only taken as a corridor's name when
# both its ends are that corridor's own, which no such accident survives.
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
    stations: tuple[tuple[str, float], ...]


def _km(text: str) -> float:
    """One Indonesian-formatted distance as kilometres."""
    return float(text.replace('.', '').replace(',', '.'))


def _numbers(token: str) -> list[float]:
    """Every distance in a token, which may hold several run together.

    Stops at the first thing that is not one, so the loose digits of a
    vertical-text column end the row rather than joining it.
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
    1 also prints as its (i-1)th value, so the matrix checks itself and the
    closest agreement wins. Splitting on the index alone would not do, because
    two corridors printed side by side interleave as 1, 1, 2, 2, 3, 3 and a cut
    at every index that fails to increase would cut after every row.

    A row that agrees with no corridor's head is not guessed at -- it opens a
    column of its own, which parse_corridor_block() then drops for having no
    head to measure from. Nothing on pages 52-63 lands there: all 450 rows are
    placed by the cross-check.
    """
    columns: list[dict[int, Row]] = []
    for row in rows:
        column = None if row.index == 1 else _column_for(columns, row)
        if column is None:
            columns.append({row.index: row})
        else:
            column[row.index] = row
    return [[column[index] for index in sorted(column)] for column in columns]


def _column_for(columns: list[dict[int, Row]], row: Row) -> dict[int, Row] | None:
    gaps = {}
    for at, column in enumerate(columns):
        head = column.get(1)
        if row.index in column or not head or row.index - 2 >= len(head.values):
            continue
        gap = abs(head.values[row.index - 2] - row.values[0])
        if gap < SAME_CELL:
            gaps[at] = gap
    if not gaps:
        return None
    return columns[min(gaps, key=gaps.get)]


def _routes(lines: list[str]) -> list[str]:
    """The code routes printed above the blocks, in print order.

    A route followed by a distance is an inline pair instead -- a corridor of
    two stations with no matrix of its own -- and belongs to
    parse_inline_pairs(), so it is left out here. What keeps a corridor from
    taking a name that is not its own is _name() matching both ends; this is
    only so that what comes back is a list of routes and nothing else.
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
    on both of its ends rather than on the full-name title lines, which are not
    printed in the same order as the routes and are in the wrong alphabet to
    check. Page 53 prints two corridors that share both ends, JAKK to CKP by
    Pasar Senen and by Manggarai, and only print order tells those apart, so a
    route is claimed once and then spent. A corridor with no route of its own
    -- the Gambringan - Gundih spur on page 57, and Kampung Bandan - Manggarai
    on page 54, whose route runs one station further than its matrix does -- is
    named for its own two ends.

    A group of rows that does not start at index 1 has no head to measure from,
    so there is nothing to anchor its cumulative km to and it is dropped.
    """
    rows = [row for line in lines for row in parse_matrix_rows(line)]
    routes = _routes(lines)
    spent: set[int] = set()
    out = []
    for group in split_side_by_side(rows):
        if len(group) < 2 or group[0].index != 1:
            continue
        stations = tuple((row.code, row.km) for row in group)
        out.append(Corridor(_name(stations, routes, spent), stations))
    return out


def _name(stations: tuple[tuple[str, float], ...], routes: list[str],
          spent: set[int]) -> str:
    head, tail = stations[0][0], stations[-1][0]
    for at, route in enumerate(routes):
        ends = route.split(' - ')
        if at not in spent and ends[0] == head and ends[-1] == tail:
            spent.add(at)
            return route
    return f'{head} - {tail}'
