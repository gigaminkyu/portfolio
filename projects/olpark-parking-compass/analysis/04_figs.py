import pandas as pd, numpy as np, json, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm

fp='/usr/share/fonts/pickle-hwp/NotoSansCJKkr-Regular.otf'
fm.fontManager.addfont(fp)
plt.rcParams['font.family']=fm.FontProperties(fname=fp).get_name()
plt.rcParams['axes.unicode_minus']=False
plt.rcParams['axes.grid']=True
plt.rcParams['grid.alpha']=0.25
C={'navy':'#12355B','blue':'#2F80ED','sky':'#7FB3F5','red':'#E4572E','gray':'#8D99AE','green':'#2A9D8F','sand':'#F4A261'}

daily=pd.read_csv('data/daily.csv', parse_dates=['date'])
hs=json.load(open('data/hourly_stats.json'))
CAP=2200

# 1) 일별 입차 + 공연 규모 + 강수
fig,ax=plt.subplots(figsize=(11,4.6))
ax.bar(daily['date'], daily['entries'], color=[C['red'] if s>=10000 else (C['sky'] if s>6000 else C['gray']) for s in daily['seats']], width=0.7)
ax.set_ylabel('일 입차 대수'); ax.set_ylim(0,9500)
ax.set_title('2024년 7월 올림픽공원 일별 입차 대수와 공연 규모', fontsize=13, weight='bold')
ax2=ax.twinx()
ax2.bar(daily['date'], daily['precip_sum'], color=C['blue'], alpha=0.35, width=0.35)
ax2.set_ylabel('일 강수량(mm)', color=C['blue']); ax2.set_ylim(0,180)
from matplotlib.patches import Patch
ax.legend(handles=[Patch(color=C['red'],label='KSPO DOME 대형공연일(좌석 1만+)'),
                   Patch(color=C['sky'],label='중·소규모 공연일'),
                   Patch(color=C['gray'],label='공연 없음'),
                   Patch(color=C['blue'],alpha=0.4,label='일 강수량')], loc='upper left', fontsize=8, ncol=2)
ax.tick_params(axis='x', rotation=45, labelsize=8)
plt.tight_layout(); plt.savefig('figs/fig1_daily.png', dpi=170); plt.close()

# 2) 시간대별 입차 프로파일 + 재실
fig,axes=plt.subplots(1,2,figsize=(12,4.4))
h=range(24)
a_big=[hs['arrivals_profile_big_event'][str(i)] for i in h]
a_nor=[hs['arrivals_profile_normal'][str(i)] for i in h]
axes[0].plot(h,a_nor,marker='o',color=C['gray'],label='비공연일(중·소규모 포함)')
axes[0].plot(h,a_big,marker='s',color=C['red'],label='대형공연일(좌석 1만+)')
axes[0].fill_between(h,a_nor,a_big,color=C['red'],alpha=0.12)
axes[0].set_title('시간대별 평균 입차 대수', fontsize=12, weight='bold')
axes[0].set_xlabel('시'); axes[0].set_ylabel('대/hr'); axes[0].legend(fontsize=8); axes[0].set_xticks(range(0,24,2))
o_big=[hs['occ_profile_big_event'][str(i)] for i in h]
o_nor=[hs['occ_profile_normal'][str(i)] for i in h]
axes[1].plot(h,o_nor,marker='o',color=C['gray'],label='비공연일')
axes[1].plot(h,o_big,marker='s',color=C['red'],label='대형공연일')
axes[1].axhline(CAP*0.9, ls='--', color=C['navy'], lw=1); axes[1].text(0.3,CAP*0.9+25,'만차 기준 90%',fontsize=8,color=C['navy'])
axes[1].set_title('시간대별 평균 재실 차량(주차 점유)', fontsize=12, weight='bold')
axes[1].set_xlabel('시'); axes[1].set_ylabel('대'); axes[1].legend(fontsize=8); axes[1].set_xticks(range(0,24,2))
plt.tight_layout(); plt.savefig('figs/fig2_hourly.png', dpi=170); plt.close()

# 3) 히트맵 재실률
occ=pd.read_csv('data/occupancy_hourly.csv', index_col=0, parse_dates=True).iloc[:,0]
occ=occ[occ.index<'2024-08-01']
mat=occ.resample('1h').max().reindex(pd.date_range('2024-07-01','2024-07-31 23:00',freq='1h')).fillna(0).values.reshape(31,24)/CAP*100
fig,ax=plt.subplots(figsize=(11,4.8))
im=ax.imshow(mat, aspect='auto', cmap='YlOrRd', vmin=0, vmax=105)
ax.set_yticks(range(31)); ax.set_yticklabels([d.strftime('%m-%d') for d in daily['date']], fontsize=7)
ax.set_xticks(range(0,24,2)); ax.set_xticklabels(range(0,24,2), fontsize=8)
ax.set_title('날짜·시간대별 주차 점유율(%) — 2,200대 기준', fontsize=13, weight='bold')
ax.set_xlabel('시')
cb=plt.colorbar(im, ax=ax, pad=0.01); cb.set_label('%')
ax.grid(False)
plt.tight_layout(); plt.savefig('figs/fig3_heatmap.png', dpi=170); plt.close()

# 4) 좌석 규모 vs 피크 점유율
fig,ax=plt.subplots(figsize=(6.6,4.4))
sc=ax.scatter(daily['seats']/1000, daily['peak_occ']/CAP*100, c=daily['precip_sum'], s=45, cmap='Blues', edgecolor='k', linewidth=0.4)
for _,r in daily.nlargest(4,'peak_occ').iterrows():
    ax.annotate(r['date'].strftime('%m-%d'), (r['seats']/1000, r['peak_occ']/CAP*100), fontsize=7, xytext=(4,4), textcoords='offset points')
ax.axhline(90, ls='--', color=C['red'], lw=1)
ax.set_xlabel('당일 공연 좌석 환산 규모(천석)'); ax.set_ylabel('일 최대 점유율(%)')
ax.set_title('공연 규모와 주차 피크 점유율', fontsize=12, weight='bold')
cb=plt.colorbar(sc, ax=ax); cb.set_label('강수량(mm)')
plt.tight_layout(); plt.savefig('figs/fig4_scatter.png', dpi=170); plt.close()

# 5) 강수 구간별
fig,ax=plt.subplots(figsize=(6.4,4.2))
bins=[-0.1,0.9,4.9,19.9,999]; labels=['0~1mm','1~5mm','5~20mm','20mm+']
daily['pw']=pd.cut(daily['precip_sum'],bins=bins,labels=labels)
g=daily.groupby('pw', observed=True)['entries'].agg(['mean','count'])
bars=ax.bar(g.index.astype(str), g['mean'], color=[C['sand'],C['sky'],C['blue'],C['navy']])
for b,v,n in zip(bars,g['mean'],g['count']): ax.text(b.get_x()+b.get_width()/2, v+60, f'{v:,.0f}대\n({n}일)', ha='center', fontsize=8)
ax.set_ylim(0,8500); ax.set_ylabel('일평균 입차 대수'); ax.set_title('일 강수량 구간별 평균 입차 대수', fontsize=12, weight='bold')
plt.tight_layout(); plt.savefig('figs/fig5_weather.png', dpi=170); plt.close()

# 6) 월별 추세
m=pd.read_csv('data/monthly.bin' if False else 'data/monthly.csv', encoding='utf-8') if False else None
import csv, io
raw=open('data/monthly.bin','rb').read().decode('cp949')
m=pd.read_csv(io.StringIO(raw))
m.columns=['year','month','place','count']
m['ym']=m['year'].astype(str)+'-'+m['month'].str.replace('월','').str.zfill(2)
fig,ax=plt.subplots(figsize=(10,4))
for place,col in [('올림픽공원',C['navy']),('미사경정공원',C['green'])]:
    s=m[m['place']==place].sort_values('ym')
    ax.plot(s['ym'], s['count'], marker='o', color=col, label=place)
ax.set_title('2023~2025년 월별 주차대수(기관 월별주차현황 데이터)', fontsize=12, weight='bold')
ax.set_ylabel('월 주차대수'); ax.tick_params(axis='x', rotation=90, labelsize=7); ax.legend(fontsize=8)
plt.tight_layout(); plt.savefig('figs/fig6_monthly.png', dpi=170); plt.close()
print('figs done')
