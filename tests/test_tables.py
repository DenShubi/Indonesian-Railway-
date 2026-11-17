"""The register's JARAK ANTAR STASIUN corridor matrices.

Every line fed to the parser here is verbatim from
tests/fixtures/register_tables.txt, which holds pages 52, 55, 58, 62 and 63 of
the register. Each test names the page it leans on and the quirk that page
carries.
"""
import pytest

from scripts.gapeka.tables import (Row, parse_corridor_block, parse_inline_pairs,
                                   parse_matrix_rows, recover_vertical_codes,
                                   split_side_by_side)

MATRIX_PAGES = (52, 53, 54, 55, 58, 62, 63)


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
    wreckage = [ln for ln in register_tables[58]
                if ln.startswith(('LJ BR GL', 'SM KA P'))]
    assert len(wreckage) == 2
    rows = [row for ln in wreckage for row in parse_matrix_rows(ln)]
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


# Task 3, step 1: reading the four codes the register's vertical text lost.
# These exercise tables.py, so they live here rather than in test_topology.py,
# and they need the word coordinates in tests/fixtures/register_words.txt
# because what the page text cannot say is where one header column ends.

def test_the_wrecked_header_de_interleaves_on_its_x_coordinates(register_words):
    # Page 55's Padalarang - Sukabumi header reads "O/D P 1DL TA 2U C 3PT ..."
    # as text, with each index digit set inside its own column's code. Nothing
    # in that string says whether column 7 is C, CB or CBB.
    assert recover_vertical_codes(register_words[55], 55) == {
        1: 'PDL', 2: 'TAU', 3: 'CPT', 4: 'CPY', 5: 'CRJ', 6: 'CJ',
        7: 'CBB', 8: 'LP', 9: 'CRG', 10: 'GDS', 11: 'SI'}
    assert recover_vertical_codes(register_words[58], 58) == {
        1: 'BJR', 2: 'LN', 3: 'MLW', 4: 'CPI', 5: 'SDR', 6: 'GDM', 7: 'KWG',
        8: 'JRL', 9: 'LBG', 10: 'KH', 11: 'MA', 12: 'SKP', 13: 'KYA'}


def test_the_codes_come_from_the_coordinates_and_not_from_the_page_number():
    # Every caller hands the page its own words, so a reader that ignored the
    # words and answered from the page number would look right. The page number
    # only names the page in the one error this can raise, so a wrong one
    # changes nothing, and no words means nothing to read.
    assert recover_vertical_codes([], 55) == {}
    assert recover_vertical_codes([], 58) == {}


def test_the_page_number_does_not_pick_the_answer(register_words):
    assert recover_vertical_codes(register_words[55], 99) == \
        recover_vertical_codes(register_words[55], 55)
    assert recover_vertical_codes(register_words[58], 0)[8] == 'JRL'


def test_the_recovered_codes_agree_with_the_rows_that_did_print(register_words,
                                                                register_tables):
    # The read is only trustworthy where it can be checked, and it can be
    # checked index by index: nine of page 55's eleven columns printed a row of
    # their own, and nine of page 58's thirteen did, each carrying its own
    # index. A column boundary read one letter out shifts a letter between two
    # neighbouring codes, so it lands on an index that printed and shows here.
    for page, head in ((55, 'PDL'), (58, 'BJR')):
        codes = recover_vertical_codes(register_words[page], page)
        rows = [row for ln in register_tables[page]
                for row in parse_matrix_rows(ln)]
        group = next(g for g in split_side_by_side(rows) if g[0].code == head)
        assert len(group) == 9
        assert {row.index: row.code for row in group} == \
            {index: codes[index] for row in group for index in [row.index]}
        # And the four indexes with no row of their own are the four the
        # register wrecked, which is what there was to recover.
        assert sorted(set(codes) - {row.index for row in group}) == \
            ([7, 8] if page == 55 else [8, 9, 11, 12])


def test_a_recovered_code_is_confirmed_by_the_corridor_beside_it(register_words,
                                                                 register_tables):
    # Page 58 prints Cilacap - Maos beside Banjar - Kroya, and Krenceng - Maos
    # below it. Both call at Maos and Sikampuh, so MA at index 11 and SKP at
    # index 12 are attested by a corridor this header had no part in.
    codes = recover_vertical_codes(register_words[58], 58)
    assert (codes[11], codes[12]) == ('MA', 'SKP')
    elsewhere = {code for c in parse_corridor_block(register_tables[58])
                 if c.stations[0][0] != 'BJR' for code, _ in c.stations}
    assert {'MA', 'SKP'} <= elsewhere
    # The two that are not attested anywhere else are the two the chain's own
    # spacing has to vouch for.
    assert {codes[8], codes[9]} == {'JRL', 'LBG'}
    assert {'JRL', 'LBG'} & elsewhere == set()


def test_a_page_with_nothing_wrecked_recovers_nothing(register_words):
    assert recover_vertical_codes(register_words[52], 52) == {}


def test_the_hole_closes_on_the_km_row_one_already_printed(register_words,
                                                           register_tables):
    codes = recover_vertical_codes(register_words[55], 55)
    pdl = next(c for c in parse_corridor_block(register_tables[55], codes)
               if c.stations[0][0] == 'PDL')
    assert [c for c, _ in pdl.stations] == \
        ['PDL', 'TAU', 'CPT', 'CPY', 'CRJ', 'CJ', 'CBB', 'LP', 'CRG', 'GDS', 'SI']
    assert pdl.stations[6] == ('CBB', 58.062)
    assert pdl.stations[7] == ('LP', 67.220)
    kms = [km for _, km in pdl.stations]
    assert kms == sorted(kms) and len(set(kms)) == len(kms)


def test_the_filled_km_are_the_ones_the_surviving_rows_measure_to(register_tables):
    # Row 1 is where the filled km come from, but it is not the only row that
    # prints them: Cireungas, which did print, gives 12,268 to column 7 and
    # 3,110 to column 8 off its own km of 70,330. That is the spacing check
    # standing behind CBB and LP, neither of which appears anywhere else in the
    # register's tables.
    rows = [row for ln in register_tables[55] for row in parse_matrix_rows(ln)]
    crg = next(row for row in rows if row.code == 'CRG')
    assert (crg.code, crg.index, crg.km) == ('CRG', 9, 70.330)
    # Row 9 skips its own diagonal, so column j sits at j - 1 for j below 9.
    assert crg.km - crg.values[7 - 1] == pytest.approx(58.062, abs=0.001)
    assert crg.km - crg.values[8 - 1] == pytest.approx(67.220, abs=0.001)


def test_a_header_from_the_wrong_matrix_leaves_the_chain_alone(register_words,
                                                               register_tables):
    # Page 58's header read against page 55's matrix: its index 1 says BJR
    # where the matrix says PDL, so the chain keeps its hole rather than taking
    # thirteen stations off a corridor two hundred kilometres away.
    wrong = recover_vertical_codes(register_words[58], 58)
    pdl = next(c for c in parse_corridor_block(register_tables[55], wrong)
               if c.stations[0][0] == 'PDL')
    assert [c for c, _ in pdl.stations] == \
        ['PDL', 'TAU', 'CPT', 'CPY', 'CRJ', 'CJ', 'CRG', 'GDS', 'SI']


def test_the_corridors_that_print_whole_are_untouched_by_a_codes_map(register_words,
                                                                    register_tables):
    codes = recover_vertical_codes(register_words[55], 55)
    assert parse_corridor_block(register_tables[53], codes) == \
        parse_corridor_block(register_tables[53])


def test_a_code_past_the_end_of_row_one_has_no_km_to_be_placed_at():
    # Nothing on pages 52-63 reaches this: both wrecked headers have exactly as
    # many columns as row 1 has values, plus itself. If one ever had more, the
    # extra code would have no distance anywhere in the matrix, and a chain
    # that ends one station early is better than one with an invented km.
    corridor, = parse_corridor_block(['AA 1 5,000 9,000', 'CC 3 9,000 4,000'],
                                     {1: 'AA', 2: 'BB', 3: 'CC', 4: 'DD'})
    assert corridor.stations == (('AA', 0.0), ('BB', 5.0), ('CC', 9.0))


def test_a_header_whose_indexes_are_not_1_to_n_is_not_a_header():
    # The run to the right of an O/D is only a header if its columns come out
    # numbered 1..n. That is the check that rejects a column boundary this
    # reading got wrong, rather than returning codes assembled out of one.
    header = [(10.0, 100.0, 'O/D'), (30.0, 100.0, 'A'), (32.0, 100.0, '1A'),
              (60.0, 100.0, 'B'), (62.0, 100.0, '2B')]
    assert recover_vertical_codes(header, 1) == {1: 'AA', 2: 'BB'}
    shifted = [w if w[2] not in ('1A', '2B') else
               (w[0], w[1], {'1A': '2A', '2B': '3B'}[w[2]]) for w in header]
    assert recover_vertical_codes(shifted, 1) == {}


def test_two_wrecked_matrices_on_one_page_is_said_rather_than_chosen_between():
    # Pages 52-63 wreck at most one matrix each, so a page with two is a layout
    # this has not seen. Picking one quietly would hand a corridor a header off
    # another; the page number is in the message because that is what a caller
    # printing the failure has to name.
    two = [(10.0, 100.0, 'O/D'), (30.0, 100.0, 'A'), (32.0, 100.0, '1A'),
           (200.0, 100.0, 'O/D'), (230.0, 100.0, 'C'), (232.0, 100.0, '1C')]
    with pytest.raises(ValueError, match='page 7'):
        recover_vertical_codes(two, 7)


def test_the_closest_agreement_wins_when_two_heads_are_both_in_range():
    # Two corridors printed side by side whose heads measure almost the same
    # distance to their second station. The stray row belongs to the one it
    # agrees with most closely, not to whichever was read first -- 4 m against
    # 1 m here, both inside the 10 m the register's own roundings need.
    first = Row('AAA', 1, (10.000, 20.0))
    second = Row('BBB', 1, (10.005, 20.0))
    stray = Row('ZZZ', 2, (10.004,))
    assert split_side_by_side([first, second, stray]) == \
        [[first], [second, stray]]


def test_a_code_route_followed_by_a_distance_does_not_name_a_corridor():
    # "AA-CC 12,300" is an inline pair, a two-station corridor with no matrix
    # of its own, and it shares both ends with the matrix below it. Counted as
    # a route it would win the name on print order and leave the corridor
    # claiming two stations where it has three.
    lines = ['AA-CC 12,300', 'AA - BB - CC',
             'AA 1 5,000 9,000', 'BB 2 5,000 4,000', 'CC 3 9,000 4,000']
    assert parse_inline_pairs(lines[0]) == [('AA', 'CC', 12.300)]
    corridor, = parse_corridor_block(lines)
    assert corridor.name == 'AA - BB - CC'
    assert [c for c, _ in corridor.stations] == ['AA', 'BB', 'CC']


def test_a_station_code_is_two_to_four_characters():
    # All 396 codes in the section are, and the pattern is held to it because
    # the vertical-text wreckage is mostly loose single letters: let one count
    # as a code and "G 1 5,000" is a station at 5 km.
    assert parse_matrix_rows('AA 1 5,000')[0].code == 'AA'
    assert parse_matrix_rows('TOJB 1 5,000')[0].code == 'TOJB'
    assert parse_matrix_rows('G 1 5,000') == []
    assert parse_matrix_rows('ABCDE 1 5,000') == []
