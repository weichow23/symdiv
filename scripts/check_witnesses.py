#!/usr/bin/env python3
"""Replay accepted witnesses with Clang UBSan, under the declared rand input model."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from symdiv.extract import load_ast, _children


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--manifest',required=True);p.add_argument('--run',required=True)
    p.add_argument('--out',required=True);args=p.parse_args()
    manifest_path=Path(args.manifest).resolve()
    manifest=json.loads(manifest_path.read_text())
    root=manifest_path.parent/manifest.get('root','.')
    run=json.loads(Path(args.run).read_text())
    cases={c['id']:c for c in manifest['cases']}
    rows=[]
    with tempfile.TemporaryDirectory(prefix='symdiv-witness-') as temp:
        folder=Path(temp)
        for case in run['cases']:
            source=(root/cases[case['id']]['file']).resolve()
            ast=load_ast(source)
            functions={n['name']:n for n in _children(ast) if n.get('kind')=='FunctionDecl'}
            for finding in case['findings']:
                verification=finding['verification']
                if not verification['accepted']:continue
                site=finding['site']; witness=verification['model']
                function=functions[site['function']]
                inputs={k:v for k,v in witness.items() if not k.startswith('at_site:')}
                params=[n for n in _children(function) if n.get('kind')=='ParmVarDecl']
                values=[]
                for param in params:
                    matches=[v for k,v in inputs.items() if k.split(':')[1]==param['name']]
                    if len(matches)!=1:raise RuntimeError('input binding is not unique')
                    values.append(matches[0])
                random=[v for k,v in sorted(inputs.items(),key=lambda pair:int(pair[0].rsplit(':',1)[1])) if ':rand:' in k]
                # V2's recorded witnesses use the positive ternary arm; no inactive
                # values precede their site. V3 removes inactive-arm auxiliary inputs
                # when constructing its witness, so this stream follows actual calls.
                harness='#include '+json.dumps(str(source))+'\n'
                harness+='void printIntLine(int x){(void)x;}\nvoid printLine(const char *x){(void)x;}\n'
                harness+='int rand(void){static unsigned i;static const int a[]={'+','.join(random or ['0'])+'};return i<sizeof(a)/sizeof(a[0])?a[i++]:0;}\n'
                harness+='int main(void){(void)'+site['function']+'('+','.join(values)+');return 0;}\n'
                path=folder/'witness.c';path.write_text(harness)
                executable=folder/'witness'
                built=subprocess.run(['clang','-std=c11','-O0','-fsanitize=undefined','-fno-sanitize-recover=all',str(path),'-o',str(executable)],capture_output=True,text=True,timeout=30)
                if built.returncode:raise RuntimeError(built.stderr)
                ran=subprocess.run([str(executable)],capture_output=True,text=True,timeout=5)
                confirmed=ran.returncode!=0 and 'division by zero' in ran.stderr and (str(source)+':'+str(site['line'])+':') in ran.stderr
                diagnostic=next((line for line in ran.stderr.splitlines() if 'runtime error:' in line),'')
                diagnostic=diagnostic.replace(str(source),cases[case['id']]['file'])
                rows.append({'id':case['id'],'site_id':site['site_id'],'function':site['function'],
                             'confirmed':confirmed,'returncode':ran.returncode,'diagnostic':diagnostic,
                             'initial_inputs':inputs})
    result={'method':'Clang -O0 -fsanitize=undefined -fno-sanitize-recover=all; rand values supplied by recorded input model',
            'accepted_sites':len(rows),'confirmed_sites':sum(r['confirmed'] for r in rows),'cases':rows}
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n')
    print('{} / {} accepted witnesses confirmed'.format(result['confirmed_sites'],len(rows)))
    if result['confirmed_sites']!=len(rows):raise SystemExit(1)


if __name__=='__main__':main()
