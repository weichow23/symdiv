#!/usr/bin/env python3
"""Complete-cohort summaries, fresh-trial distributions and generated report tables."""
import json
import statistics
from pathlib import Path
from symdiv.search import prepare
from symdiv.experiment_v4 import resource_variant

ROOT=Path(__file__).resolve().parents[1]
def read(path):return json.loads((ROOT/path).read_text())
def write(path,value):
    p=ROOT/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,indent=2)+"\n")


def counts(rows,labels):
    result=dict(tp=0,fp=0,tn=0,fn=0,unknown=0,proved_safe=0,states=0,solver_calls=0)
    for identity,row in rows:
        if type(row.get("prediction")) is not bool:raise ValueError("non-Boolean prediction")
        positive=labels[identity]["expected_bug"];prediction=row["prediction"]
        result["tp" if positive and prediction else "fp" if prediction else "fn" if positive else "tn"]+=1
        result["unknown"]+=row.get("status")=="unknown"
        result["proved_safe"]+=row.get("status")=="refuted_complete"
        result["states"]+=row.get("states",0)
        result["solver_calls"]+=row.get("solver_calls",0)
    return result


def main():
    frozen=read("benchmarks/v4/freeze.json");labels={c["id"]:c for c in frozen["cases"]}
    resource=read("results/v4/resource.json");timing=read("results/v4/timing.json");config=read("configs/v4.json")
    if len(resource["cases"])!=len(labels) or {c["id"] for c in resource["cases"]}!=set(labels) or not all(c["completed"] for c in resource["cases"]):
        raise ValueError("incomplete or duplicate resource cases")
    expected={(identity,r,method) for identity in frozen["timing_cases"] for r in range(config["timing_repetitions"])
              for method in ("dfs","portfolio","lookahead","always","selective")}
    actual={(t["id"],t["repetition"],t["system"]) for t in timing["trials"]}
    if actual!=expected or len(timing["trials"])!=len(expected):raise ValueError("incomplete or duplicate timing trials")
    metrics={}
    for cohort in ("historical","external","stress"):
        cases=[c for c in resource["cases"] if c["cohort"]==cohort];metrics[cohort]={}
        for regime in ("states64","states128","states512"):
            systems=set(cases[0][regime])
            if any(set(c[regime])!=systems for c in cases):raise ValueError("incomplete policy comparison")
            metrics[cohort][regime]={system:counts([(c["id"],c[regime][system]) for c in cases],labels) for system in sorted(systems)}
    live={}
    for system in ("dfs","portfolio","lookahead","always","selective"):
        rows=[t for t in timing["trials"] if t["system"]==system]
        result=counts([(r["id"],r) for r in rows],labels)
        elapsed=[r["elapsed_end_to_end_seconds"] for r in rows]
        result.update(n=len(rows),model_calls=sum(r["initial_model_used"] for r in rows),
                      median_seconds=statistics.median(elapsed),min_seconds=min(elapsed),max_seconds=max(elapsed),
                      total_seconds=sum(elapsed),elapsed_lower_bound_trials=sum(r.get("elapsed_time_is_lower_bound",False) for r in rows),
                      total_seconds_is_lower_bound=any(r.get("elapsed_time_is_lower_bound",False) for r in rows),
                      provider_failures=sum(bool(r.get("provider_error")) for r in rows),
                      trials=[{"id":r["id"],"repetition":r["repetition"],"seconds":r["elapsed_end_to_end_seconds"],"elapsed_time_is_lower_bound":r.get("elapsed_time_is_lower_bound",False),"status":r["status"],"model":r["initial_model_used"]} for r in rows])
        live[system]=result
    ledger=read("results/v4/model-ledger.json")
    extension=read("results/v4/smt-first/timing.json")["trials"]
    if len(extension)!=15 or {(t["id"],t["repetition"]) for t in extension}!={(i,r) for i in frozen["timing_cases"] for r in range(3)}:
        raise ValueError("incomplete or duplicate SMT-first extension")
    extension_counts=counts([(t["id"],t) for t in extension],labels)
    extension_counts.update(n=len(extension),model_calls=sum(t["initial_model_used"] for t in extension),
                            median_seconds=statistics.median(t["elapsed_end_to_end_seconds"] for t in extension),
                            total_seconds=sum(t["elapsed_end_to_end_seconds"] for t in extension),
                            trials=[{k:t[k] for k in ("id","repetition","prediction","status","initial_model_used","elapsed_end_to_end_seconds")} for t in extension])
    feedback=[]
    for c in resource["cases"]:
        result=c["states128"]["feedback"]
        if result.get("feedback_trigger") is not None:
            correction=read("results/v4/calls/"+c["id"]+"-repair.json")
            feedback.append({"id":c["id"],"cohort":c["cohort"],"trigger":result["feedback_trigger"],
                "first_verdicts":[f["verdict"] for f in c["first"]["raw"]["output"]["findings"]],
                "repair_verdicts":[f["verdict"] for f in correction.get("raw",{}).get("output",{}).get("findings",[])],
                "repair_seconds":correction.get("elapsed_seconds"),"valid_correction":result["feedback_used"],
                "without":{"prediction":c["states128"]["guided"]["prediction"],"states":c["states128"]["guided"]["states"]},
                "with":{"prediction":result["prediction"],"states":result["states"],"status":result["status"]}})
    variation=[]
    for identity in frozen["timing_cases"]:
        prepared=prepare(ROOT/labels[identity]["file"])
        rows=[]
        for trial in sorted((t for t in timing["trials"] if t["id"]==identity and t["system"]=="always"),key=lambda t:t["repetition"]):
            first=trial.get("first")
            if first is None:raise ValueError("always-request timing response missing")
            result=resource_variant(prepared,config,first)
            rows.append({"repetition":trial["repetition"],"prediction":result["prediction"],"status":result["status"],
                         "states":result["states"],"guidance_error":result.get("guidance_error"),
                         "model_bug":any(f["verdict"]=="bug" for f in first.get("raw",{}).get("output",{}).get("findings",[])),
                         "provider_error":first.get("error")})
        variation.append({"id":identity,"cohort":labels[identity]["cohort"],"expected_bug":labels[identity]["expected_bug"],"trials":rows})
    summary={"resource":metrics,"timing":live,"feedback":feedback,"repeated_response_resource_results":variation,
             "smt_first_extension":extension_counts,
             "new_calls":len(ledger["calls"]),"known_tokens":ledger["known_tokens"],
             "usage_incomplete_calls":sum(not c.get("usage_complete",False) for c in ledger["calls"]),
             "provider_seconds":sum(c.get("elapsed_seconds",0) for c in ledger["calls"])}
    invalid=read("results/v4/invalid-clock-cohort/timing.json")
    summary["invalid_clock_trials_retained"]=len(invalid["trials"])
    summary["calls_by_phase"]={
        "resource":sum(not c["key"].startswith(("timing-","sitefix-")) for c in ledger["calls"]),
        "invalid_clock_timing":sum(c["key"].startswith("timing-") and not c["key"].startswith(("timing-corrected-","timing-smtfirst-")) for c in ledger["calls"]),
        "corrected_timing":sum(c["key"].startswith("timing-corrected-") for c in ledger["calls"]),
        "smt_first_extension":sum(c["key"].startswith("timing-smtfirst-") for c in ledger["calls"]),
        "site_location_repair":sum(c["key"].startswith("sitefix-") for c in ledger["calls"])}
    summary["per_case_timing"]={identity:{
        **{method:statistics.median(t["elapsed_end_to_end_seconds"] for t in timing["trials"]
                                   if t["id"]==identity and t["system"]==method) for method in live},
        "smt_first":statistics.median(t["elapsed_end_to_end_seconds"] for t in extension if t["id"]==identity)
    } for identity in frozen["timing_cases"]}
    write("results/v4/summary.json",summary)
    names=read("report/terminology.json")["method_labels"]
    methods=("clang","dfs","portfolio","lookahead","llm","guided","feedback","selective")
    lines=[r"\begin{table*}[t]",r"\centering\small",r"\caption{Main resource comparison (128 operations / 256 solver calls). Historical diagnostics, external Cppcheck regressions and authored stress remain separate. TP is confirmed bug discovery except for CSA/LLM-only reference classifications; S denotes complete refutation, U unknown. CSA has native budgets; LLM verdicts are not safety proofs.}",r"\label{tab:v4-main}",r"\begin{tabular}{lrrrrrrrrrrrr}\toprule",
           r" & \multicolumn{4}{c}{Historical: 9 bug / 9 safe} & \multicolumn{4}{c}{External: 19 bug / 6 safe} & \multicolumn{4}{c}{Stress: 6 bug / 6 safe}\\",
           r"Method & TP & FP & S & U & TP & FP & S & U & TP & FP & S & U\\\midrule"]
    for method in methods:
        values=[]
        for cohort in ("historical","external","stress"):
            m=metrics[cohort]["states128"][method]
            values += [str(m["tp"]),str(m["fp"]),"--" if method in ("clang","llm") else str(m["proved_safe"]),"--" if method in ("clang","llm") else str(m["unknown"])]
        lines.append(names[method]+" & "+" & ".join(values)+r"\\")
    lines += [r"\bottomrule\end{tabular}",r"\end{table*}"]
    lines += [r"\begin{table}[t]\centering\small",r"\caption{Fresh end-to-end 30 s trials: five cases, three repetitions each (9 positive and 6 negative runs). Median times pool the fixed selected cases; no universal speedup is inferred.}",r"\label{tab:v4-timing}",r"\begin{tabular}{lrrrrr}\toprule",r"Method & TP & S & U & Calls & Median s\\\midrule"]
    timing_names={method:names[method] for method in ("dfs","portfolio","lookahead","always","selective")}
    for method,name in timing_names.items():
        row=live[method]
        lines.append(name+" & "+" & ".join(str(row[k]) for k in ("tp","proved_safe","unknown","model_calls"))+" & %.2f"%row["median_seconds"]+r"\\")
    lines += [r"\bottomrule\end{tabular}\end{table}"]
    # Per-case timing and budget sensitivity are shown as evidence-backed figures.
    # Exact values remain in summary.json and report/figures/v4/figure-data.json.
    (ROOT/"report/generated/v4-tables.tex").write_text("\n".join(lines)+"\n")
    print(json.dumps({"resource":{c:{m:metrics[c]['states128'][m] for m in ('dfs','lookahead','guided','feedback','selective')} for c in metrics},"timing":{m:{k:v for k,v in live[m].items() if k!='trials'} for m in live},"feedback":feedback,"calls":summary["new_calls"],"tokens":summary["known_tokens"]},indent=2))


if __name__=="__main__":main()
