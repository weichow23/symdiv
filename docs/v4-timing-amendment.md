# V4 timing supervisor amendment

The original code and protocol were frozen at `9028aaa`. All 55 resource cases
finished under that version, with their original results retained. The first
fresh timing trial, `timing-s008-2-lookahead`, exceeded the declared 30-second
budget while symbolic work did not return to an internal deadline check. The
original parent watchdog terminated it after 45 seconds and then raised an
exception instead of storing an unknown result. This was a measurement-harness
failure, not a successful analysis or a model request.

The trial is retained once in the 75-trial primary timing cohort as unknown,
with elapsed time **at least 45 seconds** (the timeout threshold, not a fabricated
precise measurement). It is not rerun. Its failure record and the original
source freeze remain available. The elapsed lower bound must remain visible
when describing timed distributions.

Before continuing the other 74 trials, an external process-group supervisor
enforces the existing 30-second budget, including startup and provider children.
An overrun is recorded as unknown with no accepted findings. A killed provider
is logged as an attempted call with incomplete token accounting when necessary.
This change affects interruption/accounting, not source semantics, subjects,
labels, prompts, priority policies, budgets or trial selection. No successful
trial existed before the amendment. A cache guard also prohibits reusing a
completed model response if a live trial was interrupted before its result was
stored; completed timing results can still be resumed without rerunning.

The amendment binds the original freeze hash, original/corrected runner hashes,
and new supervisor dependency hashes. Offline resource reproduction uses this
explicit maintenance record. The original algorithm and resource outputs are
not overwritten or relabeled as having used a different implementation.
