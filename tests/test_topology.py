"""The national station graph and relasi routing.

The topologies here are synthetic, built in the test from the Corridor shape
Task 2 produces, because what needs holding down is the graph's own arithmetic
-- consecutive deltas, a junction shared between corridors, a via point, a
circular run -- and a synthetic chain says it in three stations instead of
four hundred.

Step 1 of this task, recover_vertical_codes(), lives in tables.py because the
matrix rows do, and its tests live in test_tables.py for the same reason.
"""
import networkx as nx
import pytest

from scripts.gapeka.tables import Corridor
from scripts.gapeka.topology import build_topology, check_length, route_relasi


def corridor(name: str, *stations: tuple[str, float]) -> Corridor:
    return Corridor(name, tuple(stations))


# A-B direct is 10 km; A-V-B is 30 km.
TWO_WAYS = build_topology([
    corridor('direct', ('A', 0.0), ('B', 10.0)),
    corridor('round', ('A', 0.0), ('V', 12.0), ('B', 30.0)),
], [])

# A square: A-B-C-D-A, 10 km a side.
LOOP = build_topology([
    corridor('loop', ('A', 0.0), ('B', 10.0), ('C', 20.0), ('D', 30.0)),
    corridor('close', ('D', 0.0), ('A', 10.0)),
], [])


def test_consecutive_deltas_not_absolute_km_become_edge_weights():
    g = build_topology([corridor('X', ('A', 0.0), ('B', 10.0), ('C', 25.0))], [])
    assert g['A']['B']['weight'] == 10.0
    assert g['B']['C']['weight'] == 15.0


def test_an_inline_pair_is_an_edge_of_its_own():
    g = build_topology([], [('KEN', 'CGD', 6.439)])
    assert g['KEN']['CGD']['weight'] == 6.439


# Review Focus 3
def test_a_junction_is_one_node_across_corridors():
    g = build_topology([
        corridor('X', ('A', 0.0), ('J', 10.0)),
        corridor('Y', ('J', 0.0), ('B', 5.0)),       # J at km 0 here, km 10 there
    ], [])
    assert route_relasi(g, 'A', 'B') == [('A', 0.0), ('J', 10.0), ('B', 15.0)]


def test_via_forces_the_longer_path():
    chain = route_relasi(TWO_WAYS, 'A', 'B', via=('V',))
    assert [c for c, _ in chain] == ['A', 'V', 'B']
    assert chain[-1][1] == 30.0
    # Without the via point the same pair takes the direct line, which is the
    # whole reason a relasi cannot be keyed on its endpoints alone.
    assert [c for c, _ in route_relasi(TWO_WAYS, 'A', 'B')] == ['A', 'B']


def test_each_via_point_is_taken_in_the_order_the_relasi_prints_it():
    chain = route_relasi(LOOP, 'A', 'A', via=('B', 'C', 'D'))
    assert [c for c, _ in chain] == ['A', 'B', 'C', 'D', 'A']
    assert chain[-1][1] == 40.0


# Review Focus 2
def test_a_circular_run_may_repeat_a_station_with_increasing_km():
    chain = route_relasi(LOOP, 'A', 'A', via=('C',))
    codes = [c for c, _ in chain]
    assert codes[0] == codes[-1] == 'A'
    assert codes.count('C') == 1
    kms = [km for _, km in chain]
    assert kms == sorted(kms)         # monotonic even though a code repeats
    assert kms[-1] == 40.0


def test_a_circular_run_whose_via_is_on_one_branch_doubles_back():
    # Out and back along the same spur: the station is called at twice and the
    # km keep climbing, which is what the simulation needs and what keying on
    # the endpoint pair would have collapsed to a zero-length path.
    g = build_topology([corridor('spur', ('A', 0.0), ('B', 7.0), ('C', 12.0))], [])
    chain = route_relasi(g, 'A', 'A', via=('C',))
    assert [c for c, _ in chain] == ['A', 'B', 'C', 'B', 'A']
    assert [km for _, km in chain] == [0.0, 7.0, 12.0, 17.0, 24.0]


def test_a_circular_relasi_with_no_via_point_has_nowhere_to_go():
    # None of the register's 5 circular relasi is printed without a via point,
    # and if one were, a single-station chain is the honest answer: 100% short
    # against the register's km, which is loud rather than silent.
    chain = route_relasi(LOOP, 'A', 'A')
    assert chain == [('A', 0.0)]
    assert check_length(chain, 40.0) == 1.0


def test_an_unroutable_relasi_raises_rather_than_straightening():
    g = build_topology([corridor('X', ('A', 0.0), ('B', 10.0))], [])
    with pytest.raises(nx.NetworkXException):
        route_relasi(g, 'A', 'Z')


def test_check_length_reports_the_fractional_gap():
    assert check_length([('A', 0.0), ('B', 100.0)], 110.0) == \
        pytest.approx(-100 / 110 + 1, abs=0.01)
    assert check_length([('A', 0.0), ('B', 110.0)], 100.0) == pytest.approx(-0.1)
    assert check_length([('A', 0.0), ('B', 100.0)], 100.0) == 0.0


def test_a_conflicting_edge_weight_is_recorded_and_the_shorter_one_kept():
    # ATA - BBG as the register prints it: Brumbung is at 163,822 down the
    # Tegal - Semarang - Gambringan - Cirebon Prujakan main line and at 162,942
    # on Tegal - Brumbung - Gundih, so the gap from Alastua disagrees by 880 m.
    g = build_topology([
        corridor('TG - SMT - BBG - GBN - CU', ('ATA', 156.966), ('BBG', 163.822)),
        corridor('TG - BBG - GD', ('ATA', 156.966), ('BBG', 162.942)),
    ], [])
    assert g['ATA']['BBG']['weight'] == 5.976
    conflict, = g.graph['conflicts']
    assert (conflict.a, conflict.b) == ('ATA', 'BBG')
    assert conflict.kept == 5.976
    assert conflict.readings == ((6.856, 'TG - SMT - BBG - GBN - CU'),
                                 (5.976, 'TG - BBG - GD'))


def test_the_kept_weight_does_not_depend_on_which_corridor_is_read_last():
    first = corridor('first', ('A', 0.0), ('B', 1.606))
    second = corridor('second', ('A', 0.0), ('B', 1.600))
    forwards = build_topology([first, second], [])
    backwards = build_topology([second, first], [])
    assert forwards['A']['B']['weight'] == backwards['A']['B']['weight'] == 1.600
    assert len(forwards.graph['conflicts']) == len(backwards.graph['conflicts']) == 1


def test_two_corridors_agreeing_on_an_edge_are_not_a_conflict():
    g = build_topology([
        corridor('X', ('A', 0.0), ('B', 10.0)),
        corridor('Y', ('A', 100.0), ('B', 110.0)),   # same delta, other origin
    ], [])
    assert g['A']['B']['weight'] == 10.0
    assert g.graph['conflicts'] == ()


def test_closing_the_hole_removes_the_shortcut_that_skipped_maos():
    # The hazard the Task 2 review found, and what recover_vertical_codes()
    # dissolves. Unrepaired, Banjar - Kroya runs KH -> KYA in one 14,421 km
    # edge, and every path takes it in preference to the same stretch on
    # Cilacap - Maos, which is 14,664 km over three edges and calls at Maos.
    holed = build_topology([
        corridor('BJR - MA - KYA', ('KWG', 52.694), ('KH', 77.386),
                 ('KYA', 91.807)),
        corridor('CP - MA - KYA', ('KH', 18.789), ('MA', 20.755),
                 ('SKP', 27.173), ('KYA', 33.453)),
    ], [])
    assert [c for c, _ in route_relasi(holed, 'KH', 'KYA')] == ['KH', 'KYA']

    whole = build_topology([
        corridor('BJR - MA - KYA', ('KWG', 52.694), ('JRL', 65.502),
                 ('LBG', 72.190), ('KH', 77.386), ('MA', 79.109),
                 ('SKP', 85.527), ('KYA', 91.807)),
        corridor('CP - MA - KYA', ('KH', 18.789), ('MA', 20.755),
                 ('SKP', 27.173), ('KYA', 33.453)),
    ], [])
    assert [c for c, _ in route_relasi(whole, 'KH', 'KYA')] == \
        ['KH', 'MA', 'SKP', 'KYA']


def test_a_station_repeated_inside_one_corridor_is_not_a_self_loop():
    g = build_topology([corridor('X', ('A', 0.0), ('A', 5.0), ('B', 9.0))], [])
    assert not nx.number_of_selfloops(g)
    assert g['A']['B']['weight'] == 4.0
