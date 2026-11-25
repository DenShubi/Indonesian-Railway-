"""Build data/stations.csv: a coordinate for every station the 2026 timetables print.

The timetables print 466 station codes, each with its full name. Three passes
place them, in order, and each pass only ever places a code the passes before
it could not, so a name match never replaces a ref match:

  1. `osm-ref`: OSM's railway:ref, which is the KAI code the timetable prints.
  2. `osm-name`: the printed name against OSM's names, both reduced by
     fetch_osm.norm(), for a station OSM maps without a ref or under another
     code (OSM has Tonjong Baru as TOJ; 2026 prints TOJB). An OSM station the
     first pass placed a code on is never taken by a second code's name.
  3. `km-post`: a code the distance tables print is placed at its official km
     along the routed track between the nearest stations on its corridor that
     the first two passes placed.

A code no pass can place fails the build, by name. It is never dropped, and its
coordinate is never guessed.

Two checks stand against a wrong match, both judged by a code's timetable
neighbours, the stations printed next to it in some run:

  * A ref or name OSM puts on more than one station is resolved to the
    candidate nearest those neighbours, never first-match-wins. OSM tags both
    Tegalluar Summarecon, near Bandung, and Temuguruh, near Banyuwangi, `TGR`;
    the timetables run TGR between Singojuruh and Kalisetail, so it is
    Temuguruh, and a first match in sorted order would have kept the station
    730 km away.
  * A placed station farther than FAR_KM from every placed neighbour is
    reported, so a wrong ref on a single station cannot pass quietly either. It
    is reported, not moved: which coordinate is right is for OSM to settle.

Every ambiguity, every name and km-post placement and every far station is
printed, so OSM's tagging can be fixed upstream.

Usage:  python scripts/build_stations.py
"""
import bisect
import collections
import csv
import json
import pathlib
import sys
import time

import networkx as nx

ROOT = pathlib.Path(__file__).resolve().parents[1]
D = ROOT / 'data'

sys.path.insert(0, str(ROOT / 'scripts'))
from build_shapes import build_graph, hav, route_between     # noqa: E402
from fetch_osm import norm                                    # noqa: E402

SOURCES = ('osm-ref', 'osm-name', 'km-post')
# The fetch's whole-island bbox. It exists for fetch_osm.py and is not a region
# the app publishes, so a station is never labelled with it.
ISLAND = 'java'
# Twice the farthest any correctly placed 2026 station lies from its nearest
# timetable neighbour: Ciledug (CLD) is 15.2 km from Sindanglaut. A station
# placed farther than this from every neighbour is almost certainly the wrong
# station -- TGR at Tegalluar is over 700 km from both of its own.
FAR_KM = 30.0
# How far the routed track between a km-post code's two anchors may differ from
# the span the distance table prints before the route is taken to be the wrong
# one, round a loop or down a branch, rather than the line the km run along. A
# wrong route is out by kilometres. A right one can still be out by a few
# hundred metres, because an OSM station point is not where the table's km post
# is and snaps to track up to a platform's length away; over Surabaya Kota -
# Pasarturi's 2.390 km that alone is 14%, hence the floor.
KM_SLACK = 0.10
KM_SLACK_FLOOR = 1.0


def printed_names(runs: list[dict]) -> dict[str, str]:
    """Each code the timetables print, with the name printed beside it."""
    return {row[0]: row[1] for run in runs for row in run['rows']}


def neighbours_of(runs: list[dict]) -> dict[str, set[str]]:
    """Each code's timetable neighbours: the codes printed next to it in any run."""
    out: dict[str, set[str]] = collections.defaultdict(set)
    for run in runs:
        codes = [row[0] for row in run['rows']]
        for a, b in zip(codes, codes[1:]):
            out[a].add(b)
            out[b].add(a)
    return dict(out)


def region_of(lat: float, lon: float, regions: list[dict]) -> str:
    """The published region whose bbox holds the point, or '' outside all three."""
    for region in regions:
        s, w, n, e = region['bbox']
        if region['id'] != ISLAND and s <= lat <= n and w <= lon <= e:
            return region['id']
    return ''


def cumulative_km(polyline: list[tuple[float, float]]) -> list[float]:
    out = [0.0]
    for a, b in zip(polyline, polyline[1:]):
        out.append(out[-1] + hav(a, b) / 1000)
    return out


def place_by_km(polyline: list[tuple[float, float]], cumulative: list[float],
                km: float) -> tuple[float, float]:
    """The point `km` along `polyline`, whose vertices sit at `cumulative` km."""
    if not cumulative[0] <= km <= cumulative[-1]:
        raise ValueError(f'km {km} is off a polyline of {cumulative[0]}-{cumulative[-1]} km')
    i = bisect.bisect_right(cumulative, km)
    if i == len(cumulative):
        return polyline[-1]
    f = (km - cumulative[i - 1]) / (cumulative[i] - cumulative[i - 1])
    (la0, lo0), (la1, lo1) = polyline[i - 1], polyline[i]
    return la0 + f * (la1 - la0), lo0 + f * (lo1 - lo0)


def _point(o: dict) -> tuple[float, float]:
    return float(o['lat']), float(o['lon'])


def _nearest(p, code, neighbours, where):
    """(km, code) of the nearest placed neighbour of `code` to `p`, or None."""
    near = [(hav(p, where[n]) / 1000, n) for n in sorted(neighbours.get(code, ()))
            if n in where]
    return min(near) if near else None


def _match(wanted: dict[str, list[int]], osm: list[dict], source: str,
           neighbours, where: dict, report: list[str]) -> dict[str, int]:
    """Each code on its one OSM candidate, or on the one nearest its neighbours.

    A code with several candidates waits until one of its neighbours is placed,
    and is retried as the others resolve. One that never gets a placed
    neighbour is left for the next pass, and said so, rather than decided by
    which candidate happens to come first.
    """
    chosen = {c: ix[0] for c, ix in wanted.items() if len(ix) == 1}
    pending = {c: ix for c, ix in wanted.items() if len(ix) > 1}
    progress = True
    while pending and progress:
        progress = False
        here = {**where, **{c: _point(osm[i]) for c, i in chosen.items()}}
        for code in sorted(pending):
            scored = [(_nearest(_point(osm[i]), code, neighbours, here), i)
                      for i in pending[code]]
            if scored[0][0] is None:
                continue
            scored.sort()
            (km, n), i = scored[0]
            others = '; '.join(f'{osm[j]["name"] or "(unnamed)"} {_point(osm[j])}, '
                               f'{d:.2f} km from {m}' for (d, m), j in scored[1:])
            report.append(f'  {code}: {source} on {len(scored)} OSM stations; took '
                          f'{osm[i]["name"] or "(unnamed)"} {_point(osm[i])}, {km:.2f} km '
                          f'from {n}; not {others}')
            chosen[code] = i
            del pending[code]
            progress = True
    for code in sorted(pending):
        report.append(f'  {code}: {source} on {len(pending[code])} OSM stations and no '
                      f'placed neighbour to choose by; left to the next pass')
    return chosen


def by_ref(codes: dict[str, str], osm: list[dict], neighbours, where: dict,
           report: list[str]) -> dict[str, int]:
    """Pass 1: code -> index of the OSM station carrying it as railway:ref."""
    wanted = collections.defaultdict(list)
    for i, o in enumerate(osm):
        if o['ref'] in codes:
            wanted[o['ref']].append(i)
    return _match(wanted, osm, 'railway:ref', neighbours, where, report)


def by_name(codes: dict[str, str], osm: list[dict], claimed: set[int], neighbours,
            where: dict, report: list[str]) -> dict[str, int]:
    """Pass 2: code -> index of the unclaimed OSM station bearing its printed name."""
    index = collections.defaultdict(list)
    for i, o in enumerate(osm):
        if i not in claimed and norm(o['name']):
            index[norm(o['name'])].append(i)
    wanted = {c: index[norm(name)] for c, name in codes.items() if index.get(norm(name))}
    return _match(wanted, osm, 'name', neighbours, where, report)


def by_km_post(codes: list[str], corridors: list[dict], graph, where: dict,
               report: list[str], why: dict[str, str]) -> dict[str, tuple[float, float]]:
    """Pass 3: each code the distance tables print, at its km between two anchors.

    The anchors are the nearest stations either side on the same corridor that
    the earlier passes placed. Where several corridors bracket a code, the
    tightest bracket is tried first, since the shorter the routed stretch the
    less room it has to have gone the wrong way. The routed length is scaled to
    the table's span, so both anchors keep their own coordinates and the code
    lands at its share of the way between them; a route more than KM_SLACK off
    that span, or KM_SLACK_FLOOR on a short one, is not used.
    """
    placed = {}
    for code in sorted(codes):
        brackets = []
        for corridor in corridors:
            km = dict((c, k) for c, k in corridor['stations'])
            if code not in km:
                continue
            k = km[code]
            before = [(kk, c) for c, kk in corridor['stations'] if kk < k and c in where]
            after = [(kk, c) for c, kk in corridor['stations'] if kk > k and c in where]
            if before and after:
                (k0, a), (k1, b) = max(before), min(after)
                brackets.append((k1 - k0, corridor['name'], a, k0, b, k1, k))
        if not brackets:
            tabled = any(code == c for corridor in corridors for c, _ in corridor['stations'])
            why[code] = ('no placed station either side of it on any corridor' if tabled
                         else 'on no distance-table corridor')
            continue
        tried = []
        for span, name, a, k0, b, k1, k in sorted(brackets):
            try:
                line = route_between(graph, where[a], where[b])
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                tried.append(f'{a}-{b} on {name}: no track joins them')
                continue
            cum = cumulative_km(line)
            if not cum[-1] or abs(cum[-1] - span) > max(KM_SLACK * span, KM_SLACK_FLOOR):
                tried.append(f'{a}-{b} on {name}: routed {cum[-1]:.3f} km '
                             f'against the table\'s {span:.3f}')
                continue
            placed[code] = place_by_km(line, [x * span / cum[-1] for x in cum], k - k0)
            report.append(f'  {code}: km {k:.3f} on {name}, between {a} (km {k0:.3f}) '
                          f'and {b} (km {k1:.3f}); track routed {cum[-1]:.3f} km '
                          f'against the table\'s {span:.3f}')
            break
        else:
            why[code] = 'every bracket failed: ' + '; '.join(tried)
    return placed


def far_from_neighbours(where: dict, neighbours, limit: float = FAR_KM):
    """[(code, km, nearest neighbour)] for each station farther than `limit`
    from every one of its placed neighbours."""
    far = []
    for code in sorted(where):
        near = _nearest(where[code], code, neighbours, where)
        if near and near[0] > limit:
            far.append((code, near[0], near[1]))
    return far


def build(codes: dict[str, str], osm: list[dict], neighbours=None, placed=None,
          corridors=(), graph=None, regions=()) -> dict[str, dict]:
    """A row for every code in `codes` (code -> printed name), or SystemExit.

    `placed` holds coordinates already known for codes outside `codes`, which
    count as neighbours but are not written. Without a `graph` the km-post pass
    has nothing to route over and is skipped.
    """
    neighbours = neighbours or {}
    known = dict(placed or {})
    report = {'ambiguous': [], 'name': [], 'km': []}

    refs = by_ref(codes, osm, neighbours, known, report['ambiguous'])
    where = {**known, **{c: _point(osm[i]) for c, i in refs.items()}}
    rest = {c: n for c, n in codes.items() if c not in refs}
    names = by_name(rest, osm, set(refs.values()), neighbours, where, report['ambiguous'])
    where.update({c: _point(osm[i]) for c, i in names.items()})
    for code, i in sorted(names.items()):
        o = osm[i]
        tag = f'ref {o["ref"]}' if o['ref'] else 'no ref'
        report['name'].append(f'  {code}: "{codes[code]}" is OSM\'s "{o["name"]}" ({tag})')

    why: dict[str, str] = {}
    left = [c for c in codes if c not in where]
    posts = {}
    if graph is not None:
        posts = by_km_post(left, list(corridors), graph, where, report['km'], why)
    else:
        why.update({c: 'no track graph to place a km post on' for c in left})

    rows = {}
    for code, name in codes.items():
        if code in refs or code in names:
            lat, lon = _point(osm[refs[code] if code in refs else names[code]])
            source = 'osm-ref' if code in refs else 'osm-name'
        elif code in posts:
            (lat, lon), source = posts[code], 'km-post'
        else:
            continue
        rows[code] = {'code': code, 'name': name, 'lat': lat, 'lon': lon,
                      'source': source, 'region': region_of(lat, lon, regions)}

    everywhere = {**known, **{c: (r['lat'], r['lon']) for c, r in rows.items()}}
    far = [f'  {c} ({rows[c]["source"]}): {km:.1f} km from its nearest neighbour {n}'
           for c, km, n in far_from_neighbours(everywhere, neighbours) if c in rows]

    for title, lines in (('ambiguous matches', report['ambiguous']),
                         ('placed by printed name', report['name']),
                         ('placed by km post', report['km']),
                         (f'farther than {FAR_KM:g} km from every placed neighbour', far)):
        print(f'{len(lines)} {title}' + (':' if lines else ''))
        for line in lines:
            print(line)
    tally = collections.Counter(r['source'] for r in rows.values())
    print(f'{len(rows)} of {len(codes)} stations placed: '
          + ', '.join(f'{tally[s]} {s}' for s in SOURCES))

    missing = [c for c in codes if c not in rows]
    if missing:
        lines = [f'  {c} ({codes[c]}), between {", ".join(sorted(neighbours.get(c, ()))) or "-"}:'
                 f' {why.get(c, "no pass matched it")}' for c in sorted(missing)]
        raise SystemExit(f'{len(missing)} of {len(codes)} stations no pass could place:\n'
                         + '\n'.join(lines))
    return rows


def _load(path: pathlib.Path, rebuild: str):
    if not path.exists():
        raise SystemExit(f'{path} is missing; it is committed - rebuild it with {rebuild}')
    if path.suffix == '.csv':
        return list(csv.DictReader(open(path, encoding='utf-8')))
    return json.load(open(path, encoding='utf-8'))


def main() -> None:
    runs = _load(D / 'gapeka' / 'timetables.json', 'scripts/parse_gapeka.py')['runs']
    osm = _load(D / 'osm' / 'java' / 'stations.csv', 'scripts/fetch_osm.py java')
    corridors = _load(D / 'gapeka' / 'network.json', 'scripts/parse_gapeka.py')['corridors']
    regions = _load(D / 'regions.json', 'git checkout data/regions.json')
    rail = D / 'osm' / 'java' / 'rail.geojson'
    if not rail.exists():
        raise SystemExit(f'{rail} is missing; it is committed - rebuild it with '
                         'scripts/fetch_osm.py java')

    codes = printed_names(runs)
    t0 = time.perf_counter()
    graph, _, _ = build_graph(rail, 'java')
    t1 = time.perf_counter()
    print(f'island graph built in {t1 - t0:.1f} s')
    try:
        rows = build(codes, osm, neighbours_of(runs), corridors=corridors, graph=graph,
                     regions=regions)
    finally:
        print(f'stations placed in {time.perf_counter() - t1:.1f} s')

    with open(D / 'stations.csv', 'w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=['code', 'name', 'lat', 'lon', 'source', 'region'])
        writer.writeheader()
        for code in sorted(rows):
            r = rows[code]
            writer.writerow({**r, 'lat': f'{r["lat"]:.7f}', 'lon': f'{r["lon"]:.7f}'})
    print(f'{len(rows)} stations -> data/stations.csv')


if __name__ == '__main__':
    main()
