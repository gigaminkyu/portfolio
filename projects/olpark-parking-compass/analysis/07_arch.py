import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib import font_manager as fm
fp='/usr/share/fonts/pickle-hwp/NotoSansCJKkr-Regular.otf'
fm.fontManager.addfont(fp); plt.rcParams['font.family']=fm.FontProperties(fname=fp).get_name()
fig,ax=plt.subplots(figsize=(11,4.6)); ax.set_xlim(0,110); ax.set_ylim(0,46); ax.axis('off')
def box(x,y,w,h,t,sub='',fc='#EAF1FE',ec='#2F6FEB',fs=9):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle="round,pad=0.6,rounding_size=1.2",fc=fc,ec=ec,lw=1.2))
    ax.text(x+w/2,y+h-3.2 if sub else y+h/2,t,ha='center',va='center',fontsize=fs,weight='bold',color='#0E2A47')
    if sub: ax.text(x+w/2,y+h-7.6,sub,ha='center',va='top',fontsize=7.4,color='#33475B',linespacing=1.5)
def arrow(x1,y1,x2,y2,t=''):
    ax.add_patch(FancyArrowPatch((x1,y1),(x2,y2),arrowstyle='-|>',mutation_scale=12,lw=1.2,color='#5C6B7A'))
    if t: ax.text((x1+x2)/2,(y1+y2)/2+2.6,t,ha='center',fontsize=7,color='#5C6B7A',
                  bbox=dict(fc='white',ec='none',pad=1))
box(2,25,24,17,'① 공공데이터 수집','공연정보 API\n실시간 주차현황 API\n기상청 단기예보 API\n월별·입출차 파일데이터',fc='#F1F6FF')
box(31,25,25,17,'② 예측 엔진','기저 수요(요일·시간)\n＋ 공연 부하(좌석·시작시각)\n＋ 관객 성향·날씨 보정\n＝ 게이트별 24시간 예측')
box(61,25,22,17,'③ 안내 채널','웹 대시보드(모바일 대응)\n공연 D-3 알림\n현장 안내 연계',fc='#E9F7F1',ec='#1E9E6A')
box(88,25,20,17,'④ 이용자','출발 전 확인\n게이트·시간 선택\n대안(지하철·타 주차장)',fc='#FDF3E7',ec='#E8A33D')
arrow(26.5,33.5,30.5,33.5,'30분 주기')
arrow(56.5,33.5,60.5,33.5,'정적 JSON')
arrow(83.5,33.5,87.5,33.5)
box(31,3,52,13,'⑤ 무인 운영 구조','정적 호스팅 + 서버리스 스케줄러로 30분마다 예측 JSON 갱신 · 운영자 상주 불필요 · 2028년까지 유지 가능',fc='#F4F6F8',ec='#8D99AE',fs=9)
arrow(43,16.5,43,24.5,'배포'); arrow(70,16.5,70,24.5,'')
ax.text(2,44,'「올팍 주차나침반」 서비스 구조',fontsize=13,weight='bold',color='#0E2A47')
plt.tight_layout(); plt.savefig('figs/fig7_arch.png',dpi=190,bbox_inches='tight'); print('ok')
