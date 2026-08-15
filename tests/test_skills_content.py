"""The skills shipped by `intpot add skills` must describe the current API.

These files land in other people's projects and are read by their coding agents,
so a stale one actively teaches the wrong thing. They sat at the v0.3.0 API for
five months without anything noticing.
"""

from __future__ import annotations

import dataclasses
import re

from intpot.core.models import ParameterInfo, ToolInfo
from intpot.skills.content import cli_skill_body, python_skill_body


def _all_skill_text() -> str:
    return cli_skill_body() + "\n" + python_skill_body()


def test_skills_cover_the_runtime_api():
    """The App runtime is the headline feature — it must not be missing again."""
    text = _all_skill_text()

    for symbol in ("intpot.App", "@app.tool", "app.serve", "eject"):
        assert symbol in text, f"skills never mention {symbol}"


def test_skills_cover_the_conversion_api():
    text = _all_skill_text()

    for symbol in ("intpot.load", "to_cli", "to_mcp", "to_api", "intpot to cli"):
        assert symbol in text, f"skills never mention {symbol}"


def test_skills_cover_every_cli_command():
    text = _all_skill_text()

    for command in ("intpot init", "intpot inspect", "intpot serve", "intpot eject"):
        assert command in text, f"skills never mention `{command}`"

    for target in ("cli", "mcp", "api"):
        assert f"intpot init my-project --type {target}" in text
        assert f"intpot to {target}" in text


def test_skills_explain_dry_run_does_not_sandbox_source_imports():
    text = _all_skill_text()

    assert "only prevents generated output files from being written" in text
    assert "module-level code still runs" in text
    assert "Use `--dry-run` on unfamiliar code" not in text


def test_skills_require_generated_code_to_be_executed_not_just_read():
    text = _all_skill_text()

    for check in ("compile", "import", "invoke"):
        assert check in text.lower()
    assert "successful generation does not prove" in text.lower()


def test_skills_state_current_conversion_limits_without_overpromising():
    text = _all_skill_text()

    for limitation in ("transitive dependencies", "Depends()", "nested Typer"):
        assert limitation in text
    assert "unsupported" in text.lower()


def test_skills_explain_when_framework_extras_are_actually_needed():
    text = " ".join(_all_skill_text().lower().split())

    assert "emitting source text alone does not require" in text
    assert "inspect or load a source" in text


def test_skills_only_reference_real_parameter_fields():
    """Catches the reverse failure: documenting an attribute that never existed.

    The old skill printed `param.annotation`, which is spelled
    `type_annotation` — anyone following it got an AttributeError.
    """
    valid = {f.name for f in dataclasses.fields(ParameterInfo)} | {"required"}

    referenced = set(re.findall(r"\bparam\.(\w+)", _all_skill_text()))

    assert referenced, "expected the skills to show ParameterInfo usage"
    assert referenced <= valid, f"not real ParameterInfo fields: {referenced - valid}"


def test_skills_only_reference_real_tool_fields():
    valid = {f.name for f in dataclasses.fields(ToolInfo)}

    referenced = set(re.findall(r"\btool\.(\w+)", _all_skill_text()))

    assert referenced, "expected the skills to show ToolInfo usage"
    assert referenced <= valid, f"not real ToolInfo fields: {referenced - valid}"


def test_skills_do_not_promise_the_old_network_default():
    """serve --api binds loopback since 0.5.0."""
    text = _all_skill_text()

    assert "127.0.0.1" in text
    # 0.0.0.0 may only appear as the documented opt-in, never as the default.
    for line in text.splitlines():
        if "0.0.0.0" in line:
            assert re.search(r"opt|expose|network|host=", line), (
                f"0.0.0.0 mentioned without framing it as opt-in: {line!r}"
            )
