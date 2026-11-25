"""The segment library: one routed polyline per consecutive printed station pair.

The rule tests run on tiny hand-made graphs, so each shows one rule. The last
tests hold the committed outputs, gtfs/segments.txt and run_segments.json, to
the timetables they were built from.
"""
import json

from scripts.build_shapes import build_graph, hav, route_between


def write_ways(tmp_path, ways):
    """A rail.geojson of LineStrings, each given as [(lon, lat), ...]."""
    path = tmp_path / 'rail.geojson'
    path.write_text(json.dumps({'features': [
        {'geometry': {'type': 'LineString', 'coordinates': w}} for w in ways]}))
    return path


def test_a_long_straight_inside_a_way_is_track_not_a_break(tmp_path):
    # Cikampek-Cirebon maps the straight between Cipunegara and Pegadenbaru as
    # one 2,263 m edge on each track. Splitting it cut the line, and with the
    # network still joined the long way round, nothing bridged it back.
    line = [(107.80, -6.45), (107.8326, -6.45), (107.84, -6.45)]
    corners = [(107.80, -6.45), (107.80, -6.60), (107.84, -6.60), (107.84, -6.45)]
    loop = [(lo0 + (lo1 - lo0) * i / 30, la0 + (la1 - la0) * i / 30)
            for (lo0, la0), (lo1, la1) in zip(corners, corners[1:]) for i in range(30)]
    loop.append(corners[-1])
    g, _, _ = build_graph(write_ways(tmp_path, [line, loop]), 'test')
    path = route_between(g, (-6.45, 107.80), (-6.45, 107.84))
    assert sum(hav(a, b) for a, b in zip(path, path[1:])) < 4500


def test_a_jump_no_track_makes_still_splits_its_way(tmp_path):
    # A way whose next node is 11 km off is broken, not a straight.
    way = [(110.0, -7.0), (110.001, -7.0), (110.1, -7.0), (110.101, -7.0)]
    g, _, _ = build_graph(write_ways(tmp_path, [way]), 'test')
    assert not g.has_edge((-7.0, 110.001), (-7.0, 110.1))
