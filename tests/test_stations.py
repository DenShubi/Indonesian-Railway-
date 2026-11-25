"""Station placement: the four passes, their order, and the checks on a wrong match.

The pass tests run on hand-made OSM rows and tiny graphs, so each shows one
rule. The last tests run the name passes over the committed caches, which is
where the ambiguity and the missing halts they guard against were found.
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
                                    place_by_km, printed_names, regions_by_service)

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


REGIONS = [{'id': 'surabaya', 'colors': {'Dhoho': 'E4572E'}},
           {'id': 'bandung', 'colors': {'Bandung Raya': '1F8FA8'}},
           {'id': 'java'}]


def service_run(service, *codes):
    return {'service': service, 'rows': [[c, c.title()] for c in codes]}


def test_a_region_is_the_stations_its_own_lines_run_through():
    runs = [service_run('Commuter Line Dhoho', 'SB', 'WO', 'KTS'),
            service_run('Commuter Line Bandung Raya', 'PDL', 'KAC', 'CCL'),
            service_run('Argo Bromo Anggrek', 'GMR', 'SB')]
    assert regions_by_service(runs, REGIONS) == {
        'SB': 'surabaya', 'WO': 'surabaya', 'KTS': 'surabaya',
        'PDL': 'bandung', 'KAC': 'bandung', 'CCL': 'bandung'}


def test_a_line_is_matched_whole_not_inside_another_service_name():
    regions = [{'id': 'yogyakarta', 'colors': {'Yogyakarta': 'D14836'}}]
    with pytest.raises(SystemExit, match='Commuter Line Yogyakarta'):
        regions_by_service([service_run('Commuter Line Bandara Yogyakarta', 'YK', 'YIA')],
                           regions)


def test_a_line_no_2026_service_matches_fails():
    with pytest.raises(SystemExit, match='Commuter Line Bandung Raya'):
        regions_by_service([service_run('Commuter Line Dhoho', 'SB')], REGIONS)


def test_a_station_two_regions_lines_both_reach_fails_naming_both():
    runs = [service_run('Commuter Line Dhoho', 'SB', 'XX'),
            service_run('Commuter Line Bandung Raya', 'XX', 'KAC')]
    with pytest.raises(SystemExit, match=r'XX \(bandung and surabaya\)'):
        regions_by_service(runs, REGIONS)


def test_the_committed_timetables_leave_jakarta_out_of_the_bandung_view(committed_inputs):
    runs, _ = committed_inputs
    regions = json.loads((ROOT / 'data' / 'regions.json').read_text(encoding='utf-8'))
    region = regions_by_service(runs, regions)
    assert 'AC' not in region                             # Ancol, Jakarta
    assert region['KAC'] == 'bandung'                     # Kiaracondong, Bandung Raya
    assert region['SGU'] == 'surabaya' and region['YK'] == 'yogyakarta'


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


def run(*codes):
    """A timetabled run as timetables.json holds it, reduced to its codes."""
    return {'rows': [[c, c.title()] for c in codes]}


# Ten kilometres east along the equator from A, then ten north to B.
L_TRACK = ([(0.0, i / 111.195) for i in range(11)]
           + [(i / 111.195, 10 / 111.195) for i in range(1, 11)])
A_B = [osm('A', 'Aa', *L_TRACK[0]), osm('B', 'Bee', *L_TRACK[-1])]


def test_ranji_is_not_found_inside_kranji():
    # RI Ranji (Sukabumi line) and KRI Kranji (Bekasi line) are different stations.
    kranji = osm('', 'Kranji', -6.2245133, 106.9798267)
    with pytest.raises(SystemExit, match='RI'):
        build(codes={'RI': 'Ranji'}, osm=[kranji], extra=[kranji])


def test_the_extra_cache_places_only_what_the_main_cache_could_not():
    main = [OSM_YK, osm('', 'Kalimas', -7.2198464, 112.7348088)]
    extra = [osm('', 'Stasiun Yogyakarta', -7.0, 110.0), osm('', 'Stasiun Kalimas', -7.0, 112.0),
             osm('', 'Halte Ngagel', -7.2879058, 112.748011)]
    rows = build(codes={'YK': 'Yogyakarta', 'KLM': 'Kalimas', 'NGA': 'Ngagel'},
                 osm=main, extra=extra)
    assert {c: r['source'] for c, r in rows.items()} == {
        'YK': 'osm-ref', 'KLM': 'osm-name', 'NGA': 'osm-extra'}
    assert rows['KLM']['lat'] == -7.2198464


def test_a_name_is_normalised_afresh_not_read_from_the_stored_column():
    # Both caches were written when norm() still kept "Halte".
    halt = {**osm('', 'Halte Ngagel', -7.2879058, 112.748011), 'norm': 'HALTENGAGEL'}
    assert build(codes={'NGA': 'Ngagel'}, osm=[], extra=[halt])['NGA']['source'] == 'osm-extra'


def test_unplaced_halts_are_spaced_evenly_along_the_track_in_printed_order():
    rows = build(codes={'A': 'Aa', 'X': 'Ex', 'Y': 'Why', 'B': 'Bee'}, osm=A_B,
                 runs=[run('A', 'X', 'Y', 'B'), run('B', 'Y', 'X', 'A')],
                 graph=line_graph(L_TRACK))
    assert rows['X']['source'] == rows['Y']['source'] == 'estimated'
    # A third of the 20 km of track is 6.67 km east of A, on the first leg;
    # two thirds is 3.33 km up the second.
    assert (rows['X']['lat'], rows['X']['lon'] * 111.195) == pytest.approx((0.0, 6.667), abs=1e-3)
    assert (rows['Y']['lat'] * 111.195, rows['Y']['lon'] * 111.195) == pytest.approx(
        (3.333, 10.0), abs=1e-3)


def test_an_estimate_is_on_the_track_not_across_country():
    rows = build(codes={'A': 'Aa', 'X': 'Ex', 'B': 'Bee'}, osm=A_B,
                 runs=[run('A', 'X', 'B')], graph=line_graph(L_TRACK))
    # Halfway along the track is the corner, not the midpoint of the chord.
    assert (rows['X']['lat'], rows['X']['lon'] * 111.195) == pytest.approx((0.0, 10.0), abs=1e-6)


def test_the_bracket_most_runs_print_wins_and_the_others_are_reported(capsys):
    c = osm('C', 'Cee', *L_TRACK[5])
    rows = build(codes={'A': 'Aa', 'X': 'Ex', 'B': 'Bee', 'C': 'Cee'}, osm=A_B + [c],
                 runs=[run('A', 'X', 'B'), run('B', 'X', 'A'), run('A', 'X', 'C')],
                 graph=line_graph(L_TRACK))
    assert rows['X']['lon'] * 111.195 == pytest.approx(10.0, abs=1e-6)     # A-B, not A-C
    out = capsys.readouterr().out
    assert 'X: runs disagree on its bracket; took A-B (2 runs); not A-C (1 runs)' in out


def test_an_estimate_whose_neighbours_no_track_joins_fails_the_build():
    g = line_graph(L_TRACK[:5])
    g.add_edge(L_TRACK[-2], L_TRACK[-1], weight=hav(L_TRACK[-2], L_TRACK[-1]))
    with pytest.raises(SystemExit, match='X .*no track joins A and B'):
        build(codes={'A': 'Aa', 'X': 'Ex', 'B': 'Bee'}, osm=A_B,
              runs=[run('A', 'X', 'B')], graph=g)


def test_an_estimate_never_replaces_a_km_post():
    corridor = {'name': 'A - B', 'stations': [['A', 0.0], ['X', 5.0], ['B', 20.0]]}
    rows = build(codes={'A': 'Aa', 'X': 'Ex', 'B': 'Bee'}, osm=A_B, corridors=[corridor],
                 runs=[run('A', 'X', 'B')], graph=line_graph(L_TRACK))
    assert rows['X']['source'] == 'km-post'
    assert rows['X']['lon'] * 111.195 == pytest.approx(5.0, abs=1e-3)


def test_the_committed_extra_cache_places_the_sidoarjo_halts_down_the_line(committed_inputs):
    runs, rows = committed_inputs
    path = ROOT / 'data' / 'osm' / 'java' / 'stations_extra.csv'
    if not path.exists():
        committed(path, 'scripts/fetch_osm.py java')
    extra = list(csv.DictReader(open(path, encoding='utf-8')))
    codes, neighbours = printed_names(runs), neighbours_of(runs)
    refs = by_ref(codes, rows, neighbours, {}, [])
    where = {c: (float(rows[i]['lat']), float(rows[i]['lon'])) for c, i in refs.items()}
    rest = {c: n for c, n in codes.items() if c not in refs}
    names = by_name(rest, rows, set(refs.values()), neighbours, where, [])
    rest = {c: n for c, n in rest.items() if c not in names}
    found = by_name(rest, extra, set(), neighbours, where, [])
    halts = ['NGA', 'MGR', 'JMS', 'KTL', 'STP', 'BJK', 'BDR', 'PWJ']
    lats = [float(extra[found[c]]['lat']) for c in halts]
    assert lats == sorted(lats, reverse=True)
    assert 'RI' not in found                              # never Kranji, nor Pondok Ranji
