"""Public AX miniature: synthetic inputs only; no external actions."""
import csv, json, pathlib, tempfile, re, math

def recommend(value, observed, period, expected, threshold=100):
    if not isinstance(observed,bool): raise ValueError('observation flag required')
    if any(not isinstance(x,str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',x) for x in [period,expected]): raise ValueError('YYYY-MM period required')
    if value is None:
        return {'action':'hold','reason':'uncollected'}
    if not observed: raise ValueError('value without observation')
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0: raise ValueError('invalid value')
    if period!=expected: return {'action':'hold','reason':'period_mismatch'}
    return {'action':'maintain' if value>=threshold else 'revise','reason':'threshold_met' if value>=threshold else 'below_threshold'}

def execute(path,key,expires,now,fail_at=None):
    if expires<=now: raise PermissionError('approval_expired')
    state=json.loads(path.read_text()) if path.exists() else {}
    job=state.setdefault(key,{'completed':[],'status':'pending'})
    if job['status']=='done': return 'skipped'
    for step in ['check','prepare','record']:
        if step in job['completed']: continue
        if step==fail_at:
            job['status']='failed';path.write_text(json.dumps(state));raise RuntimeError('synthetic_failure:'+step)
        job['completed'].append(step);job['status']='running';path.write_text(json.dumps(state))
    job['status']='done';path.write_text(json.dumps(state));return 'done'

def reconcile(path):
    with path.open() as source:
        rows=list(csv.DictReader(source))
    if not rows: raise ValueError('empty csv')
    results=[]
    for row in rows:
        keys=['revenue','cost','expected_deposit','actual_deposit']
        if any(not row[k].isdigit() for k in keys): raise ValueError('nonnegative integer amounts only')
        n={k:int(row[k]) for k in keys}
        results.append({'id':row['id'],'management_balance':n['revenue']-n['cost'],'deposit_difference':n['expected_deposit']-n['actual_deposit']})
    return results

def run():
    examples=json.loads((pathlib.Path(__file__).parent/'inputs.json').read_text())
    outputs=[{'case':x['case'],**recommend(x['value'],x['observed'],x['period'],'2026-09')} for x in examples]
    with tempfile.TemporaryDirectory() as folder:
        path=pathlib.Path(folder)/'state.json'
        try: execute(path,'synthetic-job',20,10,fail_at='prepare')
        except RuntimeError: pass
        failed=json.loads(path.read_text())['synthetic-job']
        recovered=execute(path,'synthetic-job',20,11)
        repeated=execute(path,'synthetic-job',20,12)
        try: execute(path,'expired-job',12,12)
        except PermissionError: expired='approval_expired'
        recovery={'after_failure':failed,'retry':recovered,'replay':repeated,'final':json.loads(path.read_text())['synthetic-job'],'expired':expired}
    return {'recommendations':outputs,'recovery':recovery,'csv':reconcile(pathlib.Path(__file__).parent/'settlement.csv')}
if __name__=='__main__': print(json.dumps(run(),ensure_ascii=False,indent=2))
