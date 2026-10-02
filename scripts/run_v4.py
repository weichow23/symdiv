#!/usr/bin/env python3
"""Frozen resource study and independent fresh end-to-end timing experiments."""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import z3
from symdiv.baseline import run_baseline_case, clang_version
from symdiv.search import prepare
from symdiv.guidance import request
from symdiv.experiment_v4 import make_search, portfolio, guided, resource_variant
from symdiv.lookahead import apply_lookahead
from symdiv.timing import supervise, shared_clock, local_origin

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/"configs/v4.json"
FREEZE=ROOT/"benchmarks/v4/freeze.json"


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value,indent=2)+"\n");temporary.replace(path)


def clean(value):
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
    if isinstance(value,list):return [clean(v) for v in value]
    if isinstance(value,str) and value.startswith(str(ROOT)+"/"):return value[len(str(ROOT))+1:]
    return value


def freeze():
    if FREEZE.exists():raise ValueError("freeze already exists")
    cases=[]
    for cohort,directory in (("historical","v3-diagnostic"),("external","v4-cppcheck"),("stress","v4-stress")):
        for original in read(ROOT/"benchmarks"/directory/"manifest.json")["cases"]:
            case=dict(original,cohort=cohort,file="benchmarks/"+directory+"/"+original["file"])
            if sha(ROOT/case["file"])!=case["sha256"]:raise ValueError("source hash")
            cases.append(case)
    cases.sort(key=lambda c:hashlib.sha256(("v4-20261001:"+c["id"]).encode()).hexdigest())
    files=list((ROOT/"src/symdiv").glob("*.py"))+[CONFIG,ROOT/"scripts/run_v4.py",ROOT/"scripts/import_v4_cppcheck.py",
        ROOT/"scripts/build_v4_stress.py",ROOT/"docs/v4-protocol.md",ROOT/"results/v3/primary.json",ROOT/"prompts/path_guidance_v3.txt",ROOT/"schemas/path-guidance-v3.schema.json"]
    for name in ("v3-diagnostic","v4-cppcheck","v4-stress"):
        files += list((ROOT/"benchmarks"/name).glob("*.json"))
    write(FREEZE,{"schema_version":4,"created_at_utc":now(),"cases":cases,
                  "timing_cases":["c010","c013","s003","s008","s011"],
                  "files":{str(p.relative_to(ROOT)):sha(p) for p in sorted(files)}})


def check_freeze():
    frozen=read(FREEZE)
    patch_path=ROOT/"benchmarks/v4/timing-amendment.json"
    patch=read(patch_path) if patch_path.exists() else {}
    if patch and patch.get("original_freeze_sha256")!=sha(FREEZE):raise ValueError("wrong maintenance freeze")
    for name,digest in frozen["files"].items():
        if not maintenance_matches(name,digest):
            raise ValueError("frozen file changed: "+name)
    for name,digest in patch.get("dependencies",{}).items():
        if sha(ROOT/name)!=digest:raise ValueError("timing supervisor dependency changed: "+name)
    for c in frozen["cases"]:
        if sha(ROOT/c["file"])!=c["sha256"]:raise ValueError("frozen source changed")
    return frozen


def maintenance_matches(name, digest):
    """Validate an exact, ordered hash chain; never accept an arbitrary edit."""
    for filename in ("timing-amendment.json", "site-location-amendment.json"):
        path=ROOT/"benchmarks/v4"/filename
        if not path.exists():continue
        amendment=read(path)
        if amendment["original_freeze_sha256"]!=sha(FREEZE):
            raise ValueError("wrong maintenance freeze")
        change=amendment.get("files",{}).get(name,{})
        if change.get("original_sha256")==digest:
            digest=change["corrected_sha256"]
        for dependency,expected in amendment.get("dependencies",{}).items():
            if sha(ROOT/dependency)!=expected:raise ValueError("maintenance dependency changed: "+dependency)
    return sha(ROOT/name)==digest


class Calls:
    def __init__(self,out,config,replay=None):
        self.out=out;self.config=config;self.replay=replay
        self.path=out/"model-ledger.json"
        self.ledger=read(self.path) if self.path.exists() else {"calls":[],"known_tokens":0}

    def obtain(self,key,prepared,feedback=None,previous=None,timeout=None):
        path=self.out/"calls"/(key+".json")
        if self.replay is not None:
            record=read(self.replay/"calls"/(key+".json"))
            if record["source_sha256"]!=prepared["source_sha256"] or record.get("feedback")!=feedback:
                raise ValueError("replay source or feedback differs: "+key)
            return record
        if path.exists():
            if key.startswith("timing-"):
                raise RuntimeError("refusing cached response in an unfinished fresh timing trial")
            record=read(path)
            if record["source_sha256"]!=prepared["source_sha256"] or record.get("feedback")!=feedback:
                raise ValueError("checkpoint differs")
            return record
        if any(c["key"]==key for c in self.ledger["calls"]):raise RuntimeError("interrupted call cannot be retried automatically")
        if len(self.ledger["calls"])>=self.config["max_calls"] or self.ledger["known_tokens"]>=self.config["max_total_tokens"]:
            raise RuntimeError("experiment call/token ceiling reached")
        entry={"key":key,"started_at_utc":now(),"started_shared":shared_clock(),"status":"started"}
        self.ledger["calls"].append(entry);write(self.path,self.ledger)
        effective=dict(self.config)
        if timeout is not None:effective["timeout_seconds"]=max(1,int(timeout))
        started=time.monotonic()
        try:
            raw=request(prepared,effective,ROOT,feedback,previous).raw
            record={"key":key,"source_sha256":prepared["source_sha256"],"feedback":feedback,"raw":raw}
            usage=raw.get("usage",{})
            complete=all(isinstance(usage.get(k),int) for k in ("input_tokens","output_tokens"))
            entry.update(status="completed",usage=usage,usage_complete=complete)
            if complete:self.ledger["known_tokens"]+=usage["input_tokens"]+usage["output_tokens"]
        except Exception as error:
            record={"key":key,"source_sha256":prepared["source_sha256"],"feedback":feedback,
                    "error":type(error).__name__+": "+str(error)}
            entry.update(status="failed",usage_complete=False,error=record["error"])
        entry["elapsed_seconds"]=time.monotonic()-started
        record["elapsed_seconds"]=entry["elapsed_seconds"]
        write(path,record);write(self.path,self.ledger)
        return record


def controls(prepared,config,budget):
    results={}
    policies=[("dfs",0),("heuristic",0),("bfs",0),("reverse",0),("discrepancy",0),("coverage",0),("distance",0),("portfolio",0)]+[("random",s) for s in config["random_seeds"]]
    for policy,seed in policies:
        search=make_search(prepared,config,policy,state_budget=budget,seed=seed)
        result=portfolio(search,config) if policy=="portfolio" else search.advance()
        result["local_seconds"]=prepared["prepare_seconds"]+result["elapsed_seconds"]
        results[policy+str(seed) if policy=="random" else policy]=result
    search=make_search(prepared,config,state_budget=budget)
    advice=apply_lookahead(search,prepared,config)
    result=search.advance()
    result["lookahead"]=advice
    result["local_seconds"]=prepared["prepare_seconds"]+result["elapsed_seconds"]
    results["lookahead"]=result
    return results


def resource(out,config,frozen,replay=None):
    calls=Calls(out,config,replay)
    old={c["id"]:c for c in read(ROOT/"results/v3/primary.json")["cases"]}
    path=out/"resource.json"
    run=read(path) if path.exists() else {"freeze_sha256":sha(FREEZE),"mode":"replay" if replay else "live","started_at_utc":now(),"cases":[]}
    completed={c["id"] for c in run["cases"] if c.get("completed")}
    for item in frozen["cases"]:
        if item["id"] in completed:continue
        identity=item["id"];prepared=prepare(ROOT/item["file"])
        first=(old[identity]["calls"][0] if item["cohort"]=="historical" else calls.obtain(identity+"-initial",prepared))
        if first["source_sha256"]!=prepared["source_sha256"]:raise ValueError("initial source hash")
        case={"id":identity,"cohort":item["cohort"],"file":item["file"],"first":first,"completed":False}
        for budget in (64,128,512):
            regime=controls(prepared,config,budget)
            regime["guided"]=resource_variant(prepared,config,first,state_budget=budget)
            if budget==128:
                def repair(trigger):
                    return calls.obtain(identity+"-repair",prepared,trigger,first["raw"]["output"])
                regime["feedback"]=resource_variant(prepared,config,first,feedback=True,repair=repair,state_budget=budget)
                regime["selective"]=resource_variant(prepared,config,first,selective=True,state_budget=budget)
                regime["llm"]={"prediction":any(f["verdict"]=="bug" for f in first.get("raw",{}).get("output",{}).get("findings",[])),"status":"unknown" if first.get("error") else "unverified_model_prediction"}
                regime["clang"]=run_baseline_case(prepared["path"])
                if not regime["clang"]["completed"]:raise RuntimeError("CSA did not complete")
            case["states"+str(budget)]=clean(regime)
        case["completed"]=True
        run["cases"].append(case);write(path,run)
        print(identity,"resource complete",len(run["cases"]),"/",len(frozen["cases"]),flush=True)


def wall_worker(item,config,system,key,out,started=None):
    # An independent process measures every method from before Clang preparation.
    started=time.monotonic() if started is None else local_origin(started)
    prepared=prepare(ROOT/item["file"])
    search=make_search(prepared,config,"portfolio",wall=True,started=started)
    calls=Calls(out,config)
    used=False;first=None;error=None
    if system in ("dfs","portfolio","lookahead"):
        advice=apply_lookahead(search,prepared,config) if system=="lookahead" else None
        result=portfolio(search,config) if system=="portfolio" else search.advance()
        if advice is not None:result["lookahead"]=advice
    else:
        if system=="selective":
            portfolio(search,config,until=started+config["local_first_seconds"])
        remaining=search.deadline-time.monotonic()
        if search.queue and not search.finding and not search.stopped and remaining>=config["minimum_model_seconds"]:
            used=True
            try:
                first=calls.obtain(key,prepared,timeout=remaining-0.2)
                error=first.get("error")
                result=guided(search,prepared,config,first,feedback=False,resource_clock=False)
            except RuntimeError as failure:
                error=str(failure)
                result=portfolio(search,config)
        else:
            result=portfolio(search,config)
    elapsed=time.monotonic()-started
    # No result obtained after the actual deadline may count as a success/proof.
    if elapsed>config["wall_budget_seconds"]:
        result.update(prediction=False,status="unknown",findings=[],stop_reason="wall_time")
    result=clean(result)
    result.update(id=item["id"],system=system,elapsed_end_to_end_seconds=elapsed,
                  initial_model_used=used,provider_error=error,first=first,
                  clock="fresh actual wall clock including preparation, provider process, parsing and search")
    write(out/"timing-workers"/(key+".json"),result)


def timing(out,config,frozen):
    path=out/"timing.json"
    run=read(path) if path.exists() else {"freeze_sha256":sha(FREEZE),"started_at_utc":now(),"trials":[]}
    done={r["key"] for r in run["trials"]}
    by_id={c["id"]:c for c in frozen["cases"]}
    tasks=[]
    for repetition in range(config["timing_repetitions"]):
        for identity in frozen["timing_cases"]:
            for system in ("dfs","portfolio","lookahead","always","selective"):
                key="timing-corrected-%s-%d-%s"%(identity,repetition,system)
                tasks.append((key,identity,repetition,system))
    tasks.sort(key=lambda t:hashlib.sha256(("timing-order:"+t[0].replace("timing-corrected-","timing-")).encode()).hexdigest())
    for key,identity,repetition,system in tasks:
        if key in done:continue
        worker_file=out/"timing-workers"/(key+".json")
        if not worker_file.exists():
            started=time.monotonic()
            started_shared=shared_clock()
            command=[sys.executable,str(ROOT/"scripts/run_v4.py"),"--wall-worker",identity,"--system",system,"--key",key,"--out",str(out),"--started",str(started_shared)]
            process=supervise(command,ROOT,started,config["wall_budget_seconds"])
            if process["timed_out"] or process["returncode"]:
                ledger_path=out/"model-ledger.json"
                ledger=read(ledger_path) if ledger_path.exists() else {"calls":[],"known_tokens":0}
                entries=[c for c in ledger["calls"] if c["key"]==key]
                first=None
                call_path=out/"calls"/(key+".json")
                if call_path.exists():first=read(call_path)
                elif entries:
                    entry=entries[0]
                    entry.update(status="failed",usage_complete=False,error="outer wall deadline terminated provider",
                                 elapsed_seconds=max(0,shared_clock()-entry.get("started_shared",started_shared)))
                    first={"key":key,"source_sha256":by_id[identity]["sha256"],"feedback":None,
                           "error":entry["error"],"elapsed_seconds":entry["elapsed_seconds"]}
                    write(call_path,first);write(ledger_path,ledger)
                result={"id":identity,"system":system,"prediction":False,"status":"unknown","findings":[],
                        "stop_reason":"supervisor_wall_time" if process["timed_out"] else "worker_error",
                        "initial_model_used":bool(entries),"first":first,
                        "provider_error":first.get("error") if first else None,
                        "partial_search_counters_available":False,"worker_stderr":process["stderr"][-2000:]}
            else:
                result=read(worker_file)
            result["elapsed_end_to_end_seconds"]=process["elapsed_seconds"]
            result["finished_at_utc"]=now()
            if result["elapsed_end_to_end_seconds"]>config["wall_budget_seconds"]:
                result.update(prediction=False,status="unknown",findings=[],stop_reason="wall_time")
            write(worker_file,result)
        result=read(worker_file)
        run["trials"].append(dict(result,key=key,repetition=repetition));write(path,run)
        print(key,result["status"],round(result["elapsed_end_to_end_seconds"],3),"model",result["initial_model_used"],flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--make-freeze",action="store_true")
    parser.add_argument("--resource",action="store_true")
    parser.add_argument("--timing",action="store_true")
    parser.add_argument("--replay")
    parser.add_argument("--out",default="results/v4")
    parser.add_argument("--wall-worker")
    parser.add_argument("--system")
    parser.add_argument("--key")
    parser.add_argument("--started",type=float)
    args=parser.parse_args()
    if args.make_freeze:freeze();return
    frozen=check_freeze();config=read(CONFIG);out=ROOT/args.out
    out.mkdir(parents=True,exist_ok=True)
    if args.wall_worker:
        item=next(c for c in frozen["cases"] if c["id"]==args.wall_worker)
        wall_worker(item,config,args.system,args.key,out,args.started);return
    write(out/"environment.json",{"python":platform.python_version(),"platform":platform.platform(),"z3":z3.get_version_string(),"clang":clang_version("clang"),"freeze_sha256":sha(FREEZE),
        "timing_amendment_sha256":sha(ROOT/"benchmarks/v4/timing-amendment.json") if (ROOT/"benchmarks/v4/timing-amendment.json").exists() else None})
    if args.resource:resource(out,config,frozen,ROOT/args.replay if args.replay else None)
    if args.timing:
        if args.replay:raise ValueError("fresh timing cannot be replayed; use recorded timing only as historical evidence")
        timing(out,config,frozen)


if __name__=="__main__":main()
