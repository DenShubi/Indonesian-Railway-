"""Build data/stations.csv: a coordinate for every station the 2026 timetables print.

The timetables print 466 station codes, each with its full name. Four passes
place them, in order, and each pass only ever places a code the passes before
it could not, so a name match never replaces a ref match:

  1. `osm-ref`: OSM's railway:ref, which is the KAI code the timetable prints.
  2. The printed name against OSM's names, both reduced by fetch_osm.norm() and
     compared exactly, never as a substring: "Ranji" is inside "Kranji", a
     different station on the Bekasi line. This is for a station OSM maps
     without a ref or under another code (OSM has Tonjong Baru as TOJ; 2026
     prints TOJB). An OSM station the first pass placed a code on is never
     taken by a second code's name. The main cache is tried first (`osm-name`),
     then stations_extra.csv (`osm-extra`), the stop positions, platforms and
     station buildings that are the other ways a station gets mapped. That
     cache stays out of the ref pass: it repeats a code on every platform.
  3. `km-post`: a code the distance tables print is placed at its official km
     along the routed track between the nearest stations on its corridor that
     the first two passes placed.
  4. `estimated`: a code no source places goes on the routed track between the
     nearest placed stations either side of it in the timetables' run order,
     with consecutive unplaced codes spaced evenly in printed order. It is the
     user's decision for halts OSM does not map at all; the position is always
     on the line the train runs, and is marked as an estimate, not a fact.

A code no pass can place fails the build, by name. It is never dropped.

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

SOURCES = ('osm-ref', 'osm-name', 'osm-extra', 'km-post', 'estimated')
# How a 2026 service names a published region's line: "Commuter Line Dhoho".
LINE_PREFIX = 'Commuter Line '
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
# Candidates for one name this close to the one taken are a single station's
# platforms and stop positions, and are reported as one line, not one each.
SAME_STATION_M = 1000.0


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


def regions_by_service(runs: list[dict], regions: list[dict]) -> dict[str, str]:
    """Each code a published region's own services run through -> that region.

    A region is its lines, the keys of its `colors`, and each line is the 2026
    service "Commuter Line <line>", matched whole: "Yogyakarta" is also inside
    the airport service's name. Every row of such a run counts, stop or pass. A
    bounding box will not do: Bandung's contains Jakarta, and would put fifty
    Jakarta stations in the Bandung view. The `java` pseudo-region has no lines,
    so it labels nothing. A line no service matches, or a code two regions'
    services both reach, fails: the regions are hundreds of kilometres apart, so
    either means something upstream has changed.
    """
    line_of = {f'{LINE_PREFIX}{line}': region['id']
               for region in regions for line in region.get('colors', {})}
    found = {run.get('service') for run in runs} & set(line_of)
    unmatched = sorted(service for service in line_of if service not in found)
    if unmatched:
        raise SystemExit('no 2026 run is the service of '
                         + ', '.join(f'{line_of[s]}\'s "{s}"' for s in unmatched))
    out: dict[str, str] = {}
    both = collections.defaultdict(set)
    for run in runs:
        region = line_of.get(run.get('service'))
        if region is None:
            continue
        for row in run['rows']:
            if out.setdefault(row[0], region) != region:
                both[row[0]] |= {out[row[0]], region}
    if both:
        raise SystemExit('served by two regions\' lines: '
                         + ', '.join(f'{c} ({" and ".join(sorted(r))})'
                                     for c, r in sorted(both.items())))
    return out


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
            took = (f'took {osm[i]["name"] or "(unnamed)"} {_point(osm[i])}, '
                    f'{km:.2f} km from {n}')
            spread = max(hav(_point(osm[i]), _point(osm[j])) for _, j in scored[1:])
            if spread <= SAME_STATION_M:
                report.append(f'  {code}: {source} on {len(scored)} OSM features, all within '
                              f'{spread:.0f} m of the one taken; {took}')
            else:
                others = '; '.join(f'{osm[j]["name"] or "(unnamed)"} {_point(osm[j])}, '
                                   f'{d:.2f} km from {m}' for (d, m), j in scored[1:])
                report.append(f'  {code}: {source} on {len(scored)} OSM stations; {took}; '
                              f'not {others}')
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
            where: dict, report: list[str], label: str = 'name') -> dict[str, int]:
    """Pass 2: code -> index of the unclaimed OSM station bearing its printed name.

    OSM's names are normalised here rather than read from the caches' stored
    `norm` column, which was written before norm() learnt to drop "Halte".
    """
    index = collections.defaultdict(list)
    for i, o in enumerate(osm):
        if i not in claimed and norm(o['name']):
            index[norm(o['name'])].append(i)
    wanted = {c: index[norm(name)] for c, name in codes.items() if index.get(norm(name))}
    return _match(wanted, osm, label, neighbours, where, report)


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


def by_estimate(codes: list[str], runs: list[dict], graph, where: dict,
                report: list[str], why: dict[str, str]) -> dict[str, tuple[float, float]]:
    """Pass 4: each remaining code on the routed track between its placed neighbours.

    In each run, a code's bracket is the nearest placed station either side of
    it, with the unplaced codes between them in printed order; a run the other
    way is the same bracket reversed. Where runs disagree, the bracket most runs
    print is used and the others reported. The codes in a bracket are spaced
    evenly along the track from one end to the other, which is an estimate and
    is labelled one. The track has to be the line between the two: a route that
    cannot be found, or that wanders off as build_shapes.py's detour guard
    judges one, fails the code rather than putting it somewhere else.
    """
    def fail(code, reason):
        why[code] = f'{why[code]}; {reason}' if code in why else reason

    left = set(codes)
    votes: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for run in runs:
        seq = [row[0] for row in run['rows']]
        anchors = [i for i, c in enumerate(seq) if c in where]
        for lo, hi in zip(anchors, anchors[1:]):
            inner = tuple(seq[lo + 1:hi])
            if not left.intersection(inner):
                continue
            a, b = seq[lo], seq[hi]
            key = (a, inner, b) if a <= b else (b, inner[::-1], a)
            for code in inner:
                votes[code][key] += 1

    chosen = {}
    for code in sorted(left):
        if not votes[code]:
            fail(code, 'no placed station either side of it in any run')
            continue
        ranked = sorted(votes[code].items(), key=lambda kv: (-kv[1], kv[0]))
        chosen[code] = ranked[0][0]
        if len(ranked) > 1:
            report.append(f'  {code}: runs disagree on its bracket; took '
                          + '; not '.join(f'{a}-{b} ({n} runs)' for (a, _, b), n in ranked))

    placed, lines = {}, []
    for key in sorted(set(chosen.values())):
        a, inner, b = key
        mine = [c for c in inner if chosen.get(c) == key]
        straight = hav(where[a], where[b]) / 1000
        try:
            line = route_between(graph, where[a], where[b])
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            for c in mine:
                fail(c, f'no track joins {a} and {b}')
            continue
        cum = cumulative_km(line)
        if cum[-1] > max(3 * straight, straight + 5):
            for c in mine:
                fail(c, f'the track from {a} to {b} runs {cum[-1]:.1f} km, against '
                        f'{straight:.1f} km straight')
            continue
        for i, code in enumerate(inner):
            if code in mine:
                placed[code] = place_by_km(line, cum, cum[-1] * (i + 1) / (len(inner) + 1))
        lines.append(f'  {", ".join(inner)}: between {a} and {b}, spaced along '
                     f'{cum[-1]:.3f} km of track ({straight:.3f} km straight); '
                     f'{votes[mine[0]][key]} runs')
    report.extend(lines)
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
          corridors=(), graph=None, regions=(), extra=(), runs=()) -> dict[str, dict]:
    """A row for every code in `codes` (code -> printed name), or SystemExit.

    `placed` holds coordinates already known for codes outside `codes`, which
    count as neighbours but are not written. `extra` is stations_extra.csv, for
    names only. `runs` give pass 4 its run order, each station its region by
    regions_by_service(), and the neighbours when `neighbours` is not passed. Without a `graph` neither the km post nor the
    estimate has track to go on, and both are skipped.
    """
    extra = list(extra)
    runs = list(runs)
    neighbours = neighbours if neighbours is not None else neighbours_of(runs)
    known = dict(placed or {})
    report = {'ambiguous': [], 'name': [], 'km': [], 'estimate': []}
    found: dict[str, tuple[float, float, str]] = {}

    def where():
        return {**known, **{c: (la, lo) for c, (la, lo, _) in found.items()}}

    refs = by_ref(codes, osm, neighbours, known, report['ambiguous'])
    found.update({c: (*_point(osm[i]), 'osm-ref') for c, i in refs.items()})
    for label, cache, claimed, source in (('name', osm, set(refs.values()), 'osm-name'),
                                          ('extra name', extra, set(), 'osm-extra')):
        rest = {c: n for c, n in codes.items() if c not in found}
        names = by_name(rest, cache, claimed, neighbours, where(), report['ambiguous'], label)
        for code, i in sorted(names.items()):
            o = cache[i]
            found[code] = (*_point(o), source)
            tag = f'ref {o["ref"]}' if o['ref'] else 'no ref'
            report['name'].append(f'  {code} ({source}): "{codes[code]}" is OSM\'s '
                                  f'"{o["name"]}" ({o["railway"] or "no railway tag"}, {tag})')

    why: dict[str, str] = {}
    if graph is not None:
        left = [c for c in codes if c not in found]
        posts = by_km_post(left, list(corridors), graph, where(), report['km'], why)
        found.update({c: (*p, 'km-post') for c, p in posts.items()})
        left = [c for c in codes if c not in found]
        guesses = by_estimate(left, runs, graph, where(), report['estimate'], why)
        found.update({c: (*p, 'estimated') for c, p in guesses.items()})
    else:
        why.update({c: 'no track graph to place it on' for c in codes if c not in found})

    region = regions_by_service(runs, list(regions))
    rows = {code: {'code': code, 'name': codes[code], 'lat': la, 'lon': lo,
                   'source': source, 'region': region.get(code, '')}
            for code, (la, lo, source) in found.items()}

    far = [f'  {c} ({rows[c]["source"]}): {km:.1f} km from its nearest neighbour {n}'
           for c, km, n in far_from_neighbours(where(), neighbours) if c in rows]

    for title, lines in (('ambiguous matches', report['ambiguous']),
                         ('placed by printed name', report['name']),
                         ('placed by km post', report['km']),
                         ('placed by estimate on the track', report['estimate']),
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
    extra = _load(D / 'osm' / 'java' / 'stations_extra.csv', 'scripts/fetch_osm.py java')
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
        rows = build(codes, osm, corridors=corridors, graph=graph, regions=regions,
                     extra=extra, runs=runs)
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
