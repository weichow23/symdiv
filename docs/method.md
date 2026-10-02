# SymDiv v2 method

The authoritative method description is the final report, sections 2--3.

## The repaired boundary

The v1 query used only model predicates AND a syntactic zero denominator.
That formula could omit an actual guard or assignment. It established formula
consistency, not source feasibility. The historical pilot remains unchanged.

V2 builds paths from the C AST independently. Its acceptance formula includes
actual branch guards, the evolving declaration-ID environment, arithmetic
requirements before the target operation, the proposed predicates interpreted
in the site environment, and the AST-evaluated denominator equal to zero.
Concrete seeds are accepted only if the entire formula simplifies to true;
otherwise a Z3 SAT model supplies the witness. Confidence is never consulted.

## Declared semantics

- Materialized single-file C, 32-bit int/unsigned int, tested Clang target.
- Integer quotient truncates toward zero; remainder follows C's identity.
- Signed-overflow paths and earlier divide-by-zero paths cannot reach later sites.
- Unsigned operations wrap modulo 2^32. Selected bitwise operations and casts
  follow the stated target semantics.
- Lexical shadowing uses declaration IDs; names in model predicates refer to the
  currently visible value at the site.
- Guards, assignments, early returns, short-circuiting, conditional expressions,
  bounded loops, break, and continue are modeled.
- Pointers, arbitrary calls, mutable globals/static locals, uninitialized reads,
  unsupported types/side effects, and unmaterialized preprocessing are rejected
  or recorded as incomplete. No general interprocedural claim is made.
- Site-bearing functions are entry points. External rand results are independent
  integers in [0,2147483647]; printing is observational. Local definitions with
  these names do not inherit the library summaries.

## Outcomes and limits

`verified_sat` means a witness under this model. `refuted_unsat` means no explored
source path satisfies the proposal, with no unfinished paths. `inconclusive`
records unsupported paths, bounds or solver unknown. `model_safe` is an unproved
model classification. `model_unknown`, `missing`, and `invalid` are retained.
All non-accepted sites emit no warning, but that does not equate abstention with
proved safety. Explicit dispositions accompany warning-level confusion matrices.

Bounds: 8 loop iterations; 4,096 statement-state visits per function; 25 ms for
pruning queries (unknown retains the path); 5,000 ms per final solver query.
The implementation has targeted regressions and executable witness checks,
not a formal proof of correctness for the interpreter.
