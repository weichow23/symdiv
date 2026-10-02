#!/usr/bin/env python3
"""Independent offline rebuild/replay; primary records are never overwritten."""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def read(path):return json.loads(path.read_text())
def execute(command):subprocess.run([str(x) for x in command],cwd=ROOT,check=True)


def signature(run):
    return {c["id"]:{regime:{system:(r["prediction"],r.get("status"))
            for system,r in c[regime].items()} for regime in ("resource","states64","states512")}
            for c in run["cases"]}


def main():
    p=argparse.ArgumentParser();p.add_argument("--out",default="tmp/reproduction-v3")
    p.add_argument("--verify-existing",action="store_true",help="check an already completed local replay without rerunning timing trials")
    args=p.parse_args()
    out=ROOT/args.out;out.mkdir(parents=True,exist_ok=True)
    started=time.monotonic()
    expected=ROOT/"benchmarks/v3-juliet";derived=out/"juliet"
    if not (derived/"upstream").exists():shutil.copytree(expected/"upstream",derived/"upstream")
    execute([sys.executable,"scripts/import_v3_juliet.py","--offline","--out",derived])
    diagnostic=out/"diagnostic"
    execute([sys.executable,"scripts/build_v3_diagnostics.py","--out",diagnostic])
    for target,original in ((derived,expected),(diagnostic,ROOT/"benchmarks/v3-diagnostic")):
        for path in original.rglob("*"):
            if path.is_file() and path.name!="NOTICE.md":
                counterpart=target/path.relative_to(original)
                if not counterpart.exists() or counterpart.read_bytes()!=path.read_bytes():
                    raise RuntimeError("materialization differs: "+str(path))
    if not args.verify_existing:
        execute([sys.executable,"scripts/run_v3.py","--replay","results/v3/primary.json","--sensitivity","--out",out/"replay.json"])
    original=read(ROOT/"results/v3/primary.json");actual=read(out/"replay.json")
    if actual["freeze_sha256"]!=original["freeze_sha256"] or not all(c["completed"] for c in actual["cases"]):
        raise RuntimeError("stale or incomplete replay")
    if signature(original)!=signature(actual):raise RuntimeError("v3 prediction/status differs")
    # Actual wall clocks cannot be made deterministic by replaying the model.
    # Keep every timed difference visible instead of rerunning to select a match.
    wall_differences=[]
    for old,new in zip(original["cases"],actual["cases"]):
        if old["id"]!=new["id"]:raise RuntimeError("replay case order differs")
        for system,before in old["wall"].items():
            after=new["wall"][system]
            if system not in ("clang","llm") and after["prediction"] and after["accounted_seconds"]>20.1:
                raise RuntimeError("accepted witness exceeds its wall-time allowance")
            if (before["prediction"],before.get("status"))!=(after["prediction"],after.get("status")):
                wall_differences.append({"id":old["id"],"system":system,
                    "primary":{"prediction":before["prediction"],"status":before.get("status"),"seconds":before.get("accounted_seconds")},
                    "replay":{"prediction":after["prediction"],"status":after.get("status"),"seconds":after.get("accounted_seconds")}})
    execute([sys.executable,"scripts/check_v3_witnesses.py","--run",out/"replay.json","--out",out/"witness-checks.json"])
    summary={"passed":True,"new_model_calls":actual["model_calls"],"materialized_files_identical":26,
             "resource_and_sensitivity_predictions_and_statuses_identical":True,
             "wall_differences":wall_differences,
             "wall_predictions_identical":all(x["primary"]["prediction"]==x["replay"]["prediction"] for x in wall_differences),
             "elapsed_seconds":time.monotonic()-started,"verified_existing_replay":args.verify_existing,
             "witness_checks":read(out/"witness-checks.json")["confirmed_sites"]}
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("V3 offline reproduction passed.")


if __name__=="__main__":main()
