# Post-study correction of nested division locations

During the final case audit, c008 exposed an operator identity collision:
Clang's AST ranges for `x/2*3/0` begin at the same byte. The old catalog keyed
both divisions by that beginning and the operator, retaining only one entry.
The source executor still detected real division by zero, but attached the
metadata for the inner `/2`. The model catalog omitted the first zero divisor.
Source-line-only UBSan validation did not expose that within-line alias.

The repair distinguishes colliding entries by the actual operator token between
their operand ranges, respecting comments and UTF-8 byte offsets. Extraction,
the v2 context collector and the resumable search use the same map. Unambiguous
locations retain their identifiers. Regressions cover repeated division,
remainder, three nested operators and non-ASCII comments.

This is a post-study implementation repair, not an unreported alteration of the
frozen comparison. Audit the catalogs of all 55 programs. Retain the original
tables and calls; independently rerun the affected c008 at all three resource
budgets with one fresh, source-only response. Confirm the repaired reported
operator's exact line and column with compiled UBSan. Additionally recheck DFS
and guidance on all 55 cases at the main cap using the new response only for
c008. Record every difference. The new request shares the original global
80-attempt limit and receives its own cost category.

Exact original and repaired hashes are chained in
`benchmarks/v4/site-location-amendment.json`. The v3 maintenance record also
allows the same implementation repair; its original study has no collision.
`make reproduce-v4` explicitly selects `SYMDIV_ARCHIVED_SITE_LOCATIONS=1` only
for archived resource replay, preserving the original prompts and findings.
Ordinary analysis and the separate repaired-case checks use corrected locations.
The original freeze files, timing cohorts and experimental results are unchanged.
