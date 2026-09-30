import json,html,pathlib,shutil
root=pathlib.Path(__file__).parent
c=json.loads((root/'content.json').read_text());page=(root/'index.template.html').read_text()
for k,v in c.items():
 if isinstance(v,str):page=page.replace('{{'+k+'}}',html.escape(v))
flows=[['관측·기간','판단 기준','보류·수정·유지'],['승인 검사','단계 기록','실패 → 재개'],['합성 CSV','정수 검산','잔액 ≠ 입금 차이']]
cases=[]
for i,case in enumerate(c['cases']):
 esc=html.escape
 labels=flows[i]
 svg=f'<svg viewBox="0 0 560 150" role="img" aria-labelledby="flow-{i} flow-desc-{i}"><title id="flow-{i}">{esc(case["title"])}</title><desc id="flow-desc-{i}">{esc(" → ".join(labels))}</desc><path d="M55 70H505" stroke="#b8b5ab" stroke-width="2"/>'
 for n,label in enumerate(labels):
  x=85+n*195;svg+=f'<circle cx="{x}" cy="70" r="6" fill="#3b512f"/><text x="{x}" y="110" text-anchor="middle" font-size="16" fill="#171a17">{esc(label)}</text>'
 svg+='</svg>'
 fields=''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k,v in case['fields'].items())
 cases.append(f'<article><div class="project-head"><span class="number">0{i+1}</span><div><span class="status">독립 구현 · 합성 예제 검증</span><h2>{esc(case["title"])}</h2></div><span class="project-type">{esc(case["label"])}</span></div><div class="project-grid"><p class="lead">{esc(case["lead"])}</p><figure class="paper">{svg}<figcaption>공개 축소 재현의 흐름입니다. 실제 운영 효과와 구분합니다.</figcaption></figure></div><dl class="case-details">{fields}</dl></article>')
page=page.replace('{{cases}}',''.join(cases));assert '{{' not in page
out=root/'dist';out.mkdir(exist_ok=True);(out/'index.html').write_text(page)
shutil.copy(root/'style.css',out/'style.css');shutil.copytree(root/'assets',out/'assets',dirs_exist_ok=True)
shutil.copytree(root/'public-demo',out/'public-demo',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
(out/'.nojekyll').touch();print('Built AX portfolio')
