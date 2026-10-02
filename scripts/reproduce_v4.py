#!/usr/bin/env python3
"""Regenerate new subjects and replay fixed-resource evidence without a model."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def read(path):return json.loads(path.read_text())
def execute(args, archived=False):
    environment=dict(os.environ)
    if archived:environment["SYMDIV_ARCHIVED_SITE_LOCATIONS"]="1"
    subprocess.run([str(a) for a in args],cwd=ROOT,env=environment,check=True)


def signature(run):
    return {c["id"]:{regime:{system:(r["prediction"],r.get("status")) for system,r in c[regime].items()}
                     for regime in ("states64","states128","states512")} for c in run["cases"]}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--out",default="tmp/reproduction-v4")
    parser.add_argument("--verify-existing",action="store_true")
    args=parser.parse_args();out=ROOT/args.out;out.mkdir(parents=True,exist_ok=True)
    start=time.monotonic()
    execute([sys.executable,"scripts/import_v4_cppcheck.py","--out",out/"cppcheck"])
    execute([sys.executable,"scripts/build_v4_stress.py","--out",out/"stress"])
    total=0
    for actual,expected in ((out/"cppcheck",ROOT/"benchmarks/v4-cppcheck"),(out/"stress",ROOT/"benchmarks/v4-stress")):
        for source in (expected/"sources").glob("*.c"):
            if source.read_bytes()!=(actual/"sources"/source.name).read_bytes():raise RuntimeError("regenerated source differs")
            total+=1
    if not args.verify_existing:
        execute([sys.executable,"scripts/run_v4.py","--resource","--replay","results/v4","--out",out],archived=True)
    original=read(ROOT/"results/v4/resource.json");actual=read(out/"resource.json")
    differences=[]
    old=signature(original);new=signature(actual)
    if set(old)!=set(new):raise RuntimeError("replay cohort differs")
    for identity in old:
        for regime in old[identity]:
            for system,before in old[identity][regime].items():
                after=new[identity][regime][system]
                if before!=after:differences.append({"id":identity,"regime":regime,"system":system,"original":before,"replay":after})
    execute([sys.executable,"scripts/check_v4_witnesses.py","--run-dir",out,"--out",out/"witness-checks.json"])
    summary={"regenerated_sources_identical":total,"resource_predictions_and_statuses_identical":not differences,
             "differences":differences,"new_model_calls":0,"fresh_timing_replayed":False,
             "confirmed_witnesses":read(out/"witness-checks.json")["confirmed"],"elapsed_seconds":time.monotonic()-start}
    (out/"reproduction-summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,indent=2))
    if differences:raise SystemExit(1)


if __name__=="__main__":main()
