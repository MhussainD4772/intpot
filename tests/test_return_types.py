"""Return annotations must describe what the body actually returns.

FastAPI validates the response against the annotation, so an annotation that
overstates what comes back is a 500 on every call rather than a type-checker
complaint. `-> None` and "no annotation at all" are different answers, and
collapsing both onto `str` produced exactly that.
"""

from __future__ import annotations

import inspect
import warnings
from typing import Any

import pytest
from fastapi.testclient import TestClient

from intpot import App
from intpot.core.inspectors._utils import python_return_type_name

warnings.filterwarnings("ignore")


def _eject_and_load(app: App, target: str) -> Any:
    source = app.eject(target)
    namespace: dict[str, Any] = {}
    exec(compile(source, "<generated>", "exec"), namespace)
    return source, namespace


def test_no_annotation_is_unknown_not_str() -> None:
    assert python_return_type_name(inspect.Parameter.empty) == "Any"


def test_an_explicit_none_annotation_is_none() -> None:
    assert python_return_type_name(None) == "None"
    assert python_return_type_name(type(None)) == "None"


def test_a_real_annotation_is_unchanged() -> None:
    assert python_return_type_name(int) == "int"
    assert python_return_type_name(str) == "str"


def _app_with_awkward_returns() -> App:
    app = App("t")

    @app.tool()
    def log_it(msg: str, level: str = "info") -> None:
        """Returns nothing."""
        return None

    @app.tool()
    def untyped(a: int, b: int):
        """No return annotation."""
        return a + b

    return app


def test_the_tool_info_distinguishes_none_from_unknown() -> None:
    types = {t.name: t.return_type for t in _app_with_awkward_returns().tools}

    assert types == {"log_it": "None", "untyped": "Any"}


def test_an_ejected_endpoint_returning_none_does_not_500() -> None:
    """The regression: `-> str` over a body returning None is a 500 on every call."""
    source, namespace = _eject_and_load(_app_with_awkward_returns(), "api")
    client = TestClient(namespace["app"])

    response = client.post("/log_it", json={"msg": "x", "level": "warn"})

    assert response.status_code == 200, response.text
    assert response.json() is None
    assert ") -> None:" in source


def test_an_ejected_endpoint_without_an_annotation_returns_its_value() -> None:
    source, namespace = _eject_and_load(_app_with_awkward_returns(), "api")
    client = TestClient(namespace["app"])

    response = client.post("/untyped", json={"a": 2, "b": 3})

    assert response.status_code == 200, response.text
    assert response.json() == 5
    assert ") -> Any:" in source


def test_any_is_imported_into_the_generated_module() -> None:
    """An annotation nothing imports is a NameError at import time."""
    source, _ = _eject_and_load(_app_with_awkward_returns(), "api")

    assert "from typing import Any" in source


@pytest.mark.parametrize("target", ["cli", "mcp", "api"])
def test_every_target_still_generates_importable_code(target: str) -> None:
    _eject_and_load(_app_with_awkward_returns(), target)
