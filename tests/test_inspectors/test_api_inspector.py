"""Tests for the API inspector."""

from __future__ import annotations

from fastapi import FastAPI

from intpot.core.inspectors.api import APIInspector


def test_inspect_fastapi_endpoints():
    app = FastAPI()

    @app.post("/add")
    def add(a: int, b: int) -> dict:
        """Add two numbers."""
        return {"result": a + b}

    @app.post("/greet")
    def greet(name: str, greeting: str = "Hello") -> dict:
        """Greet someone."""
        return {"message": f"{greeting}, {name}!"}

    inspector = APIInspector()
    tools = inspector.inspect(app)

    assert len(tools) == 2

    add_tool = next(t for t in tools if t.name == "add")
    assert add_tool.description == "Add two numbers."
    assert len(add_tool.parameters) == 2
    assert add_tool.parameters[0].name == "a"
    assert add_tool.parameters[0].type_annotation == "int"
    assert add_tool.parameters[0].required

    greet_tool = next(t for t in tools if t.name == "greet")
    assert greet_tool.parameters[1].name == "greeting"
    assert greet_tool.parameters[1].default == "Hello"


def test_skips_internal_routes():
    app = FastAPI()

    @app.get("/hello")
    def hello() -> dict:
        return {"msg": "hi"}

    inspector = APIInspector()
    tools = inspector.inspect(app)

    # Should only have "hello", not openapi/swagger/redoc
    names = [t.name for t in tools]
    assert "hello" in names
    assert "openapi" not in names
    assert "swagger_ui_html" not in names


def test_query_and_header_param_sources():
    from fastapi import Header, Query

    from intpot.core.models import ParamSource

    app = FastAPI()

    @app.get("/search")
    def search(
        q: str = Query(..., description="Search term"),
        limit: int = Query(10),
        token: str = Header(...),
    ) -> dict:
        return {"q": q, "limit": limit}

    inspector = APIInspector()
    tools = inspector.inspect(app)

    search_tool = next(t for t in tools if t.name == "search")
    params = {p.name: p for p in search_tool.parameters}

    assert params["q"].param_source == ParamSource.query
    assert params["limit"].param_source == ParamSource.query
    assert params["token"].param_source == ParamSource.header


def test_body_param_source():
    from fastapi import Body

    from intpot.core.models import ParamSource

    app = FastAPI()

    @app.post("/create")
    def create(data: dict = Body(...)) -> dict:
        return {"received": data}

    inspector = APIInspector()
    tools = inspector.inspect(app)

    create_tool = next(t for t in tools if t.name == "create")
    params = {p.name: p for p in create_tool.parameters}

    assert params["data"].param_source == ParamSource.body


def test_path_param_source_explicit():
    from fastapi import Path

    from intpot.core.models import ParamSource

    app = FastAPI()

    @app.get("/items/{item_id}")
    def get_item(item_id: int = Path(...)) -> dict:
        return {"id": item_id}

    inspector = APIInspector()
    tools = inspector.inspect(app)

    get_item_tool = next(t for t in tools if t.name == "get_item")
    params = {p.name: p for p in get_item_tool.parameters}

    assert params["item_id"].param_source == ParamSource.path


def test_path_param_source_implicit():
    from intpot.core.models import ParamSource

    app = FastAPI()

    @app.get("/users/{user_id}")
    def get_user(user_id: int) -> dict:
        return {"id": user_id}

    inspector = APIInspector()
    tools = inspector.inspect(app)

    get_user_tool = next(t for t in tools if t.name == "get_user")
    params = {p.name: p for p in get_user_tool.parameters}

    assert params["user_id"].param_source == ParamSource.path


def test_generator_output_correct_fastapi_types():
    from fastapi import Header, Query

    from intpot.core.generators.api import APIGenerator

    app = FastAPI()

    @app.get("/search")
    def search(
        q: str = Query(...),
        token: str = Header(...),
    ) -> dict:
        return {"q": q}

    inspector = APIInspector()
    tools = inspector.inspect(app)

    generator = APIGenerator()
    output = generator.generate(tools)

    assert "Query" in output
    assert "Header" in output
    assert "q: str = Query(" in output
    assert "token: str = Header(" in output
