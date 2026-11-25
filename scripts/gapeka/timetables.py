"""Parse GAPEKA 2026's station-by-station timetables. No IO.

Pages 52-1672 print one timetable per train, in two sections: intercity
(52-668), headed "KA 1 (Anggrek) Relasi SBI - GMR", and commuter, local,
airport and freight (669-1672), headed "KA 2107 (Commuter Line Tangerang)
Lintas Pelayanan TNG - DU". Beneath the header, one row per station in the
order the train runs:

    1 Surabaya Pasarturi (SBI) 115 - 08:15:00
    2 Tandes (TES) 115 Ls 08:21:00
    35 Semarang Tawang (SMT) 50 11:09:00 11:14:00 // ka 2509 (ka 2509 =)

that is: sequence number, station name, code in brackets, maximum speed in
km/h, arrival, departure, then an optional operational note. A run that does
not fit its page carries on at the top of the next, under a repeated column
heading, with its numbering unbroken.

What fills the two time columns decides the row's kind:

    - T       origin         departs, no arrival
    T -       destination    arrives, no departure
    T T       stop           arrives and departs at printed times
    Ls T      pass           one printed time, the moment it runs through
    Ls -      untimed_pass   runs through, no time printed
    Berh Sb   untimed_stop   no time printed, in place of both

The document has NO LEGEND for "Ls" or "Berh Sb". Reading Ls as a pass and
Berh Sb as a stop are inferences from structure, not facts the source states:
Ls carries one time where a stop carries two, which is what a train running
straight through has, and Berh Sb fills every intermediate row of the commuter
lines, where every train stops -- "Berh" is almost certainly "berhenti",
"stops". Code downstream that treats a pass as never a call relies on that
reading.

The note -- "x ka 455 (ka 455 x)" for a crossing, "= ka 4 (ka 4 //)" for an
overtake -- is kept in `note` and never changes the kind. Times are HH:MM:SS.

Five things the layout does that make the obvious reading wrong:

  * Each section, and most groups of trains within it, opens with a contents
    list ("DAFTAR WAKTU ... ISI:") that repeats every train's header line with
    no rows beneath it. The document prints 4,024 header lines; 1,935 are
    contents entries and 2,089 head a timetable. A run starts only at a header
    followed straight away by the column heading ("Kecepatan"), which no
    contents entry has. So a real header misprinted out of recognition does
    not hand its rows to the contents entry above it: with no run open, those
    rows are reported as rows outside any timetable.
  * A station name too long for its column wraps round its row: the row
    prints with no name or code ("7 0 05:09:00 -"), the name's first line
    above it ("Yogyakarta International") and the rest, ending in the code,
    below it ("Airport (YIA)"). Jakarta International Stadium does the same,
    with the code alone below. 114 rows print this way, and they hold the only
    two codes, YIA and JIS, that never print on a line of their own.
  * A note too long for its column wraps the same way, a line above the row
    and a line below, the row itself whole. So a stray line between rows
    belongs to a row next to it, and which one is fixed by the row above: a
    row that took a line from above is owed as many from below. Every wrapped
    cell in this edition is that symmetric.
  * A destination's speed column often prints "-" rather than "0". That is
    kept as None: the timetable prints no speed, and 0 would be a number it
    did not print.
  * Station names hold spaces, so a row is anchored on the bracketed code
    immediately before the speed column, never on word positions.

Nothing is skipped silently. A line inside a timetable that looks like a
station row and does not parse, a row out of sequence, a wrapped cell with no
lower half, a run that ends before its destination row, or a run whose first
and last codes disagree with its header -- every one is collected, and
parse_runs() raises TimetableError listing them all. Over the whole document
there are none.

Times are seconds from midnight, rolled past 86,400 where a run has crossed
midnight. The rule is step-wise, because each step is short: a printed time
earlier than the printed time before it in the same run has crossed midnight,
and it and every time after gain a day. Revision 1 learned that end-to-end
arithmetic fails -- a single "arrival before departure, add a day" rule puts
any run over 24 h a day short. 157 runs cross midnight in 2026, 23 of them
inside a single row (Cisauk, KA 1802: arrives 23:59:00, departs 00:01:00); the
longest run, KA 2523 Massao Cargo, takes 19 h 44 min, so none rolls twice.

A paired register number such as "32-33" is two consecutive legs, each with
its own timetable here; linking them belongs to the register, not to this
module. One consequence: the Dhoho and Penataran, which 2025 printed as loops
calling at Wonokromo twice, are one-way legs in 2026, and no 2026 run calls
at any station twice. Rows are kept by position all the same.
"""
import math
import re
from dataclasses import dataclass, field, replace

DAY = 86400
TIME = r'\d{2}:\d{2}:\d{2}'
CODE = r'[A-Z][A-Z0-9]*'

HEADER = re.compile(r'^KA\s+(\S+)\s*\((.+)\)\s*(?:Relasi|Lintas Pelayanan)\s+(.+?)\s*$')
DASH = re.compile(r'\s*-\s*')
# n, name, code, speed, the rest. The name is lazy so that the code is the
# FIRST bracketed token followed by a speed; a note's own brackets
# ("(ka 455 x)") hold spaces and can never match CODE.
ROW = re.compile(rf'^(\d+)\s+(.+?)\s+\(({CODE})\)\s+(\d+|-)\s+(.+)$')
# A row whose name and code wrapped round it: n, speed, the rest.
BARE = re.compile(rf'^(\d+)\s+(\d+|-)\s+((?:-|Ls|Berh|{TIME})(?:\s.*)?)$')
CELLS = re.compile(rf'^(?:Berh\s+Sb|(-|Ls|{TIME})\s+(-|{TIME}))(?:\s+(.*?))?\s*$')
TAIL_CODE = re.compile(rf'^(.*?)\s*\(({CODE})\)\s*$')
# Anything that starts with a number and carries a time or a row-kind marker.
# Inside a run, a line like this that ROW and BARE both refuse is reported.
LOOKS_LIKE_A_ROW = re.compile(
    rf'^\d+\s.*(?:\({CODE}\)\s+(?:\d+|-)\s|{TIME}|\sLs(?:\s|$)|Berh\s+Sb)')
# The column heading every page of a run repeats, and the page number.
STRUCTURE = re.compile(r'^(?:Kecepatan|No\. Stasiun dan Perhentian\b.*|\(Km/Jam\)|\d+)$')

KINDS = ('origin', 'destination', 'stop', 'pass', 'untimed_pass', 'untimed_stop')


@dataclass(frozen=True)
class Row:
    """One timetable row. `arr` and `dep` are printed times only, None where
    the row prints none; a pass has one time and carries it in both."""
    code: str
    name: str
    max_kmh: int | None
    arr: int | None
    dep: int | None
    kind: str
    note: str


@dataclass(frozen=True)
class Run:
    no: str
    service: str
    origin: str
    destination: str
    rows: tuple[Row, ...]


class TimetableError(ValueError):
    """Every timetable line that did not parse, as (page, line, why)."""

    def __init__(self, problems: list[tuple[str, str, str]]):
        self.problems = problems
        super().__init__(f'{len(problems)} timetable line(s) did not parse:\n' + '\n'.join(
            f'  page {page}: {why}: {line!r}' for page, line, why in problems))


def _seconds(cell: str) -> int:
    h, m, s = (int(part) for part in cell.split(':'))
    return h * 3600 + m * 60 + s


def _cells(text: str) -> tuple[int | None, int | None, str, str] | None:
    """(arr, dep, kind, note) from what follows the speed column, or None."""
    m = CELLS.match(text)
    if not m:
        return None
    arr, dep, note = m.group(1), m.group(2), m.group(3) or ''
    if arr is None:
        return None, None, 'untimed_stop', note
    if arr == 'Ls':
        if dep == '-':
            return None, None, 'untimed_pass', note
        return _seconds(dep), _seconds(dep), 'pass', note
    if arr == '-':
        return None if dep == '-' else (None, _seconds(dep), 'origin', note)
    if dep == '-':
        return _seconds(arr), None, 'destination', note
    return _seconds(arr), _seconds(dep), 'stop', note


def _speed(cell: str) -> int | None:
    return None if cell == '-' else int(cell)


def parse_row(line: str) -> Row | None:
    """One whole-line station row, times not yet rolled, or None.

    A row whose name wrapped round it cannot be read from its own line; only
    parse_runs(), which sees the lines either side, reads those.
    """
    m = ROW.match(line.strip())
    cells = m and _cells(m.group(5))
    if not cells:
        return None
    _, name, code, speed, _ = m.groups()
    return Row(code, ' '.join(name.split()), _speed(speed), *cells)


def roll_midnight(rows: list[Row]) -> tuple[Row, ...]:
    """The rows with every printed time after a backwards step a day later."""
    out, last, offset = [], None, 0
    for row in rows:
        times = []
        for t in (row.arr, row.dep):
            if t is not None:
                if last is not None and t + offset < last:
                    offset += DAY
                t = last = t + offset
            times.append(t)
        out.append(replace(row, arr=times[0], dep=times[1]))
    return tuple(out)


@dataclass
class _Read:
    """A row as read, before a wrapped cell's lower half has arrived."""
    line: str
    name: str | None            # None: the name wrapped round the row
    code: str | None
    speed: int | None
    cells: tuple
    above: list[str]
    below: list[str] = field(default_factory=list)


@dataclass
class _Block:
    """The run under the last header, while its rows are still arriving."""
    no: str
    service: str
    origin: str
    destination: str
    rows: list[_Read] = field(default_factory=list)
    spill: list[str] = field(default_factory=list)   # lines since the last row
    owed: int = 0               # lines the last row is owed from below
    done: bool = False          # its destination row has been read


def _row(read: _Read, page: str, problems: list) -> Row | None:
    arr, dep, kind, note = read.cells
    if read.code is None:
        tail = TAIL_CODE.match(read.below[-1]) if read.below else None
        if not tail:
            problems.append((page, read.line, 'a wrapped station name with no code below it'))
            return None
        name = ' '.join(' '.join(read.above + read.below[:-1] + [tail.group(1)]).split())
        return Row(tail.group(2), name, read.speed, arr, dep, kind, note)
    note = ' '.join(part for part in read.above + [note] + read.below if part)
    return Row(read.code, read.name, read.speed, arr, dep, kind, note)


def parse_runs(pages: dict[str, str]) -> list[Run]:
    """Every timetabled run, in print order.

    `pages` is the cache, {"<0-based page>": "<page text>"}, or any part of
    it; pages are read in page order, so a run carries on across a page break.
    A run opens only at a header whose next line is the column heading; a
    header without one -- a contents-list entry -- is not a run, and a station
    row under it is reported. Raises TimetableError if any line inside a run
    fails to parse.
    """
    runs: list[Run] = []
    problems: list[tuple[str, str, str]] = []
    block: _Block | None = None
    heading_for: _Block | None = None     # a header waiting for its heading
    page = ''

    def settle() -> None:
        """Hand the last row the lines it is owed from below."""
        if block.owed:
            block.rows[-1].below = block.spill[:block.owed]
            if len(block.rows[-1].below) < block.owed:
                problems.append((page, block.rows[-1].line, 'a wrapped cell with no lower half'))
            block.spill = block.spill[block.owed:]
            block.owed = 0

    def close() -> None:
        nonlocal block
        if block is None:
            return
        settle()
        if block.rows:
            rows = [row for row in (_row(read, page, problems) for read in block.rows) if row]
            if not block.done:
                problems.append((page, block.rows[-1].line,
                                 f'KA {block.no} ends before its destination row'))
            elif rows and (rows[0].code, rows[-1].code) != (block.origin, block.destination):
                problems.append((page, block.rows[-1].line,
                                 f'KA {block.no} runs {rows[0].code}-{rows[-1].code}, its header '
                                 f'says {block.origin}-{block.destination}'))
            runs.append(Run(block.no, block.service, block.origin, block.destination,
                            roll_midnight(rows)))
        block = None

    for page in sorted(pages, key=int):
        for raw in pages[page].split('\n'):
            line = raw.strip()
            if not line:
                continue
            if heading_for is not None:
                if line == 'Kecepatan':
                    block, heading_for = heading_for, None
                    continue
                if not line.isdigit():            # a page number may come between
                    heading_for = None
            header = HEADER.match(line)
            if header:
                close()
                no, service, relasi = header.groups()
                stops = [stop for stop in DASH.split(relasi) if stop]
                heading_for = _Block(no, ' '.join(service.split()), stops[0], stops[-1])
                continue
            full, bare = ROW.match(line), BARE.match(line)
            if block is None:
                # Between runs: contents lists, rolling stock, the register. A
                # whole station row here would be a run whose header was missed.
                if full and _cells(full.group(5)):
                    problems.append((page, line, 'a station row outside any timetable'))
                continue
            if full or bare:
                if full:
                    n, name, code, speed, rest = full.groups()
                    name = ' '.join(name.split())
                else:
                    n, speed, rest = bare.groups()
                    name = code = None
                cells = _cells(rest)
                if cells is None:
                    problems.append((page, line, 'times in no form a row prints'))
                elif block.done:
                    problems.append((page, line,
                                     f'a row after KA {block.no} reached its destination'))
                elif int(n) != len(block.rows) + 1:
                    problems.append((page, line,
                                     f'row {n} after row {len(block.rows)} of KA {block.no}'))
                else:
                    settle()
                    above, block.spill = block.spill, []
                    # A wrapped name always owes at least its code from below.
                    block.owed = len(above) if full else max(len(above), 1)
                    block.rows.append(_Read(line, name, code, _speed(speed), cells, above))
                    block.done = cells[2] == 'destination'
                    if block.done and not block.owed:
                        close()
                continue
            if LOOKS_LIKE_A_ROW.match(line):
                problems.append((page, line, 'looks like a station row but does not parse'))
            elif not STRUCTURE.match(line):
                block.spill.append(line)
                if block.done and len(block.spill) >= block.owed:
                    close()
    close()
    if problems:
        raise TimetableError(problems)
    return runs


def estimate_times(run: Run, km: list[float]) -> list[tuple[int, int, bool]]:
    """Every row's (arr, dep, estimated), printed times kept exactly.

    `km` is each row's distance along the run, non-decreasing: real distances
    exist only once the run's geometry is routed, so the caller supplies them.
    An untimed row gets one time, arrival and departure alike, interpolated by
    distance between the nearest printed rows either side -- the departure of
    the one before, the arrival of the one after. Consecutive untimed rows
    therefore come out in order. A printed row fills its missing side from the
    side it prints: an origin arrives when it departs.

    Raises ValueError when the run or `km` cannot carry that: the wrong
    number of distances, one that is not a finite number (a NaN compares false
    both ways, so it would slip past the order check), a distance going
    backwards, untimed rows between two printed rows at the same km, a run that
    does not start and end on a printed time, or printed times that go
    backwards -- which parse_runs() never returns, having rolled them past
    midnight, but a Run built any other way might.
    """
    rows = run.rows
    if len(km) != len(rows):
        raise ValueError(f'KA {run.no}: {len(km)} distances for {len(rows)} rows')
    if not all(math.isfinite(d) for d in km):
        raise ValueError(f'KA {run.no}: every distance must be a finite number')
    if any(b < a for a, b in zip(km, km[1:])):
        raise ValueError(f'KA {run.no}: distances must not decrease')
    printed = [i for i, row in enumerate(rows) if row.arr is not None or row.dep is not None]
    if not printed or printed[0] != 0 or printed[-1] != len(rows) - 1:
        raise ValueError(f'KA {run.no} does not start and end on a printed time')
    times = [t for row in rows for t in (row.arr, row.dep) if t is not None]
    if any(b < a for a, b in zip(times, times[1:])):
        raise ValueError(f'KA {run.no}: printed times go backwards; roll them past '
                         f'midnight first')
    out = []
    for before, after in zip(printed, printed[1:] + [None]):
        row = rows[before]
        arr = row.arr if row.arr is not None else row.dep
        dep = row.dep if row.dep is not None else row.arr
        out.append((arr, dep, False))
        if after is None or after == before + 1:
            continue
        t0, t1 = dep, rows[after].arr if rows[after].arr is not None else rows[after].dep
        span = km[after] - km[before]
        if span <= 0:
            raise ValueError(f'KA {run.no}: untimed rows between {row.code} and '
                             f'{rows[after].code}, which are at the same km')
        for i in range(before + 1, after):
            t = round(t0 + (t1 - t0) * (km[i] - km[before]) / span)
            out.append((t, t, True))
    return out


def run_record(run: Run) -> dict:
    """A run as timetables.json stores it: printed times only, null where none."""
    return {'no': run.no, 'service': run.service, 'origin': run.origin,
            'destination': run.destination,
            'rows': [[r.code, r.name, r.max_kmh, r.arr, r.dep, r.kind, r.note]
                     for r in run.rows]}
