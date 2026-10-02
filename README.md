# SymDiv

A source-verified analyzer for integer division and remainder by zero in C. SymDiv combines a bounded symbolic interpreter with optional language-model branch guidance. Every accepted finding is checked against source-derived path constraints. Clang Static Analyzer provides the external baseline; deterministic search orders and SMT lookahead provide additional controls.

## Repository layout

- `src/` — parser integration, symbolic interpreter, search policies, and model interface.
- `prompts/`, `schemas/`, `configs/` — guidance prompts, response formats, and experiment settings.
- `benchmarks/` — diagnostic, Juliet, Cppcheck, and stress subjects with provenance and applicable notices.
- `results/` — frozen predictions, model records, resource comparisons, timings, witness checks, and reproduction summaries.
- `scripts/`, `tests/` — experiment, reporting, reproduction, and regression tooling.
- `docs/` — method contract, protocols, and implementation notes.
- `report/` — LaTeX sources and generated tables for a technical report.

The final submission PDF is kept separately. Generated PDFs and local run outputs are not tracked here.

## Requirements

Python 3.9 or newer, `make`, and Clang with JSON AST and SARIF support. The tested setup used Apple Clang 17, Python 3.9, Z3 4.13.3, and pytest 8.3.5. `make setup` installs pinned Python dependencies. Reproduction may take several minutes. Tectonic is needed only to rebuild the report.

## Reproduce the recorded results

Run from the repository root:

```sh
make setup
make test
make reproduce-v4
```

`make reproduce-v4` regenerates the new cohorts, verifies frozen hashes, replays the recorded responses and fixed-resource comparisons, and checks accepted witnesses. It makes no model requests. Historical snapshots are available with `make reproduce-v3` and `make reproduce`. Use `make report-v4` to regenerate the tables and report from the stored evidence.

Fresh model experiments are separate from offline reproduction and require an authenticated model-service client. Their limits and protocol are documented in `docs/v4-protocol.md` and `configs/v4.json`.

## Evaluation and interpretation

The v4 study separates 18 historical diagnostics, 25 unchanged external regressions, and 12 authored stress programs. The main comparison uses 128 execution-state operations and 256 solver calls, with 64- and 512-state sensitivity runs. Fresh end-to-end timing uses five preselected cases and three repetitions per method. The repository preserves unknown outcomes, failures, and invalid timing records for audit.

The interpreter has restricted scalar-C semantics. An unknown result is not a proof of safety; the study does not claim production-level C coverage or general superiority over static-analysis tools. See `docs/v4-protocol.md` and `docs/v4-clock-correction.md` for the frozen methodology and timing correction.
