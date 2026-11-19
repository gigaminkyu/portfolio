import pandas as pd, numpy as np, json, re, glob

CAP=2200
VENUE={'02':('KSPO DOME',15000),'01':('올림픽홀',2700),'03':('핸드볼경기장',5000),
       '04':('우리금융아트홀',1000),'07':('뮤즈라이브',400),'05':('K-아트홀',300),'06':('야외(88잔디마당)',8000)}
GATES={'동2문':'P1·P2·P4·P5','남2문':'P1·P2·P7','북2문':'P4·P5·P6'}
LOTS={'P1':562,'P2':320,'P4':117,'P5':176,'P6':167,'P7':137,'P11':190}

occ=pd.read_csv('data/occupancy_hourly.csv', index_col=0, parse_dates=True).iloc[:,0]
occ=occ[occ.index<'2024-08-01']; o=occ.resample('1h').max()
daily=pd.read_csv('data/daily.csv'); daily['date']=pd.to_datetime(daily['date'])
big=daily[daily.seats>=10000]
df=pd.DataFrame({'occ':o}); df['date']=df.index.normalize(); df['hour']=df.index.hour; df['dow']=df.index.day_of_week
base=df.merge(daily[['date','seats']],on='date',how='left')
base=base[base.seats<10000]
bw=base[base.dow<5].groupby('hour')['occ'].mean()
be=base[base.dow>=5].groupby('hour')['occ'].mean()
base_map={'wd':bw.round(0).to_dict(),'we':be.round(0).to_dict()}
# uplift per 1000 seats by hour (mean over big-event days, clipped to >=0)
ups=[]
for _,r in big.iterrows():
    d=pd.Timestamp(r['date'])
    prof=df[(df.date==d)]
    b = bw if d.weekday()<5 else be
    diff=(prof.set_index('hour')['occ'] - b).reindex(range(24)).fillna(0)
    ups.append(diff.clip(lower=0)/ (r['seats']/1000))
U=pd.concat(ups,axis=1).mean(axis=1).fillna(0)
print('uplift per 1000 seats by hour:', {int(k):round(float(v),2) for k,v in U.items()})
# per-day uplift summary
rows=[]
for _,r in big.iterrows():
    d=pd.Timestamp(r['date']); b = bw if d.day_of_week<5 else be
    prof=df[df.date==d].set_index('hour')['occ'].reindex(range(24)).fillna(0)
    diff=(prof-b).fillna(0)
    rows.append({'date':str(d),'seats':float(r['seats']),'peak_occ':int(r['peak_occ']),
                 'uplift_at_peak':int(round(float(diff.max()))),'precip':float(r['precip_sum'])})
print(pd.DataFrame(rows).to_string())

# 2024-07 일별 요약 (근거 패널용)
july=daily[['date','entries','seats','peak_occ','precip_sum','tmax','dow']].copy()
july['date']=july['date'].dt.strftime('%Y-%m-%d')

# ---- 데모용 공연 일정: 2026-11-19 ~ 2026-12-06 ----
ev=pd.read_pickle('data/events.pkl'); ev['plcCd']=ev['plcCd'].astype(str).str.strip()
ev=ev[ev.plcCd.isin(VENUE)]
ev['beginDt']=pd.to_datetime(ev['beginDt']); ev['endDt']=pd.to_datetime(ev['endDt'])
def times(tm, dow):
    t=str(tm)
    out=[]
    for m in re.finditer(r'(\d{1,2})\s*(?::|시)\s*(\d{2})?', t):
        hh=int(m.group(1)); mm=int(m.group(2) or 0)
        if 10<=hh<=23: out.append(hh*60+mm)
    if not out:
        out=[19*60]
    return out
demo=[]
lo,hi=pd.Timestamp('2026-11-19'),pd.Timestamp('2026-12-06')
for _,r in ev[(ev.endDt>=lo)&(ev.beginDt<=hi)].iterrows():
    dd=r['beginDt']
    while dd<=r['endDt']:
        if dd.dayofWeek if False else dd.day_of_week!=0:
            ts=times(r['tm'], dd.day_of_week)
            demo.append({'date':dd.strftime('%Y-%m-%d'),'title':r['title'],'venue':VENUE[r['plcCd']][0],
                         'plcCd':r['plcCd'],'starts':ts,'price':str(r['tktPrc'])[:60],
                         'car_factor': 4.6 if re.search(r'조용필|트로트|미스터|나훈아|임영웅|SG워너비|이승철|발라드|박재정|10CM|휘인', str(r['title'])) else (1.5 if re.search(r'뮤지컬|발레|호두까기|정글북|핑크퐁|어린이|가족|최현우', str(r['title'])) else 1.0)})
        dd+=pd.Timedelta(days=1)
# 11/21 기관 예상이용률 페이지에 등재된 공연(스크랩 일정엔 없음)
demo += [{'date':'2026-11-21','title':'미스터트롯 콘서트','venue':'올림픽홀','plcCd':'01','starts':[13*60],'price':'','car_factor':4.6},
         {'date':'2026-11-21','title':'산타와 빈양말','venue':'체조경기장(KSPO DOME)','plcCd':'02','starts':[14*60],'price':'','car_factor':1.5}]
demo=sorted(demo,key=lambda x:(x['date'],x['starts'][0] if x['starts'] else 0))
print(len(demo),'demo event-days'); print(pd.DataFrame(demo).head(20).to_string())

data={
 'meta':{'updated':'2026-11-19','cap':CAP,
   'sources':['한국체육산업개발(주) 올림픽공원 입출차 정보(2024.07, 215,528건)',
              '한국체육산업개발(주) 올림픽공원 공연/행사 일정',
              '한국체육산업개발(주) 월별주차현황(2023~2025)',
              '기상청 단기예보(서비스 연동 예정) / 분석 시 ERA5 재분석 대체',
              '한국체육산업개발(주) 실시간 주차현황(동2문·남2문·북2문)']},
 'baseOcc':{k:{int(h):float(v) for h,v in d.items()} for k,d in base_map.items()},
 'upliftPerK':{int(h):round(float(v),3) for h,v in U.items()},
 'venues':{k:{'name':v[0],'cap':v[1]} for k,v in VENUE.items()},
 'lots':LOTS,'gates':GATES,
 'events':demo,
 'july':july.to_dict('records'),
 'stats':{},
}
st=json.load(open('data/stats.json')); hst=json.load(open('data/hourly_stats.json'))
data['stats']={'overall':st['overall'],'compare':st['compare'],'regression':st['regression'],
               'dome_pre2h':hst['dome_show_pre2h_arrivals_mean'],'base_window':hst['baseline_same_window_mean'],
               'big_days':rows}
json.dump(data, open('web/data.json','w'), ensure_ascii=False, indent=1) if False else None
import os; os.makedirs('web',exist_ok=True)
json.dump(data, open('web/data.json','w'), ensure_ascii=False, indent=1)
print('written web/data.json')
