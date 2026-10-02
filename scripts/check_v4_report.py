#!/usr/bin/env python3
"""Check the current manuscript's terminology, references and teaser provenance."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    terminology = json.loads((ROOT / 'report/terminology.json').read_text())
    paths = ('report/v4.tex', 'report/generated/v4-macros.tex',
             'report/generated/v4-tables.tex')
    raw = '\n'.join((ROOT / p).read_text() for p in paths)
    normalized = re.sub(r'\s+', ' ', raw).lower()
    for alias in terminology['forbidden_report_aliases']:
        if alias.lower() in normalized:
            raise ValueError('Noncanonical report term: ' + alias)
    for term in terminology['terms']:
        if term.lower() not in normalized:
            raise ValueError('Canonical term is not defined/used: ' + term)
    labels = re.findall(r'\\label\{([^}]+)\}', raw)
    if len(labels) != len(set(labels)):
        raise ValueError('Duplicate figure/table/section label')
    refs = re.findall(r'\\(?:ref|eqref)\{([^}]+)\}', raw)
    if set(refs) - set(labels):
        raise ValueError('Unresolved report references: ' + repr(set(refs) - set(labels)))
    bibliography = (ROOT / 'report/references-v4.bib').read_text()
    bibkeys = set(re.findall(r'@\w+\{([^,]+),', bibliography))
    citations = {key for group in re.findall(r'\\cite\{([^}]+)\}', raw)
                 for key in group.split(',')}
    if citations - bibkeys:
        raise ValueError('Missing bibliography entries: ' + repr(citations - bibkeys))
    for label in terminology['method_labels'].values():
        if label == 'SMT-first*':
            continue  # The star is defined in the plotted exploratory-arm legend.
        if label not in raw:
            raise ValueError('Method label not present in manuscript/tables: ' + label)
    provenance = json.loads((ROOT / 'report/figures/v4/teaser-provenance.json').read_text())
    for key, path_key in [('sha256', 'image'), ('prompt_sha256', 'prompt')]:
        actual = hashlib.sha256((ROOT / provenance[path_key]).read_bytes()).hexdigest()
        if actual != provenance[key]:
            raise ValueError('Teaser provenance changed: ' + path_key)
    if not provenance['conceptual_illustration'] or provenance['experimental_data']:
        raise ValueError('Teaser must remain a conceptual illustration')
    print('Verified 11 canonical terms, method labels, references and GPT-Image teaser provenance')


if __name__ == '__main__':
    main()
