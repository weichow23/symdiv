#!/usr/bin/env python3
"""Exploratory integration after the frozen comparison: cheap SMT advice first."""
import argparse
import sys
import time
from pathlib import Path

from run_v4 import ROOT, CONFIG, FREEZE, Calls, read, write, sha, now, clean, check_freeze, maintenance_matches
from symdiv.search import prepare
from symdiv.experiment_v4 import make_search, portfolio, guided
from symdiv.lookahead import apply_lookahead
from symdiv.timing import shared_clock, local_origin, supervise

SPEC=ROOT/"benchmarks/v4/smt-first-freeze.json"


def worker(identity,repetition,started_shared,out):
    spec=read(SPEC);config=read(CONFIG);item=next(c for c in read(FREEZE)["cases"] if c["id"]==identity)
    started=local_origin(started_shared);prepared=prepare(ROOT/item["file"])
    search=make_search(prepared,config,wall=True,started=started)
    advice=apply_lookahead(search,prepared,config)
    if advice["status"]=="sat_advice":
        while search.queue and not search.finding and not search.stopped and time.monotonic()<started+config["local_first_seconds"]:
            search.advance(extra_states=config["portfolio_batch"])
    else:
        portfolio(search,config,until=started+config["local_first_seconds"])
    first=None;used=False
    key="timing-smtfirst-%s-%d"%(identity,repetition)
    remaining=search.deadline-time.monotonic()
    if search.queue and not search.finding and not search.stopped and remaining>=config["minimum_model_seconds"]:
        used=True
        first=Calls(ROOT/"results/v4",config).obtain(key,prepared,timeout=remaining-0.2)
        result=guided(search,prepared,config,first,feedback=False,resource_clock=False)
    else:
        result=portfolio(search,config)
    result=clean(result)
    result.update(id=identity,repetition=repetition,key=key,system="smt_first",lookahead=advice,
                  first=first,initial_model_used=used,provider_error=first.get("error") if first else None)
    write(out/"workers"/(key+".json"),result)


def main():
    p=argparse.ArgumentParser();p.add_argument("--make-freeze",action="store_true")
    p.add_argument("--worker");p.add_argument("--repetition",type=int);p.add_argument("--started",type=float)
    args=p.parse_args();frozen=check_freeze();config=read(CONFIG);out=ROOT/"results/v4/smt-first"
    if args.make_freeze:
        if SPEC.exists():raise ValueError("extension freeze exists")
        files=list((ROOT/"src/symdiv").glob("*.py"))+[Path(__file__).resolve(),ROOT/"scripts/run_v4.py",CONFIG,
              ROOT/"docs/v4-smt-first-extension.md",FREEZE,ROOT/"benchmarks/v4/timing-amendment.json"]
        write(SPEC,{"created_at_utc":now(),"timing_cases":frozen["timing_cases"],"repetitions":3,
                    "role":"Exploratory integration on already studied cases; not held-out evidence. All trials fresh; historical comparisons are descriptive, not a new interleaved significance test.",
                    "files":{str(f.relative_to(ROOT)):sha(f) for f in files}});return
    spec=read(SPEC)
    for name,digest in spec["files"].items():
        if not maintenance_matches(name,digest):raise ValueError("extension frozen input changed: "+name)
    if args.worker:worker(args.worker,args.repetition,args.started,out);return
    path=out/"timing.json";run=read(path) if path.exists() else {"freeze_sha256":sha(SPEC),"trials":[]}
    done={r["key"] for r in run["trials"]}
    for identity in spec["timing_cases"]:
        item=next(c for c in frozen["cases"] if c["id"]==identity)
        for repetition in range(spec["repetitions"]):
            key="timing-smtfirst-%s-%d"%(identity,repetition)
            if key in done:continue
            target=out/"workers"/(key+".json")
            if not target.exists():
                started=time.monotonic();start_shared=shared_clock()
                command=[sys.executable,str(Path(__file__).resolve()),"--worker",identity,"--repetition",str(repetition),"--started",str(start_shared)]
                process=supervise(command,ROOT,started,config["wall_budget_seconds"])
                if process["timed_out"] or process["returncode"]:
                    ledger_path=ROOT/"results/v4/model-ledger.json";ledger=read(ledger_path)
                    entries=[e for e in ledger["calls"] if e["key"]==key]
                    call=ROOT/"results/v4/calls"/(key+".json");first=read(call) if call.exists() else None
                    if entries and first is None:
                        entry=entries[0]
                        elapsed=max(0,shared_clock()-entry.get("started_shared",start_shared))
                        entry.update(status="failed",usage_complete=False,elapsed_seconds=elapsed,error="outer wall deadline terminated provider")
                        first={"key":key,"source_sha256":item["sha256"],"feedback":None,"error":entry["error"],"elapsed_seconds":elapsed}
                        write(call,first);write(ledger_path,ledger)
                    result={"id":identity,"repetition":repetition,"key":key,"system":"smt_first",
                            "prediction":False,"status":"unknown","findings":[],"initial_model_used":bool(entries),
                            "first":first,"provider_error":first.get("error") if first else None,
                            "stop_reason":"supervisor_wall_time" if process["timed_out"] else "worker_error",
                            "worker_stderr":process["stderr"][-2000:]}
                else:result=read(target)
                result["elapsed_end_to_end_seconds"]=process["elapsed_seconds"]
                result["finished_at_utc"]=now()
                if process["elapsed_seconds"]>config["wall_budget_seconds"]:
                    result.update(prediction=False,status="unknown",findings=[],stop_reason="wall_time")
                write(target,result)
            result=read(target);run["trials"].append(result);write(path,run)
            print(key,result["status"],round(result["elapsed_end_to_end_seconds"],3),"model",result["initial_model_used"],flush=True)


if __name__=="__main__":main()
