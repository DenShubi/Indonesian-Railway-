import pdfplumber, re, json, sys
from collections import defaultdict
sys.path.insert(0,'/home/claude/jtv/scripts')
from words import build_words, CODE, TIME

PDF='/mnt/user-data/uploads/Java Train VIsualizer/Train Timetables/Jadwal Commuter Line Wilayah 8 Surabaya.pdf'
pdf=pdfplumber.open(PDF)

def cluster(vals, gap=10):
    vals=sorted(vals); out=[]; cur=[vals[0]]
    for v in vals[1:]:
        if v-cur[-1]<=gap: cur.append(v)
        else: out.append(sum(cur)/len(cur)); cur=[v]
    out.append(sum(cur)/len(cur)); return out

def nearest(v,cs): return min(range(len(cs)), key=lambda i:abs(cs[i]-v))

# ---------- pages 1-2 : stations as rows ----------
def parse_station_rows(pi, line_name):
    pg=pdf.pages[pi]; W=build_words(pg)
    anchors=sorted([(w['top'], CODE.match(w['text']).group(1))
                    for w in W if CODE.match(w['text']) and w['x0']<90])
    # assign each left-column text token to its NEAREST code anchor (avoids row bleed)
    nbuf={i:[] for i in range(len(anchors))}
    for w in W:
        if not (24<w['x0']<92): continue
        if CODE.match(w['text']) or w['text'].isdigit(): continue
        if not re.search(r'[A-Za-z]', w['text']): continue
        ai=min(range(len(anchors)), key=lambda i:abs(anchors[i][0]-w['top']))
        if abs(anchors[ai][0]-w['top'])>9: continue
        nbuf[ai].append((w['x0'], w['text']))
    names={}
    for i,(top,code) in enumerate(anchors):
        if code in names: continue          # loop repeats: keep first occurrence only
        txt=' '.join(t for _,t in sorted(nbuf[i])).title()
        names[code]=txt or code
    trains=[w['text'] for w in sorted(
        [w for w in W if 95<w['top']<113 and re.fullmatch(r'\d{3}(-\d{3})?',w['text'])],
        key=lambda w:w['x0'])]
    routes=sorted([(w['mid'], w['text'].strip('()')) for w in W
                   if w['text'].startswith('(') and '-' in w['text'] and w['top']<140])
    times=[w for w in W if TIME.match(w['text'])]
    centers=cluster([w['mid'] for w in times])
    assert len(centers)==len(trains), f"p{pi+1}: cols {len(centers)} != trains {len(trains)}"
    cols=defaultdict(list); dropped=0
    for w in times:
        ci=nearest(w['mid'],centers)
        ai=min(range(len(anchors)), key=lambda i:abs(anchors[i][0]-w['top']))
        if abs(anchors[ai][0]-w['top'])>11: dropped+=1; continue
        cols[ci].append((anchors[ai][0], anchors[ai][1], w['text']))
    trips=[]
    for ci in sorted(cols):
        st=sorted(cols[ci])
        rc=[t for c,t in routes if centers[ci]-34<=c<=centers[ci]+34]
        trips.append({'train':trains[ci],'route_codes':rc,
                      'stops':[{'code':c,'time':t} for _,c,t in st]})
    return {'line':line_name,'layout':'station_rows','dropped':dropped,
            'station_order':[c for _,c in anchors],'names':names,'trips':trips}

# ---------- pages 3,5 : trains as rows ----------
def parse_train_rows(pi, line_name):
    pg=pdf.pages[pi]; W=build_words(pg)
    codes=[(w['mid'],w['top'],CODE.match(w['text']).group(1)) for w in W
           if CODE.match(w['text']) and w['x0']>195]
    bytop=defaultdict(list)
    for x,t,c in codes: bytop[round(t/3)].append((x,c))
    hdrs=sorted([(k*3,sorted(v)) for k,v in bytop.items() if len(v)>=5])
    times=[w for w in W if TIME.match(w['text'])]
    names={}
    tables=[]
    for i,(htop,hc) in enumerate(hdrs):
        nxt=hdrs[i+1][0] if i+1<len(hdrs) else 10**6
        centers=[x for x,_ in hc]; cods=[c for _,c in hc]
        for x,c in hc:
            toks=[w['text'] for w in W if abs(w['mid']-x)<26 and htop-26<w['top']<htop-1
                  and not CODE.match(w['text'])]
            if toks: names.setdefault(c,' '.join(toks).title())
        rows=defaultdict(list)
        for w in times:
            if htop+4 < w['top'] < nxt-4: rows[round(w['top']/3)].append(w)
        trips=[]
        for k in sorted(rows):
            tw=sorted(rows[k],key=lambda a:a['x0']); top=tw[0]['top']
            lab=[w['text'] for w in W if abs(w['top']-top)<5 and w['x0']<200]
            num=next((s for s in lab if re.fullmatch(r'\d{3}(-\d{3})?',s)),None)
            stops=[]
            for w in tw:
                ci=nearest(w['mid'],centers)
                if abs(centers[ci]-w['mid'])<17: stops.append({'code':cods[ci],'time':w['text']})
            if len(stops)>=3:
                trips.append({'train':num,'relasi':' '.join(lab),'stops':stops})
        if trips: tables.append({'station_order':cods,'trips':trips})
    return {'line':line_name,'layout':'train_rows','names':names,'tables':tables}

out={}
out['dhoho']=parse_station_rows(0,'Commuter Line Dhoho')
out['penataran']=parse_station_rows(1,'Commuter Line Penataran')
out['supas']=parse_train_rows(2,'Commuter Line Supas')
out['arjonegoro']=parse_train_rows(4,'Commuter Line Arjonegoro')
json.dump(out, open('/home/claude/jtv/data/wil8_parsed.json','w'), indent=1, ensure_ascii=False)

for k in ('dhoho','penataran'):
    d=out[k]; tot=sum(len(t['stops']) for t in d['trips'])
    print(f"\n### {d['line']}  stations={len(d['station_order'])} trips={len(d['trips'])} stop_times={tot} dropped={d['dropped']}")
    for t in d['trips']:
        s=t['stops']
        print(f"   KA {t['train']:<9} n={len(s):<3} {'>'.join(t['route_codes']):<24} {s[0]['code']} {s[0]['time']} -> {s[-1]['code']} {s[-1]['time']}")
for k in ('supas','arjonegoro'):
    d=out[k]
    print(f"\n### {d['line']}  tables={len(d['tables'])}")
    for tb in d['tables']:
        print(f"   order: {'-'.join(tb['station_order'])}")
        for t in tb['trips']:
            s=t['stops']
            print(f"     KA {str(t['train']):<9} n={len(s):<3} {s[0]['code']} {s[0]['time']} -> {s[-1]['code']} {s[-1]['time']}")
print("\nTOTAL stop_times:", sum(len(t['stops']) for k in ('dhoho','penataran') for t in out[k]['trips'])
      + sum(len(t['stops']) for k in ('supas','arjonegoro') for tb in out[k]['tables'] for t in tb['trips']))
