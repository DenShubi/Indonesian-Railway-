"""Match the 62 parsed station codes to OSM stations (ref first, then normalised name)."""
import json, csv, re, unicodedata, pathlib, difflib
D=pathlib.Path('/home/claude/jtv/data')
def norm(s):
    s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().upper()
    s=re.sub(r'^STASIUN\s+','',s)
    return re.sub(r'[^A-Z0-9]','',s)

names=json.load(open(D/'station_names.json'))
osm=list(csv.DictReader(open(D/'osm_stations.csv')))
by_ref={}
for o in osm:
    if o['ref']: by_ref.setdefault(o['ref'],[]).append(o)
by_norm={}
for o in osm: by_norm.setdefault(o['norm'],[]).append(o)
cands=list(by_norm.keys())

out=[]; unmatched=[]
for code,nm in sorted(names.items()):
    hit=None; how=None
    if code in by_ref: hit=by_ref[code][0]; how='ref'
    else:
        n=norm(nm)
        if n in by_norm: hit=by_norm[n][0]; how='name'
        else:
            m=difflib.get_close_matches(n,cands,n=1,cutoff=0.86)
            if m: hit=by_norm[m[0]][0]; how=f'fuzzy({m[0]})'
    if hit: out.append({'code':code,'name':nm,'lat':hit['lat'],'lon':hit['lon'],
                        'osm_id':hit['osm_id'],'match':how})
    else: unmatched.append((code,nm))

with open(D/'stations.csv','w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['code','name','lat','lon','osm_id','match']); w.writeheader(); w.writerows(out)
print(f"matched {len(out)}/{len(names)}")
for r in out:
    if r['match']!='ref': print(f"   {r['code']:<5}{r['name']:<24}{r['match']}")
if unmatched:
    print("UNMATCHED (need manual coords):")
    for c,n in unmatched: print(f"   {c:<5}{n}")
