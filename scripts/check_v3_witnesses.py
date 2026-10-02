#!/usr/bin/env python3
"""Replay every distinct accepted witness across all primary v3 search arms."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--run",default="results/v3/primary.json")
    p.add_argument("--out",default="results/v3/witness-checks.json")
    args=p.parse_args()
    run=json.loads((ROOT/args.run).read_text()); frozen=json.loads((ROOT/"benchmarks/v3/freeze.json").read_text())
    work=ROOT/"tmp/v3-witnesses";work.mkdir(parents=True,exist_ok=True)
    cases=[];seen=set();occurrences=[]
    for c in run["cases"]:
        for regime in ("resource","wall","states64","states512"):
            for system,result in c.get(regime,{}).items():
                if system in ("clang","llm"):continue
                for finding in result.get("findings",[]):
                    key=hashlib.sha256(json.dumps([c["id"],finding["site"]["site_id"],finding["verification"]["model"]],sort_keys=True).encode()).hexdigest()
                    occurrences.append({"id":c["id"],"regime":regime,"system":system,"witness_key":key})
                    if key not in seen:
                        seen.add(key);cases.append({"id":c["id"],"findings":[finding]})
    # The v2 checker accepts repeated case IDs: each carries a distinct witness.
    (work/"run.json").write_text(json.dumps({"cases":cases},indent=2)+"\n")
    (work/"manifest.json").write_text(json.dumps({"root":str(ROOT),"cases":frozen["cases"]},indent=2)+"\n")
    subprocess.run([sys.executable,str(ROOT/"scripts/check_witnesses.py"),"--manifest",str(work/"manifest.json"),
                    "--run",str(work/"run.json"),"--out",str(work/"checked.json")],check=True,cwd=ROOT)
    checked=json.loads((work/"checked.json").read_text())
    checked.update(occurrences=len(occurrences),unique_witnesses=len(seen),mapping=occurrences)
    out=ROOT/args.out;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(checked,indent=2)+"\n")


if __name__=="__main__":main()
