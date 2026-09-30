import json, html, pathlib, shutil
root=pathlib.Path(__file__).parent
content=json.loads((root/'content.json').read_text())
page=(root/'index.template.html').read_text()
for key,value in content.items():
    if isinstance(value,str): page=page.replace('{{'+key+'}}',html.escape(value))
links=''.join(f'<a href="{html.escape(x["url"],quote=True)}" rel="noopener noreferrer">{html.escape(x["label"])} ↗<span>공개 글 / Tistory</span></a>' for x in content['references'])
page=page.replace('{{links}}',links)
assert '{{' not in page
out=root/'dist';out.mkdir(exist_ok=True)
(out/'index.html').write_text(page)
shutil.copy(root/'style.css',out/'style.css');shutil.copytree(root/'assets',out/'assets',dirs_exist_ok=True)
(out/'.nojekyll').touch()
print('Built static site:',out)
