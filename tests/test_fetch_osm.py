"""The island-wide OSM fetch: tiling, empty tiles, and merging on OSM id.

Nothing here touches the network. Overpass is a donated public service and a
test suite is the last thing that should be calling it, so requests.post is
replaced with a recorder that also counts the calls -- which is the assertion
Review Focus 5 actually needs: an empty sea tile must cost ONE request, not a
walk through every endpoint with a sleep between each.
"""
import json

import pytest

from scripts.fetch_osm import (RAIL_QUERY, gather, merge_rail, merge_stations,
                               overpass, tiles)

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
    # Surabaya's bbox is 2.0 degrees of longitude to the digit, and the
    # subtraction that measures it is not exact in binary.
    assert merge_rail(gather(RAIL_QUERY, LAND_BBOX))['features']
    assert len(calls) == 1
