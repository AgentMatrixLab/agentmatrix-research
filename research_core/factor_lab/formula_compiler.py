"""
GTJA191-style formula compiler.

Parses factor expressions like:
    (-1 * CORR(RANK(DELTA(LOG(VOLUME),1)), RANK((CLOSE-OPEN)/OPEN), 6))
and compiles them to executable Python functions that operate on long-panel
DataFrames (columns: date, code, open, high, low, close, volume, amount).

Usage:
    from research_core.factor_lab.formula_compiler import compile_formula

    alpha1 = compile_formula(
        "(-1 * CORR(RANK(DELTA(LOG(VOLUME),1)), RANK((CLOSE-OPEN)/OPEN), 6))",
        alpha_name="_alpha1",
    )
    result: pd.Series = alpha1(df)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from research_core.factor_lab.operators import (
    SequenceSpec,
    compute_vwap,
    cross_sectional_rank,
    cross_sectional_scale,
    decay_linear,
    indneutralize,
    rolling_corr,
    rolling_cov,
    rolling_regression_beta,
    safe_div,
    signed_power,
    sma,
    sort_panel,
    ts_decay_linear,
    ts_delay,
    ts_delta,
    ts_max,
    ts_mean,
    ts_min,
    ts_rank,
    ts_std,
    ts_sum,
    wma,
)

# ── AST node types ──────────────────────────────────────────────────────

@dataclass
class Field:
    """A field reference: OPEN, CLOSE, VOLUME, VWAP, etc."""
    name: str


@dataclass
class Literal:
    """A numeric literal."""
    value: float


@dataclass
class BinOp:
    """Binary operation: +, -, *, /, ^"""
    op: str
    left: "Expr"
    right: "Expr"


@dataclass
class UnaryOp:
    """Unary negation: -expr"""
    op: str
    operand: "Expr"


@dataclass
class FuncCall:
    """Function call: RANK(x), CORR(x, y, d), SMA(x, n, m), etc."""
    func: str
    args: list["Expr"]


@dataclass
class IfExpr:
    """IF(cond, true_val, false_val)"""
    cond: "Expr"
    true_val: "Expr"
    false_val: "Expr"


Expr = Field | Literal | BinOp | UnaryOp | FuncCall | IfExpr


# ── Tokenizer ───────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r"""
    \s*(?:
        ([A-Za-z_][A-Za-z0-9_]*)               |  # identifier
        ([0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?) |  # number
        (>=|<=|!=|==|[+\-*/^(),<>])            |  # operator / paren / comma / comparison
        (.+)                                      # error
    )
""", re.VERBOSE)


def tokenize(expr: str) -> list[tuple[str, str]]:
    """Tokenize a formula string into (type, value) pairs."""
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(expr):
        m = _TOKEN_RE.match(expr, pos)
        if m is None:
            raise ValueError(f"Unexpected character at position {pos}: {expr[pos:]!r}")
        pos = m.end()
        if m.group(1):
            tokens.append(("IDENT", m.group(1)))
        elif m.group(2):
            tokens.append(("NUMBER", m.group(2)))
        elif m.group(3):
            tokens.append((m.group(3), m.group(3)))
        elif m.group(4):
            raise ValueError(f"Unexpected token at position {pos}: {m.group(4)!r}")
    tokens.append(("EOF", ""))
    return tokens


# ── Recursive-descent parser ────────────────────────────────────────────

class Parser:
    """Recursive-descent parser for GTJA191 formula expressions.

    Grammar (loose):
        expr        → if_expr
        if_expr     → 'IF' '(' expr ',' expr ',' expr ')' | add_sub
        add_sub     → mul_div (('+' | '-') mul_div)*
        mul_div     → power (('*' | '/') power)*
        power       → unary ('^' unary)?
        unary       → '-' unary | primary
        primary     → NUMBER | IDENT ('(' args ')')? | '(' expr ')'
        args        → expr (',' expr)*
    """

    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> tuple[str, str]:
        return self.tokens[self.pos]

    def consume(self) -> tuple[str, str]:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, value: str) -> None:
        tok = self.consume()
        if tok[1] != value:
            raise ValueError(f"Expected {value!r}, got {tok[1]!r}")

    def parse(self) -> Expr:
        result = self._if_expr()
        tok = self.peek()
        if tok[0] != "EOF":
            raise ValueError(f"Unexpected token after expression: {tok}")
        return result

    def _if_expr(self) -> Expr:
        if self.peek()[0] == "IDENT" and self.peek()[1].upper() == "IF":
            self.consume()
            self.expect("(")
            cond = self._if_expr()
            self.expect(",")
            true_val = self._if_expr()
            self.expect(",")
            false_val = self._if_expr()
            self.expect(")")
            return IfExpr(cond, true_val, false_val)
        return self._comparison()

    def _comparison(self) -> Expr:
        left = self._add_sub()
        while self.peek()[1] in ("<", ">", "<=", ">=", "==", "!="):
            op = self.consume()[1]
            right = self._add_sub()
            left = BinOp(op, left, right)
        return left

    def _add_sub(self) -> Expr:
        left = self._mul_div()
        while self.peek()[1] in ("+", "-"):
            op = self.consume()[1]
            right = self._mul_div()
            left = BinOp(op, left, right)
        return left

    def _mul_div(self) -> Expr:
        left = self._power()
        while self.peek()[1] in ("*", "/"):
            op = self.consume()[1]
            right = self._power()
            left = BinOp(op, left, right)
        return left

    def _power(self) -> Expr:
        left = self._unary()
        while self.peek()[1] == "^":
            self.consume()
            right = self._unary()
            left = BinOp("^", left, right)
        return left

    def _unary(self) -> Expr:
        if self.peek()[1] == "-":
            self.consume()
            operand = self._unary()
            return UnaryOp("-", operand)
        return self._primary()

    def _primary(self) -> Expr:
        tok = self.peek()
        if tok[0] == "NUMBER":
            val = self.consume()[1]
            return Literal(float(val))
        if tok[0] == "IDENT":
            name = self.consume()[1]
            if self.peek()[1] == "(":
                # Function call
                self.consume()
                args: list[Expr] = []
                if self.peek()[1] != ")":
                    args.append(self._if_expr())
                    while self.peek()[1] == ",":
                        self.consume()
                        args.append(self._if_expr())
                self.expect(")")
                return FuncCall(name, args)
            # Bare field reference
            return Field(name)
        if tok[1] == "(":
            self.consume()
            expr = self._if_expr()
            self.expect(")")
            return expr
        raise ValueError(f"Unexpected token at position {self.pos}: {tok}")


# ── Default field-name mapping (formula → DataFrame column) ─────────────

DEFAULT_FIELD_MAP: dict[str, str] = {
    "OPEN": "open",
    "HIGH": "high",
    "LOW": "low",
    "CLOSE": "close",
    "VOLUME": "volume",
    "AMOUNT": "amount",
    "VWAP": "vwap",
    "RETURNS": "returns",
}


# ── Operator registry ───────────────────────────────────────────────────

# (python_callable, num_series_args) — the last positional arg is always the
# window / parameter and is passed directly (not assigned as a column).
_PANEL_OPERATORS: dict[str, tuple[str, int]] = {
    "RANK":          ("cross_sectional_rank", 1),
    "TS_RANK":       ("ts_rank",               1),
    "DELTA":         ("ts_delta",              1),
    "MEAN":          ("ts_mean",               1),
    "STD":           ("ts_std",                1),
    "SUM":           ("ts_sum",                1),
    "MAX":           ("ts_max",                1),
    "MIN":           ("ts_min",                1),
    "DECAY_LINEAR":  ("ts_decay_linear",       1),
    "SCALE":         ("cross_sectional_scale", 1),
    "INDNEUTRALIZE": ("indneutralize",         2),   # (value_expr, group_field)
    "CORR":          ("rolling_corr",          2),
    "COV":           ("rolling_cov",           2),
}

_SERIES_OPERATORS: dict[str, str] = {
    "LOG":  "np.log",
    "ABS":  "np.abs",
    "SIGN": "np.sign",
}

# Wide-form operators (operate on date × symbol DataFrames — used here via
# groupby + transform for the long-panel path).
_WIDE_OPERATORS: dict[str, str] = {
    "SMA":      "sma",
    "WMA":      "wma",
    "REGBETA":  "rolling_regression_beta",
}


# ── Code generator ──────────────────────────────────────────────────────

class CodeGenerator:
    """Walk the AST and emit Python statements that compute the factor.

    Strategy
    --------
    * Field references emit ``df["col"]``.
    * Literals emit their numeric value.
    * Arithmetic / LOG / ABS / SIGN operate on bare Series and emit an
      intermediate variable, e.g. ``_v3 = _v1 + _v2``.
    * Long-panel operators (RANK, TS_RANK, CORR, …) need the input series
      to be columns in a temporary DataFrame, so we emit::

          _v5 = cross_sectional_rank(df.assign(_v5=_v3), "_v5")

      For two-series operators (CORR, COV)::

          _v12 = rolling_corr(df.assign(_v12__a=_v5, _v12__b=_v10),
                              "_v12__a", "_v12__b", 6)

    * IF(cond, a, b) → ``np.where(cond, a, b)``.
    * SEQUENCE(n) → ``SequenceSpec(n)``.
    """

    def __init__(self, field_map: dict[str, str] | None = None) -> None:
        self.field_map = field_map or DEFAULT_FIELD_MAP
        self._counter = 0
        self.statements: list[str] = []

    def _next_var(self) -> str:
        name = f"_v{self._counter}"
        self._counter += 1
        return name

    def generate(self, ast: Expr) -> str:
        """Generate code for the whole AST; return the final result variable name."""
        return self._gen(ast)

    def _gen(self, node: Expr) -> str:
        # ── leaves ──────────────────────────────────────────────────
        if isinstance(node, Literal):
            return repr(node.value)

        if isinstance(node, Field):
            col = self.field_map.get(node.name.upper(), node.name.lower())
            return f'df["{col}"]'

        # ── unary ───────────────────────────────────────────────────
        if isinstance(node, UnaryOp):
            operand = self._gen(node.operand)
            var = self._next_var()
            self.statements.append(f"{var} = -{operand}")
            return var

        # ── binary ──────────────────────────────────────────────────
        if isinstance(node, BinOp):
            left = self._gen(node.left)
            right = self._gen(node.right)
            var = self._next_var()

            if node.op == "/":
                self.statements.append(f"{var} = safe_div({left}, {right})")
            elif node.op == "^":
                self.statements.append(f"{var} = signed_power({left}, {right})")
            elif node.op in ("<", ">", "<=", ">=", "==", "!="):
                # Comparison operators → boolean Series
                self.statements.append(f"{var} = {left} {node.op} {right}")
            else:
                self.statements.append(f"{var} = {left} {node.op} {right}")
            return var

        # ── IF(cond, a, b) ──────────────────────────────────────────
        if isinstance(node, IfExpr):
            cond = self._gen(node.cond)
            true_val = self._gen(node.true_val)
            false_val = self._gen(node.false_val)
            var = self._next_var()
            # Use pd.Series(np.where(...)) to ensure we always get a Series,
            # even when true_val/false_val are scalars.
            self.statements.append(
                f"{var} = pd.Series(np.where({cond}.astype(bool), {true_val}, {false_val}), index=df.index)"
            )
            return var

        # ── function calls ──────────────────────────────────────────
        if isinstance(node, FuncCall):
            func_name = node.func.upper()

            # SEQUENCE(n)
            if func_name == "SEQUENCE":
                n = node.args[0] if node.args else Literal(1.0)
                if isinstance(n, Literal):
                    var = self._next_var()
                    self.statements.append(f"{var} = SequenceSpec({int(n.value)})")
                    return var
                n_var = self._gen(n)
                var = self._next_var()
                self.statements.append(f"{var} = SequenceSpec(length=int({n_var}))")
                return var

            # Element-wise series ops: LOG, ABS, SIGN
            if func_name in _SERIES_OPERATORS:
                arg_vars = [self._gen(a) for a in node.args]
                var = self._next_var()
                py_func = _SERIES_OPERATORS[func_name]
                self.statements.append(f"{var} = {py_func}({', '.join(arg_vars)})")
                return var

            # Long-panel operators that need df.assign
            if func_name in _PANEL_OPERATORS:
                py_func, num_series = _PANEL_OPERATORS[func_name]
                arg_vars = [self._gen(a) for a in node.args]
                var = self._next_var()

                series_vars = arg_vars[:num_series]
                param_vars = arg_vars[num_series:]

                if num_series == 1:
                    col_name = var
                    assign = f"df.assign({col_name}={series_vars[0]})"
                    if func_name == "RANK":
                        # RANK takes no extra parameters
                        self.statements.append(
                            f"{var} = {py_func}({assign}, \"{col_name}\")"
                        )
                    elif func_name == "SCALE":
                        scale = param_vars[0] if param_vars else "1.0"
                        self.statements.append(
                            f"{var} = {py_func}({assign}, \"{col_name}\", scale={scale})"
                        )
                    elif func_name == "INDNEUTRALIZE":
                        # Second arg is a group-column name (a field, not an expression)
                        # param_vars[0] is the group column reference
                        group_col = param_vars[0] if param_vars else f'"{self.field_map.get("INDUSTRY", "industry")}"'
                        self.statements.append(
                            f"{var} = {py_func}({assign}, \"{col_name}\", {group_col})"
                        )
                    else:
                        # TS_RANK, DELTA, MEAN, STD, SUM, MAX, MIN, DECAY_LINEAR
                        window = param_vars[0] if param_vars else "1"
                        self.statements.append(
                            f"{var} = {py_func}({assign}, \"{col_name}\", {window})"
                        )
                elif num_series == 2:
                    # CORR(x, y, d), COV(x, y, d), INDNEUTRALIZE(x, g)
                    col_a = f"{var}__a"
                    col_b = f"{var}__b"
                    assign = f"df.assign({col_a}={series_vars[0]}, {col_b}={series_vars[1]})"
                    window = param_vars[0] if param_vars else "1"
                    self.statements.append(
                        f"{var} = {py_func}({assign}, \"{col_a}\", \"{col_b}\", {window})"
                    )
                return var

            # Wide-form operators: SMA, WMA, REGBETA
            # Wrap in groupby + transform for long-panel compatibility.
            if func_name in _WIDE_OPERATORS:
                py_func = _WIDE_OPERATORS[func_name]
                arg_vars = [self._gen(a) for a in node.args]
                var = self._next_var()

                if func_name == "SMA":
                    # SMA(x, n, m) — recursive SMA via groupby
                    x_var, n_var, m_var = arg_vars[0], arg_vars[1], arg_vars[2]
                    self.statements.append(
                        f"{var} = _sma_long_panel(df.assign({var}={x_var}), \"{var}\", int({n_var}), int({m_var}))"
                    )
                elif func_name == "WMA":
                    # WMA(x, d)
                    x_var, d_var = arg_vars[0], arg_vars[1]
                    self.statements.append(
                        f"{var} = _wma_long_panel(df.assign({var}={x_var}), \"{var}\", int({d_var}))"
                    )
                elif func_name == "REGBETA":
                    # REGBETA(y, x, d)
                    y_var, x_var, d_var = arg_vars[0], arg_vars[1], arg_vars[2]
                    self.statements.append(
                        f"{var} = _regbeta_long_panel(df.assign({var}__y={y_var}, {var}__x={x_var}), \"{var}__y\", \"{var}__x\", int({d_var}))"
                    )
                return var

            # Fallback: treat as a generic call
            arg_vars = [self._gen(a) for a in node.args]
            var = self._next_var()
            self.statements.append(f"{var} = {func_name}({', '.join(arg_vars)})")
            return var

        raise TypeError(f"Unknown AST node type: {type(node).__name__}")


# ── Long-panel wrappers for wide-form operators ─────────────────────────

def _sma_long_panel(
    df: pd.DataFrame, value_col: str, n: int, m: int, *, code_col: str = "code"
) -> pd.Series:
    """Recursive SMA for long-panel data."""
    n_f, m_f = float(n), float(m)

    def _sma(series: pd.Series) -> pd.Series:
        values = series.to_numpy(dtype=float)
        result = np.full(len(values), np.nan)
        start = None
        for i, v in enumerate(values):
            if not np.isnan(v):
                result[i] = v
                start = i
                break
        if start is None:
            return pd.Series(result, index=series.index)
        for i in range(start + 1, len(values)):
            result[i] = (
                result[i - 1]
                if np.isnan(values[i])
                else (values[i] * m_f + result[i - 1] * (n_f - m_f)) / n_f
            )
        return pd.Series(result, index=series.index)

    return df.groupby(code_col)[value_col].transform(_sma)


def _wma_long_panel(
    df: pd.DataFrame, value_col: str, window: int, *, code_col: str = "code"
) -> pd.Series:
    """Weighted MA with 0.9^distance weights for long-panel data."""
    weights = np.power(0.9, np.arange(window - 1, -1, -1, dtype=float))
    weights /= weights.sum()

    def _wma_apply(series: pd.Series) -> pd.Series:
        return series.rolling(window, min_periods=window).apply(
            lambda x: float(np.dot(x, weights)) if not np.isnan(x).any() else np.nan,
            raw=True,
        )

    return df.groupby(code_col)[value_col].transform(_wma_apply)


def _regbeta_long_panel(
    df: pd.DataFrame,
    y_col: str,
    x_col: str,
    window: int,
    *,
    code_col: str = "code",
) -> pd.Series:
    """Rolling regression beta of y on x for long-panel data."""

    def _beta(series: pd.Series) -> pd.Series:
        y_vals = df.loc[series.index, y_col].to_numpy(dtype=float)
        x_vals = df.loc[series.index, x_col].to_numpy(dtype=float)
        result = np.full(len(series), np.nan)
        for i in range(window - 1, len(series)):
            yw = y_vals[i - window + 1 : i + 1]
            xw = x_vals[i - window + 1 : i + 1]
            valid = np.isfinite(yw) & np.isfinite(xw)
            if valid.sum() < 2:
                continue
            xm = xw[valid].mean()
            ym = yw[valid].mean()
            num = ((xw[valid] - xm) * (yw[valid] - ym)).sum()
            den = ((xw[valid] - xm) ** 2).sum()
            if den != 0:
                result[i] = num / den
        return pd.Series(result, index=series.index)

    return df.groupby(code_col)[y_col].transform(_beta)


# ── Public API ──────────────────────────────────────────────────────────

def compile_formula(
    formula: str,
    field_map: dict[str, str] | None = None,
    alpha_name: str = "_alpha",
) -> Callable[[pd.DataFrame], pd.Series]:
    """Compile a GTJA191-style formula into a callable Python function.

    Parameters
    ----------
    formula : str
        Factor expression, e.g.
        ``"(-1 * CORR(RANK(DELTA(LOG(VOLUME),1)), RANK((CLOSE-OPEN)/OPEN), 6))"``
    field_map : dict[str, str] | None
        Maps uppercase formula field names to lowercase DataFrame column names.
        Default: ``{"OPEN": "open", "HIGH": "high", ...}``.
    alpha_name : str
        Name for the generated function (default ``"_alpha"``).

    Returns
    -------
    Callable[[pd.DataFrame], pd.Series]
        A function that accepts a long-panel DataFrame (with columns ``date``,
        ``code``, ``open``, ``high``, ``low``, ``close``, ``volume``, ``amount``)
        and returns a ``pd.Series`` of factor values.
    """
    # 1. Tokenize & parse
    tokens = tokenize(formula)
    ast = Parser(tokens).parse()

    # 2. Generate code
    gen = CodeGenerator(field_map)
    result_var = gen.generate(ast)

    # 3. Build function source
    lines = [f"def {alpha_name}(df):"]
    for stmt in gen.statements:
        lines.append(f"    {stmt}")
    lines.append(f"    return {result_var}")

    source = "\n".join(lines)

    # 4. Compile & exec in a namespace with all required bindings
    namespace: dict[str, object] = {
        "np": np,
        "pd": pd,
        "safe_div": safe_div,
        "signed_power": signed_power,
        "cross_sectional_rank": cross_sectional_rank,
        "cross_sectional_scale": cross_sectional_scale,
        "ts_rank": ts_rank,
        "ts_delta": ts_delta,
        "ts_delay": ts_delay,
        "ts_mean": ts_mean,
        "ts_std": ts_std,
        "ts_sum": ts_sum,
        "ts_min": ts_min,
        "ts_max": ts_max,
        "rolling_corr": rolling_corr,
        "rolling_cov": rolling_cov,
        "ts_decay_linear": ts_decay_linear,
        "sma": sma,
        "wma": wma,
        "decay_linear": decay_linear,
        "rolling_regression_beta": rolling_regression_beta,
        "indneutralize": indneutralize,
        "compute_vwap": compute_vwap,
        "SequenceSpec": SequenceSpec,
        "_sma_long_panel": _sma_long_panel,
        "_wma_long_panel": _wma_long_panel,
        "_regbeta_long_panel": _regbeta_long_panel,
    }

    code = compile(source, f"<{alpha_name}>", "exec")
    exec(code, namespace)

    return namespace[alpha_name]


# ── Convenience: compile and show generated source ──────────────────────

def compile_and_show(
    formula: str,
    field_map: dict[str, str] | None = None,
    alpha_name: str = "_alpha",
) -> str:
    """Compile a formula and return the generated Python source (for debugging)."""
    tokens = tokenize(formula)
    ast = Parser(tokens).parse()
    gen = CodeGenerator(field_map)
    result_var = gen.generate(ast)

    lines = [f"def {alpha_name}(df):"]
    for stmt in gen.statements:
        lines.append(f"    {stmt}")
    lines.append(f"    return {result_var}")
    return "\n".join(lines)
