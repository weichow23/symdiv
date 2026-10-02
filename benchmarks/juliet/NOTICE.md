# Juliet source and license

The 12 upstream files are unmodified bytes extracted from the official NIST
Juliet C/C++ 1.3 archive, with SHA-256
`ada9d7e1c323d283446df3f55bdee0d00bda1fed786785fe98764d58688f38eb`.
The individual hashes are in `upstream/checksums.json`.

NIST suite: https://samate.nist.gov/SARD/test-suites/112
Author: NSA Center for Assured Software. Published 1 October 2017.
The upstream suite is public domain in the United States and offered under
CC0 1.0 for any foreign rights NIST may claim. NIST provides no warranty.

Derived files retain arithmetic, guards, assignments, and control flow from the
selected preprocessor branch. The importer removes comments, renames label-bearing
identifiers, and replaces diagnostic string literals with a neutral message.
The minimal compatibility header retains the upstream RAND32 and URAND31 macros
exactly, plus external prototypes for random input and printing. No vulnerability
statements or guard conditions are hand-copied or changed. All good helper
functions are retained, so negative files may have multiple division sites.

The archive is not bundled. The verified selected files are bundled so that
`python scripts/import_juliet_cwe369.py --offline` works without network access.
