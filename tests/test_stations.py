"""Station placement: the three passes, their order, and the checks on a wrong match.

The pass tests run on hand-made OSM rows and tiny graphs, so each shows one
rule. The last tests run the first two passes over the committed caches, which
is where the ambiguity they guard against was found.
"""
import csv
import json
import pathlib

import networkx as nx
import pytest

from conftest import committed
from scripts.build_shapes import hav, route_between
from scripts.build_stations import (build, by_name, by_ref, cumulative_km,
                                    far_from_neighbours, neighbours_of,
                                    place_by_km, printed_names, region_of)

ROOT = pathlib.Path(__file__).resolve().parents[1]


def osm(ref, name, lat, lon):
    """One row as data/osm/java/stations.csv holds it, strings and all."""
    return {'ref': ref, 'name': name, 'railway': 'station', 'lat': str(lat), 'lon': str(lon)}


OSM_YK = osm('YK', 'Yogyakarta', -7.7892387, 110.3634648)
OSM_BST_NO_REF = osm('', 'Bandara Soekarno-Hatta', -6.1272786, 106.6525156)
# data/osm/java/stations.csv, both tagged railway:ref=TGR.
OSM_TEGALLUAR = osm('TGR', 'Tegalluar Summarecon', -6.963812, 107.7146978)
OSM_TEMUGURUH = osm('TGR', 'Temuguruh', -8.3095269, 114.2018418)
SGJ_KSL = {'SGJ': (-8.3066286, 114.240545), 'KSL': (-8.30277, 114.139772)}

# Due south from the equator: a degree of latitude is 111.195 km on hav()'s
# sphere, so 25 km down the line is 0.2248 degrees.
STRAIGHT_POLYLINE = [(0.0, 0.0), (-0.25, 0.0), (-0.5, 0.0)]
STRAIGHT_KMS = cumulative_km(STRAIGHT_POLYLINE)


def line_graph(points):
    """A graph of one track through `points`, weighted as build_graph weighs."""
    g = nx.Graph()
    for a, b in zip(points, points[1:]):
        g.add_edge(a, b, weight=hav(a, b))
    return g


def test_a_code_matched_on_railway_ref_wins():
    assert build(codes={'YK': 'Yogyakarta'}, osm=[OSM_YK])['YK']['source'] == 'osm-ref'


def test_a_code_with_no_ref_is_matched_on_its_printed_name():
    rows = build(codes={'BST': 'Bandara Soekarno Hatta'}, osm=[OSM_BST_NO_REF])
    assert rows['BST']['source'] == 'osm-name'


def test_a_name_match_never_replaces_a_ref_match():
    # The printed name points at another OSM station; the ref still decides.
    tugu = osm('', 'Tugu', -7.0, 110.0)
    rows = build(codes={'YK': 'Tugu'}, osm=[OSM_YK, tugu])
    assert (rows['YK']['source'], rows['YK']['lat']) == ('osm-ref', -7.7892387)


def test_a_station_a_ref_placed_is_not_taken_again_by_a_name():
    with pytest.raises(SystemExit, match='XX'):
        build(codes={'YK': 'Yogyakarta', 'XX': 'Yogyakarta'}, osm=[OSM_YK])


def test_a_ref_on_two_stations_takes_the_one_nearest_its_neighbours():
    # OSM tags Tegalluar Summarecon (Bandung) and Temuguruh (Banyuwangi) both TGR;
    # the timetables put TGR between SGJ and KSL, so it is Temuguruh.
    rows = build(codes={'TGR': 'Temuguruh'}, osm=[OSM_TEGALLUAR, OSM_TEMUGURUH],
                 neighbours={'TGR': ['SGJ', 'KSL']}, placed=SGJ_KSL)
    assert rows['TGR']['lon'] == pytest.approx(114.2018, abs=1e-3)


def test_the_choice_does_not_depend_on_the_order_osm_lists_them():
    rows = build(codes={'TGR': 'Temuguruh'}, osm=[OSM_TEMUGURUH, OSM_TEGALLUAR],
                 neighbours={'TGR': ['SGJ', 'KSL']}, placed=SGJ_KSL)
    assert rows['TGR']['lon'] == pytest.approx(114.2018, abs=1e-3)


def test_an_ambiguous_ref_with_no_placed_neighbour_is_not_decided_by_order():
    with pytest.raises(SystemExit, match='TGR'):
        build(codes={'TGR': 'Somewhere'}, osm=[OSM_TEGALLUAR, OSM_TEMUGURUH],
              neighbours={'TGR': ['SGJ', 'KSL']})


def test_a_ref_far_from_both_its_neighbours_is_reported_but_not_moved(capsys):
    # A single wrong ref, with no duplicate to give it away: TGR on Tegalluar only.
    rows = build(codes={'TGR': 'Temuguruh'}, osm=[OSM_TEGALLUAR],
                 neighbours={'TGR': ['SGJ', 'KSL']}, placed=SGJ_KSL)
    assert rows['TGR']['lon'] == pytest.approx(107.7147, abs=1e-3)
    out = capsys.readouterr().out
    assert '1 farther than 30 km' in out and 'TGR (osm-ref)' in out


def test_a_neighbour_within_reach_is_not_reported():
    where = {'TGR': (-8.3095269, 114.2018418), **SGJ_KSL}
    assert far_from_neighbours(where, {'TGR': {'SGJ', 'KSL'}}) == []


def test_a_code_placed_by_km_post_lies_on_its_corridor():
    lat, lon = place_by_km(STRAIGHT_POLYLINE, STRAIGHT_KMS, 25.0)
    assert lat == pytest.approx(-0.2249, abs=1e-3)


def test_a_km_off_the_polyline_is_refused():
    with pytest.raises(ValueError):
        place_by_km(STRAIGHT_POLYLINE, STRAIGHT_KMS, 60.0)


def test_the_km_post_pass_places_a_station_between_its_corridor_anchors():
    # A and B are on OSM, X only in the distance table, halfway. The track is
    # 33.4 km and the table 32: X goes to its share of the way, not to km 16.
    track = [(0.0, 110.0 + i / 100) for i in range(31)]
    corridor = {'name': 'A - B', 'stations': [['A', 0.0], ['X', 16.0], ['B', 32.0]]}
    rows = build(codes={'A': 'Aa', 'X': 'Ex', 'B': 'Bee'},
                 osm=[osm('A', 'Aa', *track[0]), osm('B', 'Bee', *track[-1])],
                 corridors=[corridor], graph=line_graph(track))
    assert rows['X']['source'] == 'km-post'
    assert rows['X']['lon'] == pytest.approx(110.15, abs=1e-6)


def test_a_km_post_whose_route_is_far_off_the_table_is_not_used():
    # The track between the anchors is twice the span the table prints.
    track = [(0.0, 110.0 + i / 100) for i in range(31)]
    corridor = {'name': 'A - B', 'stations': [['A', 0.0], ['X', 5.0], ['B', 15.0]]}
    with pytest.raises(SystemExit, match='X .*routed'):
        build(codes={'A': 'Aa', 'X': 'Ex', 'B': 'Bee'},
              osm=[osm('A', 'Aa', *track[0]), osm('B', 'Bee', *track[-1])],
              corridors=[corridor], graph=line_graph(track))


def test_a_station_no_pass_can_place_fails_the_build():
    with pytest.raises(SystemExit, match='ZZZ'):
        build(codes={'ZZZ': 'Nowhere'}, osm=[])


def test_route_between_snaps_its_ends_and_takes_the_shorter_way():
    short = [(0.0, 0.0), (0.0, 0.01), (0.0, 0.02)]
    g = line_graph(short)
    nx.add_path(g, [(0.0, 0.0), (0.05, 0.01), (0.0, 0.02)])
    for a, b in [((0.0, 0.0), (0.05, 0.01)), ((0.05, 0.01), (0.0, 0.02))]:
        g[a][b]['weight'] = hav(a, b)
    assert route_between(g, (0.0001, -0.0001), (0.0, 0.0201)) == short


def test_route_between_raises_where_no_track_joins_the_ends():
    g = line_graph([(0.0, 0.0), (0.0, 0.01)])
    g.add_edge((1.0, 1.0), (1.0, 1.01), weight=hav((1.0, 1.0), (1.0, 1.01)))
    with pytest.raises(nx.NetworkXNoPath):
        route_between(g, (0.0, 0.0), (1.0, 1.0))


def test_a_station_takes_the_published_region_around_it_and_never_the_island():
    regions = json.loads((ROOT / 'data' / 'regions.json').read_text(encoding='utf-8'))
    assert region_of(-7.2652, 112.7522, regions) == 'surabaya'        # Surabaya Gubeng
    assert region_of(-6.9763, 110.4269, regions) == ''                # Semarang Tawang


def test_neighbours_are_the_codes_printed_either_side():
    runs = [{'rows': [['A', 'Aa'], ['B', 'Bee'], ['C', 'Cee']]},
            {'rows': [['D', 'Dee'], ['B', 'Bee']]}]
    assert neighbours_of(runs)['B'] == {'A', 'C', 'D'}


@pytest.fixture(scope='module')
def committed_inputs():
    timetables = ROOT / 'data' / 'gapeka' / 'timetables.json'
    stations = ROOT / 'data' / 'osm' / 'java' / 'stations.csv'
    if not timetables.exists():
        committed(timetables, 'scripts/parse_gapeka.py')
    if not stations.exists():
        committed(stations, 'scripts/fetch_osm.py java')
    runs = json.loads(timetables.read_text(encoding='utf-8'))['runs']
    return runs, list(csv.DictReader(open(stations, encoding='utf-8')))


def test_tgr_on_the_committed_caches_is_temuguruh(committed_inputs):
    runs, rows = committed_inputs
    codes, neighbours = printed_names(runs), neighbours_of(runs)
    placed = by_ref(codes, rows, neighbours, {}, [])
    assert rows[placed['TGR']]['name'] == 'Temuguruh'


def test_the_committed_caches_place_the_airport_by_name(committed_inputs):
    runs, rows = committed_inputs
    codes, neighbours = printed_names(runs), neighbours_of(runs)
    refs = by_ref(codes, rows, neighbours, {}, [])
    where = {c: (float(rows[i]['lat']), float(rows[i]['lon'])) for c, i in refs.items()}
    names = by_name({c: n for c, n in codes.items() if c not in refs}, rows,
                    set(refs.values()), neighbours, where, [])
    assert 'BST' not in refs and rows[names['BST']]['name'] == 'Bandara Soekarno-Hatta'
