"""Source-grounded acceptance of neural hypotheses, with explicit abstention."""
from pathlib import Path
import z3
from .expressions import ExpressionTranslator, UnsupportedExpression, truth
from .ground import build_context
from .model import DivisionSite, Hypothesis, Verification


def concrete_seed_witness(solver, reach, variables):
    """Cheap, exact witness search before mixed Int/BV solving; never proves safety."""
    inputs = sorted(reach.state.inputs.items())
    vectors = [[0] * len(inputs), [1] * len(inputs), [-1] * len(inputs)]
    for index in range(min(len(inputs), 32)):
        for value in (1, -1):
            vector = [0] * len(inputs)
            vector[index] = value
            vectors.append(vector)
    formula = z3.And(*solver.assertions())
    for vector in vectors:
        substitutions = [(variable, z3.IntVal(value)) for (_, variable), value in zip(inputs, vector)]
        concrete = z3.simplify(z3.substitute(formula, *substitutions))
        if z3.is_true(concrete):
            witness = {name: str(value) for (name, _), value in zip(inputs, vector)}
            witness.update({"at_site:" + name: str(z3.simplify(z3.substitute(value, *substitutions)))
                            for name, value in sorted(variables.items())})
            return witness
    return None


def verify_hypothesis(site: DivisionSite, hypothesis: Hypothesis, timeout_ms=5000,
                      context=None) -> Verification:
    if hypothesis.site_id != site.site_id:
        return Verification("invalid", False, "site ID does not match")
    if hypothesis.denominator.strip() != site.denominator.strip():
        return Verification("invalid", False, "denominator does not match extracted source")
    if hypothesis.verdict == "safe":
        return Verification("model_safe", False, "model supplied no bug hypothesis; safety is not proved")
    if hypothesis.verdict == "unknown":
        return Verification("model_unknown", False, "model reported uncertainty")
    if hypothesis.verdict != "bug":
        return Verification("invalid", False, "unsupported verdict")
    if context is None:
        path = Path(site.file)
        if not path.is_file():
            return Verification("unsupported", False, "source context is required for verification")
        context = build_context(path, timeout_ms=timeout_ms).get(site.site_id)
    if context is None:
        return Verification("invalid", False, "site is not present in current source context")
    problems = list(context.incomplete)
    for reach in context.reaches:
        variables = {name: reach.state.env[key] for name, key in reach.state.names.items()
                     if key in reach.state.env and reach.state.env[key] is not None}
        translator = ExpressionTranslator(variables)
        solver = z3.Solver()
        solver.set(timeout=timeout_ms)
        solver.add(*reach.state.constraints)
        solver.add(reach.denominator == 0)
        try:
            for condition in hypothesis.path_conditions:
                solver.add(truth(translator.parse(condition)))
            solver.add(*translator.guards)
        except (UnsupportedExpression, z3.Z3Exception, TypeError, ValueError) as error:
            problems.append("unsupported hypothesis: " + str(error))
            continue
        concrete = concrete_seed_witness(solver, reach, variables)
        if concrete is not None:
            return Verification("verified_sat", True, "concrete inputs satisfy the source path and hypothesis", concrete)
        result = solver.check()
        if result == z3.sat:
            model = solver.model()
            witness = {name: str(model.evaluate(value, model_completion=True))
                       for name, value in sorted(reach.state.inputs.items())}
            witness.update({"at_site:" + name: str(model.evaluate(value, model_completion=True))
                            for name, value in sorted(variables.items())})
            return Verification("verified_sat", True, "source path and hypothesis reach a zero denominator", witness)
        if result == z3.unknown:
            problems.append("solver_unknown: " + solver.reason_unknown())
    if problems:
        return Verification("inconclusive", False, "; ".join(sorted(set(problems))))
    return Verification("refuted_unsat", False, "no source-feasible path satisfies this zero-denominator hypothesis")
