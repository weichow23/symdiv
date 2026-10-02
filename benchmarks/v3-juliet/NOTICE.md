# Juliet 1.3: additional control-flow families

The four unmodified upstream files are from the official NIST Juliet C/C++ 1.3
archive, SHA-256 `ada9d7e1c323d283446df3f55bdee0d00bda1fed786785fe98764d58688f38eb`.
Individual checksums and transformation mappings are retained alongside them.

Source: https://samate.nist.gov/SARD/test-suites/112
Author: NSA Center for Assured Software; published 1 October 2017.
The suite is public domain in the United States and offered under CC0 1.0 for
foreign rights NIST may claim. It is provided without warranty.

Flows 02 (divide) and 04 (modulo) were not used by v2. Both zero/rand input
families and complete bad/good branches are included, giving eight derived files.
The materializer changes label-bearing identifiers and diagnostic strings only,
besides ordinary preprocessing using the exact upstream random macros. No guard
or arithmetic expression is hand-written to match an expected prediction.

Offline rebuild: `python scripts/import_v3_juliet.py --offline --out <directory>`.
Copy this directory's `upstream/` into the output directory before regenerating.
