#!/usr/bin/env python3
"""Build-context and AST applicability screen, NOT a vulnerability evaluation."""
import argparse
import hashlib
import json
import shlex
import subprocess
import tarfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from symdiv.extract import _children, _walk, load_ast

ROOT=Path(__file__).resolve().parents[1]
PROJECTS=[
    {"project":"libpng","version":"1.6.44","commit":"f5e92d76973a7a53f517579bc95d61483bf108c0",
     "repository":"https://github.com/pnggroup/libpng","file":"pngrutil.c",
     "url":"https://codeload.github.com/pnggroup/libpng/tar.gz/f5e92d76973a7a53f517579bc95d61483bf108c0",
     "options":["-DPNG_SHARED=OFF","-DPNG_TESTS=OFF"]},
    {"project":"libsndfile","version":"1.2.2","commit":"72f6af15e8f85157bd622ed45b979025828b7001",
     "repository":"https://github.com/libsndfile/libsndfile","file":"src/pcm.c",
     "url":"https://codeload.github.com/libsndfile/libsndfile/tar.gz/72f6af15e8f85157bd622ed45b979025828b7001",
     "options":["-DBUILD_PROGRAMS=OFF","-DBUILD_EXAMPLES=OFF","-DBUILD_TESTING=OFF","-DENABLE_EXTERNAL_LIBS=OFF","-DENABLE_MPEG=OFF"]},
    {"project":"libtiff","version":"4.7.0","commit":"9dff73bebc5661f2dace6f16e14cf9e857172f4e",
     "repository":"https://gitlab.com/libtiff/libtiff","file":"libtiff/tif_dirread.c",
     "url":"https://gitlab.com/libtiff/libtiff/-/archive/9dff73bebc5661f2dace6f16e14cf9e857172f4e/libtiff-9dff73bebc5661f2dace6f16e14cf9e857172f4e.tar.gz",
     "options":["-Dtiff-tools=OFF","-Dtiff-tests=OFF","-Dtiff-contrib=OFF","-Dtiff-docs=OFF","-Dzlib=OFF","-Djpeg=OFF","-Djbig=OFF","-Dlzma=OFF","-Dzstd=OFF","-Dwebp=OFF"]},
]


def command(args,cwd):
    process=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=120)
    return {"command":args,"directory":str(cwd),"returncode":process.returncode,
            "stdout":process.stdout,"stderr":process.stderr}


def main():
    p=argparse.ArgumentParser();p.add_argument("--cmake",default=str(ROOT/".venv/bin/cmake"))
    p.add_argument("--out",default="results/v3/realworld-screen.json")
    args=p.parse_args();folder=ROOT/"tmp/realworld";folder.mkdir(parents=True,exist_ok=True)
    rows=[]
    for specification in PROJECTS:
        row=dict(specification);rows.append(row);name=row["project"]
        try:
            archive=folder/(name+".tar.gz")
            if not archive.exists():urllib.request.urlretrieve(row["url"],archive)
            row["archive_sha256"]=hashlib.sha256(archive.read_bytes()).hexdigest()
            destination=folder/(name+"-source");destination.mkdir(exist_ok=True)
            with tarfile.open(archive) as data:
                for item in data.getmembers():
                    target=(destination/item.name).resolve()
                    if destination.resolve() not in target.parents or item.issym() or item.islnk():
                        raise ValueError("unsafe archive member")
                data.extractall(destination)
            source_root=next(p for p in destination.iterdir() if p.is_dir())
            build=folder/(name+"-build")
            row["configure"]=command([args.cmake,"-S",str(source_root),"-B",str(build),
                "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"]+row["options"],ROOT)
            if row["configure"]["returncode"]:raise RuntimeError("configuration failed")
            if name=="libpng":
                row["generate_header"]=command([args.cmake,"--build",str(build),"--target","pnglibconf_h"],ROOT)
                if row["generate_header"]["returncode"]:raise RuntimeError("upstream generated header target failed")
            selected=(source_root/row["file"]).resolve()
            row["source_sha256"]=hashlib.sha256(selected.read_bytes()).hexdigest()
            entries=json.loads((build/"compile_commands.json").read_text())
            matches=[e for e in entries if Path(e["file"]).resolve()==selected]
            if not matches:raise RuntimeError("selected file absent from compilation database")
            entry=matches[0];original=shlex.split(entry["command"])
            flags=[];skip=False
            for word in original[1:]:
                if skip:skip=False;continue
                if word=="-o":skip=True;continue
                if word=="-c" or word==str(selected):continue
                flags.append(word)
            ast_path=folder/(name+"-ast.json")
            ast_command=[original[0]]+flags+["-fsyntax-only","-Xclang","-ast-dump=json",str(selected)]
            with ast_path.open("w") as output:
                process=subprocess.run(ast_command,cwd=entry["directory"],stdout=output,
                                       stderr=subprocess.PIPE,text=True,timeout=60)
            row["syntax"]={"command":ast_command,"directory":entry["directory"],
                           "returncode":process.returncode,"stderr":process.stderr}
            if process.returncode:raise RuntimeError("syntax/AST compilation failed")
            ast=json.loads(ast_path.read_text());functions=[];last_file=None
            for node in _children(ast):
                location=node.get("loc",{})
                if "file" in location:last_file=location["file"]
                if node.get("kind")!="FunctionDecl" or location.get("includedFrom") or last_file!=str(selected):continue
                if not any(n.get("kind")=="CompoundStmt" for n in _children(node)):continue
                divisions=[n for n in _walk(node) if n.get("opcode") in ("/","%","/=","%=") and
                           not any(t in n.get("type",{}).get("qualType","") for t in ("float","double"))]
                if not divisions:continue
                reasons=set()
                for n in _walk(node):
                    kind=n.get("kind")
                    if kind in ("ParmVarDecl","VarDecl"):
                        spelling=n.get("type",{}).get("desugaredQualType",n.get("type",{}).get("qualType",""))
                        normalized=spelling.replace("const ","").replace("volatile ","")
                        if normalized not in ("int","unsigned int","_Bool"):reasons.add("non-scalar-or-unsupported-type")
                    if kind in ("MemberExpr","ArraySubscriptExpr"):reasons.add("memory-access")
                    if kind=="CallExpr":reasons.add("calls-need-reviewed-summaries")
                    if kind in ("SwitchStmt","GotoStmt"):reasons.add("unsupported-control-flow")
                functions.append({"function":node["name"],"line":location.get("line"),"integer_division_sites":len(divisions),
                                  "structural_blockers":sorted(reasons)})
            row["functions_with_integer_division"]=functions
            row["selected_unit_sites"]=sum(f["integer_division_sites"] for f in functions)
            row["without_structural_blockers"]=sum(not f["structural_blockers"] for f in functions)
            try:
                load_ast(selected)
                row["direct_frontend"]="accepted"
            except Exception as error:
                row["direct_frontend"]="rejected: "+str(error)
            row["completed"]=True
        except Exception as error:
            row["completed"]=False;row["error"]=type(error).__name__+": "+str(error)
        print(name,"screen complete" if row["completed"] else row["error"],flush=True)
    result={"recorded_at_utc":datetime.now(timezone.utc).isoformat(),
        "method":"Configure upstream build, syntax-check one fixed translation unit with its compilation-database flags, inspect actual AST for required unsupported features. No source slicing, semantic replacement, vulnerability labels, or whole-project performance claims.",
        "cmake":command([args.cmake,"--version"],ROOT)["stdout"].splitlines()[0],
        "projects":rows}
    out=ROOT/args.out;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+"\n")


if __name__=="__main__":main()
