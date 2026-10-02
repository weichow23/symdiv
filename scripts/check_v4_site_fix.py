#!/usr/bin/env python3
"""Audit catalogs and evaluate the separately recorded location repair."""
import json
import os
import subprocess
import tempfile
from pathlib import Path

from run_v4 import ROOT, CONFIG, Calls, check_freeze, read, write, clean, controls
from symdiv.search import prepare
from symdiv.experiment_v4 import resource_variant


def main():
    frozen=check_freeze();config=read(CONFIG)
    original={c['id']:c for c in read(ROOT/'results/v4/resource.json')['cases']}
    changed=[];catalogs={};prepared_cases={}
    for item in frozen['cases']:
        os.environ['SYMDIV_ARCHIVED_SITE_LOCATIONS']='1'
        old=prepare(ROOT/item['file'])
        os.environ.pop('SYMDIV_ARCHIVED_SITE_LOCATIONS')
        current=prepare(ROOT/item['file']);prepared_cases[item['id']]=current
        before=[s.to_dict() for s in old['sites']];after=[s.to_dict() for s in current['sites']]
        if before!=after:
            changed.append(item['id']);catalogs[item['id']]={'before':before,'after':after}
    if changed!=['c008']:raise ValueError('unexpected affected catalog: '+repr(changed))
    prepared=prepared_cases['c008']
    first=Calls(ROOT/'results/v4',config).obtain('sitefix-c008-initial',prepared)
    corrected={}
    for budget in (64,128,512):
        rows=controls(prepared,config,budget)
        rows['guided']=resource_variant(prepared,config,first,state_budget=budget)
        if budget==128:
            rows['selective']=resource_variant(prepared,config,first,selective=True)
            rows['feedback']=resource_variant(prepared,config,first,feedback=True)
        corrected['states'+str(budget)]=rows
    finding=corrected['states128']['guided']['findings'][0]
    if finding['site']['denominator']!='0':raise ValueError('incorrect repaired denominator')
    with tempfile.TemporaryDirectory(prefix='symdiv-site-fix-') as temporary:
        root=Path(temporary);source=prepared['path']
        harness=root/'check.c';exe=root/'check'
        harness.write_text('#include '+json.dumps(str(source))+'\nint main(void){f(0,0);return 0;}\n')
        subprocess.run(['clang','-std=c11','-O0','-fsanitize=undefined','-fno-sanitize-recover=all',str(harness),'-o',str(exe)],check=True,capture_output=True)
        run=subprocess.run([str(exe)],capture_output=True,text=True)
        diagnostic=next((line for line in run.stderr.splitlines() if 'runtime error:' in line),'')
        location=str(source)+':'+str(finding['site']['line'])+':'+str(finding['site']['column'])+':'
        if run.returncode==0 or location not in diagnostic or 'division by zero' not in diagnostic:
            raise ValueError('operator-specific compiled witness failed: '+diagnostic)
    differences=[];checked=0
    for identity,prepared in prepared_cases.items():
        advice=first if identity=='c008' else original[identity]['first']
        from symdiv.experiment_v4 import make_search
        results={'dfs':make_search(prepared,config).advance(),'guided':resource_variant(prepared,config,advice)}
        for policy,result in results.items():
            before=original[identity]['states128'][policy]
            checked+=1
            if (before['prediction'],before['status'])!=(result['prediction'],result['status']):
                differences.append({'id':identity,'policy':policy,'before':[before['prediction'],before['status']],
                                    'after':[result['prediction'],result['status']]})
    result={'role':'Post-study repair; original comparison retained unchanged','catalogs_checked':len(frozen['cases']),
            'affected_cases':changed,'catalogs':catalogs,'first':first,'corrected_case':corrected,
            'original_llm_prediction':original['c008']['states128']['llm']['prediction'],
            'corrected_llm_prediction':any(f['verdict']=='bug' for f in first.get('raw',{}).get('output',{}).get('findings',[])),
            'operator_witness':{'confirmed':True,'diagnostic':diagnostic,'line':finding['site']['line'],'column':finding['site']['column']},
            'current_main_cap_checks':checked,'differences':differences}
    write(ROOT/'results/v4/site-location-fix.json',clean(result))
    print(json.dumps({k:result[k] for k in ('catalogs_checked','affected_cases','original_llm_prediction','corrected_llm_prediction','operator_witness','current_main_cap_checks','differences')},indent=2))


if __name__=='__main__':main()
