# Frozen experiment protocol

## Questions

- RQ1: How accurately do Clang `core.DivideZero` and SymDiv classify the same
  labelled C programs?
- RQ2: Which path patterns explain unique successes and failures of each method?
- RQ3: How often does symbolic verification accept, refute, or reject model
  hypotheses, and at what time/token cost?

## Primary outcomes

Report TP, FP, TN, FN, precision, recall, F1, and wall-clock time per system.
For SymDiv also report input/output/total tokens, accepted/refuted/unsupported/
missing hypotheses, and median and interquartile request latency. Do not discard
Codex-process errors or analyzer crashes; count and describe them separately.

## Configuration control

- Freeze the manifest before the primary live model run.
- Commit the exact prompt and configuration before observing model results.
- Use temperature 0 when the chosen model supports it.
- Run each primary subject once. If a reliability study repeats calls, report it
  as a separate experiment.
- Preserve raw model responses with secrets removed, normalized findings, Clang
  stderr/SARIF summaries, and tool versions.
- Stop before a request when the call budget is exhausted; stop after a response
  if its reported usage crosses the total-token ceiling, and report the overrun.

## Case analysis

Select at least one true positive, false positive, false negative, and true
negative per method when the category exists. Also report every verifier-refuted
hypothesis and every unsupported expression. Include negative or inconclusive
findings even if they weaken the method's apparent performance.

## Final-run checklist

- [x] Student name and NUS identifier are correct in `report/main.tex`.
- [ ] Public repository URL is immutable and accessible without login.
- [ ] API keys and local credentials are absent from Git history.
- [ ] Baseline and neural runs have no unaccounted failed cases.
- [ ] Results were regenerated from committed raw data.
- [ ] A second person or clean environment followed the README.
- [ ] The PDF is 6--10 body pages plus no more than one references page.
- [ ] Every report claim maps to a committed result or cited source.
- [ ] AI Usage Statement accurately identifies student decisions/interventions.

## Final v2 delivery

The archived v1 primary result remains unchanged. The repaired evaluation and
its frozen pre-run amendment are documented in `external-benchmark-plan.md`.
V2 reports both strata and four systems, including the negative finding that
adding the model improves no observed classification over symbolic-only.
Final reproduction evidence is in `results/validation.json`. The public URL,
student-owned review/disclosure confirmation, and official Canvas/rubric checks
remain explicitly uncompleted; they are not disguised by placeholder links.
