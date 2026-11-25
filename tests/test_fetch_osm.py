"""The island-wide OSM fetch: tiling, empty tiles, and merging on OSM id.

Nothing here touches the network. Overpass is a donated public service and a
test suite is the last thing that should be calling it, so requests.post is
replaced with a recorder that also counts the calls -- which is the assertion
Review Focus 5 actually needs: an empty sea tile must cost ONE request, not a
walk through every endpoint with a sleep between each.
"""
import json

import pytest

from scripts.fetch_osm import (RAIL_QUERY, TILE, WIDE, gather, merge_rail,
                               merge_stations, norm, overpass, tiles)

JAVA = (-9.0, 105.0, -5.8, 114.7)
SEA_TILE = (-9.0, 105.0, -8.0, 106.0)
LAND_BBOX = (-8.45, 111.2, -6.8, 113.2)

WAY_7 = {'type': 'way', 'id': 7, 'tags': {'railway': 'rail'},
         'geometry': [{'lat': -7.0, 'lon': 110.0}, {'lat': -7.1, 'lon': 110.1}]}
WAY_8 = {'type': 'way', 'id': 8, 'tags': {'railway': 'rail', 'name': 'Spoor'},
         'geometry': [{'lat': -7.1, 'lon': 110.1}, {'lat': -7.2, 'lon': 110.2}]}


class Answer:
    """Just enough of requests.Response for overpass() to read."""

    def __init__(self, payload: dict, status: int = 200):
        self.text = json.dumps(payload)
        self.content = self.text.encode()
        self.status_code = status
        self.ok = status == 200

    def json(self) -> dict:
        return json.loads(self.text)


@pytest.fixture
def post(monkeypatch):
    """Record every Overpass call, and answer with whatever is set up.

    time.sleep goes too: the failure path sleeps eight seconds per endpoint,
    and a test that waits twenty-four seconds to prove a point is a test
    nobody runs.
    """
    calls, answers = [], []

    def recording(url, **kwargs):
        calls.append((url, kwargs.get('data', {}).get('data', '')))
        return answers[min(len(calls) - 1, len(answers) - 1)]

    monkeypatch.setattr('scripts.fetch_osm.requests.post', recording)
    monkeypatch.setattr('scripts.fetch_osm.time.sleep', lambda _: None)
    return calls, answers


def test_tiles_cover_the_bbox_with_no_gaps():
    covered = tiles(JAVA, step=1.0)
    assert len(covered) == 4 * 10
    assert min(s for s, _, _, _ in covered) <= -9.0
    assert max(n for _, _, n, _ in covered) >= -5.8
    assert min(w for _, w, _, _ in covered) <= 105.0
    assert max(e for _, _, _, e in covered) >= 114.7


def test_tiles_abut_without_overlapping_or_overhanging():
    covered = tiles(JAVA, step=1.0)
    assert all(-9.0 <= s < n <= -5.8 and 105.0 <= w < e <= 114.7
               for s, w, n, e in covered)
    # The area of the tiles is the area of the bbox: no gap, no double cover.
    area = sum((n - s) * (e - w) for s, w, n, e in covered)
    assert area == pytest.approx((-5.8 - -9.0) * (114.7 - 105.0))


def test_a_bbox_inside_one_tile_is_one_tile():
    assert tiles((-8.0, 111.0, -7.5, 111.5), step=1.0) == [(-8.0, 111.0, -7.5, 111.5)]


# Review Focus 5
def test_an_empty_tile_is_accepted_not_retried(post):
    calls, answers = post
    answers.append(Answer({'elements': []}))
    assert overpass(RAIL_QUERY, SEA_TILE, allow_empty=True) == {'elements': []}
    assert len(calls) == 1              # one endpoint, no retry storm


def test_an_empty_response_still_fails_when_emptiness_is_not_expected(post):
    calls, answers = post
    answers.append(Answer({'elements': []}))
    with pytest.raises(SystemExit, match='zero elements'):
        overpass(RAIL_QUERY, LAND_BBOX, allow_empty=False)
    assert len(calls) == 3              # every endpoint tried before giving up


def test_the_bbox_reaches_the_query_as_the_tile_not_the_region(post):
    calls, answers = post
    answers.append(Answer({'elements': [WAY_7]}))
    overpass(RAIL_QUERY, SEA_TILE)
    assert '(-9.0,105.0,-8.0,106.0)' in calls[0][1]


def test_ways_repeated_across_tiles_are_deduplicated_by_id():
    merged = merge_rail([{'elements': [WAY_7]}, {'elements': [WAY_7, WAY_8]}])
    assert sorted(f['properties']['id'] for f in merged['features']) == [7, 8]
    assert merged['type'] == 'FeatureCollection'


def test_a_way_with_no_usable_geometry_is_dropped():
    stub = {'type': 'way', 'id': 9, 'geometry': [{'lat': -7.0, 'lon': 110.0}]}
    assert merge_rail([{'elements': [stub, {'type': 'way', 'id': 10}]}])['features'] == []


def test_stations_repeated_across_tiles_are_deduplicated_by_type_and_id():
    node = {'type': 'node', 'id': 1, 'lat': -7.0, 'lon': 110.0}
    area = {'type': 'way', 'id': 1, 'center': {'lat': -7.0, 'lon': 110.0}}
    merged = merge_stations([{'elements': [node, area]}, {'elements': [node]}])
    assert [(el['type'], el['id']) for el in merged] == [('node', 1), ('way', 1)]


def test_a_region_exactly_at_the_threshold_is_not_tiled(post):
    calls, answers = post
    answers.append(Answer({'elements': [WAY_7]}))
    # Surabaya's bbox is 2.0 degrees of longitude to the digit, and so is the
    # subtraction that measures it: 113.2 - 111.2 is exactly 2.0 in binary.
    assert merge_rail(gather(RAIL_QUERY, LAND_BBOX))['features']
    assert len(calls) == 1


def test_the_default_tile_is_no_larger_than_a_proven_single_query_bbox():
    # Overpass is queue-bound, so the request count is the cost: ten tiles of
    # the largest side already known to answer, not forty of half it.
    assert TILE == WIDE
    assert len(tiles(JAVA)) == 10
    assert all(round(n - s, 6) <= WIDE and round(e - w, 6) <= WIDE
               for s, w, n, e in tiles(JAVA))


STATION = {'type': 'node', 'id': 42, 'lat': -6.137, 'lon': 106.815,
           'tags': {'railway': 'station', 'name': 'Jakarta Kota', 'railway:ref': 'JAKK'}}


def test_the_island_stations_go_as_one_request_not_one_per_tile(post, monkeypatch, tmp_path):
    # Stations are light -- about a thousand points for the whole island, less
    # than one railway tile -- so tiling them only queues ten times at a service
    # that is already full, and gives each of the ten a chance to fail the fetch.
    from scripts import fetch_osm
    calls, answers = post
    answers.append(Answer({'elements': [STATION]}))
    monkeypatch.setattr(fetch_osm, 'ROOT', tmp_path)
    fetch_osm.fetch_stations(tmp_path, JAVA)
    assert len(calls) == 1
    assert '(-9.0,105.0,-5.8,114.7)' in calls[0][1]      # the island, not a tile
    rows = (tmp_path / 'stations.csv').read_text(encoding='utf-8').splitlines()
    assert rows[1].startswith('JAKK,Jakarta Kota,station,')


def test_the_island_railway_is_still_tiled(post):
    calls, answers = post
    answers.append(Answer({'elements': [WAY_7]}))
    gather(RAIL_QUERY, JAVA)
    assert len(calls) == 10


def test_an_untiled_query_that_comes_back_empty_still_fails(post):
    # Untiled is not the same as allow_empty: a whole island answering with no
    # stations at all is the mirror failure, not a sea tile.
    from scripts.fetch_osm import STATION_QUERY
    calls, answers = post
    answers.append(Answer({'elements': []}))
    with pytest.raises(SystemExit):
        gather(STATION_QUERY, JAVA, tiled=False)


TIMED_OUT = {'elements': [],
             'remark': 'runtime error: Query timed out in "query" at line 3 '
                       'after 241 seconds.'}


def test_a_timed_out_tile_is_not_taken_for_sea(post):
    calls, answers = post
    answers.extend([Answer(TIMED_OUT), Answer({'elements': [WAY_7]})])
    assert overpass(RAIL_QUERY, LAND_BBOX, allow_empty=True) == {'elements': [WAY_7]}
    assert len(calls) == 2              # the remark sent it to the next endpoint


def test_a_partial_answer_with_a_remark_is_not_taken_for_a_whole_one(post):
    calls, answers = post
    partial = dict(TIMED_OUT, elements=[WAY_7])
    answers.extend([Answer(partial), Answer({'elements': [WAY_7, WAY_8]})])
    assert overpass(RAIL_QUERY, LAND_BBOX) == {'elements': [WAY_7, WAY_8]}
    assert len(calls) == 2


def test_a_remark_from_every_endpoint_fails_the_fetch(post):
    calls, answers = post
    answers.append(Answer(TIMED_OUT))
    with pytest.raises(SystemExit, match='remark'):
        overpass(RAIL_QUERY, SEA_TILE, allow_empty=True)
    assert len(calls) == 3


# Review Focus 5, where it is wired in: gather() is what tiles the island and
# passes allow_empty, so it is gather() that has to be held to it.
def test_the_island_fetch_accepts_an_empty_tile_at_one_call(post):
    calls, answers = post
    # The second tile is sea. Retried, it would cost three calls, not one.
    answers.extend([Answer({'elements': [WAY_7]}), Answer({'elements': []})]
                   + [Answer({'elements': [WAY_8]})] * 8)
    payloads = gather(RAIL_QUERY, JAVA)
    assert len(calls) == 10
    assert len({query for _, query in calls}) == 10      # ten tiles, no repeats
    assert payloads[1] == {'elements': []}
    assert sorted(f['properties']['id'] for f in merge_rail(payloads)['features']) == [7, 8]


def test_the_island_fetch_fails_when_every_tile_is_empty(post):
    calls, answers = post
    answers.append(Answer({'elements': []}))
    with pytest.raises(SystemExit, match='all 10 tiles answered with zero elements'):
        gather(RAIL_QUERY, JAVA)
    assert len(calls) == 10             # each tile accepted at its first call


def test_a_two_degree_span_that_is_not_two_in_binary_is_not_tiled(post):
    # -6.8 - -8.8 is 2.000000000000001. No region in data/regions.json has a
    # span like it -- Surabaya's 113.2 - 111.2 is exactly 2.0 -- so this is the
    # case the rounding in gather() guards against rather than one it meets.
    # Tiled, it would still be one tile, so the rounding changes only how an
    # empty answer is treated: as a single query it must hold track, and fails
    # after every endpoint has been tried, where a tile would be taken for sea.
    bbox = (-8.8, 111.2, -6.8, 113.2)
    assert bbox[2] - bbox[0] > WIDE
    calls, answers = post
    answers.append(Answer({'elements': []}))
    with pytest.raises(SystemExit, match='All Overpass endpoints failed'):
        gather(RAIL_QUERY, bbox)
    assert len(calls) == 3


def test_a_step_that_drifts_as_it_is_walked_leaves_no_sliver():
    # 105.0 plus 0.1 ten times is 105.99999999999994, and -9.0 plus 0.1 ten
    # times is -8.000000000000004: unrounded, each walk stops just short of the
    # edge and queries a sliver of its own, 121 tiles where 100 cover it.
    covered = tiles((-9.0, 105.0, -8.0, 106.0), step=0.1)
    assert len(covered) == 100
    assert covered[-1] == (-8.1, 105.9, -8.0, 106.0)


def test_the_extra_station_tags_go_as_one_request_into_their_own_file(post, monkeypatch, tmp_path):
    from scripts import fetch_osm
    calls, answers = post
    answers.append(Answer({'elements': [{'type': 'node', 'id': 9, 'lat': -6.2, 'lon': 106.8,
                                         'tags': {'railway': 'stop', 'name': 'Karet'}}]}))
    monkeypatch.setattr(fetch_osm, 'ROOT', tmp_path)
    fetch_osm.fetch_stations(tmp_path, JAVA, fetch_osm.EXTRA_STATION_QUERY, 'stations_extra.csv')
    assert len(calls) == 1 and 'train_station' in calls[0][1]
    assert (tmp_path / 'stations_extra.csv').exists()
    assert not (tmp_path / 'stations.csv').exists()        # the main cache is left alone


def test_a_leading_halte_or_stasiun_is_not_part_of_the_name():
    # OSM maps the Surabaya - Sidoarjo halts as "Halte Ngagel"; GAPEKA prints "Ngagel".
    assert norm('Halte Ngagel') == norm('Stasiun Ngagel') == norm('Ngagel') == 'NGAGEL'
    assert norm('Pondok Cina') == norm('Pondokcina')
