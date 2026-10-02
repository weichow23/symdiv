#!/usr/bin/env python3
"""Deliberately wrong advice, then one genuine repair. Separate from primary."""
import argparse
import json
from pathlib import Path

from symdiv.guidance import request, validate_response
from symdiv.search import Search, prepare

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument("--replay");p.add_argument("--out",default="results/v3/injected-feedback.json")
    args=p.parse_args();out=ROOT/args.out
    if out.exists():raise ValueError("refusing to overwrite diagnostic")
    path=ROOT/"benchmarks/v3-robustness/injected.c";path.parent.mkdir(parents=True,exist_ok=True)
    source="int f("+", ".join("int x%d"%i for i in range(6))+") {\n    int d=0;\n"
    for i in range(6):source+="    if(x%d>0) d+=%d; else d-=%d;\n"%(i,2**i,2**i)
    source+="    return 100/(d+59);\n}\n" # unique vector: false,true,false,false,false,false
    if path.exists() and path.read_text()!=source:raise ValueError("diagnostic source mismatch")
    path.write_text(source);prepared=prepare(path);config=json.loads((ROOT/"configs/v3.json").read_text())
    site=prepared["sites"][0]
    injected={"findings":[{"site_id":site.site_id,"verdict":"bug","path_conditions":[],"denominator":site.denominator,
              "rationale":"Deliberately injected wrong all-true path for a separate mechanism test.","confidence":1}],
              "choices":[{"branch_id":b["branch_id"],"visit":1,"take":True} for b in prepared["branches"]]}
    search=Search(prepared,policy="guided",preferences=validate_response(injected,prepared),
                  state_budget=128,query_budget=256,wall_seconds=20)
    before=search.advance(extra_states=48)
    if before["prediction"] or not before["feedback"]:raise RuntimeError("injection did not create a failed probe")
    feedback={"failures":before["feedback"],"last_trace":before["last_trace"],
              "spent_states":before["states"],"spent_solver_calls":before["solver_calls"]}
    if args.replay:
        old=json.loads((ROOT/args.replay).read_text())
        if old["source_sha256"]!=prepared["source_sha256"]:raise ValueError("stale feedback diagnostic")
        raw=old["repair_raw"]
    else:
        raw=request(prepared,config,ROOT,feedback,injected).raw
    # Pause remote time out of the mechanical state-budget trial. Its measured
    # latency is reported separately; this is not an equal-wall-budget claim.
    search.deadline+=raw["_client_elapsed_seconds"] if not args.replay else 0
    search.update_guidance(validate_response(raw["output"],prepared))
    after=search.advance(extra_states=48)
    if not after["prediction"] and search.queue and not search.stopped:
        search.use_fallback();after=search.advance()
    control=Search(prepared,policy="guided",preferences=validate_response(injected,prepared),
                   state_budget=128,query_budget=256,wall_seconds=20)
    control.advance(extra_states=48);control.use_fallback();without=control.advance()
    for result in (after,without):
        for finding in result["findings"]:finding["site"]["file"]=str(path.relative_to(ROOT))
    record={"kind":"injected_wrong_advice_not_natural_model_error","source_sha256":prepared["source_sha256"],
            "file":str(path.relative_to(ROOT)),"injected":injected,"probe":before,
            "repair_raw":raw,"with_repair":after,"without_repair":without,
            "new_model_calls":0 if args.replay else 1}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(record,indent=2)+"\n")
    print("Injected advice:",without["status"],"; after genuine repair:",after["status"],flush=True)


if __name__=="__main__":main()
