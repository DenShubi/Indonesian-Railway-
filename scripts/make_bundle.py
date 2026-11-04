"""Precompute a compact animation bundle for the web visualizer.

Covers every region in one file: routes and stops carry their region id, and the
`regions` list gives the app each network's name, bounding box and any caveat
about the timetable edition it came from.
"""
import csv, json, math, pathlib
from collections import defaultdict
ROOT=pathlib.Path(__file__).resolve().parents[1]
G=ROOT/'gtfs'; D=ROOT/'data'

def hav(a,b):
    p=math.pi/180
    x=math.sin((b[0]-a[0])*p/2)**2+math.cos(a[0]*p)*math.cos(b[0]*p)*math.sin((b[1]-a[1])*p/2)**2
    return 2*6371000*math.asin(math.sqrt(x))
def secs(t):
    h,m,s=map(int,t.split(':')); return h*3600+m*60+s

regions=json.load(open(D/'regions.json',encoding='utf-8'))
station_region={r['code']:r['region'] for r in csv.DictReader(open(D/'stations.csv',encoding='utf-8'))}
stops={r['stop_id']:r for r in csv.DictReader(open(G/'stops.txt'))}
routes={r['route_id']:r for r in csv.DictReader(open(G/'routes.txt'))}
trips=list(csv.DictReader(open(G/'trips.txt')))
shp=defaultdict(list)
for r in csv.DictReader(open(G/'shapes.txt')):
    shp[r['shape_id']].append((int(r['shape_pt_sequence']),float(r['shape_pt_lat']),
                               float(r['shape_pt_lon']),float(r['shape_dist_traveled'])))
for k in shp: shp[k].sort()
stimes=defaultdict(list)
for r in csv.DictReader(open(G/'stop_times.txt')): stimes[r['trip_id']].append(r)
for v in stimes.values(): v.sort(key=lambda r:int(r['stop_sequence']))

# shapes -> flat coord arrays + cumulative distance
shapes={}; 
for sid,pts in shp.items():
    shapes[sid]={'c':[[round(lo,5),round(la,5)] for _,la,lo,_ in pts],
                 'd':[round(d,4) for *_,d in pts]}

TOL=0.15   # km: how much further than the closest approach still counts as "here"
LAT0=math.radians(-7.5)   # mid-latitude of the network, for the local metric frame

def proj(sid, la, lo, after=0.0):
    """Distance (km) along the shape where it FIRST passes this station, at or
    after `after`.

    Projects onto the shape's SEGMENTS, not just its vertices: build_shapes
    simplifies straight stretches away, so a station in the middle of one (Ngujang,
    Tulangan, Peterongan) has no vertex within kilometres even though the line
    runs right through it.

    "First" matters because the circular Dhoho and Penataran runs pass Wonokromo
    and Gubeng twice. Both passes are metres away, so taking the globally nearest
    one was a coin flip, and picking the second dragged the monotonic cursor to the
    end of the line and flattened every later stop onto the same distance.
    """
    pts = shp[sid]
    px, py = lo * 111320.0 * math.cos(LAT0), la * 110570.0
    cands = []
    for i in range(1, len(pts)):
        _, la1, lo1, d1 = pts[i - 1]
        _, la2, lo2, d2 = pts[i]
        if d2 < after - 0.001:
            continue
        ax, ay = lo1 * 111320.0 * math.cos(LAT0), la1 * 110570.0
        bx, by = lo2 * 111320.0 * math.cos(LAT0), la2 * 110570.0
        vx, vy = bx - ax, by - ay
        span = vx * vx + vy * vy
        t = 0.0 if span < 1e-9 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / span))
        along = d1 + (d2 - d1) * t
        if along < after - 0.001:
            continue
        dist = math.hypot(px - (ax + vx * t), py - (ay + vy * t))
        cands.append((dist, along))
    if not cands:
        return after
    closest = min(d for d, _ in cands)
    for dist, along in cands:               # segments come in order along the shape
        if dist <= closest + TOL * 1000:
            return along
    return cands[0][1]

out_trips=[]
for t in trips:
    sid=t['shape_id']; rows=stimes[t['trip_id']]
    ck=[]; cursor=0.0
    for r in rows:
        s=stops[r['stop_id']]
        d=proj(sid,float(s['stop_lat']),float(s['stop_lon']),cursor)
        cursor=d
        ck.append([secs(r['arrival_time']), secs(r['departure_time']), round(d,4), r['stop_id']])
    out_trips.append({'id':t['trip_id'],'n':t['trip_short_name'],'r':t['route_id'],
                      'h':t['trip_headsign'],'s':sid,'k':ck})

# per-route representative polyline = longest shape used by that route's trips
rep={}
for t in out_trips:
    sid=t['s']; L=shapes[sid]['d'][-1]
    if t['r'] not in rep or L>rep[t['r']][1]: rep[t['r']]=(sid,L)
bundle={'regions':[{'id':r['id'],'name':r['name'],'subtitle':r.get('subtitle',''),
                    'bbox':r['bbox'],'note':r.get('timetableNote','')} for r in regions],
        'routes':{k:{'name':v['route_short_name'],'color':'#'+v['route_color'],
                     'rep':rep.get(k,(None,0))[0],'g':v.get('region','')}
                  for k,v in routes.items()},
        'stops':{k:{'n':v['stop_name'],'y':round(float(v['stop_lat']),5),
                    'x':round(float(v['stop_lon']),5),'g':station_region.get(k,'')}
                 for k,v in stops.items()},
        'shapes':shapes,'trips':out_trips}
p=D/'bundle.json'; json.dump(bundle,open(p,'w'),separators=(',',':'))
print("bundle:",p.stat().st_size,"bytes")
print("trips:",len(out_trips),"shapes:",len(shapes),"stops:",len(stops))
# sanity: checkpoint distances must be non-decreasing, and span the shape
bad=0
for t in out_trips:
    ds=[c[2] for c in t['k']]
    if any(b<a-0.001 for a,b in zip(ds,ds[1:])): bad+=1; print("  NONMONO dist",t['id'])
    tot=shapes[t['s']]['d'][-1]
    if ds[-1] < tot*0.90: print(f"  SHORT {t['id']}: last stop at {ds[-1]:.1f} of {tot:.1f} km")
print("non-monotonic trips:",bad)
