"""Independent, bounded symbolic execution of a deliberately restricted C subset.

LLM text never supplies control flow or assignments. Integer execution uses the
recorded 32-bit int, two's-complement Clang target. Unsupported paths and unfinished
loops are explicit incompleteness, never proofs of safety.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List
import z3
from .extract import load_ast, extract_sites, division_locations, _children, _offset, _line_column, _walk
from .expressions import c_div, c_rem, truth, integer, UnsupportedExpression

MIN_INT, MAX_INT, MODULUS = -(2 ** 31), 2 ** 31 - 1, 2 ** 32


@dataclass
class State:
    env: Dict[str, Any] = field(default_factory=dict)
    names: Dict[str, str] = field(default_factory=dict)
    constraints: List[Any] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)
    flow: str = "normal"

    def copy(self):
        return State(dict(self.env), dict(self.names), list(self.constraints), dict(self.inputs), self.flow)


@dataclass
class Reach:
    state: State
    denominator: Any


@dataclass
class SiteContext:
    reaches: List[Reach] = field(default_factory=list)
    incomplete: List[str] = field(default_factory=list)


def type_name(node):
    return node.get("type", {}).get("qualType", "").replace("const ", "").replace("volatile ", "")


def signed(value):
    residue = value % MODULUS
    return z3.If(residue > MAX_INT, residue - MODULUS, residue)


class Executor:
    def __init__(self, path, sites, root, loop_bound=8, state_limit=4096, timeout_ms=5000):
        self.source = path.read_text(encoding="utf-8")
        self.sites = sites
        self.site_locations = division_locations(self.source, root)
        self.by_location = {(s.line, s.column, s.operator): s.site_id for s in sites}
        self.contexts = {s.site_id: SiteContext() for s in sites}
        self.globals = {n["id"]: n for n in _children(root) if n.get("kind") == "VarDecl"}
        self.functions = {n["name"]: n for n in _children(root)
                          if n.get("kind") == "FunctionDecl" and any(c.get("kind") == "CompoundStmt" for c in _children(n))}
        self.loop_bound, self.state_limit, self.timeout_ms = loop_bound, state_limit, timeout_ms
        self.steps = self.serial = 0
        self.function = ""

    def note(self, reason):
        for site in self.sites:
            if site.function == self.function and reason not in self.contexts[site.site_id].incomplete:
                self.contexts[site.site_id].incomplete.append(reason)

    def feasible(self, state):
        solver = z3.Solver()
        # This is only a pruning optimization: unknown retains the exact path.
        # It neither loses paths nor justifies a safety/abstention conclusion.
        solver.set(timeout=min(self.timeout_ms, 25))
        solver.add(*state.constraints)
        result = solver.check()
        return result != z3.unsat

    @staticmethod
    def add(state, condition, active=True):
        state.constraints.append(z3.Implies(active, condition))

    def bounded(self, value, node, state, active=True):
        t = type_name(node)
        if t == "unsigned int":
            return value % MODULUS
        if t not in ("int", "_Bool"):
            raise UnsupportedExpression("unsupported integer type: " + t)
        if t == "_Bool":
            return integer(truth(value))
        self.add(state, z3.And(value >= MIN_INT, value <= MAX_INT), active)
        return value

    def fresh(self, name, state, unsigned=False, nonnegative=False):
        self.serial += 1
        key = "{}:{}:{}".format(self.function, name, self.serial)
        value = z3.Int(key)
        state.inputs[key] = value
        state.constraints.extend([value >= (0 if unsigned or nonnegative else MIN_INT),
                                  value <= (MODULUS - 1 if unsigned else MAX_INT)])
        return value

    def record(self, node, state, denominator, active):
        location = self.site_locations.get(node.get("id"))
        if location is None:
            return
        line, column = location
        site_id = self.by_location.get((line, column, node["opcode"]))
        if site_id:
            snapshot = state.copy()
            snapshot.constraints.append(truth(active) if z3.is_expr(active) else z3.BoolVal(active))
            self.contexts[site_id].reaches.append(Reach(snapshot, denominator))

    @staticmethod
    def mutates(node):
        return any(n.get("kind") == "CompoundAssignOperator" or
                   n.get("opcode") in ("=", "++", "--") for n in _walk(node))

    def eval(self, node, state, active=True, allow_mutation=False):
        kind = node.get("kind")
        inner = list(_children(node))
        if not allow_mutation and self.mutates(node):
            raise UnsupportedExpression("side effects inside an expression are unsupported")
        if kind in ("IntegerLiteral", "CharacterLiteral"):
            return z3.IntVal(int(node["value"]))
        if kind == "DeclRefExpr":
            decl = node.get("referencedDecl", {})
            identity = decl.get("id")
            if identity not in state.env and identity in self.globals:
                definition = self.globals[identity]
                if "const" not in definition.get("type", {}).get("qualType", ""):
                    raise UnsupportedExpression("mutable global requires calling context")
                self.declare(definition, state)
            if identity not in state.env or state.env[identity] is None:
                raise UnsupportedExpression("uninitialized or unavailable value: " + decl.get("name", "?"))
            return state.env[identity]
        if kind == "ParenExpr":
            return self.eval(inner[0], state, active, allow_mutation)
        if kind in ("ImplicitCastExpr", "CStyleCastExpr"):
            if node.get("castKind") not in ("LValueToRValue", "NoOp", "IntegralCast", "IntegralToBoolean"):
                raise UnsupportedExpression("unsupported cast: " + str(node.get("castKind")))
            value = integer(self.eval(inner[0], state, active))
            target = type_name(node)
            if target == "unsigned int":
                return value % MODULUS
            if target == "int":
                return signed(value) if type_name(inner[0]) == "unsigned int" else value
            if target == "_Bool":
                return integer(value != 0)
            raise UnsupportedExpression("unsupported cast target: " + target)
        if kind == "UnaryOperator":
            op = node.get("opcode")
            if op in ("++", "--"):
                target = self.lvalue(inner[0])
                old = self.eval(inner[0], state, active)
                new = self.bounded(old + (1 if op == "++" else -1), node, state, active)
                state.env[target] = new
                return old if node.get("isPostfix") else new
            value = integer(self.eval(inner[0], state, active))
            if op == "!": return integer(value == 0)
            if op == "+": return value
            if op == "-": return self.bounded(-value, node, state, active)
            if op == "~":
                value = z3.BV2Int(~z3.Int2BV(value, 32))
                return value if type_name(node) == "unsigned int" else signed(value)
            raise UnsupportedExpression("unsupported unary operator: " + str(op))
        if kind == "ConditionalOperator":
            condition = truth(self.eval(inner[0], state, active))
            yes = self.eval(inner[1], state, z3.And(active, condition))
            no = self.eval(inner[2], state, z3.And(active, z3.Not(condition)))
            return z3.If(condition, integer(yes), integer(no))
        if kind in ("BinaryOperator", "CompoundAssignOperator"):
            op = node["opcode"]
            if kind == "CompoundAssignOperator" and node.get("computeResultType", {}).get("qualType") != type_name(node):
                raise UnsupportedExpression("compound assignment with a different promoted result type")
            if op == "=":
                value = self.eval(inner[1], state, active)
                state.env[self.lvalue(inner[0])] = self.bounded(integer(value), inner[0], state, active)
                return value
            left = integer(self.eval(inner[0], state, active))
            right_active = active
            if op == "&&": right_active = z3.And(active, left != 0)
            if op == "||": right_active = z3.And(active, left == 0)
            right = integer(self.eval(inner[1], state, right_active))
            effective = op[:-1] if kind == "CompoundAssignOperator" else op
            if effective in ("/", "%"):
                self.record(node, state, right, active)
                self.add(state, right != 0, active)
                if type_name(node) == "int":
                    self.add(state, z3.Not(z3.And(left == MIN_INT, right == -1)), active)
                value = c_div(left, right) if effective == "/" else c_rem(left, right)
            elif effective in ("+", "-", "*"):
                value = {"+": lambda: left + right, "-": lambda: left - right,
                         "*": lambda: left * right}[effective]()
            elif effective in ("&", "|", "^", "<<", ">>"):
                a, b = z3.Int2BV(left, 32), z3.Int2BV(right, 32)
                if effective in ("<<", ">>"):
                    self.add(state, z3.And(right >= 0, right < 32), active)
                    if type_name(node) != "unsigned int":
                        raise UnsupportedExpression("signed shifts are outside the supported subset")
                bits = {"&": lambda: a & b, "|": lambda: a | b, "^": lambda: a ^ b,
                        "<<": lambda: a << b, ">>": lambda: z3.LShR(a, b)}[effective]()
                value = z3.BV2Int(bits)
                if type_name(node) == "int": value = signed(value)
            elif effective in ("==", "!=", "<", "<=", ">", ">=", "&&", "||"):
                return integer({"==": lambda: left == right, "!=": lambda: left != right,
                                "<": lambda: left < right, "<=": lambda: left <= right,
                                ">": lambda: left > right, ">=": lambda: left >= right,
                                "&&": lambda: z3.And(left != 0, right != 0),
                                "||": lambda: z3.Or(left != 0, right != 0)}[effective]())
            else:
                raise UnsupportedExpression("unsupported binary operator: " + op)
            value = self.bounded(value, node, state, active)
            if kind == "CompoundAssignOperator": state.env[self.lvalue(inner[0])] = value
            return value
        if kind == "CallExpr":
            references = [n.get("referencedDecl", {}) for n in _walk(inner[0]) if n.get("kind") == "DeclRefExpr"]
            name = references[0].get("name", "") if references else ""
            if name in self.functions:
                raise UnsupportedExpression("local call requires interprocedural analysis: " + name)
            if name == "rand" and len(inner) == 1:
                # Independent library results in [0,RAND_MAX], as specified by the benchmark model.
                return self.fresh("rand", state, nonnegative=True)
            if name in ("printIntLine", "printLine"):
                if type_name(node) != "void" or len(inner) != 2:
                    raise UnsupportedExpression("printing summary requires the declared void interface")
                for argument in inner[1:]:
                    literal = argument
                    while literal.get("kind") in ("ImplicitCastExpr", "ParenExpr"):
                        literal = list(_children(literal))[0]
                    if literal.get("kind") != "StringLiteral":
                        self.eval(argument, state, active)
                return z3.IntVal(0)
            raise UnsupportedExpression("call requires an unavailable summary: " + name)
        raise UnsupportedExpression("unsupported expression: " + str(kind))

    def lvalue(self, node):
        while node.get("kind") == "ParenExpr":
            node = list(_children(node))[0]
        if node.get("kind") != "DeclRefExpr":
            raise UnsupportedExpression("only scalar local assignments are supported")
        identity = node["referencedDecl"]["id"]
        if identity in self.globals:
            raise UnsupportedExpression("mutable global assignment")
        return identity

    def declare(self, node, state):
        if type_name(node) not in ("int", "unsigned int", "_Bool") or "volatile" in node.get("type", {}).get("qualType", ""):
            raise UnsupportedExpression("unsupported declaration type")
        if node.get("storageClass") == "static" and "const" not in node.get("type", {}).get("qualType", ""):
            raise UnsupportedExpression("mutable static local")
        children = list(_children(node))
        # An initializer is evaluated in the pre-declaration environment; reads of
        # the new declaration's own ID remain uninitialized and are rejected.
        value = self.eval(children[-1], state) if children else None
        state.names[node["name"]] = node["id"]
        state.env[node["id"]] = self.bounded(integer(value), node, state) if value is not None else None

    def statement(self, node, states):
        output = []
        for state in states:
            if state.flow != "normal":
                output.append(state)
                continue
            self.steps += 1
            if self.steps > self.state_limit:
                self.note("state exploration limit reached")
                break
            if not self.feasible(state):
                continue
            try:
                output.extend(self.one_statement(node, state))
            except UnsupportedExpression as error:
                self.note(str(error))
        return output

    def one_statement(self, node, state):
        kind, children = node.get("kind"), list(_children(node))
        if kind == "CompoundStmt":
            saved_names = dict(state.names)
            states = [state]
            for child in children:
                states = self.statement(child, states)
            for item in states: item.names = dict(saved_names)
            return states
        if kind == "DeclStmt":
            for child in children: self.declare(child, state)
            return [state]
        if kind == "IfStmt":
            if node.get("hasInit") or node.get("hasVar"):
                raise UnsupportedExpression("declaration in branch condition")
            condition = truth(self.eval(children[0], state))
            yes, no = state.copy(), state.copy()
            yes.constraints.append(condition)
            no.constraints.append(z3.Not(condition))
            output = self.statement(children[1], [yes])
            output += self.statement(children[2], [no]) if len(children) > 2 else [no]
            return output
        if kind in ("WhileStmt", "ForStmt", "DoStmt"):
            outer_names = dict(state.names)
            if kind == "WhileStmt":
                condition, body = children
                initial, increment = None, None
            elif kind == "DoStmt":
                body, condition = children
                initial, increment = None, None
            else:
                raw = node.get("inner", [])
                if len(raw) != 5 or raw[1]:
                    raise UnsupportedExpression("unsupported for-loop shape")
                initial, _, condition, increment, body = raw
            states = self.statement(initial, [state]) if initial else [state]
            finished = []
            for iteration in range(self.loop_bound + 1):
                entering = []
                for current in states:
                    if current.flow == "return":
                        finished.append(current); continue
                    cond = (z3.BoolVal(True) if not condition or (kind == "DoStmt" and iteration == 0)
                            else truth(self.eval(condition, current)))
                    leave, go = current.copy(), current.copy()
                    leave.constraints.append(z3.Not(cond))
                    go.constraints.append(cond)
                    if self.feasible(leave): finished.append(leave)
                    if self.feasible(go): entering.append(go)
                if not entering: break
                if iteration == self.loop_bound:
                    self.note("loop bound reached ({})".format(self.loop_bound)); break
                states = self.statement(body, entering)
                continuing = []
                for current in states:
                    if current.flow == "break":
                        current.flow = "normal"; finished.append(current)
                    elif current.flow == "return": finished.append(current)
                    else:
                        current.flow = "normal"
                        continuing.append(current)
                states = self.statement(increment, continuing) if increment else continuing
            for current in finished: current.names = dict(outer_names)
            return finished
        if kind == "ReturnStmt":
            if children: self.eval(children[0], state)
            state.flow = "return"
            return [state]
        if kind in ("BreakStmt", "ContinueStmt"):
            state.flow = "break" if kind == "BreakStmt" else "continue"
            return [state]
        if kind == "NullStmt": return [state]
        self.eval(node, state, allow_mutation=True)
        return [state]

    def run(self):
        for function in sorted({s.function for s in self.sites}):
            self.function, self.steps = function, 0
            node = self.functions.get(function)
            if node is None:
                self.note("function body not found"); continue
            state = State()
            try:
                for param in _children(node):
                    if param.get("kind") == "ParmVarDecl":
                        if type_name(param) not in ("int", "unsigned int") or "volatile" in param.get("type", {}).get("qualType", ""):
                            raise UnsupportedExpression("unsupported parameter type")
                        state.env[param["id"]] = self.fresh(param["name"], state, type_name(param) == "unsigned int")
                        state.names[param["name"]] = param["id"]
                body = next(c for c in _children(node) if c.get("kind") == "CompoundStmt")
                self.statement(body, [state])
            except UnsupportedExpression as error:
                self.note(str(error))
        return self.contexts


def build_context(path: Path, sites=None, clang="clang", loop_bound=8, state_limit=4096, timeout_ms=5000):
    root = load_ast(path, clang)
    sites = sites if sites is not None else extract_sites(path, clang, root)
    return Executor(path, sites, root, loop_bound, state_limit, timeout_ms).run()
