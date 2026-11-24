"""GAPEKA 2026's station-by-station timetables, parsed from the page text.

Every timetable line fed to the parser here is verbatim from
tests/fixtures/timetables_2026.txt, or from the committed cache of the whole
document, except where a test says it has cut a line out or built a block by
hand -- and those say why. Each test names the run it leans on and the quirk
that run carries.
"""
import collections

import pytest

from scripts.gapeka.timetables import (DAY, TimetableError, estimate_times,
                                       parse_row, parse_runs, run_record)


def hms(text: str) -> int:
    h, m, s = (int(part) for part in text.split(':'))
    return h * 3600 + m * 60 + s


@pytest.fixture(scope='module')
def runs(timetable_pages):
    return {r.no: r for r in parse_runs(timetable_pages)}


@pytest.fixture(scope='module')
def document(cached_2026_pages):
    return parse_runs(cached_2026_pages)


def page_lines(pages, page):
    return pages[str(page)].split('\n')


def test_both_header_forms_are_read(runs):
    anggrek, tangerang = runs['1'], runs['2107']     # "Relasi", "Lintas Pelayanan"
    assert (anggrek.service, anggrek.origin, anggrek.destination) == ('Anggrek', 'SBI', 'GMR')
    assert (tangerang.service, tangerang.origin, tangerang.destination) == \
        ('Commuter Line Tangerang', 'TNG', 'DU')
    assert len(anggrek.rows) == 97                    # across three pages


# Review Focus 1
def test_a_contents_list_entry_is_not_a_run(timetable_pages):
    # Page 669 names KA 352-356 as header lines with nothing beneath them;
    # KA 351's own timetable is the first block of page 670.
    pages = {page: timetable_pages[page] for page in ('669', '670')}
    assert [r.no for r in parse_runs(pages)] == ['351']


def test_row_kinds_come_from_what_the_columns_hold(runs):
    kinds = [row.kind for row in runs['2107'].rows]
    assert kinds[0] == 'origin' and kinds[-1] == 'destination'
    assert kinds[2] == 'stop'                         # Batuceper, 20:13:00 20:14:00
    assert kinds[1] == 'untimed_stop'                 # Tanah Tinggi, Berh Sb
    assert runs['351'].rows[1].kind == 'untimed_pass'  # Rajamandala, Ls -
    tanah_tinggi = runs['2107'].rows[1]
    assert tanah_tinggi.arr is None and tanah_tinggi.dep is None


def test_a_pass_carries_one_time(runs):
    tandes = runs['1'].rows[1]
    assert tandes.kind == 'pass' and tandes.arr == tandes.dep == 8 * 3600 + 21 * 60


def test_origin_and_destination_carry_only_the_time_they_print(runs):
    first, last = runs['2107'].rows[0], runs['2107'].rows[-1]
    assert (first.arr, first.dep) == (None, hms('20:07:00'))
    assert (last.arr, last.dep) == (hms('20:33:00'), None)


def test_an_operational_note_is_kept_but_does_not_change_the_kind():
    # Verbatim from page 381, KA 168 at Sidoarjo: a crossing with KA 455.
    row = parse_row('20 Sidoarjo (SDA) 80 08:59:00 09:05:00 x ka 455 (ka 455 x)')
    assert row.kind == 'stop' and row.note == 'x ka 455 (ka 455 x)'
    assert (row.code, row.name, row.max_kmh) == ('SDA', 'Sidoarjo', 80)


def test_a_note_on_a_pass_does_not_make_it_a_stop(runs):
    kaliwungu = runs['1'].rows[38]                    # "Ls 11:30:00 // ka 229 (ka 229 =)"
    assert kaliwungu.kind == 'pass' and kaliwungu.note == '// ka 229 (ka 229 =)'


def test_a_note_too_long_for_its_column_is_put_back_together(runs):
    rows = runs['93'].rows
    porong = rows[17]
    assert porong.code == 'PR' and porong.kind == 'pass'
    assert porong.note == 'x ka 168 (ka 168 x), // ka 2647f jj (ka 2647f jj =)'
    # The halves above and below Porong are Porong's, not its neighbours'.
    assert rows[16].note == '' and rows[18].note == 'x ka 224f jj'


def test_a_name_too_long_for_its_column_is_put_back_together(runs):
    airport = runs['541'].rows[-1]                    # "7 0 05:09:00 -" between its name
    assert (airport.code, airport.name, airport.kind, airport.arr) == \
        ('YIA', 'Yogyakarta International Airport', 'destination', hms('05:09:00'))
    assert runs['542'].rows[0].code == 'YIA' and runs['542'].rows[0].kind == 'origin'
    stadium = runs['2200'].rows[3]                    # "4 40 Ls -", code alone below
    assert (stadium.code, stadium.name, stadium.kind, stadium.max_kmh) == \
        ('JIS', 'Jakarta International Stadium', 'untimed_pass', 40)


def test_a_dash_in_the_speed_column_is_no_speed_not_zero(runs):
    assert runs['93'].rows[-1].max_kmh is None        # "26 Malang (ML) - 10:05:00 -"
    assert runs['1'].rows[-1].max_kmh == 0            # "97 Gambir (GMR) 0 16:12:00 -"


def test_a_station_name_keeps_its_spaces(runs):
    assert runs['1'].rows[0].name == 'Surabaya Pasarturi'
    assert runs['2107'].rows[7].name == 'Taman Kota'


# Review Focus 2
def test_a_run_crossing_midnight_rolls_its_later_times_past_86400(runs):
    rows = runs['1802'].rows
    times = [t for r in rows for t in (r.arr, r.dep) if t is not None]
    assert times == sorted(times) and times[-1] > DAY
    # Cisauk crosses midnight inside its own row, across a page break.
    cisauk = rows[8]
    assert cisauk.code == 'CSK'
    assert (cisauk.arr, cisauk.dep) == (hms('23:59:00'), DAY + hms('00:01:00'))
    assert rows[-1].arr == DAY + hms('00:12:00')


def test_a_run_that_stays_inside_the_day_is_not_rolled(runs):
    assert runs['1'].rows[-1].arr == hms('16:12:00')


# Review Focus 3
def test_the_2026_dhoho_is_printed_as_one_way_legs(runs):
    # 2025's circular Dhoho called at Wonokromo twice in one working. GAPEKA
    # 2026 prints it as legs -- KA 435 Surabayakota to Kertosono, KA 436 back
    # via Blitar and Malang -- so within one run it calls there once. Two
    # visits come back only when Task 6 links the legs.
    dhoho = runs['435']
    assert (dhoho.origin, dhoho.destination) == ('SB', 'KTS')
    assert [r.code for r in dhoho.rows].count('WO') == 1


def test_a_run_calling_at_a_station_twice_keeps_both_visits():
    # Built by hand, not verbatim: no 2026 timetable calls anywhere twice (see
    # the whole-document test below), so a looped run has to be made up to
    # prove the parser keeps rows by position and never collapses them by code.
    looped = {'0': '\n'.join([
        'KA 9 (Constructed Loop) Lintas Pelayanan SB - SB',
        '1 Surabayakota (SB) 50 - 03:55:00',
        '2 Surabayagubeng (SGU) 90 04:03:00 04:06:00',
        '3 Wonokromo (WO) 90 04:12:00 04:14:00',
        '4 Surabayagubeng (SGU) 90 04:20:00 04:22:00',
        '5 Surabayakota (SB) 0 04:30:00 -',
    ])}
    codes = [r.code for r in parse_runs(looped)[0].rows]
    assert codes == ['SB', 'SGU', 'WO', 'SGU', 'SB']


# Every line in a timetable block is accounted for
def test_a_missing_row_is_reported_not_skipped(timetable_pages):
    lines = page_lines(timetable_pages, 1300)
    cut = [line for line in lines if not line.startswith('3 Batuceper')]
    with pytest.raises(TimetableError) as caught:
        parse_runs({'1300': '\n'.join(cut)})
    assert any('row 4 after row 2 of KA 2107' in why for _, _, why in caught.value.problems)


def test_a_row_whose_times_fit_no_known_form_is_reported(timetable_pages):
    lines = [line.replace('20:13:00 20:14:00', '20:13:00 Ls')
             for line in page_lines(timetable_pages, 1300)]
    with pytest.raises(TimetableError) as caught:
        parse_runs({'1300': '\n'.join(lines)})
    page, line, _ = caught.value.problems[0]
    assert page == '1300' and line.startswith('3 Batuceper')


def test_a_run_that_stops_short_of_its_destination_is_reported(timetable_pages):
    lines = page_lines(timetable_pages, 1300)
    cut = [line for line in lines if not line.startswith('11 Duri')]
    with pytest.raises(TimetableError) as caught:
        parse_runs({'1300': '\n'.join(cut)})
    assert any('KA 2107' in why for _, _, why in caught.value.problems)


def test_a_header_that_disagrees_with_its_rows_is_reported(timetable_pages):
    lines = [line.replace('Lintas Pelayanan TNG - DU', 'Lintas Pelayanan TNG - THB', 1)
             for line in page_lines(timetable_pages, 1300)]
    with pytest.raises(TimetableError) as caught:
        parse_runs({'1300': '\n'.join(lines)})
    assert any('KA 2107' in why for _, _, why in caught.value.problems)


def test_a_wrapped_name_that_never_gets_its_code_is_reported(timetable_pages):
    lines = [line for line in page_lines(timetable_pages, 770) if line != 'Airport (YIA)']
    with pytest.raises(TimetableError):
        parse_runs({'770': '\n'.join(lines)})


# Review Focus 5
# Test inputs, not measurements: real distances come from the routed segment
# library (Task 8). TNG, BPR, RW and DU sit at the 2026 distance table's km
# (page 1875: DU to RW 9,241, to BPR 15,722, to TNG 19,297), read from
# Tangerang; the six halts between are made-up but in order.
KM_2107 = [0.0, 1.9, 3.575, 5.2, 7.4, 10.056, 11.8, 13.6, 15.0, 16.9, 19.297]


def test_estimated_times_fall_between_their_printed_neighbours_and_in_order(runs):
    est = estimate_times(runs['2107'], KM_2107)
    times = [t for a, d, _ in est for t in (a, d)]
    assert times == sorted(times)
    assert [e for _, _, e in est][1] is True          # Tanah Tinggi was estimated
    # 1.9 km of the 3.575 from Tangerang (dep 20:07) to Batuceper (arr 20:13).
    assert est[1] == (72611, 72611, True)
    # Poris and Kalideres, two untimed rows in a row, between Batuceper's
    # departure at 20:14 and Rawabuaya's arrival at 20:21.
    assert hms('20:14:00') < est[3][0] < est[4][0] < hms('20:21:00')


def test_printed_times_come_through_estimation_unchanged(runs):
    run = runs['2107']
    est = estimate_times(run, KM_2107)
    assert est[0] == (hms('20:07:00'), hms('20:07:00'), False)    # origin
    assert est[2] == (hms('20:13:00'), hms('20:14:00'), False)    # Batuceper
    assert est[-1] == (hms('20:33:00'), hms('20:33:00'), False)   # destination
    assert [e for _, _, e in est] == [r.arr is None and r.dep is None for r in run.rows]


def test_estimation_across_midnight_stays_in_order(runs):
    run = runs['1802']
    km = [float(i) for i in range(len(run.rows))]
    times = [t for a, d, _ in estimate_times(run, km) for t in (a, d)]
    assert times == sorted(times) and times[-1] == DAY + hms('00:12:00')


def test_estimation_refuses_distances_it_cannot_use(runs):
    run = runs['2107']
    with pytest.raises(ValueError):
        estimate_times(run, KM_2107[:-1])               # one km short
    with pytest.raises(ValueError):
        estimate_times(run, KM_2107[:3] + [3.0] + KM_2107[4:])   # km going back
    with pytest.raises(ValueError):
        estimate_times(run, [0.0] * 3 + [3.575] * 3 + KM_2107[6:])  # no span to spread over


def test_a_record_is_the_row_in_column_order(runs):
    record = run_record(runs['2107'])
    assert (record['no'], record['service'], record['origin'], record['destination']) == \
        ('2107', 'Commuter Line Tangerang', 'TNG', 'DU')
    assert record['rows'][1] == ['THI', 'Tanah Tinggi', 75, None, None, 'untimed_stop', '']
    assert record['rows'][2] == ['BPR', 'Batuceper', 90, hms('20:13:00'), hms('20:14:00'),
                                 'stop', '']


# The whole document, from the committed cache
def test_every_run_starts_and_ends_on_a_printed_time(document):
    for r in document:
        assert r.rows[0].kind == 'origin' and r.rows[0].dep is not None, r.no
        assert r.rows[-1].kind == 'destination' and r.rows[-1].arr is not None, r.no


def test_the_whole_document_parses_to_the_counts_it_prints(document):
    # The plan's probe gave 48,554 rows and 464 codes, but the six row kinds
    # it counted sum to 48,414. It missed 271 rows: the 114 whose station name
    # wraps round them (YIA and JIS, the two missing codes), the 134
    # destinations that print "-" for a speed, and the 23 rows of KA 2763F that
    # run on to page 1672, past where it stopped looking. Every count here is
    # cross-checked by the parser itself: each run's rows are numbered 1 to n
    # with none missing, each starts at its header's origin and ends at its
    # destination, and the whole document has 48,685 lines that start with a
    # number and carry a time, "Ls" or "Berh Sb" -- one per row.
    assert len(document) == 2089
    assert sum(len(r.rows) for r in document) == 48685
    assert len({row.code for r in document for row in r.rows}) == 466
    assert collections.Counter(row.kind for r in document for row in r.rows) == {
        'origin': 2089, 'destination': 2089, 'stop': 13115, 'pass': 18242,
        'untimed_pass': 3444, 'untimed_stop': 9706}


def test_each_train_number_has_one_timetable(document):
    numbers = collections.Counter(r.no for r in document)
    assert [no for no, n in numbers.items() if n > 1] == []


def test_no_2026_run_calls_at_a_station_twice(document):
    # Review Focus 3 expected the circular Dhoho and Penataran here; 2026
    # prints them as legs. If a later edition prints a loop again, this fails
    # and the looped-run test above is the behaviour that matters.
    assert [r.no for r in document if len({x.code for x in r.rows}) < len(r.rows)] == []


def test_midnight_is_crossed_by_157_runs_and_no_run_lasts_a_day(document):
    def span(r):
        times = [t for x in r.rows for t in (x.arr, x.dep) if t is not None]
        return times[0], times[-1]
    crossing = [r for r in document if span(r)[1] >= DAY]
    assert len(crossing) == 157
    longest = max(document, key=lambda r: span(r)[1] - span(r)[0])
    # KA 2523 Massao Cargo, Kalimas - Tanjungpriuk, 19 h 44 min. Nothing runs
    # over 24 h in 2026, so the step-wise rule never has to roll twice.
    assert longest.no == '2523' and span(longest)[1] - span(longest)[0] == 19 * 3600 + 44 * 60
