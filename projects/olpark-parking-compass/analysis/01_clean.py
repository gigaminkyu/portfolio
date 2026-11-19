import pandas as pd, numpy as np, json, glob, re, os

# ---------- 1. 입출차 ----------
df = pd.read_csv('data/inout_202407.csv', encoding='cp949')
df.columns = ['entry_dt', 'entry_ts', 'exit_ts']
df['entry_ts'] = pd.to_datetime(df['entry_ts'], errors='coerce')
df['exit_ts']  = pd.to_datetime(df['exit_ts'], errors='coerce')
df['entry_date'] = df['entry_ts'].dt.date
# dwell: exit before entry (stays overnight / data quirk) -> keep raw but flag
df['dwell_min'] = (df['exit_ts'] - df['entry_ts']).dt.total_seconds() / 60
df['dwell_min_adj'] = df['dwell_min'].where(df['dwell_min'] >= 0, df['dwell_min'] + 1440)
df = df.dropna(subset=['entry_ts'])
df.to_parquet('data/entries.parquet') if False else df.to_pickle('data/entries.pkl')
print('rows', len(df), 'days', df['entry_date'].nunique())
print(df['dwell_min'].describe())
print('negative dwell', (df['dwell_min'] < 0).sum(), 'zero', (df['dwell_min'] == 0).sum())
print('over 24h', (df['dwell_min'] > 1440).sum())

# ---------- 2. 공연 일정 ----------
rows = {}
for f in sorted(glob.glob('data/events/*.json')):
    d = json.load(open(f))
    if not isinstance(d, list): continue
    for arr in d:
        if not isinstance(arr, list): continue
        for e in arr:
            if isinstance(e, dict) and 'evtSeq' in e: rows[e['evtSeq']] = e
ev = pd.DataFrame(rows.values())
ev['beginDt'] = pd.to_datetime(ev['beginDt']); ev['endDt'] = pd.to_datetime(ev['endDt'])
ev['plcCd'] = ev['plcCd'].astype(str).str.strip()
ev['plc'] = ev['plc'].astype(str).str.strip()
ev.to_pickle('data/events.pkl')
print('events', len(ev), ev['beginDt'].min(), ev['endDt'].max())
print(ev['plcCd'].value_counts())
