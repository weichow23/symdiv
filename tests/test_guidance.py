import copy
import importlib.util
from pathlib import Path

import pytest

from symdiv.guidance import validate_response
from symdiv.search import prepare


def test_guidance_does_not_accept_missing_sites_or_neural_constraints(tmp_path):
    path=tmp_path/"input.c";path.write_text("int f(int x){return 1/x;}")
    p=prepare(path);s=p["sites"][0]
    output={"findings":[{"site_id":s.site_id,"verdict":"bug","denominator":"x","path_conditions":[]}],"choices":[]}
    assert validate_response(output,p)=={}
    for key,value in (("site_id","fiction"),("denominator","7"),("path_conditions",["x==0"]),("verdict","maybe")):
        bad=copy.deepcopy(output);bad["findings"][0][key]=value
        with pytest.raises(ValueError):validate_response(bad,p)
    for findings in ([],output["findings"]*2):
        with pytest.raises(ValueError):validate_response({"findings":findings},p)


def test_v3_scoring_rejects_partial_results():
    path=Path(__file__).resolve().parents[1]/"scripts/run_v3.py"
    spec=importlib.util.spec_from_file_location("v3runner",path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    frozen={"cases":[{"id":"a","cohort":"diagnostic","expected_bug":True}]}
    for cases in ([],[{"id":"a","completed":False}],[{"id":"a","completed":True}]*2):
        with pytest.raises(ValueError):module.score({"cases":cases},frozen)
