"""The national station graph, and a route for every relasi over it. No IO.

Task 2's corridors are 37 separate chains, each measuring its own km from its
own head. This turns them into one graph of 396 stations: a code that appears
on several corridors is ONE node, and each corridor contributes only its
consecutive deltas, never its absolute km. Rebasing on the absolute values is
the mistake the chains are laid out to invite -- Bandung is at km 89.727 on
Cikampek - Banjar and km 2.729 on the Andir branch, and either number is
meaningless outside its own corridor, while the gap to the next station along
is the same fact either way.

What comes out is connected: 396 stations on 399 nodes and 411 edges, one
component, and every one of the 89 codes the register's relasi name is in it.
The three stations with a second node are the junctions below.

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

  * A junction can be printed at two km on two lines through it. Brumbung
    is at km 163,822 on the north-coast main line and at km 162,942 on the
    Gundih line, both measured from Tegal over the same track, so Alastua -
    Brumbung reads 6.856 on one corridor and 5.976 on the other. Three
    junctions do this:

        BBG  Brumbung          ATA - BBG  6.856 main line, 5.976 Gundih line
        CNP  Cirebon Prujakan  CN - CNP   1.606 main line, 1.600 Purwokerto line
        KH   Kasugihan         MA - KH    1.966 Cilacap line, 1.723 Banjar line

    Collapsing either reading into one number biases the graph, and the
    biased edge is not harmless: build_java_network.py picks the path whose
    length best matches the register's km, and a selector like that routes
    AROUND a systematic error -- keeping the minimum at Brumbung left every
    Jakarta - Surabaya route 0.88 km short, and 16 relasi took a needless loop
    through the Pasarturi triangle to make the 0.88 km up. So each junction
    in JUNCTIONS is one node per line, the line's own node named
    "<code>@<line>", joined by the offset the register prints between the
    two readings. The shared stretch to the junction is one piece of track
    and is carried once, to the nearer reading; the line that prints the
    junction further on runs through the nearer reading to reach it. Every
    line's km then come out exactly as its own table prints them, and
    to_stations() folds the two nodes back into one call at the station.

    A disagreement JUNCTIONS does not account for is still recorded on the
    graph as a Conflict, with the shortest reading kept, so that it is
    reported rather than decided by iteration order. The register has none
    left once the three junctions are split.
"""
import collections
from dataclasses import dataclass

import networkx as nx

from .tables import Corridor

# Where an inline pair, which has no corridor to name, comes from.
INLINE = 'inline pair'
# Where the edge joining a junction's two line-nodes comes from.
JOIN = 'junction offset'
# The register prints three decimals, so a delta is rounded to three before it
# is compared: 19,515 - 10,757 is 8.758000000000001 in float, and two corridors
# that agree exactly must not be read as disagreeing by a billionth.
PLACES = 3
# Joins a station code to the line tag of its second node, "BBG@GD". No
# register code contains it, so station() always recovers the code.
SPLIT = '@'


@dataclass(frozen=True)
class Junction:
    """A station the register prints at different km on different lines.

    The occurrence of `code` on each corridor in `corridors` becomes the node
    "<code>@<line>"; its occurrence on every other corridor stays `code`.
    """
    code: str
    line: str
    corridors: tuple[str, ...]


# Page numbers are pages.json's, as everywhere in this package.
JUNCTIONS = (
    # Page 57. Brumbung is at 163,822 on TG - SMT - BBG - GBN - CU and at
    # 162,942 on TG - BBG - GD. Both tables print SMT at 149,859 and ATA at
    # 156,966, so they agree up to the junction and part at it.
    Junction('BBG', 'GD', ('TG - BBG - GD',)),
    # Page 56. Cirebon Prujakan is 1,606 past Cirebon on CKP - CNP - TG and
    # 1,600 past it on CN - CNP - PPK, the Purwokerto line that leaves there.
    Junction('CNP', 'PPK', ('CN - CNP - PPK',)),
    # Page 58. Kasugihan is 1,966 short of Maos on both Cilacap tables,
    # CP - MA - KYA and KRL - GM - MA, and 1,723 short of it on BJR - MA - KYA,
    # the Banjar line that joins there. Maos - Sikampuh is 6,418 on both.
    Junction('KH', 'BJR', ('BJR - MA - KYA',)),
)


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


@dataclass(frozen=True)
class Split:
    """One junction as the graph carries it.

    `shared` is the station both lines reach the junction from. `near` is the
    junction's node on the line that prints it closer to `shared`, and the only
    one of the two joined to `shared`; `far` is the other, `offset` km on.
    """
    code: str
    shared: str
    near: str
    far: str
    offset: float


def station(node: str) -> str:
    """The register's station code for a graph node: "BBG@GD" is BBG."""
    return node.split(SPLIT, 1)[0]


def to_stations(chain: list[tuple[str, float]],
                graph: nx.Graph) -> list[tuple[str, float]]:
    """A chain of graph nodes as a chain of stations, one call per junction.

    A route over a split junction passes both of its nodes back to back, and
    that is one station on the map, so the pair folds into one entry. Its km is
    the far node's, which is where the line actually run prints the junction:
    a main-line train runs ATA, BBG@GD, BBG and is at Brumbung 6.856 km past
    Alastua, as the main line prints it, not the Gundih line's 5.976. At either
    end of the chain the end's own km is kept instead, so a chain still starts
    at 0 and still ends at the route's whole length.
    """
    far = {split.far for split in graph.graph.get('splits', ())}
    out: list[tuple[str, float]] = []
    for at, (node, km) in enumerate(chain):
        code = station(node)
        if at and station(chain[at - 1][0]) == code and chain[at - 1][0] != node:
            if at > 1 and (node in far or at == len(chain) - 1):
                out[-1] = (code, km)
            continue
        out.append((code, km))
    return out


def build_topology(corridors: list[Corridor],
                   pairs: list[tuple[str, str, float]],
                   junctions: tuple[Junction, ...] = ()) -> nx.Graph:
    """One graph over every station the register's distance tables name.

    Nodes are station codes, except that each junction in `junctions` -- the
    register's are JUNCTIONS, and the caller passes them -- has a second node
    for the line that prints it at a different km; see the module docstring.
    An edge joins stations that are consecutive on some corridor, or that the
    register prints as a short branch of their own ("KEN-CGD 6,439"), and
    carries that gap as `weight` in km.

    graph.graph['splits'] holds a Split for every junction, and
    graph.graph['nodes'] maps each split station's code to both its nodes.
    graph.graph['conflicts'] holds a Conflict for every edge still measured two
    ways, which on this register is none.

    A junction that no corridor prints, or whose two lines share no station to
    measure the offset from, or that both lines print at the same km, raises
    ValueError: JUNCTIONS is then out of date, and a split that does nothing
    must not pass for one that does something.

    An edge is keyed on its two codes SORTED, not on a frozenset of them: the
    key has to identify an undirected pair, which either does, but iteration
    over a two-element frozenset of strings follows the hash seed, so a
    Conflict built from one would name the same edge A-B on one run and B-A on
    the next and a printed report would not be reproducible.
    """
    rename = {(corridor, j.code): f'{j.code}{SPLIT}{j.line}'
              for j in junctions for corridor in j.corridors}
    readings: dict[tuple[str, str],
                   list[tuple[float, str]]] = collections.defaultdict(list)
    for corridor in corridors:
        nodes = [(rename.get((corridor.name, code), code), km)
                 for code, km in corridor.stations]
        for (a, ka), (b, kb) in zip(nodes, nodes[1:]):
            if a != b:
                readings[tuple(sorted((a, b)))].append(
                    (round(kb - ka, PLACES), corridor.name))
    for a, b, km in pairs:
        if a != b:
            readings[tuple(sorted((a, b)))].append((round(km, PLACES), INLINE))

    splits = tuple(_split(readings, junction) for junction in junctions)

    graph, conflicts = nx.Graph(), []
    for (a, b), found in readings.items():
        kept = min(km for km, _ in found)
        if len({km for km, _ in found}) > 1:
            conflicts.append(Conflict(a, b, kept, tuple(found)))
        graph.add_edge(a, b, weight=kept)
    graph.graph['conflicts'] = tuple(conflicts)
    graph.graph['splits'] = splits
    graph.graph['nodes'] = {s.code: tuple(sorted((s.near, s.far)))
                            for s in splits}
    return graph


def _split(readings: dict, junction: Junction) -> Split:
    """Join a junction's two nodes by their offset, in `readings`, and say how.

    The two lines reach the junction from one shared station over one piece of
    track, and each line's table prints that stretch at its own length. So the
    shorter reading ends at the near node and the longer is replaced by near to
    far at the difference: the longer line's km is then the shorter's plus the
    offset, exactly as it prints it, and the stretch is carried once. Keeping
    both readings as a triangle would carry it twice, and every route through
    the junction would tie with a copy of itself that went round the triangle.
    """
    plain, line = junction.code, f'{junction.code}{SPLIT}{junction.line}'

    def neighbours(node: str) -> dict[str, list[float]]:
        out = collections.defaultdict(list)
        for (a, b), found in readings.items():
            if node in (a, b):
                out[b if a == node else a].extend(km for km, _ in found)
        return out

    from_plain, from_line = neighbours(plain), neighbours(line)
    if not from_plain or not from_line:
        raise ValueError(f'junction {plain}: no corridor prints both {plain} '
                         f'and {line}; JUNCTIONS is out of date')
    shared = sorted(set(from_plain) & set(from_line))
    if len(shared) != 1:
        raise ValueError(f'junction {plain}: its two lines should reach it from '
                         f'one shared station, not {shared or "none"}')
    shared = shared[0]
    if len(set(from_plain[shared])) > 1 or len(set(from_line[shared])) > 1:
        raise ValueError(f'junction {plain}: one line measures {shared} - '
                         f'{plain} two ways')
    to_plain, to_line = from_plain[shared][0], from_line[shared][0]
    offset = round(abs(to_plain - to_line), PLACES)
    if not offset:
        raise ValueError(f'junction {plain}: both lines print it {to_plain} km '
                         f'from {shared}, so there is nothing to split')
    near, far = (plain, line) if to_plain < to_line else (line, plain)
    del readings[tuple(sorted((shared, far)))]
    readings[tuple(sorted((near, far)))].append((offset, JOIN))
    return Split(plain, shared, near, far, offset)


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
