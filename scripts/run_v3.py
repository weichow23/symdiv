#!/usr/bin/env python3
"""Frozen v3 experiment. Live calls are checkpointed; replay makes zero calls.

Wall-budget runs charge recorded service latency before resuming actual local
search. This is a serial latency-accounted replay, not a new live timing trial.
"""
import argparse
import hashlib
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import z3

from symdiv.baseline import clang_version, run_baseline_case
from symdiv.guidance import request, validate_response
from symdiv.search import Search, prepare
from symdiv.budgets import search_budgets

ROOT = Path(__file__).resolve().parents[1]


def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n"); temp.replace(path)


def make_freeze(path, config_path):
    manifests = [ROOT/"benchmarks"/name/"manifest.json" for name in ("v3-diagnostic", "v3-juliet")]
    cases=[]
    for manifest_path in manifests:
        for case in read(manifest_path)["cases"]:
            item=dict(case)
            item["cohort"] = "diagnostic" if "diagnostic" in str(manifest_path) else "juliet"
            item["file"] = str((manifest_path.parent/case["file"]).relative_to(ROOT))
            if sha(ROOT/item["file"]) != item["sha256"]: raise ValueError("source checksum mismatch")
            cases.append(item)
    # Balanced mix of cohorts in a deterministic, label-independent order.
    cases.sort(key=lambda c:hashlib.sha256(("621503:"+c["id"]).encode()).hexdigest())
    files = sorted(list((ROOT/"src/symdiv").glob("*.py")) +
                   [ROOT/"scripts/run_v3.py",ROOT/"scripts/build_v3_diagnostics.py",ROOT/"scripts/import_v3_juliet.py",
                    ROOT/"scripts/import_juliet_cwe369.py", config_path,
                    ROOT/read(config_path)["prompt"], ROOT/read(config_path)["output_schema"]]+manifests)
    write(path, {"schema_version":3,"frozen_at_utc":now(),"name":"v3-primary-26",
        "root":"../..", "cases":cases, "files":{str(f.relative_to(ROOT)):sha(f) for f in files},
        "protocol":"Authored diagnostics and new external flow families kept separate. Labels never enter model input. First real response shared by LLM-only and both guided arms; at most one correction per positive/unknown model proposal, after 48 states and a recorded source failure, with nonempty frontier. Then DFS on retained frontier. Primary 128 states/256 solver calls, sensitivity 64 and 512; three fixed random seeds. Wall-time projection uses 20 s including recorded model latency and measured preparation/search. No retries or outcome-based selection."})


def check_freeze(frozen, strict_code=True):
    compatibility_path = ROOT / "benchmarks/v3/maintenance-patch.json"
    compatibility = read(compatibility_path) if compatibility_path.exists() else {}
    for file,digest in frozen["files"].items():
        # Replay must match the code as well as the source/prompt/config.
        actual = sha(ROOT/file)
        if actual != digest:
            patch = compatibility.get("files", {}).get(file, {})
            if patch.get("original_sha256") != digest or patch.get("corrected_sha256") != actual:
                raise ValueError("frozen input changed: "+file)
    for file, digest in compatibility.get("dependencies", {}).items():
        if sha(ROOT/file) != digest: raise ValueError("maintenance dependency changed: " + file)
    for case in frozen["cases"]:
        if sha(ROOT/case["file"]) != case["sha256"]: raise ValueError("frozen subject changed: "+case["id"])
    ids=[c["id"] for c in frozen["cases"]]
    if len(ids)!=len(set(ids)): raise ValueError("duplicate case ID")


def clean_result(search):
    result=search.result()
    for finding in result["findings"]:
        path=Path(finding["site"]["file"])
        if path.is_absolute(): finding["site"]["file"]=str(path.relative_to(ROOT))
    return result


def feedback_for(search, first, config):
    result=search.result()
    positive = any(f["verdict"] in ("bug","unknown") for f in first["raw"]["output"]["findings"])
    if positive and not result["prediction"] and search.queue and not search.stopped and result["feedback"]:
        return {"status":result["status"],"spent_states":result["states"],
                "spent_solver_calls":result["solver_calls"],"remaining_tasks":result["remaining_tasks"],
                "failures":result["feedback"],"last_trace":result["last_trace"],
                "incomplete":result["incomplete"]}
    return None


def valid_preferences(record, prepared):
    try:
        return validate_response(record["raw"]["output"], prepared), None
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return {}, str(error)


def make_search(prepared, config, policy, seed=0, wall=False, state_budget=None, query_budget=None):
    states, queries = search_budgets(config, state_budget, query_budget)
    return Search(prepared, policy=policy, seed=seed,
        state_budget=1000000 if wall else states,
        query_budget=2000000 if wall else queries,
        loop_bound=config["loop_bound"],solver_ms=config["z3_timeout_ms"],
        wall_seconds=max(0,(config["wall_budget_seconds"] if wall else config["search_wall_seconds"])-prepared["prepare_seconds"]))


def guided(prepared, config, first, repair=None, use_feedback=False, wall=False, state_budget=None, request_repair=None):
    search=make_search(prepared,config,"guided",wall=wall,state_budget=state_budget)
    preferences,error=valid_preferences(first,prepared)
    search.update_guidance(preferences)
    charged=first["raw"]["_client_elapsed_seconds"]
    if wall: search.deadline-=charged
    search.advance(extra_states=config["guidance_states"])
    probe=clean_result(search)
    feedback=feedback_for(search,first,config) if not error else None
    used_repair=False;repair_error=None
    if use_feedback and feedback and not search.finding and not search.stopped:
        if request_repair is not None:
            repair=request_repair(feedback)
        if repair is not None:
            used_repair=True
            prefs,repair_error=valid_preferences(repair,prepared)
            search.update_guidance(prefs)
            charged+=repair["raw"]["_client_elapsed_seconds"]
            if wall: search.deadline-=repair["raw"]["_client_elapsed_seconds"]
            search.advance(extra_states=config["repair_states"])
    fallback=not search.finding and bool(search.queue) and not search.stopped
    if fallback:
        search.use_fallback();search.advance()
    result=clean_result(search)
    result.update(initial_policy="guided",feedback_used=used_repair,fallback_used=fallback,
                  guidance_error=error,repair_error=repair_error,probe=probe,
                  charged_model_seconds=charged,
                  accounted_seconds=prepared["prepare_seconds"]+result["elapsed_seconds"]+charged)
    # In live collection the correction request occurred during this search's
    # clock. Its cost is counted once; state-budget results expose both timings.
    if request_repair is not None and used_repair:
        latency=repair["raw"]["_client_elapsed_seconds"]
        result["accounted_seconds"]-=latency
    return result,repair


def controls(prepared, config, wall=False, state_budget=None):
    results={}
    for policy,seed in [("dfs",0),("heuristic",0)]+[("random",s) for s in config["random_seeds"]]:
        search=make_search(prepared,config,policy,seed,wall,state_budget)
        search.advance();result=clean_result(search)
        result["accounted_seconds"]=prepared["prepare_seconds"]+result["elapsed_seconds"]
        results[policy+str(seed) if policy=="random" else policy]=result
    return results


def score(run, frozen):
    expected={c["id"]:c for c in frozen["cases"]}
    cases=run["cases"]
    if len(cases)!=len(expected) or {c["id"] for c in cases}!=set(expected) or not all(c.get("completed") for c in cases):
        raise ValueError("cannot score missing, duplicate, failed, or incomplete cases")
    report={}
    for cohort in ("diagnostic","juliet"):
        selected=[c for c in cases if expected[c["id"]]["cohort"]==cohort]
        report[cohort]={}
        for regime in ("resource","wall","states64","states512"):
            if regime not in selected[0]: continue
            systems=set(selected[0][regime])
            if any(set(c[regime])!=systems for c in selected):raise ValueError("incomplete system outputs")
            report[cohort][regime]={}
            for system in sorted(systems):
                counts=dict(tp=0,fp=0,tn=0,fn=0,unknown=0,proved_safe=0)
                for c in selected:
                    r=c[regime][system]; prediction=r.get("prediction")
                    if type(prediction) is not bool: raise ValueError("prediction is not Boolean")
                    truth=expected[c["id"]]["expected_bug"]
                    counts["tp" if truth and prediction else "fp" if prediction else "fn" if truth else "tn"]+=1
                    counts["unknown"]+=r.get("status")=="unknown"
                    counts["proved_safe"]+=r.get("status")=="refuted_complete"
                counts["accuracy"]=(counts["tp"]+counts["tn"])/len(selected)
                counts["recall"]=counts["tp"]/(counts["tp"]+counts["fn"])
                counts["states"]=sum(c[regime][system].get("states",0) for c in selected)
                counts["seconds"]=sum(c[regime][system].get("accounted_seconds",c[regime][system].get("elapsed_seconds",0)) for c in selected)
                report[cohort][regime][system]=counts
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--config",default="configs/v3.json")
    p.add_argument("--freeze",default="benchmarks/v3/freeze.json")
    p.add_argument("--make-freeze",action="store_true")
    p.add_argument("--live",action="store_true")
    p.add_argument("--replay")
    p.add_argument("--out",default="results/v3/primary.json")
    p.add_argument("--sensitivity",action="store_true")
    args=p.parse_args()
    config_path=ROOT/args.config;config=read(config_path);freeze_path=ROOT/args.freeze
    if args.make_freeze:
        if freeze_path.exists():raise ValueError("refusing to overwrite an existing freeze")
        make_freeze(freeze_path,config_path);return
    frozen=read(freeze_path);check_freeze(frozen)
    if args.live == bool(args.replay): raise ValueError("select exactly one of --live or --replay")
    out=ROOT/args.out
    recorded=read(ROOT/args.replay) if args.replay else None
    if recorded and recorded["freeze_sha256"]!=sha(freeze_path):raise ValueError("replay freeze mismatch")
    old={c["id"]:c for c in recorded["cases"]} if recorded else {}
    if out.exists():raise ValueError("refusing to overwrite run output")
    run={"schema_version":3,"recorded_at_utc":now(),"mode":"live" if args.live else "replay",
         "freeze_sha256":sha(freeze_path),"configuration":config,
         "maintenance_patch":read(ROOT/"benchmarks/v3/maintenance-patch.json") if (ROOT/"benchmarks/v3/maintenance-patch.json").exists() else None,
         "environment":{"python":platform.python_version(),"platform":platform.platform(),"z3":z3.get_version_string(),"clang":clang_version("clang")},
         "timing_protocol":"Wall runs: serial recorded-latency-accounted replay with actual local search, not fresh live model requests. Resource runs: actual live or replay search with model latency reported separately.",
         "cases":[],"model_calls":0,"tokens":0,"stop_reason":None}
    for item in frozen["cases"]:
        identity=item["id"]; case={"id":identity,"file":item["file"],"source_sha256":item["sha256"],"completed":False,"calls":[]}
        run["cases"].append(case)
        if run["stop_reason"]:
            case["error"]="not run: "+run["stop_reason"];continue
        def obtain(prepared, feedback=None, previous=None):
            stage="repair" if feedback is not None else "initial"
            if recorded:
                matches=[r for r in old[identity]["calls"] if r["stage"]==stage]
                if len(matches)!=1:raise ValueError("replay is missing required call: "+identity+"/"+stage)
                record=matches[0]
                if record["source_sha256"]!=prepared["source_sha256"]:raise ValueError("stale source in replay")
            else:
                if run["model_calls"]>=config["max_calls"] or run["tokens"]>=config["max_total_tokens"]:
                    raise RuntimeError("configured model budget exhausted")
                run["model_calls"]+=1
                r=request(prepared,config,ROOT,feedback,previous)
                usage=r.raw["usage"]
                if not isinstance(usage.get("input_tokens"),int) or not isinstance(usage.get("output_tokens"),int):
                    raise RuntimeError("unknown model token usage")
                run["tokens"]+=usage["input_tokens"]+usage["output_tokens"]
                record={"stage":stage,"recorded_at_utc":now(),"source_sha256":prepared["source_sha256"],"feedback":feedback,"raw":r.raw}
            case["calls"].append(record);write(out,run)
            return record
        try:
            prepared=prepare(ROOT/item["file"]);case["prepare_seconds"]=prepared["prepare_seconds"]
            case["branches"]=prepared["branches"]
            baseline=run_baseline_case(prepared["path"])
            if not baseline["completed"]:raise RuntimeError("CSA did not complete")
            case["resource"]=controls(prepared,config)
            first=obtain(prepared)
            case["resource"]["guided"],_=guided(prepared,config,first)
            def repair_request(feedback):
                return obtain(prepared,feedback,first["raw"]["output"])
            # Record a correction against a probe without charging remote wait to
            # the local resource budget; then replay its priority on the frontier.
            probe_search=make_search(prepared,config,"guided")
            probe_search.update_guidance(valid_preferences(first,prepared)[0])
            probe_search.advance(extra_states=config["guidance_states"])
            feedback=feedback_for(probe_search,first,config)
            repair=repair_request(feedback) if feedback else None
            case["resource"]["feedback"],_=guided(prepared,config,first,repair,use_feedback=True)
            payload=first["raw"]["output"]
            case["resource"]["llm"]={"prediction":any(f["verdict"]=="bug" for f in payload["findings"]),
                "elapsed_seconds":first["raw"]["_client_elapsed_seconds"],"status":"unverified_model_prediction"}
            case["resource"]["clang"]=baseline
            case["wall"]=controls(prepared,config,wall=True)
            for name,feedback_flag in (("guided",False),("feedback",True)):
                case["wall"][name],_=guided(prepared,config,first,repair,feedback_flag,wall=True)
            for name in ("clang","llm"):
                base=dict(case["resource"][name]);base["prediction"] &= base["elapsed_seconds"]<=config["wall_budget_seconds"]
                if base["elapsed_seconds"]>config["wall_budget_seconds"]:
                    base.update(status="unknown",stop_reason="wall_time")
                case["wall"][name]=base
            if args.sensitivity:
                for budget in (64,512):
                    regime=controls(prepared,config,state_budget=budget)
                    for name,feedback_flag in (("guided",False),("feedback",True)):
                        regime[name],_=guided(prepared,config,first,repair,feedback_flag,state_budget=budget)
                    case["states"+str(budget)]=regime
            case["completed"]=True
        except Exception as error:
            case["error"]=type(error).__name__+": "+str(error)
            run["stop_reason"]="failed case; no automatic retry or unaccounted further calls"
        write(out,run)
        print(identity, "done" if case["completed"] else case["error"], "calls",run["model_calls"],"tokens",run["tokens"],flush=True)
    write(out,run)
    if not all(c["completed"] for c in run["cases"]):raise SystemExit(1)
    write(out.with_name(out.stem+"-metrics.json"),score(run,frozen))


if __name__=="__main__":main()
