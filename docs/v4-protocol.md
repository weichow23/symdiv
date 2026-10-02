# V4 evaluation protocol (frozen before new predictions)

This follow-up addresses independent evidence, stronger cheap controls, natural
verification-triggered feedback, and selective model use with real wall clocks.
The historical v3 freeze, outputs, report and negative results remain unchanged.
The independent solver-budget maintenance fix preserves the historical 256/128
ratio; its exact hashes are recorded in `benchmarks/v3/maintenance-patch.json`.

## Subjects and labels

- Development/historical: all 18 v3 authored diagnostics. Reuse their already
  recorded first responses; any new repair is an additional genuine request.
- External: all 25 unchanged C11 snippets containing integer divide/remainder
  extracted from the pinned Cppcheck `zeroDiv*` regression methods (excluding the
  diagnostic-format test). Record all 61 screened candidates and exclusions.
  Include unsupported long integers, expression mutation, globals, sizeof and
  generic selection in the denominator. Do not silently remove these failures.
  No model or analyzer outcomes enter selection. Source-level label reasoning
  is recorded separately from Cppcheck's expected warnings: a missing warning
  is not proof of safety. Validate every positive label with a concrete compiled
  witness, including those outside the interpreter's subset.
- Authored stress: 12 paired cases, three fixed families (random small weights,
  shuffled correlated bits, affine-weight loops), two depths per family and a
  fixed RNG seed 20261001. Enumerate attainable sums independently. These are
  new parameter/structure tests, not independent external or production evidence.

All new inputs, labels, code, prompt, configuration and this protocol are hashed
before any new model predictions or comparative analyzer measurements. Historical
inputs are explicitly development data. Public regression data may be familiar
to a pretrained model; no claim of contamination-free evaluation is made.

## Resource comparison

Same source interpreter, loop bound 8, integer rules and witness acceptance for
all custom policies. Main budget: 128 state pops, 256 solver calls; sensitivities
64/128 and 512/1024. An independent 30-second local guard prevents runaway
queries. Provider wait is excluded only for this local-compute experiment and
reported separately. No aggregate warning accuracy treats unknown as a proof.

Controls: DFS, existing static heuristic, random seeds 11/29/47, branch-depth
breadth-first search, minimum-true and minimum-false discrepancy policies,
least-visited-branch priority, optimistic AST statement distance to a sink, and
a retained-frontier portfolio. Portfolio cycles distance, coverage, DFS and
minimum-false discrepancy every 16 pops. Every policy uses the same complete
retained frontier. The coverage/distance implementations are local policies,
not KLEE reproductions; KLEE's documented search families motivate the controls:
https://klee-se.org/docs/options/ . No claim to match a state-of-the-art engine.

Guidance has 80 initial pops then portfolio fallback. Event-driven feedback
pauses at the first actual source-verification failure consistent with the
model's encountered preferences, for a bug/unknown proposal. Require an open
frontier and at least 16 states remaining. At most one correction, 32 guided
pops, then the same portfolio. Never restart counters or remove alternatives.
No injected incorrect advice enters this primary follow-up. Feedback/no-feedback
share the same first response. Sensitivity uses first responses only, avoiding
reuse of repairs generated against a different failure state.

The resource selective arm first spends 64 pops on the portfolio; only an
unfinished frontier uses the first response. All spent resources remain charged.
CSA and LLM-only are separate reference classifiers; CSA is not assigned the
custom interpreter's state cap. Clang and model-only rows must not be described
as using an identical internal compute budget.

A targeted additional control computes SMT advice using bounded if-conversion:
merge scalar branch assignments with ITE expressions and unroll simple bounded
loops. Spend at most 64 summary statement visits (also at most half the state
budget), 16 solver calls and one second. Charge these costs to the same overall
budgets, then verify the suggested path using the unchanged interpreter. This
summary is only a prioritizer: unsupported features, timeout or an UNSAT summary
never prove safety or remove paths. Mixed summary-node and execution-pop counts
are an explicit operation-budget convention, not equal CPU work; the separate
wall-clock experiment includes all costs. This control directly asks whether a
cheap symbolic component can supply the advice attributed to the LLM.

## Fresh latency and variability study

Preselected cases: c010 (external bounded safe loop), c013 (external equality
defect), s003 (11-branch weighted defect), s008 (11-branch correlated safe case),
s011 (8-iteration weighted defect). Three independent repetitions per case.
No outcome-based reselection. Run DFS, portfolio, SMT lookahead, always-request guidance, and
local-first selective guidance on every case/repetition, in a fixed hash order.

Each trial starts in a fresh Python process. A parent monotonic timer includes
process startup, source preparation, model subprocess, response parsing, search
and result return. Total budget 30 seconds. A model request's timeout is bounded
by actual remaining time, reserving 0.2 seconds for returning. A result returned
after the deadline is unknown and cannot contribute an accepted witness.
Selective runs the local portfolio for up to 2 seconds, then calls the model
only if an unfinished frontier remains and at least 12 seconds remain. This
study is serial, not an asynchronous background-search design. Timing trials
make fresh initial requests independently for both neural arms; no cached
response or subtracted historical latency substitutes for a live run. Repairs
are disabled in this timing ablation to isolate gating from correction cost.

Reuse the genuinely repeated always-request responses in offline resource-cap
search to describe model-output variability, keeping all three repetitions.
Report individual counts and timing distributions; no significance or general
real-world speedup claim follows from five selected cases.

## Accounting and validation

At most 80 new calls and 1.8 million observed tokens across this follow-up; no
automatic retries. Log every attempted request before starting, including
errors/timeouts. Token usage can be missing for a cancelled/timed-out provider:
report incomplete accounting and known-token totals explicitly, never zero cost.
Existing responses and completed trials may be resumed from exact checkpoints;
interrupted started calls without a result cannot be silently repeated.

Retain raw responses, failed suggestions, trigger traces, search results and
timings. Compile and execute every distinct accepted witness with UBSan at its
source line. Reproduce all fixed-resource predictions offline; time results
remain observations rather than deterministic replay promises. Selection and
source regeneration, configuration tests, event/frontier invariants and a clean
checkout form the artifact checks. Freeze changes after first predictions would
require a new protocol version, never overwriting this one.
