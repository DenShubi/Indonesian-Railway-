"""Route selection: the register's km picks the path, not the graph's geometry.

The topologies here are synthetic, as test_topology.py's are, because what
needs holding down is the choice between two routes of different lengths, and
a four-station graph says that as well as four hundred do. The real register's
own figures are checked by build_java_network.py itself, which refuses to write
an unroutable relasi and prints every disagreement sorted worst first.
"""
import networkx as nx
import pytest

from scripts.build_java_network import (add_missing_edges, register_km,
                                        select_path, within)
from scripts.gapeka.tables import Corridor
from scripts.gapeka.topology import build_topology


def corridor(name: str, *stations: tuple[str, float]) -> Corridor:
    return Corridor(name, tuple(stations))


# A - B direct is 10 km; A - V - B is 30 km. The register's km is the only
# thing that says which of the two a train takes.
TWO_WAYS = build_topology([
    corridor('direct', ('A', 0.0), ('B', 10.0)),
    corridor('round', ('A', 0.0), ('V', 12.0), ('B', 30.0)),
], [])

# A square, 10 km a side, so A back to A is 40 km whichever way round it goes.
LOOP = build_topology([
    corridor('loop', ('A', 0.0), ('B', 10.0), ('C', 20.0), ('D', 30.0)),
    corridor('close', ('D', 0.0), ('A', 10.0)),
], [])


def codes(chain) -> list[str]:
    return [code for code, _ in chain]


def test_the_register_km_takes_the_long_way_round():
    chain, gap, km, rank, _, _ = select_path(TWO_WAYS, 'A', 'B', (), 30.0)
    assert codes(chain) == ['A', 'V', 'B']
    assert km == 30.0 and gap == 0.0
    assert rank == 2                   # the shortest path was weighed and rejected


def test_the_shortest_path_wins_when_it_is_the_one_that_matches():
    chain, _, km, rank, _, _ = select_path(TWO_WAYS, 'A', 'B', (), 10.0)
    assert codes(chain) == ['A', 'B'] and km == 10.0 and rank == 1


def test_the_closest_match_wins_rather_than_the_first_tolerable_one():
    # 10 km is within the repo's 3 km floor of 12, and 30 km is not: the point
    # of selecting on length is that the floor does not get to decide.
    assert within(10.0, 12.0)
    assert select_path(TWO_WAYS, 'A', 'B', (), 12.0).km == 10.0
    assert select_path(TWO_WAYS, 'A', 'B', (), 28.0).km == 30.0


def test_a_via_point_is_called_at_in_the_order_it_is_printed():
    chain, _, km, _, _, _ = select_path(TWO_WAYS, 'A', 'B', ('V',), 30.0)
    assert codes(chain) == ['A', 'V', 'B'] and km == 30.0


def test_a_via_point_is_selected_on_the_whole_route_not_leg_by_leg():
    # Via C, each of A - C and C - D can go either way round the square, so the
    # route is a choice of PAIRS and only the total says which pair is meant.
    chain, _, km, _, _, _ = select_path(LOOP, 'A', 'D', ('C',), 30.0)
    assert codes(chain) == ['A', 'B', 'C', 'D'] and km == 30.0
    # 50 km is not the sum of either leg's shortest, nor of either's longest.
    chain, _, km, _, _, _ = select_path(LOOP, 'A', 'D', ('C',), 50.0)
    assert km == 50.0
    assert [km for _, km in chain] == sorted(km for _, km in chain)


# Review Focus 2
def test_a_circular_relasi_comes_back_with_monotonic_km():
    chain, _, km, _, _, _ = select_path(LOOP, 'A', 'A', ('C',), 40.0)
    assert codes(chain)[0] == codes(chain)[-1] == 'A'
    assert codes(chain).count('C') == 1
    assert [km for _, km in chain] == sorted(km for _, km in chain)
    assert km == 40.0


def test_exhausting_the_cap_is_reported_not_hidden():
    # Nothing in the graph is 500 km long, so the search runs to the cap.
    found = select_path(TWO_WAYS, 'A', 'B', (), 500.0, cap=1)
    assert found.exhausted is True and found.examined == 1
    # Where the answer is settled, by passing it or by running out of paths,
    # the same relasi is not flagged.
    assert select_path(TWO_WAYS, 'A', 'B', (), 500.0, cap=9).exhausted is False
    assert select_path(TWO_WAYS, 'A', 'B', (), 10.0, cap=400).exhausted is False


def test_a_station_the_register_does_not_carry_is_refused():
    with pytest.raises(nx.NodeNotFound):
        select_path(TWO_WAYS, 'A', 'ZZZ', (), 10.0)


def test_a_missing_edge_is_taken_from_the_train_rows():
    graph = build_topology([corridor('X', ('A', 0.0), ('B', 4.0))], [])
    added = add_missing_edges(graph, {('B', 'C', ()): 6.0, ('A', 'C', ()): 10.0},
                              missing=((('B', 'C'), ('A', 'C', ())),))
    assert added == [('B', 'C', 6.0)]
    assert graph['B']['C']['weight'] == 6.0


def test_a_missing_edge_the_register_does_not_corroborate_is_refused():
    graph = build_topology([corridor('X', ('A', 0.0), ('B', 4.0))], [])
    with pytest.raises(SystemExit, match='does not corroborate'):
        add_missing_edges(graph, {('B', 'C', ()): 6.0, ('A', 'C', ()): 99.0},
                          missing=((('B', 'C'), ('A', 'C', ())),))


def test_an_edge_the_tables_already_carry_is_not_added_twice():
    graph = build_topology([corridor('X', ('A', 0.0), ('B', 4.0))], [])
    with pytest.raises(SystemExit, match='out of date'):
        add_missing_edges(graph, {('A', 'B', ()): 9.0},
                          missing=((('A', 'B'), ('A', 'B', ())),))


def test_the_km_most_trains_print_is_the_one_selected_on():
    rows = [{'km': 904.635}, {'km': 881.432}, {'km': 881.432}]
    assert register_km(rows) == 881.432
    assert register_km([{'km': 904.635}, {'km': 881.432}]) == 881.432   # tie: lower
