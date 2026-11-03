import json, csv, re, unicodedata, difflib, pathlib
D=pathlib.Path('/home/claude/jtv/data')
SRC='/home/claude/ext/tk/static/data/all-national-stations.json'

def norm(s):
    s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().upper()
    s=re.sub(r'^STASIUN\s+','',s)
    return re.sub(r'[^A-Z0-9]','',s)

names=json.load(open(D/'station_names.json'))
# manual name corrections for kerning/parse artefacts
FIX={'SGU':'Surabaya Gubeng','BNW':'Benowo','SB':'Surabaya Kota','SBI':'Surabaya Pasar Turi'}
names={**names, **{k:v for k,v in FIX.items() if k in names}}

src=json.load(open(SRC))
by_code={}
for s in src:
    c=(s.get('code') or '').strip().upper()
    if c and s.get('coords'): by_code.setdefault(c,s)
by_name={}
for s in src:
    if s.get('coords'): by_name.setdefault(norm(s.get('name')),s)
cands=list(by_name)

rows=[]; miss=[]
for code,nm in sorted(names.items()):
    hit=how=None
    if code in by_code: hit,how=by_code[code],'code'
    else:
        n=norm(nm)
        if n in by_name: hit,how=by_name[n],'name'
        else:
            m=difflib.get_close_matches(n,cands,n=1,cutoff=0.85)
            if m: hit,how=by_name[m[0]],'fuzzy:'+m[0]
    if hit:
        lat,lon=hit['coords']
        rows.append({'code':code,'name':nm,'lat':lat,'lon':lon,
                     'src_code':hit.get('code'),'src_name':hit.get('name'),'match':how})
    else: miss.append((code,nm))

with open(D/'stations.csv','w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['code','name','lat','lon','src_code','src_name','match'])
    w.writeheader(); w.writerows(rows)
print(f"matched {len(rows)}/{len(names)}")
print("\nnon-exact matches (review):")
for r in rows:
    if r['match']!='code': print(f"   {r['code']:<5}{r['name']:<22} -> {r['src_code']:<5}{r['src_name']:<24}{r['match']}")
if miss:
    print("\nUNMATCHED:")
    for c,n in miss: print(f"   {c:<5}{n}")
# sanity: all inside East Java-ish bbox
bad=[r for r in rows if not(-8.6<=float(r['lat'])<=-6.7 and 110.9<=float(r['lon'])<=114.0)]
print("\noutside expected bbox:",[(r['code'],r['lat'],r['lon']) for r in bad])
