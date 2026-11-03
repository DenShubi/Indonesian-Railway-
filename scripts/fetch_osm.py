"""Fetch East Java railway stations + rail geometry from OpenStreetMap via Overpass.
Run once overpass-api.de is on the session allowlist."""
import json, re, subprocess, sys, csv, unicodedata, pathlib

BBOX="-8.45,111.30,-6.85,113.20"      # East Java: covers Bojonegoro..Pasuruan..Blitar..Malang
OUT=pathlib.Path('/home/claude/jtv/data')
ENDPOINTS=["https://overpass-api.de/api/interpreter",
           "https://overpass.kumi.systems/api/interpreter",
           "https://overpass.osm.ch/api/interpreter"]

def overpass(q):
    last=None
    for ep in ENDPOINTS:
        r=subprocess.run(["curl","-sS","-m","180","-G",ep,"--data-urlencode","data="+q],
                         capture_output=True,text=True)
        if r.returncode==0 and r.stdout.strip().startswith("{"):
            print(f"  [ok] {ep}", file=sys.stderr); return json.loads(r.stdout)
        last=(ep, r.returncode, (r.stderr or r.stdout)[:160])
        print(f"  [fail] {last}", file=sys.stderr)
    raise SystemExit(f"All Overpass endpoints unreachable. Last: {last}")

def norm(s):
    s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().upper()
    s=re.sub(r'^STASIUN\s+','',s)
    return re.sub(r'[^A-Z0-9]','',s)

# ---- 1. stations ----
q_st=f'[out:json][timeout:180];(node["railway"~"^(station|halt)$"]({BBOX});'\
     f'way["railway"~"^(station|halt)$"]({BBOX}););out tags center;'
st=overpass(q_st)
rows=[]
for e in st['elements']:
    t=e.get('tags',{})
    lat=e.get('lat') or (e.get('center') or {}).get('lat')
    lon=e.get('lon') or (e.get('center') or {}).get('lon')
    if lat is None: continue
    rows.append({'osm_id':f"{e['type']}/{e['id']}",'name':t.get('name',''),
                 'ref':(t.get('ref') or t.get('railway:ref') or '').strip().upper(),
                 'railway':t.get('railway',''),'lat':lat,'lon':lon,'norm':norm(t.get('name',''))})
with open(OUT/'osm_stations.csv','w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(f"stations fetched: {len(rows)}")

# ---- 2. rail geometry (for shapes.txt) ----
q_rail=f'[out:json][timeout:300];way["railway"~"^(rail|light_rail)$"]'\
       f'["service"!~"^(siding|spur|yard|crossover)$"]({BBOX});out geom;'
rl=overpass(q_rail)
ways=[{'id':e['id'],'tags':e.get('tags',{}),
       'geom':[(p['lat'],p['lon']) for p in e.get('geometry',[]) if p]}
      for e in rl['elements'] if e.get('geometry')]
json.dump(ways, open(OUT/'osm_rail.json','w'))
print(f"rail ways fetched: {len(ways)}  nodes: {sum(len(w['geom']) for w in ways)}")
