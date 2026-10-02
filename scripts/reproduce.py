#!/usr/bin/env python3
"""Offline reproduction without overwriting the archived primary experiments."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def read(path): return json.loads(path.read_text())
def signature(run):
    return [(c['id'],c['prediction'],c['llm_prediction'],c['symbolic_prediction'],
             [(f['site']['site_id'],f['verification']['status'],f['symbolic_only']['status']) for f in c['findings']])
            for c in run['cases']]


def execute(command):
    subprocess.run([str(x) for x in command],cwd=ROOT,check=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',default='tmp/reproduction');args=p.parse_args()
    out=(ROOT/args.out).resolve();out.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    derived=out/'juliet-materialization'
    if not (derived/'upstream').exists():shutil.copytree(ROOT/'benchmarks/juliet/upstream',derived/'upstream')
    execute([sys.executable,'scripts/import_juliet_cwe369.py','--offline','--out',derived])
    expected=ROOT/'benchmarks/juliet'
    for filename in ['manifest.json','provenance.json']+[str(p.relative_to(expected)) for p in sorted((expected/'sources').glob('*.c'))]:
        if (derived/filename).read_bytes() != (expected/filename).read_bytes():
            raise RuntimeError('Juliet materialization differs: '+filename)
    checks=[]
    for group in ('pilot','juliet'):
        folder=out/group;folder.mkdir(parents=True,exist_ok=True)
        manifest=ROOT/'benchmarks'/group/'manifest.json'
        expected_neuro=read(ROOT/'results/v2'/group/'neuro.json')
        config=dict(expected_neuro['configuration'])
        config.update(provider='replay',replay_run=str(ROOT/'results/v2'/group/('recordings.json' if group=='pilot' else 'neuro.json')))
        config_path=folder/'replay.json';config_path.write_text(json.dumps(config,indent=2)+'\n')
        execute([sys.executable,'-m','symdiv','baseline','--manifest',manifest,'--out',folder/'baseline.json'])
        execute([sys.executable,'-m','symdiv','neuro','--manifest',manifest,'--config',config_path,'--out',folder/'neuro.json'])
        execute([sys.executable,'-m','symdiv','evaluate','--manifest',manifest,'--baseline',folder/'baseline.json','--neuro',folder/'neuro.json','--out-dir',folder])
        actual=read(folder/'metrics.json'); expected_metrics=read(ROOT/'results/v2'/group/'metrics.json')
        if actual!=expected_metrics:raise RuntimeError('metrics differ: '+group)
        if signature(read(folder/'neuro.json'))!=signature(expected_neuro):raise RuntimeError('site dispositions differ: '+group)
        checks.append({'stratum':group,'metrics_identical':True,'site_dispositions_identical':True})
    result={'passed':True,'new_model_calls':0,'materialized_files_identical':24,
            'checks':checks,'elapsed_seconds':time.monotonic()-started,'workspace':str(ROOT)}
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Offline reproduction passed: both strata, all systems, and all site dispositions.')


if __name__=='__main__':main()
