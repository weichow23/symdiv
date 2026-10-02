#!/usr/bin/env python3
"""Independent all-positive label witnesses, including unsupported source syntax."""
import json
import re
import subprocess
from pathlib import Path
from symdiv.extract import extract_sites,load_ast,_children

ROOT=Path(__file__).resolve().parents[1]


def main():
    manifest=json.loads((ROOT/"benchmarks/v4-cppcheck/manifest.json").read_text())
    work=ROOT/"tmp/v4-label-witnesses";work.mkdir(parents=True,exist_ok=True)
    results=[]
    for case in manifest["cases"]:
        if not case["expected_bug"]:continue
        source=ROOT/"benchmarks/v4-cppcheck"/case["file"]
        sites=extract_sites(source);function=sites[0].function
        node=next(n for n in _children(load_ast(source)) if n.get("kind")=="FunctionDecl" and n.get("name")==function and any(c.get("kind")=="CompoundStmt" for c in _children(n)))
        count=sum(c.get("kind")=="ParmVarDecl" for c in _children(node))
        text='#define main original_main\n#include "'+str(source)+'"\n#undef main\n'
        if case["id"]=="c020":text+='void do_something(void) {}\n'
        if case["id"]=="c021":text+='void do_something(int x) {(void)x;}\n'
        target="original_main" if function=="main" else function
        text+='int main(void){'+target+'('+','.join('0' for _ in range(count))+');return 0;}\n'
        harness=work/(case["id"]+".c");harness.write_text(text)
        exe=work/case["id"]
        compiled=subprocess.run(["clang","-std=c11","-O0","-fsanitize=undefined","-fno-sanitize-recover=all",str(harness),"-o",str(exe)],capture_output=True,text=True)
        if compiled.returncode:raise RuntimeError(compiled.stderr)
        ran=subprocess.run([str(exe)],capture_output=True,text=True,timeout=5)
        confirmed=ran.returncode!=0 and any(re.search(re.escape(str(source))+r':'+str(s.line)+r':\d+: runtime error: division by zero',ran.stderr) for s in sites)
        results.append({"id":case["id"],"function":function,"all_entry_arguments":0,
                        "global_environment":"C static zero initialization", "confirmed":confirmed,
                        "stderr":ran.stderr.replace(str(ROOT)+"/", ""),"returncode":ran.returncode})
        if not confirmed:raise RuntimeError("label witness not confirmed: "+case["id"]+" "+ran.stderr)
    out=ROOT/"benchmarks/v4-cppcheck/positive-label-checks.json"
    out.write_text(json.dumps({"method":"Direct C execution of explicit all-zero entry arguments; independent of SymDiv and model. All positives, no supported-subset selection.","cases":results,"confirmed":len(results)},indent=2)+"\n")
    print("Confirmed",len(results),"external positive labels")


if __name__=="__main__":main()
