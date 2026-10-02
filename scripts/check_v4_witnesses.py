#!/usr/bin/env python3
"""Verify all distinct accepted v4 inputs, including fresh timing trials."""
import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from symdiv.extract import load_ast,_children

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser();p.add_argument("--run-dir",default="results/v4");p.add_argument("--out",default="results/v4/witness-checks.json")
    args=p.parse_args();directory=ROOT/args.run_dir
    frozen=json.loads((ROOT/"benchmarks/v4/freeze.json").read_text())
    labels={c["id"]:c for c in frozen["cases"]}
    resource=json.loads((directory/"resource.json").read_text())
    records=[]
    for case in resource["cases"]:
        for regime in ("states64","states128","states512"):
            for policy,result in case[regime].items():
                # Reference classifiers emit warnings/verdicts, not executable
                # input witnesses from our interpreter.
                if policy in ("clang", "llm"):
                    continue
                for finding in result.get("findings",[]):
                    records.append((case["id"],regime+":"+policy,finding))
    if (directory/"timing.json").exists():
        for trial in json.loads((directory/"timing.json").read_text())["trials"]:
            for finding in trial.get("findings",[]):records.append((trial["id"],trial["key"],finding))
    if (directory/"smt-first/timing.json").exists():
        for trial in json.loads((directory/"smt-first/timing.json").read_text())["trials"]:
            for finding in trial.get("findings",[]):records.append((trial["id"],trial["key"],finding))
    seen={};occurrences=[]
    for identity,arm,finding in records:
        key=hashlib.sha256(json.dumps([identity,finding["site"]["site_id"],finding["verification"]["model"]],sort_keys=True).encode()).hexdigest()
        occurrences.append({"id":identity,"arm":arm,"key":key})
        seen[key]=(identity,finding)
    rows=[]
    with tempfile.TemporaryDirectory(prefix="symdiv-v4-witness-") as temp:
        work=Path(temp)
        for key,(identity,finding) in seen.items():
            source=ROOT/labels[identity]["file"]
            nodes=[n for n in _children(load_ast(source)) if n.get("kind")=="FunctionDecl"]
            function=next(n for n in nodes if n.get("name")==finding["site"]["function"] and any(c.get("kind")=="CompoundStmt" for c in _children(n)))
            inputs={k:v for k,v in finding["verification"]["model"].items() if not k.startswith("at_site:")}
            values=[]
            for param in (n for n in _children(function) if n.get("kind")=="ParmVarDecl"):
                matches=[v for k,v in inputs.items() if k.split(":")[1]==param["name"]]
                if len(matches)!=1:raise RuntimeError("ambiguous witness input")
                values.append(matches[0])
            random=[v for k,v in sorted(inputs.items(),key=lambda pair:int(pair[0].rsplit(":",1)[1])) if ":rand:" in k]
            text='#define main original_main\n#include '+json.dumps(str(source))+'\n#undef main\n'
            defined={n["name"] for n in nodes if any(c.get("kind")=="CompoundStmt" for c in _children(n))}
            for node in nodes:
                name=node["name"]
                if name in defined or name=="rand":continue
                defined.add(name)
                ret=node["type"]["qualType"].split("(")[0].strip()
                params=[n["type"]["qualType"]+" p"+str(i) for i,n in enumerate(c for c in _children(node) if c.get("kind")=="ParmVarDecl")]
                text+=ret+" "+name+"("+(",".join(params) or "void")+"){"+("" if ret=="void" else "return 0;")+"}\n"
            if any(n["name"]=="rand" for n in nodes):
                text+='int rand(void){static unsigned i;static const int a[]={'+','.join(random or ['0'])+'};return i<sizeof(a)/sizeof(a[0])?a[i++]:0;}\n'
            target="original_main" if function["name"]=="main" else function["name"]
            text+='int main(void){(void)'+target+'('+','.join(values)+');return 0;}\n'
            path=work/"witness.c";path.write_text(text);exe=work/"witness"
            built=subprocess.run(["clang","-std=c11","-O0","-fsanitize=undefined","-fno-sanitize-recover=all",str(path),"-o",str(exe)],capture_output=True,text=True,timeout=30)
            if built.returncode:raise RuntimeError(identity+": "+built.stderr)
            ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=5)
            diagnostic=next((line for line in ran.stderr.splitlines() if "runtime error:" in line),"")
            confirmed=ran.returncode!=0 and "division by zero" in diagnostic and (str(source)+":"+str(finding["site"]["line"])+":") in diagnostic
            rows.append({"id":identity,"key":key,"site_id":finding["site"]["site_id"],"confirmed":confirmed,
                         "inputs":inputs,"diagnostic":diagnostic.replace(str(ROOT)+"/", "")})
            if not confirmed:raise RuntimeError("unconfirmed witness: "+identity+" "+ran.stderr)
    result={"occurrences":len(occurrences),"unique_witnesses":len(rows),"confirmed":sum(c["confirmed"] for c in rows),
            "cases":rows,"mapping":occurrences,"method":"Source-line-matched C/UBSan with explicit recorded entry and random inputs; inert external stubs occur only after accepted zero division or observational prints."}
    (ROOT/args.out).parent.mkdir(parents=True,exist_ok=True)
    (ROOT/args.out).write_text(json.dumps(result,indent=2)+"\n")
    print("All",len(rows),"distinct v4 witnesses confirmed")


if __name__=="__main__":main()
