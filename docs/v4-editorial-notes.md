# V4 paper revision: structure, terminology and teaser

This is a presentation revision of the recorded study, not a new evaluation.
The requested GPT-Image teaser is a conceptual illustration; all data plots
continue to come from the recorded JSON through Python/Matplotlib.

## Papers consulted

Read on 2026-10-01: the abstract, introduction, method overview and evaluation
organization of the following primary sources. The observations below concern
writing structure, not a claim that their results transfer to SymDiv.

- [AutoBug, OOPSLA 2025](https://mengrj.github.io/pdfs/autobug-oopsla25.pdf): introduces the technical representation before the implementation and gives evaluation questions explicit roles. SymDiv now defines the verification contract before explaining the scheduling policy.
- [KLEECopilot, July 2026 preprint](https://arxiv.org/html/2607.21676v1): connects a concrete search limitation to a specific mechanism and organizes results by research question. SymDiv now pairs each result with its relevant control and interpretation.
- [SAILOR, April 2026 preprint](https://arxiv.org/pdf/2604.06506): makes the responsibilities of its stages and the validation step explicit. SymDiv now distinguishes branch preferences, source verification and compiled-witness validation throughout.

The revision uses original wording. It does not copy their contribution
claims, numerical results, examples, algorithms or distinctive phrasing.
KLEECopilot and SAILOR remain identified as preprints in the bibliography.

## Editorial changes

- Lead with the scientific question: what does an LLM add once strong symbolic controls and actual request latency are included?
- Present the current method first. Keep the earlier versions as a compact design rationale and preserve their frozen evidence in the artifact.
- Separate the experimental protocol, results, validation evidence and limitations. Give each research question a direct answer tied to counts or traces.
- Explain the counting convention for the shared operation budget, and separate benchmark labels from analyzer outcomes.
- Retain the unfavorable external results, natural feedback without extra discovery, invalid-clock cohort, source-location repair and later exploratory status of SMT-first.

## Terminology contract

The canonical source is `report/terminology.json`. Tables and Python plots read
method labels from it. The paper uses **LLM-guided search**, **branch preference**,
**retained frontier**, **source verification**, **confirmed witness**,
**complete refutation**, **unknown**, **operation budget**, **solver-call budget**,
**end-to-end time**, and **model request** with distinct meanings.

“Operation budget” includes state pops and charged summary-node visits;
“state pop” denotes only worklist execution. “Safe” can denote a benchmark
label or a quoted model verdict, but is not substituted for a proof outcome.
Archived source keys and old-version reports retain their original names.

## Teaser provenance

Created with the built-in GPT-Image tool, not a CLI/API fallback. The complete
generation prompt is `report/figures/v4/teaser-prompt.txt`; any edit prompts and
selected output metadata are retained alongside the final image. The image
illustrates the architecture and evaluation dimensions without fabricated
measurements. It is disclosed separately from the experimental model calls.
