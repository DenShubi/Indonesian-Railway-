"""The national station graph, and a route for every relasi over it. No IO.

Task 2's corridors are 37 separate chains, each measuring its own km from its
own head. This turns them into one graph of 396 stations: a code that appears
on several corridors is ONE node, and each corridor contributes only its
consecutive deltas, never its absolute km. Rebasing on the absolute values is
the mistake the chains are laid out to invite -- Bandung is at km 89.727 on
Cikampek - Banjar and km 2.729 on the Andir branch, and either number is
meaningless outside its own corridor, while the gap to the next station along
is the same fact either way.

What comes out is connected: 396 nodes, 408 edges, one component, and every one
of the 89 codes the register's relasi name is in it.

Three things about this graph that are not obvious from the chains.

  * A relasi is keyed on (origin, destination, via), never on the pair. The
    register prints 316 distinct triples over only 304 distinct pairs, so
    twelve differ by via point alone, and the pair alone would merge routes
    that are not the same route. Five triples are circular, with origin ==
    destination -- Joglosemarkerto, the Dhoho and Penataran runs out of
    Surabaya, and the circular Cikarang workings, 32 train rows between them --
    and on the pair alone every one of those is a zero-length path. All five
    print a via point, so none of them needs one invented.

  * A code may repeat inside one routed chain. Dhoho runs SB - KTS - BL - SB
    and calls at Wonokromo and Gubeng twice, and route_relasi() emits both. The
    cumulative km is what has to stay monotonic, and it does by construction,
    because the km is accumulated edge by edge along the way rather than read
    off any corridor's absolute column. make_bundle.py's keyframe distances
    need exactly that.

  * Two corridors can disagree about one edge. nx.Graph keeps whichever weight
    is written last, so iteration order would decide the answer; instead every
    reading is collected first, the shortest is kept, and the disagreement is
    recorded on the graph as a Conflict for the caller to print. Three edges of
    408 are affected:

        ATA - BBG   6.856 vs 5.976   Brumbung at 163,822 and at 162,942
        CN - CNP    1.606 vs 1.600
        KH - MA     1.723 vs 1.966   two corridors say 1.966

    The third only appears once the vertical-text hole in Banjar - Kroya is
    closed, which is what makes KH - MA a consecutive pair at all. Keeping the
    shortest takes the minority reading there; that is deliberate, because one
    rule applied to every edge beats a majority vote that still needs a
    tie-break for the first two, and 243 m on one edge cannot change a route or
    move a relasi check that runs over hundreds of kilometres.
"""
import collections
from dataclasses import dataclass

import networkx as nx

from .tables import Corridor

# Where an inline pair, which has no corridor to name, comes from.
INLINE = 'inline pair'
# The register prints three decimals, so a delta is rounded to three before it
# is compared: 19,515 - 10,757 is 8.758000000000001 in float, and two corridors
# that agree exactly must not be read as disagreeing by a billionth.
PLACES = 3


@dataclass(frozen=True)
class Conflict:
    """One station pair the register measures two ways.

    `readings` is every (km, source) in the order the register prints them, so
    a report can name the corridors; `kept` is the weight the graph carries.
    """
    a: str
    b: str
    kept: float
    readings: tuple[tuple[float, str], ...]


def build_topology(corridors: list[Corridor],
                   pairs: list[tuple[str, str, float]]) -> nx.Graph:
    """One graph over every station the register's distance tables name.

    Nodes are station codes; an edge joins stations that are consecutive on
    some corridor, or that the register prints as a short branch of their own
    ("KEN-CGD 6,439"), and carries that gap as `weight` in km.
    graph.graph['conflicts'] holds a Conflict for every edge measured two ways.

    An edge is keyed on its two codes SORTED, not on a frozenset of them: the
    key has to identify an undirected pair, which either does, but iteration
    over a two-element frozenset of strings follows the hash seed, so a
    Conflict built from one would name the same edge A-B on one run and B-A on
    the next and a printed report would not be reproducible.
    """
    readings: dict[tuple[str, str],
                   list[tuple[float, str]]] = collections.defaultdict(list)
    for corridor in corridors:
        for (a, ka), (b, kb) in zip(corridor.stations, corridor.stations[1:]):
            if a != b:
                readings[tuple(sorted((a, b)))].append(
                    (round(kb - ka, PLACES), corridor.name))
    for a, b, km in pairs:
        if a != b:
            readings[tuple(sorted((a, b)))].append((round(km, PLACES), INLINE))

    graph, conflicts = nx.Graph(), []
    for (a, b), found in readings.items():
        kept = min(km for km, _ in found)
        if len({km for km, _ in found}) > 1:
            conflicts.append(Conflict(a, b, kept, tuple(found)))
        graph.add_edge(a, b, weight=kept)
    graph.graph['conflicts'] = tuple(conflicts)
    return graph


def route_relasi(graph: nx.Graph, origin: str, destination: str,
                 via: tuple[str, ...] = ()) -> list[tuple[str, float]]:
    """The station chain a relasi runs over, with km from the origin.

    The shortest path is taken leg by leg over [origin, *via, destination], so
    each via point the relasi names is called at in the order it is printed and
    the chain can pass the same station twice. km accumulates edge by edge and
    is therefore non-decreasing whatever the chain revisits.

    Raises nx.NodeNotFound for a code the tables do not carry and
    nx.NetworkXNoPath when no route exists, rather than returning a chain that
    cuts across country: the spec's first anti-goal is a map implying
    precision it does not have, and a silently straightened leg is that.
    """
    chain = [(origin, 0.0)]
    waypoints = [origin, *via, destination]
    for start, end in zip(waypoints, waypoints[1:]):
        path = nx.shortest_path(graph, start, end, weight='weight')
        for a, b in zip(path, path[1:]):
            chain.append((b, chain[-1][1] + graph[a][b]['weight']))
    return chain


def check_length(chain: list[tuple[str, float]], register_km: float) -> float:
    """How far a routed chain disagrees with the register's own km, signed.

    Positive when the route is shorter than the register says, negative when it
    is longer, as a fraction of the register's figure: 100 km routed against
    110 km printed is +0.091. A relasi with no printed km cannot disagree, and
    0.0 rather than a division by zero is what says so; no row in this edition
    prints km 0, so that is a guard rather than a case.
    """
    if not register_km:
        return 0.0
    return (register_km - chain[-1][1]) / register_km
