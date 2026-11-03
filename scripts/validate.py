"""Structural + domain validation of the generated GTFS feed."""
import csv, io, zipfile, math, sys
from collections import defaultdict
import pathlib
Z=pathlib.Path(__file__).resolve().parents[1]/'data'/'gtfs_wilayah8_surabaya.zip'
zf=zipfile.ZipFile(Z)
def rd(n): return list(csv.DictReader(io.TextIOWrapper(zf.open(n),'utf-8')))

REQ={'agency.txt':['agency_name','agency_url','agency_timezone'],
     'stops.txt':['stop_id','stop_name','stop_lat','stop_lon'],
     'routes.txt':['route_id','route_type'],
     'trips.txt':['route_id','service_id','trip_id'],
     'stop_times.txt':['trip_id','arrival_time','departure_time','stop_id','stop_sequence'],
     'calendar.txt':['service_id','monday','start_date','end_date']}
E=[];W=[]
have=set(zf.namelist())
for f,cols in REQ.items():
    if f not in have: E.append(f"missing file {f}"); continue
    hdr=rd(f)[0].keys() if rd(f) else []
    for c in cols:
        if c not in hdr: E.append(f"{f}: missing column {c}")
if E:
    print("ERRORS:"); [print('  -',e) for e in E]; sys.exit(1)

stops=rd('stops.txt'); routes=rd('routes.txt'); trips=rd('trips.txt')
st=rd('stop_times.txt'); cal=rd('calendar.txt')

sid={s['stop_id'] for s in stops}; rid={r['route_id'] for r in routes}
tid={t['trip_id'] for t in trips}; svc={c['service_id'] for c in cal}
if len(sid)!=len(stops): E.append("duplicate stop_id")
if len(tid)!=len(trips): E.append("duplicate trip_id")
for t in trips:
    if t['route_id'] not in rid: E.append(f"trip {t['trip_id']}: unknown route_id")
    if t['service_id'] not in svc: E.append(f"trip {t['trip_id']}: unknown service_id")
for r in routes:
    if r['route_type'] not in {'0','1','2','3','4','5','6','7','11','12'}:
        E.append(f"route {r['route_id']}: bad route_type")
# coords
for s in stops:
    la,lo=float(s['stop_lat']),float(s['stop_lon'])
    if not(-90<=la<=90 and -180<=lo<=180): E.append(f"stop {s['stop_id']}: coords out of range")
    if not(-8.8<=la<=-6.5 and 110.5<=lo<=114.5): W.append(f"stop {s['stop_id']}: outside East Java bbox")

def secs(t):
    h,m,s=map(int,t.split(':')); return h*3600+m*60+s
def hav(a,b):
    (la1,lo1),(la2,lo2)=a,b
    p=math.pi/180; dla=(la2-la1)*p; dlo=(lo2-lo1)*p
    x=math.sin(dla/2)**2+math.cos(la1*p)*math.cos(la2*p)*math.sin(dlo/2)**2
    return 2*6371000*math.asin(math.sqrt(x))
C={s['stop_id']:(float(s['stop_lat']),float(s['stop_lon'])) for s in stops}

bytrip=defaultdict(list)
for r in st:
    if r['trip_id'] not in tid: E.append(f"stop_times: unknown trip {r['trip_id']}")
    if r['stop_id'] not in sid: E.append(f"stop_times: unknown stop {r['stop_id']}")
    bytrip[r['trip_id']].append(r)

fast=[]; dists=[]
for t,rows in bytrip.items():
    rows.sort(key=lambda r:int(r['stop_sequence']))
    if len(rows)<2: E.append(f"trip {t}: fewer than 2 stops")
    seqs=[int(r['stop_sequence']) for r in rows]
    if len(set(seqs))!=len(seqs): E.append(f"trip {t}: duplicate stop_sequence")
    prev=None
    for r in rows:
        a,d=secs(r['arrival_time']),secs(r['departure_time'])
        if d<a: E.append(f"trip {t} seq{r['stop_sequence']}: departure before arrival")
        if prev is not None:
            pa,pd,pstop=prev
            if a<pd: E.append(f"trip {t} seq{r['stop_sequence']}: time goes backwards")
            dt=a-pd
            m=hav(C[pstop],C[r['stop_id']]); dists.append(m)
            if dt>0 and m>50:
                kmh=m/dt*3.6
                if kmh>160: fast.append((t,pstop,r['stop_id'],round(m/1000,1),dt,round(kmh)))
        prev=(a,d,r['stop_id'])
for t in tid:
    if t not in bytrip: E.append(f"trip {t}: no stop_times")

print(f"ERRORS: {len(E)}   WARNINGS: {len(W)}")
for e in E[:25]: print('  E',e)
for w in W[:10]: print('  W',w)
if fast:
    print(f"\nimplausible segment speeds (>160 km/h): {len(fast)}")
    for f in fast[:12]: print('   ',f)
else:
    print("\nsegment speeds: all plausible (<=160 km/h)")
print(f"\nfeed: stops={len(stops)} routes={len(routes)} trips={len(trips)} stop_times={len(st)}")
if dists:
    dists.sort()
    print(f"inter-stop distance  min={dists[0]:.0f}m  median={dists[len(dists)//2]:.0f}m  max={dists[-1]:.0f}m")
sys.exit(1 if E else 0)
