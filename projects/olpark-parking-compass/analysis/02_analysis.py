import pandas as pd, numpy as np, json, re
from datetime import datetime, timedelta

CAP = 2200  # 동2문·남2문·북2문 주차 가능대수 (기관 예상이용률 서비스 표기)
df = pd.read_pickle('data/entries.pkl')
ev = pd.read_pickle('data/events.pkl')
wx = json.load(open('data/weather_2024summer.json'))

VENUE_CAP = {'02':15000,'01':2700,'03':5000,'04':1000,'07':400,'05':300,'06':8000}
VENUE_NM  = {'02':'KSPO DOME','01':'올림픽홀','03':'핸드볼경기장','04':'우리금융아트홀','07':'뮤즈라이브','05':'K-아트홀','06':'야외(88잔디마당 등)'}

# ---------- 일별 ----------
df['date'] = df['entry_ts'].dt.date
daily = df.groupby('date').size().rename('entries').to_frame()
daily['dow'] = pd.to_datetime(daily.index).dayofweek
daily['is_weekend'] = daily['dow'] >= 5
daily['dwell_med'] = df.groupby('date')['dwell_min_adj'].median()
daily['dwell_mean'] = df.groupby('date')['dwell_min_adj'].mean()

# ---------- 공연 부하 (일별) ----------
ev['plcCd']=ev['plcCd'].astype(str).str.strip()
ev = ev[ev['plcCd'].isin(VENUE_CAP)]
def shows_per_day(row):
    # count show times in tm string; fallback 1
    t = str(row['tm'])
    return max(1, len(re.findall(r'\d{1,2}\s*[:시]', t)) // 2) if t else 1
ev['n_shows'] = ev.apply(shows_per_day, axis=1)
ev['cap'] = ev['plcCd'].map(VENUE_CAP)

# split events at month boundaries: estimate daily seats by distributing shows across run days (Mon off)
def expand(row):
    days = pd.date_range(row['beginDt'], row['endDt'])
    days = [d for d in days if d.dayofweek != 0]   # 월 공연없음 (기관 공연 관행)
    if not days: days = [row['beginDt']]
    out=[]
    for d in days:
        # weekday vs weekend show count from tm text
        n = row['n_shows']
        if d.dayofweek >= 5: n = max(n, 2)
        out.append((d.date(), n, row['cap'], row['plcCd'], row['title']))
    return out

rows=[]
for _,r in ev.iterrows():
    rows += expand(r)
seats = pd.DataFrame(rows, columns=['date','n_shows','cap','plcCd','title'])
seat_daily = seats.groupby('date').apply(lambda g: pd.Series({
    'seats': (g['n_shows']*g['cap']).sum(),
    'n_events': g['title'].nunique(),
    'dome': int((g['plcCd']=='02').any()),
    'hall': int((g['plcCd']=='01').any()),
    'arena': int((g['plcCd']=='03').any()),
    'small': int(g['plcCd'].isin(['04','05','07']).any()),
}), include_groups=False)
daily = daily.join(seat_daily).fillna({'seats':0,'n_events':0,'dome':0,'hall':0,'arena':0,'small':0})

# ---------- 날씨 ----------
h = pd.DataFrame({'t':pd.to_datetime(wx['hourly']['time']),'temp':wx['hourly']['temperature_2m'],
                  'precip':wx['hourly']['precipitation'],'wind':wx['hourly']['wind_speed_10m']})
h['date']=h['t'].dt.date
h['hour']=h['t'].dt.hour
wd = h.groupby('date').agg(precip_sum=('precip','sum'), rain_hours=('precip',lambda s:(s>=0.1).sum()),
                           tmax=('temp','max'), tmean=('temp','mean'))
daily = daily.join(wd)

# ---------- 시간대 프로파일 ----------
df['hour'] = df['entry_ts'].dt.hour
hour_in = df.pivot_table(index='hour', columns=pd.to_datetime(df['entry_ts']).dt.date, values='entry_ts', aggfunc='count').fillna(0)

# 재실(occupancy): 10분 단위
start = datetime(2024,6,30,0,0); end = datetime(2024,10,1,0,0)
idx = pd.date_range(start, end, freq='10min')
arr = np.zeros(len(idx)); dep = np.zeros(len(idx))
def hist(ts):
    t = ts.values.astype('datetime64[ns]').astype('int64')
    b = ((t - idx[0].value)//(600*10**9)).astype(int)
    return b
d = df.dropna(subset=['exit_ts'])
a_in = hist(df['entry_ts']); a_out = hist(d['exit_ts'])
for b in a_in: arr[b]+=1
for b in a_out: dep[b]+=1
occ = pd.Series(np.cumsum(arr-dep), index=idx)
occ = occ[(occ.index>='2024-07-01')&(occ.index<'2024-08-01')]
occ_day = occ.groupby(occ.index.date)
daily['peak_occ'] = occ_day.max()
daily['peak_time'] = occ_day.idxmax().dt.strftime('%H:%M')
daily['p90_occ'] = occ_day.quantile(0.9)
daily['over80_hours'] = occ_day.apply(lambda s: (s>CAP*0.8).sum()/6)

stats = {}
stats['overall'] = {
 'rows': int(len(df)), 'days': int(daily.shape[0]),
 'entries_per_day_mean': float(daily['entries'].mean()),
 'entries_per_day_median': float(daily['entries'].median()),
 'entries_per_day_max': int(daily['entries'].max()),
 'entries_per_day_max_date': str(daily['entries'].idxmax()),
 'entries_per_day_min': int(daily['entries'].min()),
 'entries_per_day_min_date': str(daily['entries'].idxmin()),
 'weekday_mean': float(daily[~daily.is_weekend]['entries'].mean()),
 'weekend_mean': float(daily[daily.is_weekend]['entries'].mean()),
 'dwell_median_min': float(df['dwell_min_adj'].median()),
 'dwell_mean_min': float(df['dwell_min_adj'].mean()),
 'dwell_p90_min': float(df['dwell_min_adj'].quantile(0.9)),
 'long_stay_gt24h_pct': float((df['dwell_min_adj']>1440).mean()*100),
 'peak_occ_mean': float(daily['peak_occ'].mean()),
 'peak_occ_max': int(daily['peak_occ'].max()),
 'peak_occ_max_date': str(daily['peak_occ'].idxmax()),
 'peak_occ_max_time': str(daily.loc[daily['peak_occ'].idxmax(),'peak_time']),
 'peak_occ_max_pct': float(daily['peak_occ'].max()/CAP*100),
 'days_over_90pct': int((daily['peak_occ']>CAP*0.9).sum()),
 'days_over_80pct': int((daily['peak_occ']>CAP*0.8).sum()),
 'cap': CAP,
}
# 시간대별
hourly_mean = (hour_in.T.groupy if False else hour_in.T).mean(axis=0)
stats['hourly_arrivals'] = {int(k): round(float(v),1) for k,v in hourly_mean.items()}
# 출차 시간대
df['hour_out'] = df['exit_ts'].dt.hour
stats['hourly_departures'] = {int(k): round(float(v),1) for k,v in df.groupby('hour_out').size().div(31).items()}
stats['occ_hourly_mean'] = {int(hh): round(float(occ[occ.index.hour==hh].groupby(occ[occ.index.hour==hh].index.date).max().mean()),1) for hh in range(24)}

# ---------- 공연 효과 ----------
daily['evt_big'] = (daily['seats']>=10000).astype(int)
def grp(mask,label):
    g=daily[mask]
    return {'n':int(len(g)),'mean':float(g['entries'].mean()) if len(g) else None}
stats['compare'] = {
 'all': float(daily['entries'].mean()),
 'no_event': grp(daily['seats']==0,'x'),
 'any_event': grp(daily['seats']>0,'x'),
 'dome_day': grp(daily['dome']==1,'x'),
 'no_dome': grp(daily['dome']==0,'x'),
 'big_seats_ge10k': grp(daily['seats']>=10000,'x'),
 'rain_day': grp(daily['precip_sum']>=1,'x'),
 'dry_day': grp(daily['precip_sum']<1,'x'),
 'hot_day_33': grp(daily['tmax']>=33,'x'),
}
# 회귀: entries ~ weekend + seats/1000 + precip
import numpy as np
X = np.column_stack([np.ones(len(daily)), daily['is_weekend'].astype(float), daily['seats']/1000, (daily['precip_sum']>=1).astype(float)])
y = daily['entries'].astype(float)
beta, res, rank, sv = np.linalg.lstsq(X, y, rcond=None)
yhat = X@beta
ss_res = ((y-yhat)**2).sum(); ss_tot = ((y-y.mean())**2).sum()
stats['regression'] = {'intercept':float(beta[0]),'weekend':float(beta[1]),'per_1000seats':float(beta[2]),
                       'rain':float(beta[3]),'r2':float(1-ss_res/ss_tot),'n':int(len(daily))}
# 상관
stats['corr'] = {
 'seats_vs_entries': float(daily['seats'].corr(daily['entries'])),
 'precip_vs_entries': float(daily['precip_sum'].corr(daily['entries'])),
 'tmax_vs_entries': float(daily['tmax'].corr(daily['entries'])),
}

daily_out = daily.reset_index()
daily_out['date']=daily_out['date'].astype(str)
daily_out.to_csv('data/daily.csv', index=False)
occ.resample('1h').max().to_csv('data/occupancy_hourly.csv')
json.dump(stats, open('data/stats.json','w'), ensure_ascii=False, indent=1)
pd.set_option('display.width',250); pd.set_option('display.max_rows',60)
print(daily_out[['date','dow','entries','seats','n_events','dome','precip_sum','tmax','peak_occ','peak_time']].to_string())
print(json.dumps(stats['compare'], ensure_ascii=False, indent=1))
print(json.dumps(stats['regression'], ensure_ascii=False))
print(json.dumps(stats['corr'], ensure_ascii=False))
print(json.dumps(stats['overall'], ensure_ascii=False, indent=1))
