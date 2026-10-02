import json
import subprocess
from pathlib import Path

import pytest

from symdiv.search import Search, prepare, validate_guidance


def subject(tmp_path, source):
    path = tmp_path / "subject.c"
    path.write_text(source)
    return prepare(path)


@pytest.mark.parametrize("source,expected", [
    ("int f(int x){if(x==0)return 0;return 42/x;}", "refuted_complete"),
    ("int f(void){int d=0;{int d=7;d++;}return 42/d;}", "verified_sat"),
    ("int f(void){int d=7;for(int i=0;i<3;i++){if(i<2)continue;d=0;}return 42/d;}", "verified_sat"),
    ("int f(void){int d=7;while(1){{int d=0;break;}}return 42/d;}", "refuted_complete"),
    ("int f(void){int d=7;do{d=0;}while(0);return 42/d;}", "verified_sat"),
    ("int f(void){int d=0;for(int i=0;i<2;i++){for(int j=0;j<2;j++){d++;break;}continue;}return 42/(d-2);}", "verified_sat"),
    ("int f(void){int d=0;for(;;){d=7;break;}return 42/d;}", "refuted_complete"),
    ("int f(int x){return x?42/x:0;}", "refuted_complete"),
    ("int f(void){unsigned d=4294967295u;d++;return 42/d;}", "verified_sat"),
    ("int f(int x){if(x==2147483647){int d=x+1;return 42/(d+2147483647+1);}return 0;}", "refuted_complete"),
    ("int f(int x){while(x>0)x--;return 42/(x-9);}", "unknown"),
    ("int f(int x){int *p=&x;return 42/(*p);}", "unknown"),
])
def test_scheduler_semantics(tmp_path, source, expected):
    result = Search(subject(tmp_path, source), state_budget=1000, query_budget=2000).advance()
    assert result["status"] == expected, result


def test_guidance_changes_priority_without_creating_paths(tmp_path):
    p = subject(tmp_path, "int f(int x){int d=7;if(x>0)d=7;else d=0;return 42/d;}")
    bid = p["branches"][0]["branch_id"]
    dfs = Search(p).advance()
    guided = Search(p, policy="guided", preferences={(bid, 1): False}).advance()
    assert guided["states"] < dfs["states"]
    budget = guided["states"]
    assert Search(p, state_budget=budget).advance()["status"] == "unknown"
    assert Search(p, policy="guided", preferences={(bid, 1): False}, state_budget=budget).advance()["prediction"]
    safe = subject(tmp_path, "int f(int x){if(x==0)return 0;return 42/x;}")
    wrong = {(safe["branches"][0]["branch_id"], 1): False}
    assert Search(safe, policy="guided", preferences=wrong).advance()["status"] == "refuted_complete"


def test_feedback_keeps_frontier_and_budget(tmp_path):
    p = subject(tmp_path, "int f(int x){int d=7;if(x>0)d=7;else d=0;return 42/d;}")
    bid = p["branches"][0]["branch_id"]
    search = Search(p, policy="guided", preferences={(bid, 1): True})
    first = search.advance(extra_states=6)
    visited, queries = search.visited, search.queries
    frontier = {entry[1] for entry in search.queue}
    search.update_guidance({(bid, 1): False})
    assert frontier == {entry[1] for entry in search.queue}
    assert search.visited == visited and search.queries == queries
    result = search.advance()
    assert result["prediction"] and result["states"] > first["states"]


def test_fallback_keeps_alternatives_and_spent_budget(tmp_path):
    p = subject(tmp_path, "int f(int x){int d=7;if(x>0)d=7;else d=0;return 42/d;}")
    bid=p["branches"][0]["branch_id"]
    search=Search(p,policy="guided",preferences={(bid,1):True})
    search.advance(extra_states=6)
    spent=search.visited;pending={e[1] for e in search.queue}
    search.use_fallback()
    assert pending=={e[1] for e in search.queue} and search.visited==spent
    assert search.advance()["prediction"]


def test_budgets_are_unknown_and_random_is_repeatable(tmp_path):
    p = subject(tmp_path, "int f(int x){if(x>2)x=0;return 42/x;}")
    for limits in ({"state_budget": 0}, {"query_budget": 0}, {"wall_seconds": 0}):
        assert Search(p, **limits).advance()["status"] == "unknown"
    one = Search(p, policy="random", seed=72).advance()
    two = Search(p, policy="random", seed=72).advance()
    assert (one["states"], one["solver_calls"]) == (two["states"], two["solver_calls"])


def test_guidance_validation_and_portable_ids(tmp_path):
    p = subject(tmp_path, "int f(int x){if(x>0)return 42/x;return 0;}")
    bid = p["branches"][0]["branch_id"]
    for choices in ([{"branch_id": "invented", "visit": 1, "take": True}],
                    [{"branch_id": bid, "visit": True, "take": True}],
                    [{"branch_id": bid, "visit": 1, "take": "false"}],
                    [{"branch_id": bid, "visit": 1, "take": True}] * 2):
        with pytest.raises(ValueError): validate_guidance({"choices": choices}, p)
    second = tmp_path / "relocated.c"
    second.write_bytes(p["path"].read_bytes())
    assert prepare(second)["branches"] == p["branches"]


def test_inactive_random_arm_witness_is_executable(tmp_path):
    p = subject(tmp_path, "int rand(void); int f(void){int a=rand();int d=a?rand()+1:rand();if(a)return 0;return 42/d;}")
    result = Search(p).advance()
    finding = result["findings"][0]
    inputs = {k:v for k,v in finding["verification"]["model"].items() if ":rand:" in k}
    assert len(inputs) == 2  # condition and false arm; true arm is not executed
    values = [v for k,v in sorted(inputs.items(), key=lambda x:int(x[0].rsplit(":",1)[1]))]
    harness = tmp_path / "harness.c"
    harness.write_text('#include "subject.c"\nint rand(void){static int i;int a[]={'+','.join(values)+'};return a[i++];}\nint main(void){return f();}\n')
    executable = tmp_path / "witness"
    subprocess.run(["clang", "-fsanitize=undefined", "-fno-sanitize-recover=all", str(harness), "-o", str(executable)], check=True, capture_output=True)
    ran = subprocess.run([str(executable)], capture_output=True, text=True)
    assert ran.returncode != 0 and "division by zero" in ran.stderr
