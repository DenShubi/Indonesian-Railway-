"""Route each trip along the real OSM rail network to produce shapes.txt.
Stitches near-coincident way endpoints, guards against detours, simplifies output."""
import json, csv, math, pathlib, sys
from collections import defaultdict
import networkx as nx
from scipy.spatial import cKDTree
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
D=ROOT/'data'; G=ROOT/'gtfs'
RAIL=D/'osm'/'rail.geojson'
BB=(-8.80,-6.50,110.50,114.50)
STITCH=25.0        # metres: join way endpoints this close
MAXJUMP=2000.0     # metres: split a way here instead of bridging
BRIDGE=6000.0      # metres: span a hole in the OSM data between components
RDP=8.0            # metres: output simplification

def hav(a,b):
    p=math.pi/180
    x=math.sin((b[0]-a[0])*p/2)**2+math.cos(a[0]*p)*math.cos(b[0]*p)*math.sin((b[1]-a[1])*p/2)**2
    return 2*6371000*math.asin(math.sqrt(x))

# ---- 1. build graph, splitting ways on large gaps ----
gj=json.load(open(RAIL)); g=nx.Graph(); segs=0
for f in gj['features']:
    if f['geometry']['type']!='LineString': continue
    pts=[(round(la,6),round(lo,6)) for lo,la in f['geometry']['coordinates']
         if BB[0]<=la<=BB[1] and BB[2]<=lo<=BB[3]]
    if len(pts)<2: continue
    run=[pts[0]]
    for p in pts[1:]:
        if p==run[-1]: continue
        if hav(run[-1],p)>MAXJUMP:
            if len(run)>1: segs+=1
            run=[p]; continue
        run.append(p)
        a,b=run[-2],run[-1]; d=hav(a,b)
        if g.has_edge(a,b): g[a][b]['weight']=min(g[a][b]['weight'],d)
        else: g.add_edge(a,b,weight=d)
    if len(run)>1: segs+=1
print(f"segments: {segs}  nodes: {g.number_of_nodes()}  edges: {g.number_of_edges()}",file=sys.stderr)

# ---- 2. stitch near-coincident nodes ----
nodes=list(g.nodes()); arr=np.array(nodes)
# metric-ish scaling for the KD-tree so the radius is in metres
lat0=math.radians(float(np.mean(arr[:,0])))
xy=np.c_[arr[:,0]*111320.0, arr[:,1]*111320.0*math.cos(lat0)]
tree=cKDTree(xy); added=0
for i,j in tree.query_pairs(r=STITCH):
    a,b=nodes[i],nodes[j]
    if not g.has_edge(a,b):
        g.add_edge(a,b,weight=max(hav(a,b),0.1)); added+=1
print(f"stitched {added} node pairs within {STITCH}m -> edges: {g.number_of_edges()}",file=sys.stderr)
comps=sorted(nx.connected_components(g), key=len, reverse=True)
print(f"connected components: {len(comps)}  largest: {[len(c) for c in comps[:5]]}",file=sys.stderr)

# ---- 2b. bridge components across holes in the OSM data ----
# The Lamongan-Duduk-Cerme stretch and the Kandangan-Indro branch are mapped in
# pieces, so the rail graph arrives in disconnected islands. Attach each island
# to the trunk at its closest approach; the shape then follows real track
# everywhere except the missing metres, instead of giving up on the whole
# station-to-station leg.
trunk=set(comps[0]); rest=[set(c) for c in comps[1:]]; bridges=[]
while rest:
    tnodes=np.array(sorted(trunk))
    ttree=cKDTree(np.c_[tnodes[:,0]*111320.0, tnodes[:,1]*111320.0*math.cos(lat0)])
    best=None
    for ci,c in enumerate(rest):
        cn=np.array(sorted(c))
        d,idx=ttree.query(np.c_[cn[:,0]*111320.0, cn[:,1]*111320.0*math.cos(lat0)],k=1)
        i=int(np.argmin(d))
        if best is None or d[i]<best[0]: best=(float(d[i]), ci, tuple(cn[i]), tuple(tnodes[idx[i]]))
    gap,ci,a,b=best
    if gap>BRIDGE:
        print(f"  {len(rest)} component(s) left unbridged, nearest is {gap:.0f}m away",file=sys.stderr)
        break
    g.add_edge(a,b,weight=gap)
    bridges.append((round(gap), a, b))
    trunk |= rest.pop(ci)
for gap,a,b in sorted(bridges,reverse=True):
    print(f"  bridged {gap:>5}m hole at {a[1]:.4f},{a[0]:.4f}",file=sys.stderr)

# ---- 3. snap stations ----
stations={r['code']:(float(r['lat']),float(r['lon'])) for r in csv.DictReader(open(D/'stations.csv'))}
nodes=list(g.nodes()); arr=np.array(nodes)
xy=np.c_[arr[:,0]*111320.0, arr[:,1]*111320.0*math.cos(lat0)]
tree=cKDTree(xy); snap={}; far=[]
for c,(la,lo) in stations.items():
    d,idx=tree.query([la*111320.0, lo*111320.0*math.cos(lat0)],k=1)
    snap[c]=tuple(arr[idx])
    if d>600: far.append((c,round(d)))
print(f"stations snapped; >600m from track: {far}",file=sys.stderr)

# ---- 4. route with detour guard ----
cache={}; straightened=[]
def seg(a,b):
    k=(a,b)
    if k in cache: return cache[k]
    sl=hav(snap[a],snap[b])
    try:
        p=nx.shortest_path(g,snap[a],snap[b],weight='weight')
        L=sum(hav(p[i-1],p[i]) for i in range(1,len(p)))
        if L > max(3.0*sl, sl+5000):
            straightened.append((a,b,round(sl/1000,1),round(L/1000,1))); p=[snap[a],snap[b]]
    except (nx.NetworkXNoPath,nx.NodeNotFound):
        straightened.append((a,b,round(sl/1000,1),None)); p=[snap[a],snap[b]]
    cache[k]=p; return p

def rdp(pts,eps):
    if len(pts)<3: return pts
    def perp(p,a,b):
        if a==b: return hav(p,a)
        ax,ay=a[1],a[0]; bx,by=b[1],b[0]; px,py=p[1],p[0]
        k=math.cos(lat0)
        ax*=k; bx*=k; px*=k
        num=abs((bx-ax)*(ay-py)-(ax-px)*(by-ay)); den=math.hypot(bx-ax,by-ay)
        return (num/den)*111320.0 if den else hav(p,a)
    keep=[False]*len(pts); keep[0]=keep[-1]=True
    stack=[(0,len(pts)-1)]
    while stack:
        i,j=stack.pop()
        if j<=i+1: continue
        dm,im=-1,i
        for k in range(i+1,j):
            d=perp(pts[k],pts[i],pts[j])
            if d>dm: dm,im=d,k
        if dm>eps: keep[im]=True; stack+=[(i,im),(im,j)]
    return [p for p,kp in zip(pts,keep) if kp]

trips=list(csv.DictReader(open(G/'trips.txt')))
stimes=defaultdict(list)
for r in csv.DictReader(open(G/'stop_times.txt')): stimes[r['trip_id']].append(r)
for v in stimes.values(): v.sort(key=lambda r:int(r['stop_sequence']))

seqsh={}; rows=[]; tshape={}
for t in trips:
    key=tuple(r['stop_id'] for r in stimes[t['trip_id']])
    if key not in seqsh:
        sid=f"shp_{len(seqsh)+1:03d}"; poly=[]
        for a,b in zip(key,key[1:]):
            p=seg(a,b)
            poly.extend(p[1:] if poly and poly[-1]==p[0] else p)
        cl=[poly[0]]
        for p in poly[1:]:
            if p!=cl[-1]: cl.append(p)
        cl=rdp(cl,RDP)
        seqsh[key]=(sid,cl)
        d=0.0
        for i,p in enumerate(cl):
            if i: d+=hav(cl[i-1],p)
            rows.append({'shape_id':sid,'shape_pt_lat':f"{p[0]:.6f}",'shape_pt_lon':f"{p[1]:.6f}",
                         'shape_pt_sequence':i+1,'shape_dist_traveled':f"{d/1000:.3f}"})
    tshape[t['trip_id']]=seqsh[key][0]

with open(G/'shapes.txt','w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['shape_id','shape_pt_lat','shape_pt_lon','shape_pt_sequence','shape_dist_traveled'])
    w.writeheader(); w.writerows(rows)
fn=[c for c in trips[0] if c!='shape_id']+['shape_id']
for t in trips: t['shape_id']=tshape[t['trip_id']]
with open(G/'trips.txt','w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fn); w.writeheader(); w.writerows(trips)

print(f"\nshapes={len(seqsh)}  shape points={len(rows)}")
if straightened:
    print(f"segments left as straight lines: {len(straightened)}")
    for s in straightened[:10]: print("   ",s)
else: print("every station pair routed along real track")
print("\n  shape  stops  pts   track_km  straight_km  ratio")
for key,(sid,poly) in seqsh.items():
    L=sum(hav(poly[i-1],poly[i]) for i in range(1,len(poly)))
    S=sum(hav(snap[key[i-1]],snap[key[i]]) for i in range(1,len(key)))
    print(f"  {sid}  {len(key):>4}  {len(poly):>5}  {L/1000:>7.1f}  {S/1000:>10.1f}  {L/S if S else 0:>5.2f}")
