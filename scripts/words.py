import re
CODE=re.compile(r'^\(([A-Z]{2,4})\)$')
TIME=re.compile(r'^\d{1,2}:\d{2}$')

def build_words(pg, ytol=2.0, gap=1.6):
    """Rebuild words from chars geometrically, ignoring literal space chars."""
    cs=[c for c in pg.chars if not c['text'].isspace()]
    rows={}
    for c in cs:
        rows.setdefault(round(c['top']/ytol), []).append(c)
    out=[]
    for k,v in rows.items():
        v.sort(key=lambda a:a['x0'])
        cur=[v[0]]
        for c in v[1:]:
            if c['x0']-cur[-1]['x1'] <= gap: cur.append(c)
            else:
                out.append(_mk(cur)); cur=[c]
        out.append(_mk(cur))
    return out

def _mk(chs):
    return {'text':''.join(c['text'] for c in chs),
            'x0':chs[0]['x0'], 'x1':chs[-1]['x1'],
            'top':min(c['top'] for c in chs),
            'mid':(chs[0]['x0']+chs[-1]['x1'])/2}
