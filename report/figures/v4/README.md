# V4 report figures

The three data plots present existing observations. Rebuilding them runs no
analyzer and makes no model requests. The workflow and teaser explain the
method. The original v2/v3 reports and frozen v4 records are intact.

| Asset | Source | Interpretation |
|---|---|---|
| `budget-sensitivity.pdf` | `results/v4/resource.json`, `benchmarks/v4/freeze.json` | Three distinct cohorts, all three operation budgets; positive counts, not pooled accuracy. |
| `fresh-timing.pdf` | `results/v4/timing.json`, `results/v4/smt-first/timing.json` | All 75 corrected main trials and 15 later exploratory trials. Points and medians, no inferential error bars. Deadline observations stay unknown. |
| `model-requests.pdf` | The same raw timing records | Actual request counts; the exploratory extension is separate. Equal finding counts do not establish an advantage of LLM guidance. |
| `workflow.png` | `output/figures/symdiv-workflow-v4.pptx` | Alternative ordering policies and source-only acceptance, plus arm-specific feedback and clock annotations. |
| `teaser.png` | Built-in GPT-Image generation | Conceptual overview of bounded search, source verification and evaluation dimensions. Contains no experimental measurements. |

`scripts/plot_v4_report.py` derives counts from the raw records and checks them
against `results/v4/summary.json` before plotting. `figure-data.json` retains the
exact plotted observations and SHA-256 hashes of six inputs (including canonical method labels), the builder and
six outputs. The plot PDFs contain vector text and geometry. Their PNG siblings
are inspection/export alternatives. Both files for each plot have the same data.

From `project/`, install `requirements-report.txt` and run
`make report-figures-v4`. A standard-library-only check is available as
`.venv/bin/python scripts/plot_v4_report.py --check` and is part of
`make report-v4`. No plotting packages are needed to compile using the committed
PDF figures. No hosted-model login is needed for either operation.

The canonical labels come from `report/terminology.json`; the normal report
build also runs `scripts/check_v4_report.py` to check manuscript terms, local
references, citation keys and teaser provenance. The conceptual teaser is
separate from the three plots derived from experimental data.

The 2172 x 724 pixel teaser is included without cropping or pixel edits. Its
full generation prompt is `teaser-prompt.txt`, and `teaser-provenance.json`
records the selected image and prompt hashes. It was generated once with the
built-in GPT-Image tool, copied into this project, and disclosed in the paper's
caption and AI usage statement. The image is a committed illustration, not a
deterministically reproducible plot or an experimental-model request.

The workflow is a native, editable 1280 x 414 pixel slide, rendered at 3x
resolution into the report. Its 11 labeled icon types are original native
diagram objects, not external artwork or generated scientific evidence. The
PPTX uses Arial; diagrams, labels and connections remain editable. It was
checked structurally and rendered with Artifact Tool; no native PowerPoint
compatibility claim is made.

To rebuild the workflow in the Codex bundled runtime, run
`scripts/draw_v4_workflow.mjs` with the bundled Node executable after setting:

- `RUNTIME_NODE_MODULES`: bundled Node package directory containing `@oai/artifact-tool`.
- `PRESENTATIONS_SKILL_DIR`: installed Presentations skill directory.
- `RUNTIME_PYTHON`: bundled Python executable used by the package validator.
- `WORKFLOW_OUTPUT`: an unused absolute `.pptx` filename under `output/figures/`.

The builder validates the PPTX before rendering the saved final file. Private
layout receipts and previews go under `tmp/workflow-v4/`. Editing the supplied
PPTX directly does not need that runtime; if doing so, re-export the workflow
image and rebuild the report. The existing finalized PPTX is never overwritten
by the builder.
