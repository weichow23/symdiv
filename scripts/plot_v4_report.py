#!/usr/bin/env python3
"""Publication figures from recorded v4 evidence, without running an analyzer.

Run with the optional requirements-report.txt dependencies to regenerate.
--check uses only the standard library and verifies inputs and figure hashes.
"""
import argparse
import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "report/figures/v4"
INPUTS = (
    "benchmarks/v4/freeze.json", "results/v4/resource.json",
    "results/v4/timing.json", "results/v4/smt-first/timing.json",
    "results/v4/summary.json",
    "report/terminology.json",
)
METHODS = ("dfs", "portfolio", "lookahead", "always", "selective", "smt_first")
NAMES = json.loads((ROOT / "report/terminology.json").read_text())["method_labels"]
COLORS = {"dfs": "#596777", "portfolio": "#C08525", "lookahead": "#007F8B",
          "guided": "#8051A5", "always": "#8051A5", "selective": "#C44F65",
          "smt_first": "#3778AC"}


def read(path):
    return json.loads((ROOT / path).read_text())


def digest(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def evidence():
    frozen, resource, timing, extension, summary = map(read, INPUTS[:5])
    labels = {c["id"]: c for c in frozen["cases"]}
    budgets = {}
    for cohort in ("historical", "external", "stress"):
        rows = [c for c in resource["cases"] if c["cohort"] == cohort]
        positives = sum(labels[c["id"]]["expected_bug"] for c in rows)
        budgets[cohort] = {"n": len(rows), "positive_n": positives, "methods": {}}
        for method in ("dfs", "portfolio", "lookahead", "guided"):
            values = []
            for cap in (64, 128, 512):
                tp = sum(labels[c["id"]]["expected_bug"] and
                         c["states" + str(cap)][method]["prediction"] for c in rows)
                assert tp == summary["resource"][cohort]["states" + str(cap)][method]["tp"]
                values.append(tp)
            budgets[cohort]["methods"][method] = values
    assert len(timing["trials"]) == 75 and len(extension["trials"]) == 15
    cases = frozen["timing_cases"]
    trials = []
    for method in METHODS:
        raw = extension["trials"] if method == "smt_first" else [
            t for t in timing["trials"] if t["system"] == method]
        assert len(raw) == 15
        assert {(r["id"], r["repetition"]) for r in raw} == {
            (identity, repetition) for identity in cases for repetition in range(3)}
        for row in raw:
            trials.append({"method": method, "case": row["id"],
                           "repetition": row["repetition"],
                           "seconds": row["elapsed_end_to_end_seconds"],
                           "status": row["status"], "prediction": row["prediction"],
                           "model_call": row["initial_model_used"]})
        for identity in cases:
            median = statistics.median(t["elapsed_end_to_end_seconds"] for t in raw
                                       if t["id"] == identity)
            assert median == summary["per_case_timing"][identity][method]
    calls = {}
    for method in METHODS:
        rows = [t for t in trials if t["method"] == method]
        counts = {"model_calls": sum(t["model_call"] for t in rows),
                  "tp": sum(t["prediction"] and labels[t["case"]]["expected_bug"] for t in rows),
                  "proved_safe": sum(t["status"] == "refuted_complete" for t in rows),
                  "unknown": sum(t["status"] == "unknown" for t in rows)}
        reference = summary["smt_first_extension"] if method == "smt_first" else summary["timing"][method]
        for key, value in counts.items():
            assert value == reference[key], (method, key)
        calls[method] = counts
    return {"budgets": budgets, "timing_cases": cases, "trials": trials, "calls": calls}


def draw(data):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import FixedLocator, FixedFormatter

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 8,
        "axes.titlesize": 9, "axes.titleweight": "bold", "axes.labelsize": 8,
        "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 8,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.edgecolor": "#9AA5B1", "axes.linewidth": .6,
        "text.color": "#233244", "axes.labelcolor": "#233244",
        "xtick.color": "#435366", "ytick.color": "#435366",
        "pdf.fonttype": 42, "ps.fonttype": 42, "savefig.facecolor": "white",
    })
    OUT.mkdir(parents=True, exist_ok=True)
    paths = []

    def save(fig, name):
        for extension in ("pdf", "png"):
            target = OUT / (name + "." + extension)
            kwargs = {"metadata": {"Creator": "SymDiv plot_v4_report.py", "CreationDate": None, "ModDate": None}} if extension == "pdf" else {}
            fig.savefig(target, dpi=240, **kwargs)
            paths.append(str(target.relative_to(ROOT)))
        plt.close(fig)

    # Counts, not pooled accuracy. Denominators and all three fixed caps are visible.
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.18))
    fig.subplots_adjust(left=.065, right=.992, bottom=.32, top=.83, wspace=.34)
    markers = {"dfs": "o", "portfolio": "s", "lookahead": "^", "guided": "D"}
    styles = {"dfs": "--", "portfolio": ":", "lookahead": "-.", "guided": "-"}
    titles = ("Historical diagnostics", "External regressions", "Authored stress")
    for index, (cohort, ax) in enumerate(zip(data["budgets"], axes)):
        cohort_data = data["budgets"][cohort]
        denom = cohort_data["positive_n"]
        ax.set_title(f"{chr(97 + index)}) {titles[index]}\n{denom} positives / {cohort_data['n']} programs", pad=7)
        ax.axvspan(.88, 1.12, color="#EDF0F4", zorder=0)
        for method, values in cohort_data["methods"].items():
            ax.plot(range(3), values, color=COLORS[method], marker=markers[method],
                    markersize=4.5, linewidth=1.5, linestyle=styles[method],
                    markerfacecolor="white" if method != "guided" else COLORS[method],
                    label=NAMES[method])
        ax.set_xticks(range(3), ["64", "128", "512"])
        ax.set_ylim(-.35, denom + .8)
        ax.set_yticks([0, 3, 6, 9] if denom == 9 else [0, 6, 12, 19] if denom == 19 else [0, 2, 4, 6])
        ax.set_xlim(-.12, 2.15)
        ax.grid(axis="y", color="#E1E6EB", linewidth=.5)
        ax.set_axisbelow(True)
        ax.tick_params(length=2.5)
        if cohort == "external":
            ax.text(1, 13.8, "All four: 11 / 19", ha="center", fontsize=8)
        if cohort == "stress":
            ax.annotate("6 vs 5", xy=(1, 5.5), xytext=(.1, 5.75), fontsize=7.2,
                        arrowprops={"arrowstyle": "-", "color": "#79838D", "lw": .7})
    axes[0].set_ylabel("Confirmed positives")
    fig.text(.54, .175, "Operation budget  (solver-call budget = 2 × operations)", ha="center", fontsize=8)
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=4,
               frameon=False, bbox_to_anchor=(.53, -.005), columnspacing=1.35, handlelength=2.2)
    save(fig, "budget-sensitivity")

    # Raw repetitions are shown; no inferred error bars from three observations.
    cases = data["timing_cases"]
    titles = {"c010": "c010 · safe\nC loop", "c013": "c013 · bug\nEquality",
              "s003": "s003 · bug\nWeighted sum", "s008": "s008 · safe\nCorrelated bits",
              "s011": "s011 · bug\nBounded loop"}
    fig, axes = plt.subplots(1, 5, figsize=(7.0, 2.95), sharey=True)
    fig.subplots_adjust(left=.165, right=.987, bottom=.24, top=.81, wspace=.22)
    for ax, identity in zip(axes, cases):
        ax.set_title(titles[identity], fontsize=8.4, pad=9)
        ax.axhspan(4.6, 5.42, color="#EAF0F6", zorder=0)
        ax.axhline(4.5, color="#A5B3C2", ls="--", lw=.6)
        ax.axvline(30, color="#9BA5AF", ls=":", lw=.8, zorder=1)
        for row, method in enumerate(METHODS):
            runs = sorted((t for t in data["trials"] if t["case"] == identity and t["method"] == method), key=lambda t: t["repetition"])
            times = [t["seconds"] for t in runs]
            for offset, trial in zip((-.15, 0, .15), runs):
                unknown = trial["status"] == "unknown"
                ax.scatter(trial["seconds"], row + offset, marker=">" if unknown else "o",
                           s=19 if unknown else 16, facecolors="white", edgecolors=COLORS[method],
                           linewidths=.9, zorder=3)
            ax.plot([statistics.median(times)] * 2, [row-.23, row+.23], color=COLORS[method], lw=1.5)
        ax.set_xscale("log")
        ax.set_xlim(.065, 42)
        ax.xaxis.set_major_locator(FixedLocator([.1, 1, 10, 30]))
        ax.xaxis.set_major_formatter(FixedFormatter(["0.1", "1", "10", "30"]))
        ax.minorticks_off()
        ax.tick_params(length=2, axis="both")
        ax.grid(axis="x", color="#E1E6EB", linewidth=.5)
        ax.set_axisbelow(True)
        if identity == "s008":
            ax.text(.51, .96, "All unknown", transform=ax.transAxes, ha="center", fontsize=7.1)
    axes[0].set_ylim(5.45, -.6)
    axes[0].set_yticks(range(6), [NAMES[m] for m in METHODS])
    axes[0].tick_params(axis="y", length=0, labelsize=8)
    fig.text(.56, .11, "Actual end-to-end seconds (log scale; 30 s allowance)", ha="center", fontsize=8)
    handles = [Line2D([], [], color="#596777", marker="o", markerfacecolor="white", linestyle="none", label="One fresh trial"),
               Line2D([], [], color="#596777", marker="|", markersize=8, linestyle="none", label="Median of 3"),
               Line2D([], [], color="#596777", marker=">", markerfacecolor="white", linestyle="none", label="Deadline / unknown")]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False,
               bbox_to_anchor=(.56, -.005), columnspacing=1, handletextpad=.45)
    save(fig, "fresh-timing")

    fig, ax = plt.subplots(figsize=(3.36, 1.7))
    fig.subplots_adjust(left=.335, right=.94, top=.95, bottom=.25)
    methods = ("always", "selective", "lookahead", "smt_first")
    ax.axhspan(2.5, 3.45, color="#EAF0F6", zorder=0)
    ax.axhline(2.5, color="#A5B3C2", ls="--", lw=.6)
    for index, method in enumerate(methods):
        calls = data["calls"][method]["model_calls"]
        ax.barh(index, calls, color=COLORS[method], height=.52,
                hatch="///" if method == "smt_first" else None,
                edgecolor="white", linewidth=.4, zorder=2)
        ax.text(calls + .32, index, str(calls), va="center", fontsize=8.5, weight="bold")
    ax.set_xlim(0, 17)
    ax.set_ylim(3.5, -.5)
    ax.set_yticks(range(4), [NAMES[m] for m in methods])
    ax.set_xticks([0, 5, 10, 15])
    ax.set_xlabel("Model requests per 15 fresh trials", labelpad=3)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color="#E1E6EB", linewidth=.5)
    ax.set_axisbelow(True)
    save(fig, "model-requests")
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = evidence()
    inputs = {p: digest(p) for p in INPUTS}
    builder = digest("scripts/plot_v4_report.py")
    manifest_path = OUT / "figure-data.json"
    if args.check:
        manifest = json.loads(manifest_path.read_text())
        assert manifest["inputs_sha256"] == inputs, "Figure inputs changed; regenerate figures"
        assert manifest["builder_sha256"] == builder, "Figure builder changed; regenerate figures"
        assert manifest["data"] == data, "Figure data mismatch"
        for path, expected in manifest["outputs_sha256"].items():
            assert digest(path) == expected, "Figure changed: " + path
        print("Verified 3 Python figures, 90 raw timing points, budgets, calls and source/output hashes")
        return
    paths = draw(data)
    manifest_path.write_text(json.dumps({
        "description": "Recorded evidence only. No new experiments. SMT-first is a later exploratory arm.",
        "inputs_sha256": inputs, "builder_sha256": builder,
        "outputs_sha256": {p: digest(p) for p in paths}, "data": data,
    }, indent=2) + "\n")
    print("Generated 3 vector PDF figures and PNG previews from frozen evidence")


if __name__ == "__main__":
    main()
