# Frozen external benchmark plan

## Source and provenance

Use the NIST Juliet C/C++ 1.3 CWE-369 (Divide by Zero) tests as the independent
source. The authoritative NIST SARD suite is test suite 112, published in 2017,
with archive SHA-256
`ada9d7e1c323d283446df3f55bdee0d00bda1fed786785fe98764d58688f38eb`.
NIST describes the suite as public-domain/CC0 material. For convenient scripted
acquisition, the importer may use the public Unix-build mirror at commit
`f88433e3443648a17671398797a04ea1f8e1a274`, but it must verify that selected
files match the Juliet 1.3 content and record both sources.

References:

- <https://samate.nist.gov/SARD/test-suites/112>
- <https://github.com/arichardson/juliet-test-suite-c>

## Frozen selection rule

Create 24 derived, label-balanced C cases from 12 upstream integer CWE-369
translation units. Restrict candidates before running either analyzer to:

- C files (`.c`), integer denominators, and the `divide` or `modulo` sink;
- source families `zero` and `rand`;
- single-translation-unit flow variants `01`, `03`, `06`, `16`, `17`, and `31`;
- one positive slice from the upstream `bad` entry point and one negative slice
  from the upstream `good` entry point for each selected translation unit.

Choose `divide` for variants `01`, `06`, and `17`, and `modulo` for variants
`03`, `16`, and `31`. This fixes six source/sink/flow combinations per source
family, yielding 12 positive and 12 negative cases. Do not change this rule after
viewing analyzer predictions.

## Deterministic materialization and label blinding

Implement `scripts/import_juliet_cwe369.py` so a clean checkout can regenerate
the exact subjects and manifest:

1. Verify the upstream revision or archive checksum.
2. Materialize the `bad` and `good` preprocessor branches separately with a
   committed minimal compatibility header; do not hand-copy statements.
3. Strip comments and preprocessor labels, rename functions and identifiers
   containing `bad`, `good`, `CWE`, or `369`, and assign neutral IDs such as
   `j001` through `j024`.
4. Preserve a provenance map from neutral ID to upstream path, function, source
   family, sink, and flow variant. The map is evaluation metadata and must never
   be included in the Codex prompt.
5. Require each generated file to parse under Clang C11 and contain at least one
   integer division/remainder site. Both analyzers receive the same generated
   file.
6. Manually audit the 24 generated programs against the upstream source before
   freezing labels. Record any exclusion and apply the frozen deterministic
   replacement rule rather than choosing a convenient result.

## Experiment and reporting

- Keep the existing pilot prompt and acceptance rule unchanged.
- Use separate files under `configs/`, `results/juliet/`, and
  `report/generated/`; do not overwrite pilot results.
- Freeze a separate call and token budget after a one-case integration smoke
  test. Based on the pilot, 24 independent Codex calls require approximately
  410,000 reported tokens; use a 500,000-token ceiling unless the smoke test
  justifies a documented adjustment.
- Report pilot and Juliet strata separately. An aggregate is optional and must
  not obscure the pilot's author-created nature.
- Analyze every FP/FN and every refuted, unsupported, missing, unknown, timeout,
  malformed, or process-failure outcome. If a category has zero observations,
  say so explicitly.

This plan is intentionally modest: the course values a complete, fair
exploratory study more than raw benchmark size. Twenty-four external cases plus
the 24-case harness pilot are sufficient only if provenance, label blinding,
failure accounting, and case analysis are all completed.

## 2026-09-29 amendment before the v2 primary external run

The original acceptance rule was found unsound as a source-feasibility claim:
model-provided formulas could omit a real guard or assignment. The v1 pilot is
preserved in commit `7ccbe06` and `results/pilot/`. Version 2 is a separate,
source-grounded experiment. It keeps the model, reasoning effort, prompt, source
selection, and label policy, but replaces the acceptance rule with independent
bounded execution plus the proposed predicates over values at the site.

Acquisition used the **official checksum-verified NIST archive**, not the mirror.
All 12 selected upstream files and their original bytes/hashes are bundled. The
24 derived files retain every helper in the selected good or bad branch; there
are 44 integer sites. No cases were excluded. Labels are inherited from the
upstream branches. Agent review of transformed statements has been performed;
an independent human label audit is not claimed.

The compatibility header preserves NIST's RAND32/URAND31 macros exactly. The
execution model assumes independent rand() results in [0,2147483647], 32-bit int
and unsigned int, and Clang's two's-complement unsigned-to-signed conversion.
The unit of scoring is a file with any accepted site, identical for all systems.

The one-case smoke run (j001, separate from the primary run) used 17,913 tokens.
It exposed costly repeated feasibility checks, so before the primary run we
bounded pruning queries to 25 ms and retain unknown paths without dropping their
constraints. A fixed generic zero/one/minus-one seed check was added before the
full solver; every candidate must satisfy the complete source-derived formula.
These are execution optimizations, not changes to labels or neural predictions.

Freeze: 24 model calls, 500,000 reported tokens, no retries, 300 seconds per model
call, 8 loop iterations, 4,096 explored statement states per function, and 5,000
ms per final solver query. Cases skipped by a resource cap are explicitly failed;
full-cohort scoring refuses missing, duplicate, or failed cases. The cap can be
crossed by one completed call; an overrun is retained and reported.

Comparisons: CSA, recorded model verdict alone, source-grounded SymDiv, and the
same symbolic engine proposing a bug at every site with no neural predicates.
The pilot is reverified from its historical neural recordings without a fresh
model call. External cases receive fresh calls. Strata and costs are separate.
