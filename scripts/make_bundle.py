"""Precompute a compact animation bundle for the web visualizer."""
import csv, json, math, pathlib
from collections import defaultdict
G=pathlib.Path('/home/claude/jtv/gtfs'); D=pathlib.Path('/home/claude/jtv/data')

def hav(a,b):
    p=math.pi/180
    x=math.sin((b[0]-a[0])*p/2)**2+math.cos(a[0]*p)*math.cos(b[0]*p)*math.sin((b[1]-a[1])*p/2)**2
    return 2*6371000*math.asin(math.sqrt(x))
def secs(t):
    h,m,s=map(int,t.split(':')); return h*3600+m*60+s

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

def proj(sid, la, lo, after=0.0):
    """distance (km) along shape of nearest vertex at or after `after`"""
    best=None
    for (_,sla,slo,sd) in shp[sid]:
        if sd < after-0.001: continue
        m=hav((la,lo),(sla,slo))
        if best is None or m<best[0]: best=(m,sd)
    return best[1] if best else after

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
bundle={'routes':{k:{'name':v['route_short_name'],'color':'#'+v['route_color'],
                     'rep':rep.get(k,(None,0))[0]} for k,v in routes.items()},
        'stops':{k:{'n':v['stop_name'],'y':round(float(v['stop_lat']),5),
                    'x':round(float(v['stop_lon']),5)} for k,v in stops.items()},
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
