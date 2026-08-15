"""Tests for framework-to-framework body and return-type transformation."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from intpot.core.generators.api import APIGenerator
from intpot.core.models import _SENTINEL, ParameterInfo, SourceType, ToolInfo
from intpot.core.transforms import transform_tools


def _add_tool(body: str, return_type: str = "str") -> ToolInfo:
    return ToolInfo(
        name="add",
        description="Add two numbers.",
        parameters=[
            ParameterInfo(name="a", type_annotation="int", default=_SENTINEL),
            ParameterInfo(name="b", type_annotation="int", default=_SENTINEL),
        ],
        return_type=return_type,
        function_body=body,
    )


def _to_api(tool: ToolInfo, source: SourceType) -> ToolInfo:
    return transform_tools([tool], source, SourceType.API)[0]


def test_cli_to_api_wraps_a_scalar_return():
    """`-> dict` is only honest if the body actually returns a mapping.

    typer.echo(a + b) becomes `return a + b`, which FastAPI then rejected
    against the dict annotation with a ResponseValidationError.
    """
    result = _to_api(_add_tool("typer.echo(a + b)"), SourceType.CLI)

    assert result.function_body == "return {'result': a + b}"
    assert result.return_type == "dict"


def test_mcp_to_api_wraps_a_scalar_return():
    result = _to_api(_add_tool("return a + b"), SourceType.MCP)

    assert result.function_body == "return {'result': a + b}"
    assert result.return_type == "dict"


def test_a_dict_return_is_not_nested_again():
    """A source already returning a mapping needs no wrapping."""
    tool = _add_tool("return {'sum': a + b}", return_type="dict")

    result = _to_api(tool, SourceType.MCP)

    assert result.function_body == "return {'sum': a + b}"
    assert result.return_type == "dict"


def test_a_body_that_never_returns_is_annotated_none():
    """Falling off the end yields None, which `-> dict` would also reject."""
    tool = ToolInfo(name="ping", description="Ping.", function_body="print('pong')")

    result = _to_api(tool, SourceType.CLI)

    assert result.return_type == "None"


@pytest.mark.parametrize(
    ("body", "return_type"),
    [
        ("if a:\n    return 1", "dict | None"),
        ("if a:\n    return 1\nelse:\n    return 2", "dict"),
        ("try:\n    return 1\nexcept ValueError:\n    pass", "dict | None"),
        ("try:\n    return 1\nexcept ValueError:\n    return 2", "dict"),
        ("for item in []:\n    return item", "dict | None"),
        ("for item in []:\n    pass\nelse:\n    return 1", "dict"),
        ("while True:\n    return 1", "dict"),
        (
            "with suppress(ValueError):\n    raise ValueError\nreturn 1",
            "dict",
        ),
        (
            "match a:\n    case True:\n        return 1\n    case _:\n        return 2",
            "dict",
        ),
        ("match a:\n    case True:\n        return 1", "dict | None"),
        ("return", "None"),
    ],
)
def test_api_annotation_describes_reachable_return_shapes(body, return_type):
    result = _to_api(_add_tool(body), SourceType.MCP)

    assert result.return_type == return_type


def test_returns_inside_a_nested_function_are_left_alone():
    body = "def helper():\n    return a + b\nreturn helper()"

    result = _to_api(_add_tool(body), SourceType.MCP)

    body = result.function_body or ""
    assert "return a + b" in body
    assert "return {'result': helper()}" in body


def test_converted_api_app_serves_a_real_request():
    """The end-to-end check: convert, execute the output, call it."""
    tool = _to_api(_add_tool("typer.echo(a + b)"), SourceType.CLI)
    namespace: dict[str, Any] = {}
    exec(compile(APIGenerator().generate([tool]), "<generated>", "exec"), namespace)

    response = TestClient(namespace["app"]).post("/add", json={"a": 2, "b": 3})

    assert response.status_code == 200
    assert response.json() == {"result": 5}


def test_api_target_does_not_change_other_targets():
    """Wrapping is FastAPI-specific; CLI and MCP output is untouched."""
    cli = transform_tools([_add_tool("return a + b")], SourceType.MCP, SourceType.CLI)[
        0
    ]
    mcp = transform_tools(
        [_add_tool("return a + b", return_type="int")],
        SourceType.API,
        SourceType.MCP,
    )[0]

    assert "result" not in (cli.function_body or "")
    assert cli.return_type == "None"
    assert mcp.function_body == "return a + b"
    assert mcp.return_type == "int"
