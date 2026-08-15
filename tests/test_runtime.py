"""Tests for the intpot runtime App class."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from intpot.runtime import App


def test_tool_registration():
    app = App("test")

    @app.tool()
    def greet(name: str) -> str:
        """Say hello."""
        return f"Hello, {name}!"

    assert len(app.tools) == 1
    tool = app.tools[0]
    assert tool.name == "greet"
    assert tool.description == "Say hello."
    assert len(tool.parameters) == 1
    assert tool.parameters[0].name == "name"
    assert tool.parameters[0].type_annotation == "str"
    assert tool.parameters[0].required


def test_tool_with_defaults():
    app = App("test")

    @app.tool()
    def greet(name: str, greeting: str = "Hello") -> str:
        return f"{greeting}, {name}!"

    tool = app.tools[0]
    assert tool.parameters[0].required  # name
    assert not tool.parameters[1].required  # greeting
    assert tool.parameters[1].default == "Hello"


def _var_positional(*values: int) -> int:
    return sum(values)


def _var_keyword(**values: int) -> int:
    return sum(values.values())


@pytest.mark.parametrize("func", [_var_positional, _var_keyword])
def test_tool_rejects_variadic_parameters(func: Callable[..., int]):
    app = App("test")

    with pytest.raises(
        ValueError,
        match=r"_var_.*variadic parameter.*values.*CLI, API, and MCP",
    ):
        app.tool()(func)

    assert app.tools == []


def test_ordinary_parameters_named_self_and_cls_are_preserved():
    app = App("test")

    @app.tool()
    def identity(self: str, cls: str) -> str:
        return f"{self}:{cls}"

    assert [param.name for param in app.tools[0].parameters] == ["self", "cls"]

    namespace: dict[str, Any] = {}
    exec(compile(app.eject("api"), "<generated>", "exec"), namespace)

    from fastapi.testclient import TestClient

    response = TestClient(namespace["app"]).post(
        "/identity", json={"self": "left", "cls": "right"}
    )
    assert response.status_code == 200
    assert response.json() == "left:right"


def test_tool_name_override():
    app = App("test")

    @app.tool(name="custom_name")
    def my_func() -> str:
        return "hi"

    assert app.tools[0].name == "custom_name"


def test_tool_preserves_original_function():
    app = App("test")

    @app.tool()
    def add(a: int, b: int) -> int:
        return a + b

    # Decorator returns the original function unmodified
    assert add(2, 3) == 5


def test_tool_no_params():
    app = App("test")

    @app.tool()
    def ping() -> str:
        """Ping."""
        return "pong"

    tool = app.tools[0]
    assert tool.parameters == []
    assert tool.description == "Ping."


def test_tool_no_docstring():
    app = App("test")

    @app.tool()
    def mystery() -> str:
        return "?"

    assert app.tools[0].description == ""


def test_tool_async():
    app = App("test")

    @app.tool()
    async def fetch(url: str) -> str:
        """Fetch a URL."""
        return url

    tool = app.tools[0]
    assert tool.is_async
    assert tool.name == "fetch"


def test_tool_complex_types():
    app = App("test")

    @app.tool()
    def process(items: list[str], count: int = 10) -> dict:
        return {"items": items, "count": count}

    tool = app.tools[0]
    assert tool.parameters[0].type_annotation == "list[str]"
    assert tool.parameters[1].type_annotation == "int"


def test_tool_return_type():
    app = App("test")

    @app.tool()
    def add(a: int, b: int) -> int:
        return a + b

    assert app.tools[0].return_type == "int"


def test_multiple_tools():
    app = App("test")

    @app.tool()
    def add(a: int, b: int) -> int:
        return a + b

    @app.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    assert len(app.tools) == 2
    assert app.tools[0].name == "add"
    assert app.tools[1].name == "greet"


def test_repr():
    app = App("my-app")
    assert repr(app) == "App('my-app', tools=0)"

    @app.tool()
    def foo() -> str:
        return ""

    assert repr(app) == "App('my-app', tools=1)"


def test_eject_cli():
    app = App("test")

    @app.tool()
    def greet(name: str) -> str:
        """Say hello."""
        return f"Hello, {name}!"

    code = app.eject("cli")
    assert "import typer" in code
    assert "def greet(" in code


def test_eject_api():
    app = App("test")

    @app.tool()
    def greet(name: str) -> str:
        """Say hello."""
        return f"Hello, {name}!"

    code = app.eject("api")
    assert "from fastapi import FastAPI" in code
    assert "greet" in code


def test_eject_mcp():
    app = App("test")

    @app.tool()
    def greet(name: str) -> str:
        """Say hello."""
        return f"Hello, {name}!"

    code = app.eject("mcp")
    assert "from fastmcp import FastMCP" in code
    assert "def greet(" in code


def test_eject_invalid_target():
    app = App("test")

    @app.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    with pytest.raises(ValueError, match="Unknown target"):
        app.eject("invalid")


def test_serve_no_tools():
    app = App("test")
    with pytest.raises(RuntimeError, match="No tools registered"):
        app.serve(mode="cli")


def test_serve_invalid_mode():
    app = App("test")

    @app.tool()
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    with pytest.raises(ValueError, match="Unknown mode"):
        app.serve(mode="invalid")


def test_function_body_extracted():
    app = App("test")

    @app.tool()
    def add(a: int, b: int) -> int:
        """Add numbers."""
        return a + b

    tool = app.tools[0]
    assert tool.function_body is not None
    assert "return a + b" in tool.function_body


def test_tool_description_override():
    app = App("test")

    @app.tool(description="Custom description")
    def add(a: int, b: int) -> int:
        """Docstring description."""
        return a + b

    assert app._tools[0].info.description == "Custom description"


def test_tool_description_falls_back_to_docstring():
    app = App("test")

    @app.tool()
    def add(a: int, b: int) -> int:
        """Docstring description."""
        return a + b

    assert app._tools[0].info.description == "Docstring description."
