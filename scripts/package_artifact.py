#!/usr/bin/env python3
"""Package committed coursework and branch/tag history; exclude app checkpoints."""
import argparse
import hashlib
import io
import json
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPOSITORY=ROOT.parent


def main():
    p=argparse.ArgumentParser();p.add_argument("--out",default="output/symdiv-artifact.zip");args=p.parse_args()
    status=subprocess.check_output(["git","status","--porcelain"],cwd=REPOSITORY,text=True)
    if status.strip():raise RuntimeError("commit the final files before packaging")
    commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPOSITORY,text=True).strip()
    archive=subprocess.check_output(["git","archive","--format=zip","--prefix=symdiv/","HEAD"],cwd=REPOSITORY)
    output=ROOT/args.out;output.parent.mkdir(exist_ok=True,parents=True)
    with zipfile.ZipFile(io.BytesIO(archive)) as original:
        entries=original.namelist()
        if any("/video/" in n or "/.venv/" in n or "/tmp/" in n or "/course-materials/" in n for n in entries):
            raise RuntimeError("excluded material was staged")
        if "symdiv/project/output/pdf/symdiv-report-v4.pdf" not in entries:raise RuntimeError("current v4 report missing")
        with tempfile.TemporaryDirectory(prefix="symdiv-package-") as temp:
            bundle=Path(temp)/"symdiv-history.bundle"
            # Desktop bookkeeping refs can contain automatic filesystem snapshots.
            # Publish the project's branch/tag history, never those private refs.
            subprocess.run(["git","bundle","create",str(bundle),"--branches","--tags"],cwd=REPOSITORY,check=True,capture_output=True)
            heads=subprocess.check_output(["git","bundle","list-heads",str(bundle)],text=True)
            if "refs/codex/" in heads:raise RuntimeError("application checkpoint included in bundle")
            with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as destination:
                for info in original.infolist():destination.writestr(info,original.read(info.filename))
                destination.write(bundle,"symdiv/project/output/symdiv-history.bundle")
                destination.writestr("symdiv/PACKAGE.json",json.dumps({"commit":commit,
                    "contents":"Committed source and reports plus complete branch/tag Git history; project under project/. No application checkpoint refs, video assignment, environments, caches, credentials, or teaching PDFs.",
                    "reproduce":"cd project; make setup; make test; make reproduce-v4",
                    "publication_status":"Local delivery; public repository URL pending"},indent=2)+"\n")
    with zipfile.ZipFile(output) as z:
        if z.testzip():raise RuntimeError("zip integrity failure")
    print(json.dumps({"path":str(output),"commit":commit,"bytes":output.stat().st_size,
                      "sha256":hashlib.sha256(output.read_bytes()).hexdigest(),"entries":len(entries)+2},indent=2))


if __name__=="__main__":main()
