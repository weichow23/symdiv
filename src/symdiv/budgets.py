"""Explicit state and solver budgets shared by experiment runners."""
import math


def search_budgets(config, state_budget=None, query_budget=None):
    states = config["state_budget"] if state_budget is None else state_budget
    if query_budget is None:
        queries = config["query_budget"]
        # Sensitivity runs preserve the configured ratio, rather than assuming 2.
        if state_budget is not None and config["state_budget"]:
            queries = math.ceil(queries * states / config["state_budget"])
    else:
        queries = query_budget
    for name, value in (("state_budget", states), ("query_budget", queries)):
        if type(value) is not int or value < 0:
            raise ValueError(name + " must be a nonnegative integer")
    return states, queries
