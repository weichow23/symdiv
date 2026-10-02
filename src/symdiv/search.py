"""V3: resumable path scheduling over the independently implemented C semantics.

Guidance changes only worklist priority. No neural predicate enters a solver.
Every queued alternative remains available until the shared budget is exhausted.
"""
import hashlib
import heapq
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import z3

from .extract import load_ast, extract_sites, _children, _walk, _offset, _slice, _line_column
from .expressions import UnsupportedExpression, truth
from .ground import Executor, State, Reach, type_name
from .verify import concrete_seed_witness


@dataclass
class SearchState(State):
    trace: list = field(default_factory=list)
    active_inputs: dict = field(default_factory=dict)
    checked: int = -1

    def copy(self):
        return SearchState(dict(self.env), dict(self.names), list(self.constraints),
                           dict(self.inputs), self.flow, list(self.trace),
                           dict(self.active_inputs), self.checked)


class BudgetExhausted(Exception):
    pass


class FoundWitness(Exception):
    pass


def prepare(path, clang="clang"):
    path = Path(path)
    started = time.monotonic()
    root = load_ast(path, clang)
    sites = extract_sites(path, clang, root)
    source = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(source.encode()).hexdigest()
    branches, nodes = [], {}
    for function in _children(root):
        if function.get("kind") != "FunctionDecl" or not any(
                n.get("kind") == "CompoundStmt" for n in _children(function)):
            continue
        for node in _walk(function):
            kind = node.get("kind")
            if kind not in ("IfStmt", "WhileStmt", "ForStmt", "DoStmt"):
                continue
            children = list(_children(node))
            condition = (node.get("inner", [])[2] if kind == "ForStmt" else
                         children[-1] if kind == "DoStmt" else children[0])
            offset = _offset(node["range"]["begin"])
            identity = "{}:{}:{}:{}".format(digest, function["name"], offset, kind)
            branch_id = "br-" + hashlib.sha256(identity.encode()).hexdigest()[:12]
            line, column = _line_column(source, offset)
            branches.append({"branch_id": branch_id, "function": function["name"],
                             "kind": kind, "line": line, "column": column,
                             "condition": _slice(source, condition.get("range", {})) if condition else "1"})
            nodes[node["id"]] = branch_id
    return {"path": path, "root": root, "sites": sites, "branches": branches,
            "node_ids": nodes, "source_sha256": digest,
            "prepare_seconds": time.monotonic() - started}


def validate_guidance(payload, prepared, loop_bound=8):
    """Reject malformed IDs/decisions; a rejected suggestion can use plain DFS."""
    by_id = {b["branch_id"]: b for b in prepared["branches"]}
    preferences = {}
    for choice in payload.get("choices", []):
        key = (choice.get("branch_id"), choice.get("visit"))
        if key[0] not in by_id or type(key[1]) is not int or not 1 <= key[1] <= loop_bound + 1:
            raise ValueError("unknown branch or invalid visit in guidance")
        if type(choice.get("take")) is not bool or key in preferences:
            raise ValueError("duplicate or non-boolean branch decision")
        preferences[key] = choice["take"]
    return preferences


class Search(Executor):
    def __init__(self, prepared, policy="dfs", preferences=None, seed=0,
                 state_budget=128, query_budget=256, loop_bound=8,
                 solver_ms=1000, wall_seconds=20):
        self.started = time.monotonic()
        self.deadline = self.started + max(0, wall_seconds)
        super().__init__(prepared["path"], prepared["sites"], prepared["root"],
                         loop_bound, state_budget, solver_ms)
        if policy not in ("dfs", "random", "heuristic", "guided"):
            raise ValueError("unknown search policy")
        self.prepared = prepared
        self.policy = policy
        self.preferences = preferences or {}
        self.rng = random.Random(seed)
        self.state_budget, self.query_budget = state_budget, query_budget
        self.queue, self.sequence = [], 0
        self.queries = self.seed_checks = self.visited = 0
        self.failures, self.incomplete = [], []
        self.finding = None
        self.stopped = None
        self.explored_trace = []
        self.catalog = {b["branch_id"]: b for b in prepared["branches"]}
        self.heuristic = self._heuristic_preferences()
        for name in reversed(sorted({s.function for s in self.sites})):
            self.function = name
            state = SearchState()
            node = self.functions.get(name)
            if node is None:
                self.note("function body not found")
                continue
            try:
                for param in _children(node):
                    if param.get("kind") != "ParmVarDecl":
                        continue
                    if type_name(param) not in ("int", "unsigned int") or "volatile" in param.get("type", {}).get("qualType", ""):
                        raise UnsupportedExpression("unsupported parameter type")
                    state.env[param["id"]] = self.fresh(param["name"], state, type_name(param) == "unsigned int")
                    state.names[param["name"]] = param["id"]
                body = next(c for c in _children(node) if c.get("kind") == "CompoundStmt")
                self.push(name, state, [("node", body)])
            except UnsupportedExpression as error:
                self.note(str(error))

    def note(self, reason):
        label = self.function + ": " + reason
        if label not in self.incomplete:
            self.incomplete.append(label)

    def _heuristic_preferences(self):
        # Fixed cheap baseline: prefer an arm containing a sink, then a literal
        # zero assignment to any variable appearing in a denominator.
        names = {n.get("referencedDecl", {}).get("name")
                 for f in self.functions.values() for n in _walk(f)
                 if n.get("kind") == "DeclRefExpr" and
                 any(n.get("referencedDecl", {}).get("name", "?") == s.denominator for s in self.sites)}
        def score(arm):
            value = 0
            for n in _walk(arm):
                inner = list(_children(n))
                if n.get("opcode") in ("/", "%", "/=", "%="): value += 4
                if n.get("opcode") == "=" and len(inner) == 2:
                    lhs = inner[0].get("referencedDecl", {}).get("name")
                    if lhs in names and inner[1].get("kind") == "IntegerLiteral" and inner[1].get("value") == "0":
                        value += 1
            return value
        result = {}
        for node in _walk(self.prepared["root"]):
            if node.get("kind") == "IfStmt":
                inner = list(_children(node))
                yes = score(inner[1]); no = score(inner[2]) if len(inner) > 2 else 0
                result[self.prepared["node_ids"][node["id"]]] = yes >= no
        return result

    def priority(self, state, sequence):
        if self.policy == "random": return (self.rng.random(), -sequence)
        penalty = 0
        for item in state.trace:
            expected = (self.preferences.get((item["branch_id"], item["visit"])) if self.policy == "guided"
                        else self.heuristic.get(item["branch_id"]) if self.policy == "heuristic" else None)
            if expected is not None and expected != item["take"]: penalty += 1
        return (penalty, -sequence)

    def push(self, function, state, frames):
        if not frames or self.finding: return
        self.sequence += 1
        heapq.heappush(self.queue, (self.priority(state, self.sequence), self.sequence,
                                    function, state, frames))

    def update_guidance(self, preferences):
        self.preferences = preferences
        self.queue = [(self.priority(state, seq), seq, fn, state, frames)
                      for _, seq, fn, state, frames in self.queue]
        heapq.heapify(self.queue)

    def use_fallback(self):
        """Resume the existing frontier with DFS; spent resources stay spent."""
        self.policy = "dfs"
        self.update_guidance({})

    def fresh(self, name, state, unsigned=False, nonnegative=False):
        result = super().fresh(name, state, unsigned, nonnegative)
        state.active_inputs[next(reversed(state.inputs))] = z3.BoolVal(True)
        return result

    def eval(self, node, state, active=True, allow_mutation=False):
        if node.get("kind") == "CallExpr":
            inner = list(_children(node))
            refs = [n.get("referencedDecl", {}) for n in _walk(inner[0]) if n.get("kind") == "DeclRefExpr"]
            if refs and refs[0].get("name") == "rand" and "rand" not in self.functions and len(inner) == 1:
                value = self.fresh("rand", state, nonnegative=True)
                state.active_inputs[next(reversed(state.inputs))] = truth(active) if z3.is_expr(active) else z3.BoolVal(active)
                return value
        return super().eval(node, state, active, allow_mutation)

    def budget(self, query=False):
        if time.monotonic() >= self.deadline: raise BudgetExhausted("wall_time")
        if query and self.queries >= self.query_budget: raise BudgetExhausted("solver_calls")

    def check(self, solver, pruning=False):
        self.budget(query=True)
        left = max(1, int((self.deadline - time.monotonic()) * 1000))
        solver.set(timeout=min(left, 25 if pruning else self.timeout_ms))
        self.queries += 1
        result = solver.check()
        self.budget()
        return result

    def feasible(self, state):
        if state.checked == len(state.constraints): return True
        solver = z3.Solver(); solver.add(*state.constraints)
        result = self.check(solver, pruning=True)
        if result == z3.unsat:
            self.failures.append({"kind": "unreachable_branch", "trace": list(state.trace)})
            return False
        state.checked = len(state.constraints)
        return True

    def record(self, node, state, denominator, active):
        location = self.site_locations.get(node.get("id"))
        if location is None: return
        line, column = location
        site_id = self.by_location.get((line, column, node["opcode"]))
        if site_id is None: return
        self.budget()
        snapshot = state.copy()
        snapshot.constraints.append(truth(active) if z3.is_expr(active) else z3.BoolVal(active))
        variables = {name: snapshot.env[key] for name, key in snapshot.names.items()
                     if key in snapshot.env and snapshot.env[key] is not None}
        constraints = snapshot.constraints + [denominator == 0]
        solver = z3.Solver(); solver.add(*constraints)
        witness = concrete_seed_witness(solver, Reach(snapshot, denominator), variables)
        self.seed_checks += 1
        core = []
        if witness is None:
            solver = z3.Solver()
            for index, condition in enumerate(constraints):
                solver.assert_and_track(condition, "constraint_{}".format(index))
            answer = self.check(solver)
            if answer == z3.unsat:
                core = [str(constraints[int(str(tag).split("_")[-1])]) for tag in solver.unsat_core()]
                self.failures.append({"kind": "zero_denominator_unsat", "site_id": site_id,
                                      "line": line, "trace": list(snapshot.trace), "unsat_core": core})
                return
            if answer == z3.unknown:
                self.note("solver_unknown: " + solver.reason_unknown()); return
            model = solver.model()
            witness = {name: str(model.evaluate(value, model_completion=True)) for name, value in snapshot.inputs.items()}
            witness.update({"at_site:" + name: str(model.evaluate(value, model_completion=True)) for name, value in variables.items()})
        self.budget()
        substitutions = [(value, z3.IntVal(witness[name])) for name, value in snapshot.inputs.items()]
        # rand() calls in inactive ?: or short-circuit arms are symbolic auxiliaries,
        # not actual calls. Exclude them from the concrete executable input stream.
        witness = {name: value for name, value in witness.items()
                   if name not in snapshot.active_inputs or z3.is_true(z3.simplify(
                       z3.substitute(snapshot.active_inputs[name], *substitutions)))}
        site = next(s for s in self.sites if s.site_id == site_id)
        self.finding = {"site": site.to_dict(), "verification": {
            "status": "verified_sat", "accepted": True,
            "reason": "source-derived path and zero denominator; no neural constraints", "model": witness},
            "trace": list(snapshot.trace), "found_seconds": time.monotonic() - self.started,
            "found_states": self.visited, "found_solver_calls": self.queries}
        raise FoundWitness()

    def branch(self, node, state, condition, take):
        result = state.copy()
        branch_id = self.prepared["node_ids"][node["id"]]
        visit = 1 + sum(t["branch_id"] == branch_id for t in result.trace)
        result.constraints.append(condition if take else z3.Not(condition))
        result.trace.append({"branch_id": branch_id, "visit": visit, "take": take,
                             "line": self.catalog[branch_id]["line"]})
        return result

    def execute(self, fn, state, frames):
        frame, tail = frames[0], frames[1:]
        operation = frame[0]
        if operation == "scope":
            state.names = frame[1]; self.push(fn, state, tail); return
        if operation == "loop_after":
            node, condition, body, increment, iteration, names = frame[1:]
            more = [("loop", node, condition, body, increment, iteration + 1, names)] + tail
            if increment: more.insert(0, ("node", increment))
            self.push(fn, state, more); return
        if operation == "loop":
            node, condition, body, increment, iteration, names = frame[1:]
            cond = (z3.BoolVal(True) if not condition or (node["kind"] == "DoStmt" and iteration == 0)
                    else truth(self.eval(condition, state)))
            leave = self.branch(node, state, cond, False)
            leave.names = dict(names)
            self.push(fn, leave, tail)
            go = self.branch(node, state, cond, True)
            if iteration >= self.loop_bound:
                if self.feasible(go): self.note("loop bound reached ({})".format(self.loop_bound))
            else:
                self.push(fn, go, [("node", body), ("loop_after", node, condition, body,
                                                   increment, iteration, names)] + tail)
            return
        node = frame[1]
        kind, children = node.get("kind"), list(_children(node))
        if kind == "CompoundStmt":
            self.push(fn, state, [("node", c) for c in children] + [("scope", dict(state.names))] + tail)
        elif kind == "DeclStmt":
            for child in children: self.declare(child, state)
            self.push(fn, state, tail)
        elif kind == "IfStmt":
            if node.get("hasInit") or node.get("hasVar"):
                raise UnsupportedExpression("declaration in branch condition")
            condition = truth(self.eval(children[0], state))
            for take in (False, True):
                arm = children[1] if take else children[2] if len(children) > 2 else None
                self.push(fn, self.branch(node, state, condition, take),
                          ([("node", arm)] if arm else []) + tail)
        elif kind in ("WhileStmt", "ForStmt", "DoStmt"):
            names = dict(state.names)
            initial = increment = None
            if kind == "WhileStmt": condition, body = children
            elif kind == "DoStmt": body, condition = children
            else:
                raw = node.get("inner", [])
                if len(raw) != 5 or raw[1]: raise UnsupportedExpression("unsupported for-loop shape")
                initial, _, condition, increment, body = raw
            more = [("loop", node, condition, body, increment, 0, names)] + tail
            if initial: more.insert(0, ("node", initial))
            self.push(fn, state, more)
        elif kind == "ReturnStmt":
            if children: self.eval(children[0], state)
        elif kind in ("BreakStmt", "ContinueStmt"):
            for index, pending in enumerate(tail):
                if pending[0] == "scope": state.names = dict(pending[1])
                if pending[0] == "loop_after":
                    state.names = dict(pending[-1]) if kind == "BreakStmt" else state.names
                    self.push(fn, state, tail[index + 1:] if kind == "BreakStmt" else tail[index:])
                    break
            else: raise UnsupportedExpression("loop control without loop frame")
        else:
            if kind != "NullStmt": self.eval(node, state, allow_mutation=True)
            self.push(fn, state, tail)

    def advance(self, extra_states=None):
        stop_at = min(self.state_budget, self.visited + extra_states) if extra_states is not None else self.state_budget
        try:
            while self.queue and not self.finding and self.visited < stop_at:
                self.budget()
                _, _, fn, state, frames = heapq.heappop(self.queue)
                self.function = fn
                self.visited += 1
                self.explored_trace = list(state.trace)
                if not self.feasible(state): continue
                try: self.execute(fn, state, frames)
                except UnsupportedExpression as error: self.note(str(error))
        except FoundWitness:
            pass
        except BudgetExhausted as error:
            self.stopped = str(error)
        if self.queue and self.visited >= self.state_budget and not self.finding:
            self.stopped = "states"
        return self.result()

    def result(self):
        if self.finding: status = "verified_sat"
        elif self.stopped or self.incomplete: status = "unknown"
        elif self.queue: status = "paused"
        else: status = "refuted_complete"
        return {"status": status, "prediction": bool(self.finding), "policy": self.policy,
                "states": self.visited, "solver_calls": self.queries, "seed_batches": self.seed_checks,
                "remaining_tasks": len(self.queue), "stop_reason": self.stopped,
                "incomplete": list(self.incomplete), "elapsed_seconds": time.monotonic() - self.started,
                "findings": [self.finding] if self.finding else [],
                "feedback": self.failures[-3:], "last_trace": self.explored_trace}
