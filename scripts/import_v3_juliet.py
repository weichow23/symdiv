#!/usr/bin/env python3
"""New flow families only; reuse the audited, deterministic v2 materializer."""
import import_juliet_cwe369 as importer
import json
import sys
from pathlib import Path

# Neither 02 nor 04 appeared in the v2 external cohort. Keep both zero and rand,
# and both bad and complete good branches. This gives eight files. The importer
# does not inspect model predictions or select cases by analyzer success.
importer.SELECTION = [("02", "divide"), ("04", "modulo")]

if __name__ == "__main__":
    importer.main()
    # The shared importer retains its v2 default; this wrapper names its own cohort.
    out = Path(sys.argv[sys.argv.index("--out")+1])
    path = out / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["name"] = "v3-juliet-new-flows-8"
    path.write_text(json.dumps(manifest, indent=2)+"\n")
