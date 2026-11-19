import re
WD={'월':0,'화':1,'수':2,'목':3,'금':4,'토':5,'일':6}
def parse_tm(tm):
    """returns (dict weekday->[minutes], default list)"""
    t=str(tm)
    byd={}; default=[]
    # split on 요일 markers keeping them
    for m in re.finditer(r'[(]?(월|화|수|목|금|토|일)(?:요일)?[)]?\s*((?:오전|오후)?\s*\d{1,2}\s*(?::|시)\s*\d{0,2}\s*(?:분)?)', t):
        wd=WD[m.group(1)]; seg=m.group(2)
        mm=re.search(r'(\d{1,2})\s*(?::|시)\s*(\d{0,2})', seg)
        if not mm: continue
        hh=int(mm.group(1)); mi=int(mm.group(2) or 0)
        if '오후' in seg and hh<12: hh+=12
        if 10<=hh<=23: byd.setdefault(wd,[]).append(hh*60+mi)
    for m in re.finditer(r'(\d{1,2})\s*(?::|시)\s*(\d{2})\s*(?:분)?', t):
        hh=int(m.group(1)); mi=int(m.group(2) or 0)
        if 10<=hh<=23: default.append(hh*60+mi)
    if not default and not byd:
        for m in re.finditer(r'(\d{1,2})\s*(?:시|PM|pm)', t):
            hh=int(m.group(1))
            if 10<=hh<=23: default.append(hh*60)
    return byd, sorted(set(default))
def starts_for(tm, dow):
    byd, default = parse_tm(tm)
    if dow in byd: return byd[dow]
    if default: return default[:2]
    if byd: return sorted({x for v in byd.values() for x in v})[:2]
    return [19*60]
