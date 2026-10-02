#!/usr/bin/env python3
"""Predefined held-out parameter/structure stress tests; explicitly authored."""
import hashlib
import itertools
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(out):
    rng = random.Random(20261001)
    cases, evidence = [], []
    (out / "sources").mkdir(parents=True, exist_ok=True)
    for family in ("weighted", "coupled", "loop"):
        for depth in ((7, 8) if family == "loop" else (9, 11)):
            weights = [rng.randrange(2, 30) for _ in range(depth)] if family != "loop" else [3*i+2 for i in range(depth)]
            choices = [bool(rng.getrandbits(1)) for _ in range(depth)]
            order = list(range(depth)); rng.shuffle(order)
            target = sum(w if b else -w for w, b in zip(weights, choices))
            for positive in (True, False):
                if family == "loop":
                    lines = ["int rand(void);", "int subject(void) {", "  int d=0, w=2;",
                             "  for(int i=0;i<%d;i++) {" % depth,
                             "    int x=rand();", "    if(x%3==1) d+=w; else d-=w;", "    w+=3;", "  }"]
                else:
                    args = "int x" if family == "coupled" else ",".join("int x%d"%i for i in range(depth))
                    lines = ["int subject("+args+") {", "  int d=0;"]
                    if family == "coupled": lines += ["  if(x<0 || x>=%d) return 0;"%(2**depth)]
                    for i, w in enumerate(weights):
                        condition = "x%%%d>=%d"%(2**(order[i]+1),2**order[i]) if family == "coupled" else "x%d%%3==1"%i
                        lines += ["  if(%s) d+=%d; else d-=%d;"%(condition,w,w)]
                denominator = "d-(%d)"%target if positive else "2*d-(%d)"%(2*target+1)
                source = "\n".join(lines+["  return 100/("+denominator+");", "}"])+"\n"
                identity = "s%03d"%(len(cases)+1)
                (out/"sources"/(identity+".c")).write_text(source)
                attainable = sorted(set(sum(w if b else -w for w,b in zip(weights,bits))
                                        for bits in itertools.product((False,True),repeat=depth)))
                zeros = [d for d in attainable if (d-target if positive else 2*d-(2*target+1))==0]
                assert bool(zeros) == positive
                cases.append({"id":identity,"file":"sources/"+identity+".c","expected_bug":positive,
                              "category":family,"depth":depth,"sha256":hashlib.sha256(source.encode()).hexdigest()})
                evidence.append({"id":identity,"weights":weights,"target":target,"choices":choices,
                                 "bit_order":order,"attainable_values":attainable,"zero_values":zeros})
    (out/"manifest.json").write_text(json.dumps({"root":".","name":"v4-authored-parameter-stress",
        "selection":"All three predefined families and both depths, each paired; seed 20261001. No result-based selection.",
        "cases":cases},indent=2)+"\n")
    (out/"label-evidence.json").write_text(json.dumps({"method":"Exhaustive finite sign vectors, with defined small arithmetic; all vectors realizable by parameters or rand. Safe denominators always odd.","cases":evidence},indent=2)+"\n")


if __name__ == "__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--out",default="benchmarks/v4-stress")
    build(ROOT/p.parse_args().out)
