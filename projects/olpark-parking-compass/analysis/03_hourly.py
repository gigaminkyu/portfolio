import pandas as pd, numpy as np, json, re
df = pd.read_pickle('data/entries.pkl'); ev = pd.read_pickle('data/events.pkl')
daily = pd.read_csv('data/daily.csv', parse_dates=['date']).set_index('date')
df['date']=df['entry_ts'].dt.date; df['hour']=df['entry_ts'].dt.hour
arr = df.groupby(['date','hour']).size().unstack(fill_value=0).reindex(columns=range(24), fill_value=0)
arr.index = pd.to_datetime(arr.index)

CAP=2200
occ = pd.read_csv('data/occupancy_hourly.csv', index_col=0, parse_dates=True).iloc[:,0]
occ = occ[occ.index < '2024-08-01']
occ_by_hour = occ.resample('1h').max().reindex(pd.date_range('2024-07-01','2024-07-31 23:00',freq='1h')).fillna(0)
occ_by_hour = pd.DataFrame(occ_by_hour.values.reshape(31,24), index=pd.date_range('2024-07-01',periods=31), columns=range(24))
big = daily['seats']>=10000
res={}
res['arrivals_profile_big_event'] = arr[big.values].mean(axis=0).round(1).to_dict()
res['arrivals_profile_normal'] = arr[~big.values].mean(axis=0).round(1).to_dict()
res['occ_profile_big_event'] = occ_by_hour[big.values].mean(axis=0).round(0).to_dict()
res['occ_profile_normal'] = occ_by_hour[~big.values].mean(axis=0).round(0).to_dict()
res['occ_p95_big_event'] = occ_by_hour[big.values].quantile(0.95).round(0).to_dict()
# peak hour stats
res['peak_arrival_hour_normal'] = int(arr[~big.values].mean(axis=0).idxmax())
res['peak_arrival_hour_big'] = int(arr[big.values].mean(axis=0).idxmax())
# show-time alignment: arrivals 2h before show start vs same clock hours on non-event days
starts=[]
for d in pd.date_range('2024-07-01','2024-07-31'):
    ds=[]
    for _,e in ev[(ev['beginDt']<=d)&(ev['endDt']>=d)].iterrows():
        for m in re.finditer(r'(\d{1,2})\s*(?::|시)\s*(\d{2})?', str(e['tm'])):
            hh=int(m.group(1))
            if 10<=hh<=22: ds.append((hh, e['plcCd']))
    starts.append(ds)
res['show_starts_sample'] = {str(d.date()): s for d,s in zip(pd.date_range('2024-07-01','2024-07-31'), starts)}
dome_days = [d for d,s in zip(pd.date_range('2024-07-01','2024-07-31'), starts) if any(x[1]=='02' for x in s)]
pre=[]; base=[]
for d,s in zip(pd.date_range('2024-07-01','2024-07-31'), starts):
    for hh,plc in s:
        if plc=='02' and 12<=hh<=22:
            pre.append(arr.loc[d].get(hh-2,0)+arr.loc[d].get(hh-1,0)+arr.loc[d].get(hh,0))
for d in arr.index[~big.values]:
    for hh in [17,18,19]:
        base.append(arr.loc[d].get(hh-2,0)+arr.loc[d].get(hh-1,0)+arr.loc[d].get(hh,0))
res['dome_show_pre2h_arrivals_mean'] = round(float(np.mean(pre)),1) if pre else None
res['baseline_same_window_mean'] = round(float(np.mean(base)),1)
res['dome_show_pre2h_n'] = len(pre)
json.dump(res, open('data/hourly_stats.json','w'), ensure_ascii=False, indent=1)
print(json.dumps({k:v for k,v in res.items() if k!='show_starts_sample'}, ensure_ascii=False, indent=1))
