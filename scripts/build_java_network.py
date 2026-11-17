"""Route every relasi the register prints over the national station graph.

Reads data/gapeka/network.json and data/gapeka/trains.json (both from
scripts/parse_gapeka.py), builds the 396-station graph, picks a route for each
of the 316 relasi and writes data/gapeka/relasi.json. No network, no PDF.

**The register's km selects the route; it is not merely a check on it.** The
obvious reading -- shortest path, then compare the length against the km the
register prints -- fails on this register, measured: 254 of 316 relasi land
within the repo's existing 3%-or-3 km slack and 32 are out by more than 10%.
The reason is that a relasi names a via point only when the register felt like
it. `SGU - PSE` prints none, yet its 819.682 km says plainly that the train
takes the southern line through Yogyakarta, 24 km longer than the coastal route
a Dijkstra finds. So the route is chosen by enumerating simple paths in
increasing length and keeping the one whose total best matches what the
register prints. That is not a heuristic: the register states the distance, and
the path through its own graph with that length is the route the train runs.

Two changes get there from the 254, and both are needed:

  * **One genuinely missing edge.** Page 54 prints the corridor
    KPB - DU - THB - MRI but its matrix stops at THB, so the distance tables
    carry no Tanah Abang - Manggarai figure and the shortest route between the
    two goes round by Kampung Bandan and Gambir: 20.082 km where the register's
    own train rows print 6.026. The number comes from those rows, and the
    register corroborates it -- Duri - Manggarai is printed at 9.663, which is
    the tables' Duri - Tanah Abang 3.637 plus exactly 6.026. add_missing_edges()
    checks that before trusting it.
  * **Selection by length.** 314 of 316 relasi then land within tolerance, the
    worst remaining gap 2.9%, and the two that do not are one relasi printed
    both ways; see RESIDUAL below. Routes recovered this way are not obscure:
    `SGU - PSE` matches as the 69th simple path and `KPB - ML` as the 191st, so
    no amount of shortest-path tie-breaking could have found either.

RESIDUAL. `YK - YIA` and `YIA - YK`, 50 trains, stay 16.8% out and no path in
the graph fixes them, because the register contradicts itself there. Its train
rows print 40.237 km; its own distance tables put Kedundang at km 35.637 of the
Kutoarjo corridor and Yogyakarta at km 63.643, so Yogyakarta to Kedundang is
28.006, and the two-station table for the airport branch prints
Kedundang - YIA as 5.465. 28.006 + 5.465 = 33.471, and 40.237 - 33.471 is
6.766, which is exactly the tables' Wates - Kedundang. The airport trains do
call at Wates, so the register's distance is measured along a route its own
tables cannot express. Nothing here invents an edge to close it: the tolerance
stays where the repo set it and the gap is reported.

Usage:  python scripts/build_java_network.py [--cap N]
"""
import collections
import json
import pathlib
import sys
import time
from heapq import heappop, heappush
from typing import NamedTuple

import networkx as nx

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from gapeka.tables import Corridor                                   # noqa: E402
from gapeka.topology import build_topology, check_length             # noqa: E402

OUT = ROOT / 'data' / 'gapeka'

# validate_gapeka.py's own slack, so one notion of "close enough" runs through
# the repo: 3% of the printed distance, or 3 km, whichever is larger.
KM_TOLERANCE = 0.03
KM_FLOOR = 3.0
# How many candidate paths a relasi may be given before the best so far is
# taken as the answer. Nothing in this edition needs more than 191.
CAP = 400

# The edge the register's distance tables omit, and the relasi that corroborates
# the number the train rows give for it. See the module docstring.
MISSING_EDGES = ((('THB', 'MRI'), ('DU', 'MRI', ())),)
# How far the corroborating relasi may be off and still corroborate: the
# register prints three decimals, so this is a rounding allowance, not slack.
CORROBORATION = 0.002


class Selection(NamedTuple):
    """A chosen route. `chain` and `gap` first, so the pair unpacks.

    `chain` is [(code, km from origin)], `gap` the signed fractional
    disagreement with the register, `km` the route's own length, `rank` where
    the chosen route came in the enumeration -- 1 is the shortest path, and
    anything above it is a route no Dijkstra would have found -- `examined` how
    many candidates were weighed and `exhausted` whether the cap stopped it,
    which is the difference between "this is the best route" and "this is the
    best of the first few hundred" and must never be silent.
    """
    chain: list[tuple[str, float]]
    gap: float
    km: float
    rank: int
    examined: int
    exhausted: bool


def within(routed: float, register: float) -> bool:
    return abs(routed - register) <= max(KM_FLOOR, KM_TOLERANCE * register)


def _chain(legs: list[list[str]], graph: nx.Graph) -> list[tuple[str, float]]:
    """The legs joined into one chain of (code, km from the origin).

    km accumulates edge by edge, exactly as topology.route_relasi() does it, so
    it stays non-decreasing even where a circular run passes a station twice.
    """
    chain = [(legs[0][0], 0.0)]
    for leg in legs:
        for a, b in zip(leg, leg[1:]):
            chain.append((b, chain[-1][1] + graph[a][b]['weight']))
    return chain


def _candidates(graph: nx.Graph, waypoints: list[str], cap: int):
    """Yield (legs, total km) for whole routes, shortest total first.

    One leg per consecutive pair of waypoints, each enumerated by
    nx.shortest_simple_paths -- Yen's algorithm, which yields a leg's simple
    paths in increasing length. A relasi with no via point has one leg and this
    is just that generator; a relasi with via points has to combine the legs,
    and combining them in increasing TOTAL length is a k-best merge: the heap
    holds one index per leg, pops the cheapest combination, and pushes the
    combinations one step along from it. Each leg is pulled from only as far as
    the heap actually reaches, so a route through three legs does not pay for
    the cross product.

    Legs are enumerated separately rather than the whole route at once because
    a via point is what makes the route non-simple: Dhoho runs SB - KTS - BL -
    SB and has to be allowed to pass Wonokromo twice, which no enumeration of
    simple SB-to-SB paths would ever offer.
    """
    legs = list(zip(waypoints, waypoints[1:]))
    walks, found, spent = [], [], []
    for a, b in legs:
        # A waypoint repeated back to back is a leg of no length, and Yen's
        # algorithm has nothing to say about a path from a node to itself.
        walks.append(iter(()) if a == b
                     else nx.shortest_simple_paths(graph, a, b, weight='weight'))
        found.append([([a], 0.0)] if a == b else [])
        spent.append(a == b)

    def pull(leg: int) -> bool:
        """One more path for this leg, or False when it has no more."""
        if spent[leg]:
            return False
        try:
            path = next(walks[leg])
        except StopIteration:
            spent[leg] = True
            return False
        found[leg].append(
            (path, sum(graph[a][b]['weight'] for a, b in zip(path, path[1:]))))
        return True

    for leg in range(len(legs)):
        if not found[leg] and not pull(leg):
            return                      # no route over this leg at all
    start = (0,) * len(legs)
    heap, seen, given = [(sum(found[i][0][1] for i in range(len(legs))), start)], {start}, 0
    while heap and given < cap:
        total, at = heappop(heap)
        given += 1
        yield [found[i][at[i]][0] for i in range(len(legs))], total
        for leg in range(len(legs)):
            step = at[:leg] + (at[leg] + 1,) + at[leg + 1:]
            if step in seen:
                continue
            while len(found[leg]) <= step[leg] and pull(leg):
                pass
            if len(found[leg]) <= step[leg]:
                continue
            seen.add(step)
            heappush(heap, (sum(found[i][step[i]][1] for i in range(len(legs))), step))


def select_path(graph: nx.Graph, origin: str, destination: str,
                via: tuple[str, ...], register_km: float,
                cap: int = CAP) -> Selection:
    """The route whose length best matches the km the register prints.

    Candidates arrive shortest total first, so once one is within `gap` of the
    register's figure every later candidate is longer than it by more than
    `gap` and cannot beat it: the search stops there, exactly, without reading
    the rest. That is why this does NOT stop at the first candidate merely
    inside the verification tolerance, which the plan suggested and which
    measurably picks worse routes -- KPB - MRI has a path at 13.038 km two
    places ahead of one at exactly the printed 14.990, and the 3 km floor
    accepts the first. Taking the true best also costs less, 8 seconds against
    19 for all 316 relasi, because it stops a short way past the answer instead
    of enumerating to the cap whenever nothing is inside the tolerance.

    Raises nx.NodeNotFound or nx.NetworkXNoPath for a relasi the graph cannot
    carry, as route_relasi() does, rather than returning a straight line.
    """
    waypoints = [origin, *via, destination]
    for code in waypoints:
        if code not in graph:
            raise nx.NodeNotFound(f'{code} is not a station in the register')
    best, examined, settled = None, 0, False
    for legs, total in _candidates(graph, waypoints, cap):
        examined += 1
        gap = abs(total - register_km)
        if best is None or gap < best[0]:
            best = (gap, legs, total, examined)
        if total - register_km > best[0]:
            settled = True              # every later candidate is longer still
            break
    if best is None:
        raise nx.NetworkXNoPath(f'no route for {" - ".join(waypoints)}')
    chain = _chain(best[1], graph)
    # Running out of candidates settles it as surely as passing the answer
    # does; only the cap cutting the search short leaves the answer in doubt.
    return Selection(chain, check_length(chain, register_km), best[2],
                     best[3], examined, not settled and examined >= cap)


def add_missing_edges(graph: nx.Graph, printed: dict,
                      missing=MISSING_EDGES) -> list[tuple[str, str, float]]:
    """Add the station pairs the distance tables leave out, from the train rows.

    `printed` maps a relasi to the km the register's train rows print for it.
    An edge is only added when the pair is genuinely absent from the tables and
    when the corroborating relasi comes out right over the new edge, so a
    mis-read number cannot slip in as topology.
    """
    added = []
    for (a, b), corroborator in missing:
        km = printed.get((a, b, ())) or printed.get((b, a, ()))
        if km is None:
            raise SystemExit(f'no train row prints a direct {a}-{b} distance')
        if graph.has_edge(a, b):
            raise SystemExit(f'{a}-{b} is already in the distance tables; '
                             'MISSING_EDGES is out of date')
        graph.add_edge(a, b, weight=km)
        added.append((a, b, km))
        origin, destination, via = corroborator
        want = printed[corroborator]
        got = select_path(graph, origin, destination, via, want).km
        if abs(got - want) > CORROBORATION:
            raise SystemExit(
                f'{a}-{b} at {km} km does not corroborate: '
                f'{" - ".join((origin, *via, destination))} routes {got:.3f} km '
                f'against the {want:.3f} the register prints')
    return added


def register_km(rows: list[dict]) -> float:
    """The km to select on, where trains on one relasi print more than one.

    Six relasi of 316 print two distances -- `ML - GMR` at 881.432 and 904.635,
    for one, which is the northern line and the southern -- so a single route
    under one key cannot satisfy both. The figure the most trains print wins,
    and the smaller on a tie; check_length() is then reported against every
    printed figure, so the disagreement with the other one stays visible rather
    than being averaged away.
    """
    counts = collections.Counter(row['km'] for row in rows)
    return min(counts, key=lambda km: (-counts[km], km))


def main() -> None:
    args = sys.argv[1:]
    cap = int(args[args.index('--cap') + 1]) if '--cap' in args else CAP

    network = json.loads((OUT / 'network.json').read_text(encoding='utf-8'))
    trains = json.loads((OUT / 'trains.json').read_text(encoding='utf-8'))['trains']
    corridors = [Corridor(c['name'], tuple((code, km) for code, km in c['stations']))
                 for c in network['corridors']]
    graph = build_topology(corridors, [tuple(p) for p in network['pairs']])
    print(f'{len(corridors)} corridors, {graph.number_of_nodes()} stations, '
          f'{graph.number_of_edges()} edges, '
          f'{nx.number_connected_components(graph)} component(s)')
    for conflict in graph.graph['conflicts']:
        print(f'  conflict {conflict.a}-{conflict.b}: kept {conflict.kept} km, '
              + ', '.join(f'{km} ({source})' for km, source in conflict.readings))

    by_relasi = collections.defaultdict(list)
    for train in trains:
        by_relasi[(train['relasi'][0], train['relasi'][1],
                   tuple(train['via']))].append(train)
    printed = {key: register_km(rows) for key, rows in by_relasi.items()}
    print(f'{len(trains)} trains over {len(by_relasi)} relasi')

    for a, b, km in add_missing_edges(graph, printed):
        print(f'  added {a}-{b} at {km} km from the train rows; the tables '
              'print no distance for it')

    started = time.time()
    routed, failed = {}, []
    for key in by_relasi:
        try:
            routed[key] = select_path(graph, key[0], key[1], key[2],
                                      printed[key], cap)
        except nx.NetworkXException as exc:
            failed.append((key, f'{type(exc).__name__}: {exc}'))
    elapsed = time.time() - started

    report = []
    for key, found in routed.items():
        kms = sorted({row['km'] for row in by_relasi[key]})
        report.append((abs(found.gap), found.gap, key, found, kms))
    report.sort(key=lambda r: (-r[0], r[2]))
    outside = [r for r in report if not within(r[3].km, printed[r[2]])]
    gross = [r for r in report if r[0] > 0.10]
    several = [r for r in report if len(r[4]) > 1]
    print(f'\nrouted {len(routed)}/{len(by_relasi)} in {elapsed:.1f}s; '
          f'{max((r[3].examined for r in report), default=0)} candidates weighed '
          f'at worst, deepest route taken was path '
          f'#{max((r[3].rank for r in report), default=0)}')
    print(f'within {KM_TOLERANCE:.0%} or {KM_FLOOR:.0f} km of the km selected on: '
          f'{len(report) - len(outside)}/{len(report)} '
          f'({100 * len(outside) / len(report):.1f}% disagreeing, budget 2%)')
    print(f'more than 10% out: {len(gross)}')
    for key, why in failed:
        print(f'  !! unroutable {" - ".join((key[0], *key[2], key[1]))}: {why}')
    for _, _, key, found, _ in report:
        if found.exhausted:
            print(f'  !! {" - ".join((key[0], *key[2], key[1]))} weighed all '
                  f'{found.examined} candidates without matching '
                  f'{printed[key]:.3f} km; took the closest at {found.km:.3f}')

    print('\nworst 15 relasi by disagreement with the km selected on:')
    for _, signed, key, found, kms in report[:15]:
        print(f'  {signed:+7.1%}  routed {found.km:8.3f}  register '
              f'{printed[key]:8.3f}  {len(by_relasi[key]):3d} train(s)  path '
              f'#{found.rank:<4d} {len(found.chain):3d} stops  '
              f'{" - ".join((key[0], *key[2], key[1]))}')

    print(f'\n{len(several)} relasi print two distances for one '
          '(origin, destination, via), so one route cannot satisfy both:')
    for _, _, key, found, kms in sorted(several, key=lambda r: r[2]):
        other = max((check_length(found.chain, km) for km in kms), key=abs)
        print(f'  {" - ".join((key[0], *key[2], key[1])):<24s} '
              f'{[f"{km:.3f}" for km in kms]} routed {found.km:8.3f}; '
              f'{other:+.1%} against the other reading')

    (OUT / 'relasi.json').write_text(json.dumps({
        'relasi': [{
            'origin': key[0], 'destination': key[1], 'via': list(key[2]),
            'km': printed[key], 'printed_km': kms, 'routed_km': round(found.km, 3),
            'gap': round(found.gap, 6), 'trains': len(by_relasi[key]),
            'rank': found.rank, 'examined': found.examined,
            'exhausted': found.exhausted,
            'chain': [[code, round(km, 3)] for code, km in found.chain],
        } for _, _, key, found, kms in sorted(report, key=lambda r: r[2])],
        'edges': sorted([a, b, graph[a][b]['weight']] for a, b in graph.edges),
        'added_edges': [[a, b, km] for (a, b), _ in MISSING_EDGES
                        for km in [graph[a][b]['weight']]],
        'conflicts': [{'a': c.a, 'b': c.b, 'kept': c.kept,
                       'readings': [[km, source] for km, source in c.readings]}
                      for c in graph.graph['conflicts']],
    }, separators=(',', ':')), encoding='utf-8')
    path = OUT / 'relasi.json'
    print(f'\n  -> {path.relative_to(ROOT)} ({path.stat().st_size / 1e3:.0f} kB)')
    if failed:
        raise SystemExit(f'{len(failed)} relasi could not be routed')


if __name__ == '__main__':
    main()
