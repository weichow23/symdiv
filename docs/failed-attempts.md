# Failed and adjusted attempts

## 2026-09-20: initial Codex smoke-test budget

The first smoke configuration allowed two Codex calls but capped the run at
20,000 reported tokens. The harness stopped after the calls because the reported
usage exceeded that cap, and the pre-fix implementation raised before writing
the partial result file. No model or authentication error occurred.

The follow-up one-case run measured 16,892 total tokens (16,825 input and 67
output). The primary cap was therefore frozen at 500,000 tokens before examining
the full pilot results. The harness was also changed to retain completed cases
and set a `stop_reason` if a completed call crosses the configured ceiling.

This adjustment changes only resource accounting and failure preservation. It
does not change the prompt, benchmark labels, model, reasoning effort, or
acceptance rule.

## 2026-09-29/30: v2 correctness repair and experiment

The audit reproduced false acceptance of empty predicates for a guarded return
and for a denominator initialized to seven. V2 replaced hypothesis-only solving
with independent source constraints. Historical v1 responses were retained.

The original two source-free verifier tests failed after the corrected API
required source context. They were replaced with concrete-source regressions;
new arithmetic tests initially selected the earlier constant division rather
than the intended later target site. Correcting the test's site selection made
the regressions check the intended behavior. No benchmark labels were changed.

The first Juliet smoke run completed one case with 17,913 tokens and roughly
40 seconds of local symbolic work. Before the primary run, short pruning queries
and exact concrete-seed substitution reduced this overhead. The fixed primary
run completed all 24 calls with 430,183 tokens and no provider failures or retries.
Its subjects, model, prompt, and configuration were committed at `0e4ea8f` before
execution. Its results are preserved under `results/v2/juliet/`.

During delivery validation, a replay-of-replay regression found that an old raw
site ID needed an explicit retained transport mapping after migration. The
adapter now retains `_replay_site_id_map` without editing the original response
payload. Input-contract checks also explicitly reject unmaterialized
preprocessing, and scoring validates saved manifest fingerprints. These changes
harden reproduction and out-of-contract inputs; they do not change any primary
subject, model response, or evaluated warning. Both full strata are rechecked
by offline reproduction with the delivery code.

A final input-boundary review added four regressions before delivery. Mixed-type
compound assignment such as `int x=-1; x/=2u` now abstains rather than using the
left-hand type for a promoted unsigned operation. Printing summaries require the
void interface and no longer skip evaluation of an arbitrary expression merely
because it contains a string literal; volatile parameters also abstain. These
cases were outside the evaluated subjects. The final full-cohort replay verifies
that the conservative fixes do not alter any reported benchmark disposition.
