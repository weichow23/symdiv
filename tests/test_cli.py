import argparse
import json
from pathlib import Path
import pytest
from symdiv.cli import command_neuro, replay_provider
from symdiv.model import ProviderResult, Hypothesis
from symdiv.extract import extract_sites
from symdiv.evaluate import evaluate


def setup_run(tmp_path, monkeypatch, max_calls=1, max_tokens=100):
    monkeypatch.chdir(tmp_path)
    (tmp_path/'a.c').write_text('int f(int x){return 42/x;}')
    (tmp_path/'b.c').write_text('int g(int x){return 42/x;}')
    manifest={'cases':[{'id':n,'file':n+'.c','expected_bug':True} for n in ('a','b')]}
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    (tmp_path/'prompt.md').write_text('test')
    (tmp_path/'config.json').write_text(json.dumps({'provider':'codex_exec','model':'mock','prompt':'prompt.md',
                                                  'max_calls':max_calls,'max_total_tokens':max_tokens}))
    def provider(source,sites,*unused):
        h=Hypothesis(sites[0].site_id,'bug',[],sites[0].denominator,'mock',1)
        return ProviderResult([h],None,10,2,{'usage':{'input_tokens':10,'output_tokens':2}})
    monkeypatch.setattr('symdiv.cli.analyze_with_codex',provider)
    args=argparse.Namespace(manifest='manifest.json',config='config.json',out='run.json',clang='clang')
    return args,manifest


def test_call_limit_preserves_missing_cases(tmp_path,monkeypatch):
    args,manifest=setup_run(tmp_path,monkeypatch)
    assert command_neuro(args)==1
    result=json.loads((tmp_path/'run.json').read_text())
    assert result['model_calls']==1
    assert len(result['cases'])==2 and result['cases'][0]['completed']
    assert result['cases'][1]['prediction'] is None
    with pytest.raises(ValueError): evaluate(manifest,{'neuro':result})


def test_budget_overrun_is_retained(tmp_path,monkeypatch):
    args,_=setup_run(tmp_path,monkeypatch,max_calls=2,max_tokens=5)
    assert command_neuro(args)==1
    result=json.loads((tmp_path/'run.json').read_text())
    assert result['total_tokens']==12 and result['model_calls']==1
    assert result['cases'][0]['completed']
    assert 'overrun retained' in result['stop_reason']


def test_replay_rejects_changed_source(tmp_path):
    path=tmp_path/'a.c';path.write_text('int f(int x){return 42/x;}')
    with pytest.raises(ValueError,match='hash'):
        replay_provider({'source_sha256':'wrong'},extract_sites(path),path)


def test_migrated_recording_can_be_replayed_again(tmp_path):
    from symdiv.cli import digest
    path=tmp_path/'a.c';path.write_text('int f(int x){return 42/x;}')
    site=extract_sites(path)[0]
    old=site.to_dict();old['site_id']='legacy-id'
    raw={'provider':'codex_exec','output':{'findings':[{'site_id':'legacy-id','verdict':'bug',
          'path_conditions':[],'denominator':'x','rationale':'recorded','confidence':1}]},'usage':{}}
    record={'source_sha256':digest(path),'raw_response':raw,'findings':[{'site':old}]}
    first=replay_provider(record,[site],path)
    second_record={'source_sha256':digest(path),'raw_response':first.raw,'findings':[{'site':site.to_dict()}]}
    second=replay_provider(second_record,[site],path)
    assert second.hypotheses[0].site_id==site.site_id
    assert second.raw['output']['findings'][0]['site_id']=='legacy-id'


def test_evaluation_rejects_changed_manifest(tmp_path,monkeypatch):
    from symdiv.cli import command_evaluate
    args,manifest=setup_run(tmp_path,monkeypatch,max_calls=2)
    assert command_neuro(args)==0
    manifest['cases'][0]['expected_bug']=False
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    evaluation=argparse.Namespace(manifest='manifest.json',baseline='run.json',neuro=None,out_dir='metrics')
    with pytest.raises(ValueError,match='different manifest'):command_evaluate(evaluation)


def test_source_hash_mismatch_is_not_a_prediction(tmp_path,monkeypatch):
    args,manifest=setup_run(tmp_path,monkeypatch,max_calls=2)
    manifest['cases'][0]['sha256']='changed'
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    assert command_neuro(args)==1
    run=json.loads((tmp_path/'run.json').read_text())
    assert not run['cases'][0]['completed'] and run['cases'][0]['prediction'] is None
    assert 'source hash mismatch' in run['cases'][0]['error']
