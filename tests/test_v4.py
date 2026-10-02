import importlib.util
from pathlib import Path

import pytest

from symdiv.budgets import search_budgets
from symdiv.search import prepare
from symdiv.search_v4 import SearchV4
from symdiv.experiment_v4 import resource_variant
from symdiv.lookahead import apply_lookahead


def test_independent_solver_budget_and_zero_overrides():
    config = {"state_budget": 128, "query_budget": 37}
    assert search_budgets(config) == (128, 37)
    assert search_budgets(config, 64) == (64, 19)
    assert search_budgets(config, 64, 7) == (64, 7)
    assert search_budgets(config, 0) == (0, 0)
    assert search_budgets(config, query_budget=0) == (128, 0)
    with pytest.raises(ValueError): search_budgets(config, -1)


def test_runner_applies_independent_solver_limit(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/run_v3.py"
    spec = importlib.util.spec_from_file_location("v3",script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    path=tmp_path/"x.c";path.write_text("int f(int x){return 42/x;}")
    config={"state_budget":128,"query_budget":0,"loop_bound":8,"z3_timeout_ms":1000,"search_wall_seconds":20}
    search=module.make_search(prepare(path),config,"dfs")
    assert search.query_budget == 0
    assert search.advance()["stop_reason"] == "solver_calls"


@pytest.mark.parametrize("policy", SearchV4.EXTRA_POLICIES)
@pytest.mark.parametrize("source,status", [
    ("int f(int x){if(x==0)return 0;return 42/x;}", "refuted_complete"),
    ("int f(int x){int d=7;if(x>0)d=7;else d=0;return 42/d;}", "verified_sat"),
    ("int f(void){int d=7;for(int i=0;i<3;i++){if(i<2)continue;d=0;}return 42/d;}", "verified_sat"),
])
def test_controls_keep_semantics(tmp_path, policy, source, status):
    path = tmp_path / "x.c"; path.write_text(source)
    result = SearchV4(prepare(path), policy=policy, state_budget=1000).advance()
    assert result["status"] == status


def test_failure_event_retains_frontier_and_counters(tmp_path):
    path = tmp_path / "x.c"
    path.write_text("int f(int x){int d=7;if(x>0)d=7;else d=0;return 42/d;}")
    prepared = prepare(path)
    search = SearchV4(prepared, policy="guided")
    result, failure = search.advance_event(stop_on_failure=True)
    assert failure["kind"] == "zero_denominator_unsat"
    assert result["states"] < 48 and not result["prediction"]
    frontier = {entry[1] for entry in search.queue}
    counters = search.visited, search.queries
    search.set_policy("guided", {(prepared["branches"][0]["branch_id"], 1): False})
    assert frontier == {entry[1] for entry in search.queue}
    assert counters == (search.visited, search.queries)
    assert search.advance()["prediction"]


def test_selective_finishes_easy_case_without_using_model(tmp_path):
    import json
    config=json.loads((Path(__file__).resolve().parents[1]/"configs/v4.json").read_text())
    path=tmp_path/"x.c";path.write_text("int f(int x){return 42/x;}")
    result=resource_variant(prepare(path),config,{},selective=True)
    assert result["prediction"] and not result["initial_model_used"]
    assert result["initial_model_seconds"] == 0


def test_natural_historical_failure_after_old_probe_can_request_feedback():
    import json
    root=Path(__file__).resolve().parents[1]
    config=json.loads((root/"configs/v4.json").read_text())
    old=json.loads((root/"results/v3/primary.json").read_text())
    case=next(c for c in old["cases"] if c["id"]=="d005")
    first=case["calls"][0]
    triggers=[]
    def no_model(trigger):
        triggers.append(trigger)
        return None
    result=resource_variant(prepare(root/case["file"]),config,first,feedback=True,repair=no_model)
    assert len(triggers)==1
    assert triggers[0]["spent_states"]>48
    assert triggers[0]["failure"]["kind"]=="zero_denominator_unsat"
    assert not result["prediction"] and not result["feedback_used"]


@pytest.mark.parametrize("identity", ["d007","d016"])
def test_symbolic_advice_is_charged_and_reverified(identity):
    import json
    root=Path(__file__).resolve().parents[1]
    config=json.loads((root/"configs/v4.json").read_text())
    prepared=prepare(root/"benchmarks/v3-diagnostic/sources"/(identity+".c"))
    search=SearchV4(prepared,state_budget=512,query_budget=1024)
    advice=apply_lookahead(search,prepared,config)
    assert advice["status"]=="sat_advice" and advice["summary_queries"]>0
    assert search.visited==advice["summary_states"]
    assert search.queries==advice["summary_queries"]
    result=search.advance()
    assert result["prediction"] and result["findings"][0]["verification"]["accepted"]


def test_unsat_summary_does_not_claim_safety_or_remove_paths(tmp_path):
    import json
    root=Path(__file__).resolve().parents[1]
    config=json.loads((root/"configs/v4.json").read_text())
    path=tmp_path/"x.c";path.write_text("int f(int x){int d=0;if(x)d+=2;else d-=2;return 42/(2*d+1);}")
    prepared=prepare(path);search=SearchV4(prepared)
    frontier={entry[1] for entry in search.queue}
    advice=apply_lookahead(search,prepared,config)
    assert advice["status"]=="no_sat_advice"
    assert {entry[1] for entry in search.queue}==frontier
    assert search.result()["status"]=="paused"
    assert search.advance()["status"]=="refuted_complete"


def test_outer_deadline_stops_uncooperative_worker(tmp_path):
    import sys,time
    from symdiv.timing import supervise
    start=time.monotonic()
    result=supervise([sys.executable,"-c","import time; time.sleep(10)"],tmp_path,start,0.1)
    assert result["timed_out"] and result["returncode"]!=0
    assert result["elapsed_seconds"]<1


def test_incomplete_live_timing_cannot_reuse_cached_model(tmp_path):
    import json
    script=Path(__file__).resolve().parents[1]/"scripts/run_v4.py"
    spec=importlib.util.spec_from_file_location("v4",script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    (tmp_path/"calls").mkdir()
    (tmp_path/"calls/timing-example.json").write_text(json.dumps({"source_sha256":"test","feedback":None}))
    calls=module.Calls(tmp_path,{})
    with pytest.raises(RuntimeError,match="refusing cached response"):
        calls.obtain("timing-example",{"source_sha256":"test"})


def test_clock_handoff_preserves_parent_age_across_processes():
    import json,subprocess,sys,time
    from symdiv.timing import shared_clock
    started=shared_clock()
    time.sleep(0.08)
    code="import time,json;from symdiv.timing import local_origin;print(json.dumps(time.monotonic()-local_origin(%r)))" % started
    elapsed=json.loads(subprocess.check_output([sys.executable,"-c",code],text=True))
    assert 0.075 < elapsed < 2
