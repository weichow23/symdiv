#!/usr/bin/env python3
"""Generate paper prose from complete v4 evidence; never relabel experiments."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads((ROOT / path).read_text())


def main():
    summary = read('results/v4/summary.json')
    witness = read('results/v4/witness-checks.json')
    validation = read('results/v4/validation.json')
    repro = read('results/v4/reproduction-summary.json')
    raw_resource = read('results/v4/resource.json')
    resource, live = summary['resource'], summary['timing']
    h, e, s = (resource[c]['states128'] for c in ('historical', 'external', 'stress'))
    always, local, smt = (live[m] for m in ('always', 'selective', 'lookahead'))
    extension = summary['smt_first_extension']
    feedback = summary['feedback']
    lines = []

    def macro(name, value):
        lines.append('\\newcommand{\\' + name + '}{' + value + '}\n')

    macro('VFourAbstract',
        f"On 55 programs, LLM-guided search confirms {h['guided']['tp']}/9 historical and {s['guided']['tp']}/6 authored stress positives under a 128-operation budget; "
        f"SMT lookahead confirms {h['lookahead']['tp']}/9 and {s['lookahead']['tp']}/6, respectively. "
        f"Both find {e['guided']['tp']}/19 external positives. "
        f"In 75 fresh timing trials on five preselected programs, Local-first reduces model requests from {always['model_calls']} to {local['model_calls']} per 15 trials without lowering the pooled median time. "
        f"A later exploratory SMT-first extension uses {extension['model_calls']} requests with unchanged discovery on the same programs. ")

    macro('VFourResource',
        f"The strongest symbolic control substantially narrows the gain over DFS (Table~\\ref{{tab:v4-main}}). "
        f"On historical diagnostics, SMT lookahead and LLM-guided search both confirm {h['guided']['tp']}/9 positives, compared with {h['dfs']['tp']}/9 for DFS and {h['portfolio']['tp']}/9 for Portfolio. "
        f"On authored stress programs, LLM-guided search confirms {s['guided']['tp']}/6, SMT lookahead {s['lookahead']['tp']}/6, and DFS {s['dfs']['tp']}/6. "
        f"Resource-selective Local-first also confirms {s['selective']['tp']}/6, with its prepass charged to the shared budget. "
        f"Figure~\\ref{{fig:v4-budget}} shows all three budget settings: the difference between SMT lookahead and LLM-guided search closes at 512 operations. "
        f"LLM-guided search produces {sum(resource[c]['states128']['guided']['fp'] for c in resource)} false positives across the three cohorts; its negative outcomes still distinguish complete refutation from unknown.")

    loop = next(c for c in raw_resource['cases'] if c['id'] == 's011')
    macro('VFourLoopCase',
        "The remaining main-budget difference is explained by s011, an eight-iteration weighted loop. "
        f"LLM-guided search reaches its witness in {loop['states128']['guided']['states']} state pops. "
        f"SMT lookahead first spends {loop['states128']['lookahead']['lookahead']['summary_states']} summary-node visits; "
        f"the combined search requires {loop['states512']['lookahead']['states']} charged operations and exceeds the 128-operation limit. "
        "The 512-operation run confirms the same defect. Thus the extra main-budget discovery depends on charging advice construction, rather than on a defect uniquely accessible to the LLM.")

    macro('VFourExternal',
        f"LLM-guided search and SMT lookahead each confirm {e['guided']['tp']}/19 external positives, while CSA warns on {e['clang']['tp']}/19 (Table~\\ref{{tab:v4-main}}). "
        f"The guided result includes {e['guided']['proved_safe']}/6 complete refutations on negative programs and {e['guided']['unknown']} unknowns overall. "
        "The eight missed positives involve wider integer types (four), mutable globals (two), expression side effects (one), and generic selection (one). "
        "The remaining unknown is a negative program using unsupported \\texttt{sizeof}. "
        "Every selected program remains in the denominator. The flat external curves in Figure~\\ref{fig:v4-budget} show that increasing the operation budget does not overcome these semantic limitations.")

    gains = sum(r['with']['prediction'] and not r['without']['prediction'] for r in feedback)
    losses = sum(r['without']['prediction'] and not r['with']['prediction'] for r in feedback)
    natural = next(r for r in feedback if r['id'] == 'd005')
    before, after = '/'.join(natural['first_verdicts']), '/'.join(natural['repair_verdicts'])
    macro('VFourFeedback',
        f"Exactly {len(feedback)} natural correction event is observed, on the reused historical response for d005. "
        f"Its source verification failure occurs at state pop {natural['trigger']['spent_states']}, after the old fixed 48-pop probe. "
        "The model had incorrectly claimed that $2\\times5-11=0$. "
        f"A fresh request changes the unverified site verdict from \\texttt{{{before}}} to \\texttt{{{after}}}, at a cost of {natural['repair_seconds']:.2f}\\,s. "
        f"The final analyzer result remains \\texttt{{{natural['with']['status']}}}. "
        f"Relative to the paired run without feedback, there are {gains} additional positive discoveries and {losses} lost discoveries. "
        "The corrected verdict therefore demonstrates a successful trigger, while the retained unexplored paths prevent a complete refutation.")

    macro('VFourTiming',
        f"Every main timing method confirms 9/9 positive runs, completely refutes 3/6 negative runs, and leaves three runs unknown (Table~\\ref{{tab:v4-timing}}). "
        f"Local-first uses {local['model_calls']} model requests instead of {always['model_calls']} for Always-request. "
        f"Their medians across the 15 runs are {local['median_seconds']:.2f}\\,s and {always['median_seconds']:.2f}\\,s, respectively, compared with {smt['median_seconds']:.2f}\\,s for SMT lookahead. "
        "Request reduction therefore does not translate into a lower pooled median on this workload. "
        "Figure~\\ref{fig:v4-case-time} shows why: the local gate avoids remote waiting on c010 and c013, but the harder positive programs still take much longer than SMT lookahead. "
        "All methods reach the 30\\,s deadline on the unresolved negative s008. Each plotted point includes preparation and provider waiting; no recorded service time is subtracted. "
        f"The corrected main cohort contains {sum(r['provider_failures'] for r in live.values())} provider failures. "
        "The pooled medians describe these selected programs, not a general speedup estimate.")

    macro('VFourExtension',
        "The strength of SMT lookahead motivates running it before the Local-first request gate. "
        "This integration is frozen and evaluated after the main study, using three fresh trials on each of the same five programs and the unchanged 30\\,s allowance. "
        f"It confirms {extension['tp']}/9 positive runs, completely refutes {extension['proved_safe']}/6 negative runs, and uses {extension['model_calls']} requests; "
        f"its pooled median is {extension['median_seconds']:.2f}\\,s. "
        "Figures~\\ref{fig:v4-case-time} and~\\ref{fig:v4-calls} mark this later arm separately. "
        "SMT lookahead already produces all positive discoveries; the remaining requests occur on s008 and add none. "
        "The extension implements a cost-motivated workflow, but its later, non-interleaved comparison on already studied programs is exploratory rather than held-out evidence.")

    varying = sum(len({(t['prediction'], t['status']) for t in c['trials']}) > 1
                  for c in summary['repeated_response_resource_results'])
    state_varying = sum(len({t['states'] for t in c['trials']}) > 1
                        for c in summary['repeated_response_resource_results'])
    phases = summary['calls_by_phase']
    macro('VFourVariance',
        f"Re-evaluating the three fresh Always-request responses under the fixed operation budget changes the warning/result pair for {varying}/5 programs and the state-pop count for {state_varying}/5. "
        "Three repetitions remain a limited probe of response variability. "
        f"The complete experimental ledger contains {summary['new_calls']} new request attempts: {phases['resource']} for the resource study, "
        f"{phases['invalid_clock_timing']} for the invalid-clock cohort, {phases['corrected_timing']} for corrected timing, "
        f"{phases['smt_first_extension']} for SMT-first, and {phases['site_location_repair']} for the source-location repair. "
        f"They account for {summary['known_tokens']:,} known tokens and {summary['provider_seconds']:.2f}\\,s of recorded provider time. "
        f"Usage is incomplete for {summary['usage_incomplete_calls']} request, so the token total is a lower bound. "
        "Reused historical responses are not counted as new requests; invalid attempts remain included in the expense.")

    macro('VFourValidation',
        f"All {witness['unique_witnesses']} distinct accepted witnesses in the primary resource and fresh-timing records are confirmed by compiled C/UBSan at the expected source lines, "
        f"covering {witness['occurrences']} repeated finding occurrences. "
        "All 19 external positive labels also have independent compiled witnesses, including programs outside the interpreter's support. "
        f"The regression suite passes {validation['tests_passed']} tests. "
        "These checks support accepted positives and implementation invariants; they do not prove the source model or every negative label.")

    repair = read('results/v4/site-location-fix.json')
    macro('VFourSiteRepair',
        "A final audit exposed an interface defect on c008: the nested divisions in \\texttt{x/2*3/0} share an AST range beginning. "
        "The old catalog merged their identities, omitted the zero divisor from the model's site list, and attached the wrong denominator metadata to a real file-level finding. "
        "Line-level UBSan validation could not distinguish the operators. The repair uses distinct operator tokens when ranges collide, shared by extraction and both symbolic engines. "
        f"Only c008 changes in an audit of all {repair['catalogs_checked']} catalogs; its separate fresh response "
        + ("reports the defect. " if repair['corrected_llm_prediction'] else "still misses the defect. ")
        + "The frozen LLM-only result remains 16/19, including this interface-induced miss. "
        f"The repaired location passes a line-and-column UBSan check. Reruns at all three budgets and {repair['current_main_cap_checks']} current main-budget DFS/LLM-guided comparisons show {len(repair['differences'])} warning/result differences. "
        "The fresh request and repair are recorded separately. Archived replay uses the original catalog mapping; ordinary analysis uses the corrected mapping.")

    macro('VFourReproduction',
        f"Completed offline regeneration reproduces all {repro['regenerated_sources_identical']} new sources byte for byte and makes {repro['new_model_calls']} model requests. "
        + ("Every fixed-budget warning/result pair matches the recorded result. "
           if repro['resource_predictions_and_statuses_identical'] else
           f"The replay retains {len(repro['differences'])} warning/result differences in the artifact. ")
        + f"It also confirms {repro['confirmed_witnesses']} distinct replay witnesses in compiled C.")

    macro('VFourConclusion',
        f"At the main operation budget, SMT lookahead matches LLM-guided search on the {h['guided']['tp']}/9 historical discoveries and finds {s['lookahead']['tp']}/6 stress positives versus {s['guided']['tp']}/6. "
        "That difference disappears with a larger operation budget, while external failures persist. "
        f"Local-first reduces timing requests from {always['model_calls']} to {local['model_calls']} without a lower pooled median. "
        f"The later SMT-first extension uses {extension['model_calls']} requests on the same workload, with no additional discovery from those remaining calls. ")

    (ROOT / 'report/generated/v4-macros.tex').write_text(''.join(lines))
    print('Generated research-question-aligned prose from the unchanged v4 evidence')


if __name__ == '__main__':
    main()
