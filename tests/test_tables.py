"""The register's JARAK ANTAR STASIUN corridor matrices.

Every line fed to the parser here is verbatim from
tests/fixtures/register_tables.txt, which holds pages 52, 55, 58, 62 and 63 of
the register. Each test names the page it leans on and the quirk that page
carries.
"""
import pytest

from scripts.gapeka.tables import (Row, parse_corridor_block, parse_inline_pairs,
                                   parse_matrix_rows, split_side_by_side)

MATRIX_PAGES = (52, 53, 54, 55, 62, 63)  # 58 is in the fixture for its wreckage


def test_station_order_comes_from_row_labels_not_the_header(register_tables):
    # Page 55's header arrives interleaved: "O/D C 1KP C 2BR PW 3K ..."
    corridor = parse_corridor_block(register_tables[55])[0]
    assert [c for c, _ in corridor.stations][:3] == ['CKP', 'CBR', 'PWK']
    assert len(corridor.stations) == 42


def test_the_interleaved_header_yields_no_rows_of_its_own(register_tables):
    header = next(ln for ln in register_tables[55] if ln.startswith('O/D C 1KP'))
    assert parse_matrix_rows(header) == []


def test_vertical_text_wreckage_yields_no_rows(register_tables):
    # Page 58 prints rows 8, 9, 11 and 12 of Banjar - Kroya as vertical text,
    # which arrives as loose digits: "LJ BR GL 98 76 25 ,, 15 90 ...". Only the
    # comma a real distance carries keeps that out of the matrix -- make the
    # comma optional and "GL 98 76" becomes a station GL at km 76, and the
    # second line gives a station P at km 21 the same way.
    rows = [row for ln in register_tables[58] for row in parse_matrix_rows(ln)]
    # The only real row on these two lines is the one the register squeezed on
    # to the end of the second, out of the Kutoarjo - Purworejo pair beside it.
    assert [(r.code, r.index, r.values) for r in rows] == [('PWR', 2, (11.688,))]


def test_cumulative_km_comes_from_the_first_value_in_each_row(register_tables):
    corridor = parse_corridor_block(register_tables[55])[0]
    assert corridor.stations[0] == ('CKP', 0.0)
    assert corridor.stations[1][1] == 7.636
    assert corridor.stations[-1][1] == 245.562


def test_a_cell_is_read_from_the_stations_own_row(register_tables):
    corridor = parse_corridor_block(register_tables[55])[0]
    assert ('CAA', 177.378) in corridor.stations
    assert ('CAW', 182.771) in corridor.stations


@pytest.mark.parametrize('page', MATRIX_PAGES)
def test_row_one_first_value_cross_checks_the_head(register_tables, page):
    # Row 1's first value is d(1,2), which is station 2's cumulative km. Every
    # station past the second is checked the same way, against row 1's (i-1)th.
    rows = [row for ln in register_tables[page] for row in parse_matrix_rows(ln)]
    groups = [g for g in split_side_by_side(rows) if len(g) > 1]
    assert groups
    for group in groups:
        head = group[0]
        assert head.index == 1
        for row in group[1:]:
            assert row.km == pytest.approx(head.values[row.index - 2], abs=0.01)


@pytest.mark.parametrize('page', MATRIX_PAGES)
def test_cumulative_km_is_strictly_increasing(register_tables, page):
    corridors = parse_corridor_block(register_tables[page])
    assert corridors
    for corridor in corridors:
        kms = [km for _, km in corridor.stations]
        assert kms[0] == 0.0
        assert kms == sorted(kms) and len(set(kms)) == len(kms)


def test_side_by_side_tables_split_on_index_reset(register_tables):
    corridors = parse_corridor_block(register_tables[62])
    assert len(corridors) == 2
    assert [c for c, _ in corridors[1].stations] == ['TRK', 'TLN', 'SDA']


def test_two_rows_on_one_line_keep_their_own_columns(register_tables):
    line = next(ln for ln in register_tables[62] if ln.startswith('SDT 2'))
    left, right = parse_matrix_rows(line)
    assert (left.code, left.index) == ('SDT', 2)
    assert (right.code, right.index) == ('TLN', 2)
    assert left.values == (5.740, 2.046, 3.506, 4.436)
    assert right.values == (14.593, 7.554)


def test_columns_run_together_are_split(register_tables):
    # Page width squeezes adjacent columns until extract_text() yields them as
    # one token; page 62's Wlingi matrix does it on every wide row.
    line = next(ln for ln in register_tables[62] if ln.startswith('SBE 1'))
    squashed = line.replace('9,246 10,176', '9,24610,176')
    assert parse_matrix_rows(squashed)[0].values == (5.740, 7.786, 9.246, 10.176)


def test_a_cell_printed_to_fewer_decimals_is_still_that_cell(register_tables):
    # Page 63 prints its KTK row as "102,1" where row 1 of the same matrix
    # gives "102,098", and does the same in eighteen cells, so the whole tail
    # of the chain hangs on matching a cell at the precision it was printed.
    corridor, = parse_corridor_block(register_tables[63])
    assert corridor.name == 'KTG - KLT - JR - BG'
    assert [c for c, _ in corridor.stations] == [
        'KTG', 'AGO', 'BWI', 'RGP', 'SGJ', 'TGR', 'KSL', 'SWD', 'GLM', 'KBR',
        'MRW', 'GRN', 'SPL', 'LDO', 'KLT', 'KTK', 'AJ', 'JR', 'MI', 'RBP',
        'BSS', 'TGL', 'JTR', 'RDA', 'KK', 'RN', 'MLS', 'LEC', 'PB', 'BYM',
        'GI', 'RO', 'PS', 'BG']
    assert corridor.stations[15] == ('KTK', 102.1)
    assert corridor.stations[-1] == ('BG', 262.47)


def test_a_row_that_matches_no_head_is_dropped_not_guessed_at():
    # Nothing on pages 52-63 reaches this, because every row cross-checks. If
    # one ever did, a wrong km in a corridor it may not even belong to is worse
    # than a missing station, so it is not placed by proximity. 20 m out is the
    # near miss that matters: page 63's roundings are 5 m at their widest, so
    # the slack that lets them through must not stretch this far.
    head = Row('AAA', 1, (5.0, 9.0))
    for stray in (Row('ZZZ', 2, (5.02,)), Row('ZZZ', 2, (400.0,))):
        assert split_side_by_side([head, stray]) == [[head], [stray]]
    assert parse_corridor_block([]) == []


def test_a_corridor_is_hashable_and_its_stations_cannot_be_appended_to(register_tables):
    corridor, = parse_corridor_block(register_tables[54])
    assert hash(corridor)                       # Task 3 keys graph edges on these
    with pytest.raises(AttributeError):
        corridor.stations.append(('XX', 99.0))


def test_a_row_lost_to_vertical_text_leaves_a_gap_not_a_wrong_chain(register_tables):
    # Page 55 prints the Padalarang - Sukabumi rows 7 and 8 as wrecked vertical
    # text, so CBB and LP are unreadable. The stations that do print keep their
    # true km, measured from the head, rather than being shuffled up.
    pdl = next(c for c in parse_corridor_block(register_tables[55])
               if c.stations[0][0] == 'PDL')
    assert [c for c, _ in pdl.stations] == \
        ['PDL', 'TAU', 'CPT', 'CPY', 'CRJ', 'CJ', 'CRG', 'GDS', 'SI']
    assert pdl.stations[-1] == ('SI', 83.299)


def test_a_corridor_is_named_for_its_code_route(register_tables):
    assert [c.name for c in parse_corridor_block(register_tables[52])] == \
        ['DU - TNG', 'THB - KEN - MER']
    assert [c.name for c in parse_corridor_block(register_tables[55])] == \
        ['CKP - AND - BD - CB - BJR', 'AND - CIR - BD', 'PDL - SI', 'CB - GRT']


def test_a_route_is_only_a_name_when_both_its_ends_match(register_tables):
    # "SBE - SDT - STM - SBI TRK - SDA" prints two routes on one line, and the
    # second table's three stations must not pick up the first table's route.
    names = [c.name for c in parse_corridor_block(register_tables[62])]
    assert names == ['SBE - SDT - STM - SBI', 'TRK - SDA']
    # Page 54's route runs KPB - DU - THB - MRI but its matrix stops at THB,
    # so the route is not this corridor's and the corridor says so itself.
    corridor, = parse_corridor_block(register_tables[54])
    assert corridor.name == 'KPB - THB'
    assert [c for c, _ in corridor.stations] == ['KPB', 'AK', 'DU', 'THB']


def test_two_corridors_sharing_both_ends_are_told_apart_by_print_order(register_tables):
    # Page 53 runs Jakarta Kota to Cikampek twice, by Pasar Senen and by
    # Manggarai, so both ends agree and only the print order separates them.
    # A route claimed by the first must not be handed to the second as well.
    first, second = parse_corridor_block(register_tables[53])
    assert first.name == 'JAKK - KPB - KMO - PSE - CKP'
    assert second.name == 'JAKK - GMR - MRI - CKP'
    assert first.stations[-1] == ('CKP', 84.007)
    assert second.stations[-1] == ('CKP', 84.663)


def test_an_inline_pair_on_a_line_of_its_own(register_tables):
    line = next(ln for ln in register_tables[54] if ln.startswith('CTA'))
    assert parse_inline_pairs(line) == [('CTA', 'NMO', 13.267)]


def test_an_inline_pair_squeezed_onto_a_matrix_row_is_not_a_distance(register_tables):
    # "KPB 2 1,364 ... 82,643 JAKK-TPK 8,115": the pair at the end belongs to a
    # different, two-station corridor and must leave the row's 15 values alone.
    line = next(ln for ln in register_tables[53] if ln.startswith('KPB 2'))
    row, = parse_matrix_rows(line)
    assert len(row.values) == 15 and row.values[-1] == 82.643
    assert parse_inline_pairs(line) == [('JAKK', 'TPK', 8.115)]
    index_row = next(ln for ln in register_tables[53] if ln.startswith('1 2 3'))
    assert parse_matrix_rows(index_row) == []
    assert parse_inline_pairs(index_row) == [('TPK', 'KMO', 8.624)]


def test_inline_pairs_are_picked_up():
    assert ('KEN', 'CGD', 6.439) in parse_inline_pairs('DU-TNG BPR - BST 12,300 KEN-CGD 6,439')


def test_a_code_route_without_a_distance_is_not_an_inline_pair(register_tables):
    line = next(ln for ln in register_tables[52] if ln.startswith('DU-TNG'))
    assert [(a, b) for a, b, _ in parse_inline_pairs(line)] == \
        [('BPR', 'BST'), ('KEN', 'CGD')]
    assert parse_inline_pairs('THB - KEN - MER') == []


def test_split_side_by_side_groups_the_rows_of_one_line(register_tables):
    rows = [row for ln in register_tables[62] for row in parse_matrix_rows(ln)]
    groups = split_side_by_side(rows)
    assert [[r.code for r in g] for g in groups] == \
        [['SBE', 'SDT', 'SB', 'STM', 'SBI'], ['TRK', 'TLN', 'SDA']]


# Review Focus 3
def test_a_junction_station_keeps_each_corridors_own_km(register_tables):
    # The plan named SMT here, but SMT's two corridors are both printed from
    # Tegal, so its km agree and it proves nothing. Bandung is the real case:
    # km 89,727 down the Cikampek - Banjar main line, and km 2,729 on the
    # Andir - Ciroyom - Bandung branch printed two blocks below it.
    corridors = parse_corridor_block(register_tables[55])
    bd_kms = [km for c in corridors for code, km in c.stations if code == 'BD']
    assert len(bd_kms) > 1
    assert len(set(bd_kms)) > 1     # different origins, deliberately not merged here
