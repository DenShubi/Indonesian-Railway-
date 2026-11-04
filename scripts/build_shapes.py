"""Route every trip along the real OSM rail network to produce gtfs/shapes.txt.

One graph per region, built from that region's data/osm/<region>/rail.geojson:
regions are hundreds of kilometres apart, so a single graph would invite the
component bridging below to connect networks that have nothing to do with each
other.

Per region the steps are: build a graph from the way geometry, stitch
near-coincident endpoints, bridge the holes OpenStreetMap leaves in otherwise
continuous lines, snap each station to its nearest graph node, then shortest-path
between consecutive stations with a detour guard. Output is simplified with
Ramer-Douglas-Peucker, with station nodes pinned so they survive.
"""
import csv, json, math, pathlib, sys
from collections import defaultdict

import networkx as nx
import numpy as np
from scipy.spatial import cKDTree

ROOT = pathlib.Path(__file__).resolve().parents[1]
D = ROOT / 'data'
G = ROOT / 'gtfs'

STITCH = 25.0       # metres: join way endpoints this close
MAXJUMP = 2000.0    # metres: split a way here instead of bridging
BRIDGE = 6000.0     # metres: span a hole in the OSM data between components
RDP = 8.0           # metres: output simplification


def hav(a, b):
    p = math.pi / 180
    x = (math.sin((b[0] - a[0]) * p / 2) ** 2
         + math.cos(a[0] * p) * math.cos(b[0] * p) * math.sin((b[1] - a[1]) * p / 2) ** 2)
    return 2 * 6371000 * math.asin(math.sqrt(x))


def build_graph(rail_path, label):
    """Rail ways -> connected graph of (lat, lon) nodes."""
    gj = json.load(open(rail_path, encoding='utf-8'))
    g = nx.Graph()
    for f in gj['features']:
        if f['geometry']['type'] != 'LineString':
            continue
        pts = [(round(la, 6), round(lo, 6)) for lo, la in f['geometry']['coordinates']]
        if len(pts) < 2:
            continue
        run = [pts[0]]
        for p in pts[1:]:
            if p == run[-1]:
                continue
            if hav(run[-1], p) > MAXJUMP:
                run = [p]
                continue
            run.append(p)
            a, b = run[-2], run[-1]
            d = hav(a, b)
            if g.has_edge(a, b):
                g[a][b]['weight'] = min(g[a][b]['weight'], d)
            else:
                g.add_edge(a, b, weight=d)

    nodes = list(g.nodes())
    arr = np.array(nodes)
    lat0 = math.radians(float(np.mean(arr[:, 0])))
    plane = lambda a: np.c_[a[:, 0] * 111320.0, a[:, 1] * 111320.0 * math.cos(lat0)]

    added = 0
    tree = cKDTree(plane(arr))
    for i, j in tree.query_pairs(r=STITCH):
        a, b = nodes[i], nodes[j]
        if not g.has_edge(a, b):
            g.add_edge(a, b, weight=max(hav(a, b), 0.1))
            added += 1

    comps = sorted(nx.connected_components(g), key=len, reverse=True)
    print(f'  {label}: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges '
          f'({added} stitched), {len(comps)} components', file=sys.stderr)

    # Attach every island to the trunk at its closest approach. OpenStreetMap maps
    # some lines in disconnected pieces (Lamongan-Duduk-Cerme, Kandangan-Indro),
    # and without this a trip gives up on the whole station-to-station leg instead
    # of only the unmapped metres.
    trunk = set(comps[0])
    rest = [set(c) for c in comps[1:]]
    bridged = []
    while rest:
        tnodes = np.array(sorted(trunk))
        ttree = cKDTree(plane(tnodes))
        best = None
        for ci, c in enumerate(rest):
            cn = np.array(sorted(c))
            d, idx = ttree.query(plane(cn), k=1)
            i = int(np.argmin(d))
            if best is None or d[i] < best[0]:
                best = (float(d[i]), ci, tuple(cn[i]), tuple(tnodes[idx[i]]))
        gap, ci, a, b = best
        if gap > BRIDGE:
            break
        g.add_edge(a, b, weight=gap)
        bridged.append(round(gap))
        trunk |= rest.pop(ci)
    if bridged:
        print(f'  {label}: bridged {len(bridged)} holes, largest {max(bridged)} m',
              file=sys.stderr)
    return g, lat0, plane


def snap_stations(g, stations, lat0, plane):
    nodes = list(g.nodes())
    arr = np.array(nodes)
    tree = cKDTree(plane(arr))
    snap, far = {}, []
    for code, (la, lo) in stations.items():
        d, idx = tree.query([la * 111320.0, lo * 111320.0 * math.cos(lat0)], k=1)
        snap[code] = tuple(arr[idx])
        if d > 600:
            far.append((code, round(d)))
    return snap, far


def rdp(pts, eps, lat0, pinned):
    """Simplify, but never drop a pinned point (the station nodes)."""
    if len(pts) < 3:
        return pts

    def perp(p, a, b):
        if a == b:
            return hav(p, a)
        k = math.cos(lat0)
        ax, ay = a[1] * k, a[0]
        bx, by = b[1] * k, b[0]
        px, py = p[1] * k, p[0]
        num = abs((bx - ax) * (ay - py) - (ax - px) * (by - ay))
        den = math.hypot(bx - ax, by - ay)
        return (num / den) * 111320.0 if den else hav(p, a)

    keep = [p in pinned for p in pts]
    keep[0] = keep[-1] = True
    anchors = [i for i, k in enumerate(keep) if k]
    stack = [(anchors[i], anchors[i + 1]) for i in range(len(anchors) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        dm, im = -1, i
        for k in range(i + 1, j):
            d = perp(pts[k], pts[i], pts[j])
            if d > dm:
                dm, im = d, k
        if dm > eps:
            keep[im] = True
            stack += [(i, im), (im, j)]
    return [p for p, k in zip(pts, keep) if k]


def main() -> None:
    regions = json.load(open(D / 'regions.json', encoding='utf-8'))
    stations_all = list(csv.DictReader(open(D / 'stations.csv', encoding='utf-8')))
    routes = {r['route_id']: r for r in csv.DictReader(open(G / 'routes.txt', encoding='utf-8'))}
    trips = list(csv.DictReader(open(G / 'trips.txt', encoding='utf-8')))
    stimes = defaultdict(list)
    for r in csv.DictReader(open(G / 'stop_times.txt', encoding='utf-8')):
        stimes[r['trip_id']].append(r)
    for v in stimes.values():
        v.sort(key=lambda r: int(r['stop_sequence']))

    rows, tshape, straightened = [], {}, []
    shape_no = 0

    for region in regions:
        rid = region['id']
        mine = [t for t in trips if routes[t['route_id']].get('region') == rid]
        if not mine:
            continue
        rail = D / 'osm' / rid / 'rail.geojson'
        if not rail.exists():
            print(f'  !! no rail data for {rid}; run scripts/fetch_osm.py {rid}', file=sys.stderr)
            continue

        g, lat0, plane = build_graph(rail, rid)
        used = {r['stop_id'] for t in mine for r in stimes[t['trip_id']]}
        stations = {s['code']: (float(s['lat']), float(s['lon']))
                    for s in stations_all if s['code'] in used}
        snap, far = snap_stations(g, stations, lat0, plane)
        if far:
            print(f'  {rid}: stations more than 600 m from any track: {far}', file=sys.stderr)

        cache = {}

        def seg(a, b):
            if (a, b) in cache:
                return cache[(a, b)]
            straight = hav(snap[a], snap[b])
            try:
                p = nx.shortest_path(g, snap[a], snap[b], weight='weight')
                length = sum(hav(p[i - 1], p[i]) for i in range(1, len(p)))
                if length > max(3.0 * straight, straight + 5000):
                    straightened.append((rid, a, b, round(straight / 1000, 1),
                                         round(length / 1000, 1)))
                    p = [snap[a], snap[b]]
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                straightened.append((rid, a, b, round(straight / 1000, 1), None))
                p = [snap[a], snap[b]]
            cache[(a, b)] = p
            return p

        seen = {}
        for t in mine:
            key = tuple(r['stop_id'] for r in stimes[t['trip_id']])
            if key not in seen:
                shape_no += 1
                sid = f'shp_{shape_no:03d}'
                poly = []
                for a, b in zip(key, key[1:]):
                    p = seg(a, b)
                    poly.extend(p[1:] if poly and poly[-1] == p[0] else p)
                clean = [poly[0]]
                for p in poly[1:]:
                    if p != clean[-1]:
                        clean.append(p)
                clean = rdp(clean, RDP, lat0, {snap[c] for c in key})
                seen[key] = sid
                dist = 0.0
                for i, p in enumerate(clean):
                    if i:
                        dist += hav(clean[i - 1], p)
                    rows.append({'shape_id': sid, 'shape_pt_lat': f'{p[0]:.6f}',
                                 'shape_pt_lon': f'{p[1]:.6f}', 'shape_pt_sequence': i + 1,
                                 'shape_dist_traveled': f'{dist / 1000:.3f}'})
            tshape[t['trip_id']] = seen[key]
        print(f'  {rid}: {len(seen)} shapes for {len(mine)} trips', file=sys.stderr)

    with open(G / 'shapes.txt', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['shape_id', 'shape_pt_lat', 'shape_pt_lon',
                                          'shape_pt_sequence', 'shape_dist_traveled'])
        w.writeheader()
        w.writerows(rows)

    fields = [c for c in trips[0] if c != 'shape_id'] + ['shape_id']
    for t in trips:
        t['shape_id'] = tshape.get(t['trip_id'], '')
    with open(G / 'trips.txt', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(trips)

    print(f'\nshapes={len(set(tshape.values()))}  shape points={len(rows)}')
    if straightened:
        print(f'station pairs left as straight lines: {len(straightened)}')
        for s in straightened[:10]:
            print('   ', s)
    else:
        print('every station pair routed along real track')


if __name__ == '__main__':
    main()
