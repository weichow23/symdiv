"""A small C-precedence constraint language; never Python eval or C execution."""
import re
from typing import Any, Dict, Optional
import z3


class UnsupportedExpression(ValueError):
    pass


def truth(value):
    return value if z3.is_bool(value) else value != 0


def integer(value):
    return z3.If(value, 1, 0) if z3.is_bool(value) else value


def c_div(left, right):
    """C99/C11 quotient, truncated towards zero (caller enforces definedness)."""
    magnitude = z3.Abs(left) / z3.Abs(right)
    return z3.If((left < 0) != (right < 0), -magnitude, magnitude)


def c_rem(left, right):
    return left - right * c_div(left, right)


_TOKEN = re.compile(r"\s*(\d+|[A-Za-z_]\w*|&&|\|\||==|!=|<=|>=|[()+*/%<>!\-])")
_PRECEDENCE = {"||": 1, "&&": 2, "==": 3, "!=": 3, "<": 4, "<=": 4,
               ">": 4, ">=": 4, "+": 5, "-": 5, "*": 6, "/": 6, "%": 6}


class ExpressionTranslator:
    def __init__(self, variables: Optional[Dict[str, Any]] = None):
        self.variables = dict(variables or {})
        self.strict_names = variables is not None
        self.guards = []

    @staticmethod
    def _as_bool(value):
        return truth(value)

    def variable(self, name):
        if name not in self.variables:
            if self.strict_names:
                raise UnsupportedExpression("identifier is not in scope: " + name)
            self.variables[name] = z3.Int(name)
        return self.variables[name]

    def parse(self, expression):
        text = expression.strip()
        tokens = []
        pos = 0
        while pos < len(text):
            match = _TOKEN.match(text, pos)
            if not match:
                raise UnsupportedExpression("unsupported constraint syntax near " + text[pos:pos + 20])
            tokens.append(match.group(1))
            pos = match.end()
        self.tokens, self.pos = tokens, 0
        tree = self._expression(1)
        if self.pos != len(self.tokens):
            raise UnsupportedExpression("unexpected constraint token")
        return self._translate(tree, z3.BoolVal(True))

    def _expression(self, minimum):
        if self.pos >= len(self.tokens):
            raise UnsupportedExpression("incomplete constraint")
        token = self.tokens[self.pos]
        self.pos += 1
        if token in ("!", "+", "-"):
            left = ("unary", token, self._expression(7))
        elif token == "(":
            left = self._expression(1)
            if self.pos >= len(self.tokens) or self.tokens[self.pos] != ")":
                raise UnsupportedExpression("unclosed parenthesis")
            self.pos += 1
        elif token.isdigit() or re.fullmatch(r"[A-Za-z_]\w*", token):
            left = ("atom", token)
        else:
            raise UnsupportedExpression("unexpected constraint token: " + token)
        while self.pos < len(self.tokens):
            operator = self.tokens[self.pos]
            precedence = _PRECEDENCE.get(operator, 0)
            if precedence < minimum:
                break
            self.pos += 1
            left = ("binary", operator, left, self._expression(precedence + 1))
        return left

    def _translate(self, tree, active):
        if tree[0] == "atom":
            token = tree[1]
            if token.isdigit():
                return z3.IntVal(int(token))
            if token in ("true", "True", "false", "False"):
                return z3.BoolVal(token.lower() == "true")
            return self.variable(token)
        if tree[0] == "unary":
            value = self._translate(tree[2], active)
            return {"!": lambda: z3.Not(truth(value)), "+": lambda: integer(value),
                    "-": lambda: -integer(value)}[tree[1]]()
        op = tree[1]
        left = self._translate(tree[2], active)
        right_active = active
        if op == "&&":
            right_active = z3.And(active, truth(left))
        if op == "||":
            right_active = z3.And(active, z3.Not(truth(left)))
        right = self._translate(tree[3], right_active)
        if op == "&&":
            return z3.And(truth(left), truth(right))
        if op == "||":
            return z3.Or(truth(left), truth(right))
        left, right = integer(left), integer(right)
        if op in ("/", "%"):
            self.guards.append(z3.Implies(active, right != 0))
        return {
            "+": lambda: left + right, "-": lambda: left - right,
            "*": lambda: left * right, "/": lambda: c_div(left, right),
            "%": lambda: c_rem(left, right), "==": lambda: left == right,
            "!=": lambda: left != right, "<": lambda: left < right,
            "<=": lambda: left <= right, ">": lambda: left > right,
            ">=": lambda: left >= right,
        }[op]()
