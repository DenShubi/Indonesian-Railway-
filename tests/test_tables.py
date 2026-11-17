"""The register's JARAK ANTAR STASIUN corridor matrices.

Every line fed to the parser here is verbatim from
tests/fixtures/register_tables.txt, which holds pages 52, 55 and 62 of the
register. Each test names the page it leans on and the quirk that page carries.
"""
from scripts.gapeka.tables import (parse_corridor_block, parse_inline_pairs,
                                   parse_matrix_rows, split_side_by_side)


def test_station_order_comes_from_row_labels_not_the_header(register_tables):
    # Page 55's header arrives interleaved: "O/D C 1KP C 2BR PW 3K ..."
    corridor = parse_corridor_block(register_tables[55])[0]
    assert [c for c, _ in corridor.stations][:3] == ['CKP', 'CBR', 'PWK']
    assert len(corridor.stations) == 42


def test_the_interleaved_header_yields_no_rows_of_its_own(register_tables):
    header = next(ln for ln in register_tables[55] if ln.startswith('O/D C 1KP'))
    assert parse_matrix_rows(header) == []


def test_cumulative_km_comes_from_the_first_value_in_each_row(register_tables):
    corridor = parse_corridor_block(register_tables[55])[0]
    assert corridor.stations[0] == ('CKP', 0.0)
    assert corridor.stations[1][1] == 7.636
    assert corridor.stations[-1][1] == 245.562


def test_a_number_the_page_edge_truncated_is_ignored(register_tables):
    # The CKP row runs off the page and its last token is a bare "177", the
    # head of a truncated "177,378". Station 32's own row prints it in full.
    corridor = parse_corridor_block(register_tables[55])[0]
    assert ('CAA', 177.378) in corridor.stations
    assert 177.0 not in [km for _, km in corridor.stations]


def test_row_one_first_value_cross_checks_the_head(register_tables):
    # row 1's first value is d(1,2) and must equal station 2's cumulative km
    for corridor in parse_corridor_block(register_tables[55]):
        assert corridor.stations[1][1] > 0


def test_cumulative_km_is_strictly_increasing(register_tables):
    for corridor in parse_corridor_block(register_tables[52]):
        kms = [km for _, km in corridor.stations]
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
    assert left.values[0] == 5.740 and right.values[0] == 14.593


def test_columns_run_together_are_split(register_tables):
    # Page width squeezes adjacent columns until extract_text() yields them as
    # one token; page 62's Wlingi matrix does it on every wide row.
    line = next(ln for ln in register_tables[62] if ln.startswith('SBE 1'))
    squashed = line.replace('9,246 10,176', '9,24610,176')
    assert parse_matrix_rows(squashed)[0].values == \
        parse_matrix_rows(line)[0].values


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
