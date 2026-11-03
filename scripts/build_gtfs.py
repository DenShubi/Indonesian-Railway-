"""Build a GTFS feed for KAI Commuter Wilayah 8 (Surabaya) from the parsed timetable."""
import json, csv, pathlib, zipfile, sys
D=pathlib.Path('/home/claude/jtv/data'); G=pathlib.Path('/home/claude/jtv/gtfs')
G.mkdir(parents=True,exist_ok=True)

P=json.load(open(D/'wil8_parsed.json'))
coords={r['code']:(float(r['lat']),float(r['lon']))
        for r in csv.DictReader(open(D/'stations.csv'))}
names=json.load(open(D/'station_names.json'))

ROUTES=[('CL_DHOHO','dhoho','Dhoho','station_rows','E4572E'),
        ('CL_PENATARAN','penataran','Penataran','station_rows','2E9BD6'),
        ('CL_SUPAS','supas','Supas','train_rows','27A567'),
        ('CL_ARJONEGORO','arjonegoro','Arjonegoro','train_rows','9B6BC9')]

def hhmmss(t, roll):
    h,m=map(int,t.split(':')); return f"{h+24*roll:02d}:{m:02d}:00"

def trip_stop_times(stops):
    """Merge consecutive duplicate stops into arrival/departure; add midnight rollover."""
    merged=[]
    for s in stops:
        if merged and merged[-1]['code']==s['code'] and len(merged[-1]['t'])==1:
            merged[-1]['t'].append(s['time'])
        else:
            merged.append({'code':s['code'],'t':[s['time']]})
    rows=[]; prev=-1; roll=0
    for i,m in enumerate(merged,1):
        arr=m['t'][0]; dep=m['t'][-1]
        for t in (arr,dep):
            h,mi=map(int,t.split(':')); v=(h+24*roll)*60+mi
            if v<prev: roll+=1
            prev=max(prev,(int(t.split(':')[0])+24*roll)*60+int(t.split(':')[1]))
        rows.append((i,hhmmss(arr,roll),hhmmss(dep,roll),m['code']))
    return rows

stops_used=set(); trips=[]; stop_times=[]
for rid,key,label,layout,color in ROUTES:
    d=P[key]
    groups=[d['trips']] if layout=='station_rows' else [tb['trips'] for tb in d['tables']]
    for gi,g in enumerate(groups):
        for t in g:
            if not t.get('train'): continue
            tid=f"{rid}_{t['train']}"
            hs=t.get('route_codes') or [t.get('relasi','')]
            head=names.get(t['stops'][-1]['code'], t['stops'][-1]['code'])
            trips.append({'route_id':rid,'service_id':'DAILY','trip_id':tid,
                          'trip_short_name':t['train'],'trip_headsign':head,
                          'direction_id':gi%2})
            for seq,arr,dep,code in trip_stop_times(t['stops']):
                if code not in coords:
                    print(f"  !! no coords for {code} (trip {tid}) -> stop dropped",file=sys.stderr); continue
                stops_used.add(code)
                stop_times.append({'trip_id':tid,'arrival_time':arr,'departure_time':dep,
                                   'stop_id':code,'stop_sequence':seq})

def write(fn, fields, rows):
    with open(G/fn,'w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

write('agency.txt',['agency_id','agency_name','agency_url','agency_timezone','agency_lang'],
      [{'agency_id':'KAIC','agency_name':'KAI Commuter','agency_url':'https://commuterline.id',
        'agency_timezone':'Asia/Jakarta','agency_lang':'id'}])
write('stops.txt',['stop_id','stop_name','stop_lat','stop_lon'],
      [{'stop_id':c,'stop_name':names.get(c,c),'stop_lat':coords[c][0],'stop_lon':coords[c][1]}
       for c in sorted(stops_used)])
write('routes.txt',['route_id','agency_id','route_short_name','route_long_name','route_type','route_color'],
      [{'route_id':r,'agency_id':'KAIC','route_short_name':lab,
        'route_long_name':f'Commuter Line {lab}','route_type':2,'route_color':col}
       for r,k,lab,ly,col in ROUTES])
write('trips.txt',['route_id','service_id','trip_id','trip_short_name','trip_headsign','direction_id'],trips)
write('stop_times.txt',['trip_id','arrival_time','departure_time','stop_id','stop_sequence'],stop_times)
write('calendar.txt',['service_id','monday','tuesday','wednesday','thursday','friday',
                      'saturday','sunday','start_date','end_date'],
      [{'service_id':'DAILY','monday':1,'tuesday':1,'wednesday':1,'thursday':1,'friday':1,
        'saturday':1,'sunday':1,'start_date':'20260101','end_date':'20271231'}])

zp=D/'gtfs_wilayah8_surabaya.zip'
with zipfile.ZipFile(zp,'w',zipfile.ZIP_DEFLATED) as z:
    for f in sorted(G.glob('*.txt')): z.write(f,f.name)
print(f"stops={len(stops_used)} routes={len(ROUTES)} trips={len(trips)} stop_times={len(stop_times)}")
print("zip:",zp, zp.stat().st_size,"bytes")
