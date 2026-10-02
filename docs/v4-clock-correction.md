# Corrected fresh timing cohort

Further investigation supersedes the initial deadline diagnosis. The recorded
runtime is Python 3.9.6 on macOS. Its `time.monotonic()` has different origins in
different interpreter processes. Passing a parent timestamp directly to a child
made the child's deadline and local-first threshold incorrect. A direct probe
is saved in `results/v4/invalid-clock-cohort/clock-probe.json`. Python's official
documentation records the macOS cross-process change in Python 3.10:
https://docs.python.org/3/library/time.html#time.monotonic .

The complete partial timing cohort is invalidated, not filtered by results.
Its worker files, measured parent durations, the initial 45-second watchdog
failure and all model requests/costs remain archived. One in-flight request
was stopped while investigating and has explicitly incomplete token usage.
No resource experiment is affected: resource timing never crosses processes.

Corrected timing uses `clock_gettime(CLOCK_MONOTONIC)` as the shared transport
clock, translates the timestamp into the worker's own local monotonic origin,
and keeps the independent parent process-group deadline. A cross-process test
checks that startup and parent age survive this translation. Provider start
timestamps also use the shared clock so interrupted-call durations are valid.

Before new corrected timing calls, the amendment freezes the corrected runner
and helper hashes. All 75 timing trials are collected anew under keys prefixed
`timing-corrected-`. Subjects, repetitions, trial order, policies, 30-second
budget, two-second threshold, and 12-second request floor remain unchanged.
The original hash order is preserved despite the new storage prefix. No cached
model response is allowed in a fresh timing trial. All failures in this new
cohort count as unknown. The initial invalid cohort is excluded from method
effectiveness/timing tables, but is included in total experiment cost and the
failure narrative. This separation avoids selecting favorable reruns.
