"""AST-based function body transformation between frameworks.

Handles the I/O boundary conversion:
- typer.echo(X)  ↔  return X
- return type annotation adjustment
- Framework-specific exit/error handling
"""

from __future__ import annotations

import ast
import copy

from intpot.core.models import SourceType, ToolInfo


def transform_tools(
    tools: list[ToolInfo],
    source: SourceType,
    target: SourceType,
) -> list[ToolInfo]:
    """Transform tool definitions from source framework conventions to target."""
    result = []
    for tool in tools:
        t = copy.deepcopy(tool)

        if t.function_body:
            t.function_body = _transform_body(t.function_body, source, target)
            if (
                target == SourceType.API
                and source != target
                and not _is_dict_type(tool.return_type)
            ):
                t.function_body = _wrap_returns_in_dict(t.function_body)

        # Pass the transformed tool: a CLI body's typer.echo() has become a
        # return by this point, and the annotation has to describe that.
        t.return_type = _target_return_type(t, source, target)
        result.append(t)
    return result


def _is_dict_type(return_type: str) -> bool:
    """Whether an annotation already denotes a mapping FastAPI can serve as-is."""
    return return_type.lstrip("\"'").lower().startswith("dict")


def _target_return_type(tool: ToolInfo, source: SourceType, target: SourceType) -> str:
    """Determine the correct return type for the target framework."""
    if target == SourceType.CLI:
        return "None"
    if target == SourceType.API:
        # FastAPI validates the response against this annotation, so it has to
        # describe every reachable output. Explicit values are wrapped into a
        # dict above; bare returns and normal fallthrough produce None.
        outcomes = _return_outcomes(tool.function_body or "")
        if "value" not in outcomes:
            return "None"
        if outcomes & {"none", "fallthrough"}:
            return "dict | None"
        return "dict"
    # MCP: preserve original if coming from MCP/API, use str from CLI
    if source == SourceType.CLI:
        return "str"
    return tool.return_type


def _transform_body(body: str, source: SourceType, target: SourceType) -> str:
    """Transform function body between framework conventions."""
    if source == target:
        return body

    if source == SourceType.CLI:
        return _from_cli(body, target)
    if source == SourceType.MCP:
        return _from_mcp(body, target)
    if source == SourceType.API:
        return _from_api(body, target)
    return body


# ---------------------------------------------------------------------------
# CLI → other
# ---------------------------------------------------------------------------


def _from_cli(body: str, target: SourceType) -> str:
    """Transform CLI body: typer.echo(X) → return X (MCP/API)."""
    try:
        tree = ast.parse(body)
    except SyntaxError:
        return body

    transformer = _TyperEchoToReturn()
    new_tree = transformer.visit(tree)
    ast.fix_missing_locations(new_tree)

    # Also remove typer.Exit raises → convert to return/raise
    remover = _TyperExitTransformer(target)
    new_tree = remover.visit(new_tree)
    ast.fix_missing_locations(new_tree)

    return ast.unparse(new_tree)


class _TyperEchoToReturn(ast.NodeTransformer):
    """Replace typer.echo(X) expression statements with return X."""

    def visit_Expr(self, node: ast.Expr) -> ast.AST:
        if self._is_typer_echo(node.value):
            call = node.value
            assert isinstance(call, ast.Call)
            if call.args:
                return ast.Return(value=call.args[0])
            return ast.Return(value=ast.Constant(value=""))
        return node

    def _is_typer_echo(self, node: ast.expr) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        # typer.echo(...)
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "echo"
            and isinstance(func.value, ast.Name)
            and func.value.id == "typer"
        ):
            return True
        # echo(...) — bare name in case of `from typer import echo`
        return isinstance(func, ast.Name) and func.id == "echo"


class _TyperExitTransformer(ast.NodeTransformer):
    """Convert raise typer.Exit(code) to appropriate target pattern."""

    def __init__(self, target: SourceType) -> None:
        self.target = target

    def visit_Raise(self, node: ast.Raise) -> ast.AST:
        if node.exc and self._is_typer_exit(node.exc):
            # For MCP/API: just return None (or raise RuntimeError for non-zero)
            call = node.exc
            assert isinstance(call, ast.Call)
            code = 0
            if call.args:
                arg = call.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
                    code = arg.value
            if code != 0:
                return ast.Raise(
                    exc=ast.Call(
                        func=ast.Name(id="RuntimeError", ctx=ast.Load()),
                        args=[ast.Constant(value=f"Exit code {code}")],
                        keywords=[],
                    ),
                    cause=None,
                )
            return ast.Return(value=None)
        return node

    def _is_typer_exit(self, node: ast.expr) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        return (
            isinstance(func, ast.Attribute)
            and func.attr in ("Exit", "Abort")
            and isinstance(func.value, ast.Name)
            and func.value.id == "typer"
        )


# ---------------------------------------------------------------------------
# MCP → other
# ---------------------------------------------------------------------------


def _from_mcp(body: str, target: SourceType) -> str:
    """Transform MCP body: return X → typer.echo(X) for CLI, passthrough for API."""
    if target == SourceType.API:
        # MCP returns values, FastAPI returns values. Mostly compatible.
        return body

    if target == SourceType.CLI:
        return _returns_to_echo(body)

    return body


# ---------------------------------------------------------------------------
# API → other
# ---------------------------------------------------------------------------


def _from_api(body: str, target: SourceType) -> str:
    """Transform API body: return X → typer.echo(X) for CLI, return X for MCP."""
    if target == SourceType.CLI:
        return _returns_to_echo(body)

    if target == SourceType.MCP:
        # API returns dicts/values, MCP returns values. Compatible.
        return body

    return body


# ---------------------------------------------------------------------------
# Shared: return → typer.echo
# ---------------------------------------------------------------------------


def _returns_to_echo(body: str) -> str:
    """Replace return statements with typer.echo() calls."""
    try:
        tree = ast.parse(body)
    except SyntaxError:
        return body

    transformer = _ReturnToEcho()
    new_tree = transformer.visit(tree)
    ast.fix_missing_locations(new_tree)
    return ast.unparse(new_tree)


_FALLTHROUGH = "fallthrough"
_VALUE_RETURN = "value"
_NONE_RETURN = "none"
_TERMINATE = "terminate"
_BREAK = "break"


def _then(
    first: set[str],
    second: set[str],
) -> set[str]:
    """Compose control-flow outcomes for two consecutive suites."""
    outcomes = first - {_FALLTHROUGH}
    if _FALLTHROUGH in first:
        outcomes.update(second)
    return outcomes


def _suite_outcomes(statements: list[ast.stmt]) -> set[str]:
    outcomes = {_FALLTHROUGH}
    for statement in statements:
        outcomes = _then(outcomes, _statement_outcomes(statement))
    return outcomes


def _statement_outcomes(statement: ast.stmt) -> set[str]:
    if isinstance(statement, ast.Return):
        return {_NONE_RETURN if statement.value is None else _VALUE_RETURN}
    if isinstance(statement, ast.Raise):
        return {_TERMINATE}
    if isinstance(statement, ast.Break):
        return {_BREAK}
    if isinstance(statement, ast.If):
        otherwise = (
            _suite_outcomes(statement.orelse) if statement.orelse else {_FALLTHROUGH}
        )
        return _suite_outcomes(statement.body) | otherwise
    if isinstance(statement, ast.Match):
        outcomes: set[str] = set()
        exhaustive = False
        for case in statement.cases:
            outcomes.update(_suite_outcomes(case.body))
            if (
                case.guard is None
                and isinstance(case.pattern, ast.MatchAs)
                and case.pattern.pattern is None
            ):
                # Both ``case _:`` and an unguarded capture pattern match every
                # remaining value, so control cannot miss every case.
                exhaustive = True
        if not exhaustive:
            outcomes.add(_FALLTHROUGH)
        return outcomes
    if isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
        body = _suite_outcomes(statement.body)
        outcomes = body - {_FALLTHROUGH, _BREAK}

        # A break skips the else suite and continues after the loop.
        if _BREAK in body:
            outcomes.add(_FALLTHROUGH)

        # For-loops may be empty, and non-constant while conditions may be false.
        # Normal exhaustion runs the else suite before continuing. A literal
        # ``while True`` has no normal-exhaustion path.
        is_infinite_while = (
            isinstance(statement, ast.While)
            and isinstance(statement.test, ast.Constant)
            and statement.test.value is True
        )
        if not is_infinite_while:
            outcomes.update(
                _suite_outcomes(statement.orelse)
                if statement.orelse
                else {_FALLTHROUGH}
            )
        return outcomes
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        outcomes = _suite_outcomes(statement.body)
        if _TERMINATE in outcomes:
            # A context manager may suppress an exception raised by its body,
            # in which case execution continues after the with statement.
            outcomes.add(_FALLTHROUGH)
        return outcomes
    if isinstance(statement, (ast.Try, ast.TryStar)):
        normal = _suite_outcomes(statement.body)
        if statement.orelse:
            normal = _then(normal, _suite_outcomes(statement.orelse))
        outcomes = normal
        for handler in statement.handlers:
            outcomes |= _suite_outcomes(handler.body)
        if statement.finalbody:
            final = _suite_outcomes(statement.finalbody)
            outcomes = (final - {_FALLTHROUGH}) | (
                outcomes if _FALLTHROUGH in final else set()
            )
        return outcomes
    # Nested definitions and ordinary statements complete normally. In
    # particular, returns inside a nested function do not describe this body.
    return {_FALLTHROUGH}


def _return_outcomes(body: str) -> set[str]:
    """Find reachable value, None, and fallthrough outcomes for a body."""
    try:
        tree = ast.parse(body)
    except SyntaxError:
        return {_FALLTHROUGH}
    return _suite_outcomes(tree.body)


def _wrap_returns_in_dict(body: str) -> str:
    """Wrap `return X` as `return {'result': X}` for FastAPI targets.

    A converted handler is annotated `-> dict`, and FastAPI validates the
    response against that annotation. Returning the source function's raw
    scalar produced a ResponseValidationError on every call.
    """
    try:
        tree = ast.parse(body)
    except SyntaxError:
        return body

    new_tree = _WrapReturnInDict().visit(tree)
    ast.fix_missing_locations(new_tree)
    return ast.unparse(new_tree)


class _WrapReturnInDict(ast.NodeTransformer):
    """Replace `return X` with `return {'result': X}` at the body's own scope."""

    def __init__(self) -> None:
        self._depth = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self._depth += 1
        result = self.generic_visit(node)
        self._depth -= 1
        return result

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Return(self, node: ast.Return) -> ast.AST:
        if self._depth > 0 or node.value is None:
            return node
        if isinstance(node.value, ast.Dict):
            return node  # already a mapping — don't nest it
        return ast.Return(
            value=ast.Dict(keys=[ast.Constant(value="result")], values=[node.value])
        )


class _ReturnToEcho(ast.NodeTransformer):
    """Replace `return X` with `typer.echo(X)` at function top-level scope."""

    def __init__(self) -> None:
        self._depth = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        # Don't transform returns inside nested functions
        self._depth += 1
        result = self.generic_visit(node)
        self._depth -= 1
        return result

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Return(self, node: ast.Return) -> ast.AST:
        if self._depth > 0:
            return node  # Inside nested function, leave alone
        if node.value is None:
            return node  # bare `return` — keep as-is
        echo_call = ast.Expr(
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="typer", ctx=ast.Load()),
                    attr="echo",
                    ctx=ast.Load(),
                ),
                args=[node.value],
                keywords=[],
            )
        )
        return echo_call
