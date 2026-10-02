"""V4 policy composition; all variants retain the same symbolic frontier."""
import time

from .budgets import search_budgets
from .guidance import validate_response
from .search_v4 import SearchV4


def make_search(prepared, config, policy="dfs", state_budget=None, wall=False, started=None, seed=0):
    states, queries = search_budgets(config, state_budget)
    search = SearchV4(prepared, policy="dfs" if policy == "portfolio" else policy, seed=seed,
                      state_budget=1000000 if wall else states,
                      query_budget=2000000 if wall else queries,
                      loop_bound=config["loop_bound"], solver_ms=config["z3_timeout_ms"],
                      wall_seconds=config["wall_budget_seconds"] if wall else config["search_wall_seconds"])
    if wall:
        search.deadline = (time.monotonic() if started is None else started) + config["wall_budget_seconds"]
    return search


def portfolio(search, config, extra_states=None, until=None):
    target = search.state_budget if extra_states is None else min(search.state_budget,search.visited+extra_states)
    batch = config["portfolio_batch"]
    while search.queue and not search.finding and not search.stopped and search.visited < target:
        if until is not None and time.monotonic() >= until:
            break
        policy = config["portfolio_policies"][(search.visited // batch) % len(config["portfolio_policies"])]
        search.set_policy(policy)
        search.advance(extra_states=min(batch,target-search.visited))
    return search.result()


def parse(record, prepared):
    try:
        return validate_response(record["raw"]["output"], prepared), None
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        return {}, str(error)


def relevant_failure(failure, first, preferences):
    if not failure:
        return False
    proposals = first["raw"]["output"]["findings"]
    if not any(f["verdict"] in ("bug","unknown") and
               (failure.get("site_id") is None or f["site_id"] == failure["site_id"]) for f in proposals):
        return False
    # Only a trace consistent with the model's actually encountered choices is
    # feedback about that candidate; unrelated pruned alternatives do not count.
    return all(preferences.get((t["branch_id"], t["visit"]),t["take"]) == t["take"] for t in failure["trace"])


def guided(search, prepared, config, first, repair=None, feedback=False, resource_clock=True):
    preferences, error = parse(first, prepared)
    search.set_policy("guided" if not error else "dfs",preferences)
    initial_states = search.visited
    correction = None
    trigger = None
    repair_seconds = 0.0
    repair_error = None
    mode = "initial"
    while search.queue and not search.finding and not search.stopped:
        guided_limit = initial_states + config["guidance_states"]
        if mode == "initial" and search.visited >= guided_limit:
            mode = "fallback"
        if mode == "repair" and search.visited >= repair_stop:
            mode = "fallback"
        if mode == "fallback":
            batch = config["portfolio_batch"]
            search.set_policy(config["portfolio_policies"][(search.visited // batch) % len(config["portfolio_policies"])])
        _, failure = search.advance_event(extra_states=1, stop_on_failure=True)
        enough = search.state_budget-search.visited >= config["repair_min_states"]
        if feedback and not error and correction is None and trigger is None and enough and search.queue and not search.stopped and relevant_failure(failure,first,preferences):
            trigger = {"spent_states":search.visited,"spent_solver_calls":search.queries,
                       "remaining_tasks":len(search.queue),"failure":failure}
            if repair is not None:
                started = time.monotonic()
                correction = repair(trigger)
                spent = time.monotonic()-started
                if resource_clock:
                    search.deadline += spent  # local-compute cap; remote cost recorded separately
                repair_seconds += spent
                if correction is not None:
                    new, repair_error = parse(correction,prepared)
                    search.set_policy("guided" if not repair_error else "dfs",new)
                    mode = "repair"
                    repair_stop = search.visited + config["repair_states"]
    result = search.result()
    result.update(guidance_error=error, repair_error=repair_error, feedback_trigger=trigger,
                  feedback_attempted=correction is not None,
                  feedback_used=correction is not None and repair_error is None,
                  repair_wait_seconds=repair_seconds, initial_states=initial_states)
    return result


def resource_variant(prepared, config, first, feedback=False, selective=False, repair=None, state_budget=None):
    search = make_search(prepared,config,state_budget=state_budget)
    if selective:
        portfolio(search,config,extra_states=config["selective_warm_states"])
    used = bool(search.queue and not search.finding and not search.stopped)
    if used:
        result = guided(search,prepared,config,first,repair=repair,feedback=feedback)
    else:
        result = search.result()
        result.update(feedback_used=False,feedback_trigger=None,repair_wait_seconds=0)
    result["initial_model_used"] = used
    result["local_seconds"] = prepared["prepare_seconds"] + result["elapsed_seconds"]-result["repair_wait_seconds"]
    result["initial_model_seconds"] = first.get("raw",{}).get("_client_elapsed_seconds",first.get("elapsed_seconds",0)) if used else 0
    return result
