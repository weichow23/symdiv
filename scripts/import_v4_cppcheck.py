#!/usr/bin/env python3
"""Extract unchanged, C-compilable zeroDiv regression snippets before evaluation.

The full selection/exclusion log is retained. Upstream warning assertions are
provenance, NOT automatically trusted as existential ground-truth labels.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(data): return hashlib.sha256(data).hexdigest()


def materialize(upstream, out):
    text = (upstream / "testother.cpp").read_text()
    provenance = json.loads((upstream / "testother.cpp.json").read_text())
    if sha(text.encode()) != provenance["sha256"]:
        raise ValueError("upstream source changed")
    (out / "sources").mkdir(parents=True, exist_ok=True)
    entries = list(re.finditer(r"^    void (\w+)\([^\n]*\)", text, re.M))
    strings = re.compile(r'"(?:\\.|[^"\\])*"')
    cases, screening = [], []
    for index, start in enumerate(entries):
        method = start[1]
        if not method.startswith("zeroDiv") or method == "zeroDivErrorPath":
            continue
        block = text[start.end():entries[index + 1].start() if index + 1 < len(entries) else len(text)]
        checks = re.finditer(r'\bcheck\((.*?)\);\s*(?:TODO_)?ASSERT_EQUALS\((.*?),\s*errout_str\(\)\);', block, re.S)
        for number, match in enumerate(checks, 1):
            argument = re.sub(r'//[^\n]*', '', match[1])
            # No raw strings or second arguments are silently accepted.
            literals = strings.findall(argument)
            rest = strings.sub('', argument).strip()
            item = {"upstream_method": method, "snippet": number,
                    "upstream_line": text[:start.end() + match.start()].count('\n') + 1}
            if rest or not literals:
                screening.append(dict(item, included=False, reason="nonliteral or configured check")); continue
            source = ''.join(json.loads(s) for s in literals)
            path = out / "candidate.c"; path.write_text(source)
            compile_result = subprocess.run(["clang", "-std=c11", "-Werror=implicit-function-declaration",
                                             "-fsyntax-only", str(path)], capture_output=True, text=True)
            if compile_result.returncode:
                screening.append(dict(item, included=False, reason="not standalone C11", diagnostics=compile_result.stderr.replace(str(path),"candidate.c"))); continue
            # No semantic analysis or prediction is involved in subject selection.
            from symdiv.extract import extract_sites
            sites = extract_sites(path)
            if not sites:
                screening.append(dict(item, included=False, reason="no integer divide/remainder site")); continue
            identity = "c%03d" % (len(cases) + 1)
            destination = out / "sources" / (identity + ".c")
            destination.write_text(source)
            assertion = ''.join(json.loads(s) for s in strings.findall(match[2]))
            cases.append(dict(item, id=identity, file="sources/"+identity+".c", sha256=sha(source.encode()),
                              upstream_expected_diagnostic=assertion, site_count=len(sites)))
            screening.append(dict(item, included=True, id=identity))
    (out / "candidate.c").unlink(missing_ok=True)
    (out / "selection.json").write_text(json.dumps({"upstream": provenance,
        "rule":"All unchanged standalone C11 snippets with integer division from zeroDiv* regression methods, excluding diagnostic-format-only zeroDivErrorPath. No outcome or model-based selection.",
        "screening": screening, "cases": cases}, indent=2) + "\n")
    print(json.dumps({"selected":len(cases), "screened":len(screening)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", default="benchmarks/v4-cppcheck/upstream")
    parser.add_argument("--out", default="benchmarks/v4-cppcheck")
    args = parser.parse_args()
    materialize(ROOT / args.upstream, ROOT / args.out)
