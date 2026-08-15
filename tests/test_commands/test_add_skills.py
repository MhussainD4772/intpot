"""Tests for the `intpot add skills` command."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from intpot.cli import app
from intpot.skills.content import cli_skill_body, python_skill_body

runner = CliRunner()


def _parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Parse a rule's YAML frontmatter with a real YAML parser."""
    assert text.startswith("---\n")
    header, separator, body = text[4:].partition("\n---\n")
    assert separator, "frontmatter is not terminated"
    parsed = yaml.safe_load(header)
    assert isinstance(parsed, dict)
    return parsed, body


# ---------------------------------------------------------------------------
# Auto-detect tests
# ---------------------------------------------------------------------------


def test_add_skills_auto_detect_claude(tmp_path: Path, monkeypatch):
    """Auto-detect Claude Code when .claude/ exists."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude").mkdir()

    result = runner.invoke(app, ["add", "skills"])
    assert result.exit_code == 0
    assert "claude" in result.output

    assert (tmp_path / ".claude" / "skills" / "intpot-cli" / "SKILL.md").exists()
    assert (tmp_path / ".claude" / "skills" / "intpot-python" / "SKILL.md").exists()

    cli_content = (
        tmp_path / ".claude" / "skills" / "intpot-cli" / "SKILL.md"
    ).read_text()
    assert "intpot" in cli_content
    assert "intpot to cli" in cli_content

    py_content = (
        tmp_path / ".claude" / "skills" / "intpot-python" / "SKILL.md"
    ).read_text()
    assert "intpot.load" in py_content


def test_add_skills_auto_detect_cursor(tmp_path: Path, monkeypatch):
    """Auto-detect Cursor when .cursor/ exists."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".cursor").mkdir()

    result = runner.invoke(app, ["add", "skills"])
    assert result.exit_code == 0
    assert "cursor" in result.output

    cli_path = tmp_path / ".cursor" / "rules" / "intpot-cli.mdc"
    assert cli_path.exists()
    metadata, body = _parse_frontmatter(cli_path.read_text())
    assert metadata["alwaysApply"] is False
    assert "globs" not in metadata
    assert "CLI" in str(metadata["description"])
    assert body.strip().startswith("# intpot CLI")


def test_add_skills_auto_detect_windsurf(tmp_path: Path, monkeypatch):
    """Auto-detect Windsurf when .windsurf/ exists."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".windsurf").mkdir()

    result = runner.invoke(app, ["add", "skills"])
    assert result.exit_code == 0
    assert "windsurf" in result.output
    for name, subject in (("intpot-cli", "CLI"), ("intpot-python", "Python")):
        path = tmp_path / ".windsurf" / "rules" / f"{name}.md"
        metadata, body = _parse_frontmatter(path.read_text())
        assert metadata["trigger"] == "model_decision"
        assert subject in str(metadata["description"])
        assert len(str(metadata["description"])) > 60
        assert body.strip().startswith(f"# intpot {subject}")


def test_add_skills_auto_detect_copilot(tmp_path: Path, monkeypatch):
    """Auto-detect Copilot from its instructions file, not from `.github/`."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "copilot-instructions.md").write_text("# Existing\n")

    result = runner.invoke(app, ["add", "skills"])
    assert result.exit_code == 0
    assert "copilot" in result.output

    instructions = tmp_path / ".github" / "copilot-instructions.md"
    assert instructions.exists()
    content = instructions.read_text()
    assert "intpot" in content
    assert "<!-- intpot:" in content


def test_add_skills_auto_detect_cline(tmp_path: Path, monkeypatch):
    """Auto-detect Cline when .clinerules/ exists."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".clinerules").mkdir()

    result = runner.invoke(app, ["add", "skills"])
    assert result.exit_code == 0
    assert "cline" in result.output
    assert (tmp_path / ".clinerules" / "intpot-cli.md").exists()
    assert (tmp_path / ".clinerules" / "intpot-python.md").exists()


def test_add_skills_codex_requires_an_explicit_request(tmp_path: Path, monkeypatch):
    """AGENTS.md is a cross-tool convention, so it cannot imply Codex.

    It used to, and because the Codex writer appends, any project with an
    AGENTS.md had intpot's skills added to its own documentation.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").write_text("# Existing agents\n")

    auto = runner.invoke(app, ["add", "skills"])
    assert auto.exit_code == 1
    assert (tmp_path / "AGENTS.md").read_text() == "# Existing agents\n"

    explicit = runner.invoke(app, ["add", "skills", "--agent", "codex"])
    assert explicit.exit_code == 0

    content = (tmp_path / "AGENTS.md").read_text()
    assert "# Existing agents" in content  # preserved
    assert "intpot" in content


# ---------------------------------------------------------------------------
# Explicit --agent tests
# ---------------------------------------------------------------------------


def test_add_skills_explicit_agent(tmp_path: Path, monkeypatch):
    """--agent flag creates skills even without marker dirs."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["add", "skills", "--agent", "claude"])
    assert result.exit_code == 0
    assert (tmp_path / ".claude" / "skills" / "intpot-cli" / "SKILL.md").exists()


def test_add_skills_explicit_path(tmp_path: Path):
    """--path flag targets a specific directory."""
    target = tmp_path / "myproject"
    target.mkdir()

    result = runner.invoke(
        app, ["add", "skills", "--agent", "cursor", "--path", str(target)]
    )
    assert result.exit_code == 0
    assert (target / ".cursor" / "rules" / "intpot-cli.mdc").exists()


# ---------------------------------------------------------------------------
# Multi-agent detection
# ---------------------------------------------------------------------------


def test_add_skills_multiple_agents(tmp_path: Path, monkeypatch):
    """Detect and install for multiple agents at once."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".cursor").mkdir()

    result = runner.invoke(app, ["add", "skills"])
    assert result.exit_code == 0
    assert "claude" in result.output
    assert "cursor" in result.output
    assert (tmp_path / ".claude" / "skills" / "intpot-cli" / "SKILL.md").exists()
    assert (tmp_path / ".cursor" / "rules" / "intpot-cli.mdc").exists()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_add_skills_no_agents_detected(tmp_path: Path, monkeypatch):
    """Exit with error when no agents detected and no --agent given."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["add", "skills"])
    assert result.exit_code == 1
    assert "No AI coding agents detected" in result.output


def test_add_skills_idempotent_copilot(tmp_path: Path, monkeypatch):
    """Running twice doesn't duplicate Copilot instructions."""
    monkeypatch.chdir(tmp_path)

    result1 = runner.invoke(app, ["add", "skills", "--agent", "copilot"])
    assert result1.exit_code == 0

    result2 = runner.invoke(app, ["add", "skills", "--agent", "copilot"])
    assert result2.exit_code == 0
    assert "already installed" in result2.output

    content = (tmp_path / ".github" / "copilot-instructions.md").read_text()
    assert content.count("<!-- intpot:managed:start -->") == 1
    assert content.count("<!-- intpot:managed:end -->") == 1


def test_add_skills_idempotent_codex(tmp_path: Path, monkeypatch):
    """Running twice doesn't duplicate Codex AGENTS.md content."""
    monkeypatch.chdir(tmp_path)

    result1 = runner.invoke(app, ["add", "skills", "--agent", "codex"])
    assert result1.exit_code == 0

    result2 = runner.invoke(app, ["add", "skills", "--agent", "codex"])
    assert result2.exit_code == 0
    assert "already installed" in result2.output

    content = (tmp_path / "AGENTS.md").read_text()
    assert content.count("# intpot CLI") == 1
    assert content.count("<!-- intpot:managed:start -->") == 1
    assert content.count("<!-- intpot:managed:end -->") == 1


@pytest.mark.parametrize(
    ("agent", "relative_path"),
    [
        ("copilot", ".github/copilot-instructions.md"),
        ("codex", "AGENTS.md"),
    ],
)
def test_managed_instructions_are_updated_and_preserve_user_content(
    tmp_path: Path, monkeypatch, agent: str, relative_path: str
):
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["add", "skills", "--agent", agent])
    path = tmp_path / relative_path
    installed = path.read_text()
    stale = installed.replace("**intpot** does two things", "STALE CONTENT", 1)
    path.write_text("USER BEFORE\n" + stale + "USER AFTER\n")

    result = runner.invoke(app, ["add", "skills", "--agent", agent])

    assert result.exit_code == 0
    updated = path.read_text()
    assert "STALE CONTENT" not in updated
    assert updated.startswith("USER BEFORE\n")
    assert updated.endswith("USER AFTER\n")
    assert updated.count("<!-- intpot:managed:start -->") == 1
    assert updated.count("<!-- intpot:managed:end -->") == 1


@pytest.mark.parametrize(
    ("agent", "relative_path", "legacy_marker"),
    [
        ("copilot", ".github/copilot-instructions.md", "<!-- intpot: intpot CLI -->"),
        ("codex", "AGENTS.md", "# intpot CLI"),
    ],
)
def test_partial_legacy_installation_is_repaired(
    tmp_path: Path,
    monkeypatch,
    agent: str,
    relative_path: str,
    legacy_marker: str,
):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"USER BEFORE\n{legacy_marker}\n")

    result = runner.invoke(app, ["add", "skills", "--agent", agent])

    assert result.exit_code == 0
    repaired = path.read_text()
    assert repaired.startswith("USER BEFORE\n")
    assert repaired.count("# intpot CLI") == 1
    assert "# intpot Python API" in repaired
    assert repaired.count("<!-- intpot:managed:start -->") == 1
    assert repaired.count("<!-- intpot:managed:end -->") == 1


@pytest.mark.parametrize(
    ("agent", "relative_path", "legacy_content"),
    [
        (
            "copilot",
            ".github/copilot-instructions.md",
            "\n<!-- intpot: intpot CLI -->\n\n"
            + cli_skill_body()
            + "\n\n<!-- intpot: intpot Python API -->\n\n"
            + python_skill_body()
            + "\n",
        ),
        ("codex", "AGENTS.md", cli_skill_body() + "\n" + python_skill_body()),
    ],
)
def test_complete_legacy_installation_is_migrated_without_deleting_following_section(
    tmp_path: Path,
    monkeypatch,
    agent: str,
    relative_path: str,
    legacy_content: str,
):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# USER BEFORE\n" + legacy_content + "\n# USER AFTER\nkeep me\n")

    result = runner.invoke(app, ["add", "skills", "--agent", agent])

    assert result.exit_code == 0
    migrated = path.read_text()
    assert migrated.startswith("# USER BEFORE\n")
    assert migrated.endswith("# USER AFTER\nkeep me\n")
    assert "<!-- intpot:managed:end -->\n# USER AFTER" in migrated
    assert migrated.count("<!-- intpot:managed:start -->") == 1
    assert migrated.count("<!-- intpot:managed:end -->") == 1


@pytest.mark.parametrize(
    ("agent", "relative_path", "legacy_marker"),
    [
        ("copilot", ".github/copilot-instructions.md", "<!-- intpot: intpot CLI -->"),
        ("codex", "AGENTS.md", "# intpot CLI"),
    ],
)
def test_ambiguous_legacy_installation_preserves_trailing_user_prose(
    tmp_path: Path,
    monkeypatch,
    agent: str,
    relative_path: str,
    legacy_marker: str,
):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    original = (
        f"# USER BEFORE\n{legacy_marker}\nold cli\n"
        "# intpot Python API\nold python\nUSER PROSE AFTER\nkeep me\n"
    )
    path.write_text(original)

    result = runner.invoke(app, ["add", "skills", "--agent", agent])

    assert result.exit_code == 0
    repaired = path.read_text()
    assert original in repaired
    assert "USER PROSE AFTER\nkeep me" in repaired
    assert repaired.count("<!-- intpot:managed:end -->") == 1

    rerun = runner.invoke(app, ["add", "skills", "--agent", agent])
    assert rerun.exit_code == 0
    assert path.read_text().count("<!-- intpot:managed:end -->") == 1


@pytest.mark.parametrize(
    ("agent", "relative_path"),
    [
        ("copilot", ".github/copilot-instructions.md"),
        ("codex", "AGENTS.md"),
    ],
)
def test_unterminated_managed_block_preserves_all_existing_content(
    tmp_path: Path, monkeypatch, agent: str, relative_path: str
):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    original = (
        "# USER BEFORE\n<!-- intpot:managed:start -->\n"
        "incomplete intpot content\nUSER PROSE AFTER\nkeep me\n"
    )
    path.write_text(original)

    result = runner.invoke(app, ["add", "skills", "--agent", agent])

    assert result.exit_code == 0
    repaired = path.read_text()
    assert original in repaired
    assert "USER PROSE AFTER\nkeep me" in repaired
    assert repaired.count("<!-- intpot:managed:end -->") == 1

    rerun = runner.invoke(app, ["add", "skills", "--agent", agent])
    assert rerun.exit_code == 0
    assert path.read_text().count("<!-- intpot:managed:end -->") == 1


def test_codex_warns_when_agents_file_exceeds_default_32_kib(
    tmp_path: Path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "AGENTS.md").write_text("x" * (32 * 1024))

    result = runner.invoke(app, ["add", "skills", "--agent", "codex"])

    assert result.exit_code == 0
    assert "32 KiB" in result.output
    assert "Codex" in result.output


def test_add_skills_invalid_path(tmp_path: Path):
    """Error when --path doesn't exist or is not a directory."""
    result = runner.invoke(
        app, ["add", "skills", "--agent", "claude", "--path", "/nonexistent/path"]
    )
    assert result.exit_code == 1
    assert "not a directory" in result.output


def test_add_skills_claude_content_quality(tmp_path: Path, monkeypatch):
    """Verify Claude skill content has all essential info."""
    monkeypatch.chdir(tmp_path)

    runner.invoke(app, ["add", "skills", "--agent", "claude"])

    cli_content = (
        tmp_path / ".claude" / "skills" / "intpot-cli" / "SKILL.md"
    ).read_text()
    # Must have the key commands
    assert "intpot init" in cli_content
    assert "intpot to cli" in cli_content
    assert "intpot to mcp" in cli_content
    assert "intpot to api" in cli_content
    assert "--output" in cli_content
    assert "--dry-run" in cli_content

    py_content = (
        tmp_path / ".claude" / "skills" / "intpot-python" / "SKILL.md"
    ).read_text()
    assert "intpot.load" in py_content
    assert "IntpotApp" in py_content
    assert ".to_cli()" in py_content
    assert ".to_mcp()" in py_content
    assert ".to_api()" in py_content
    assert ".write(" in py_content
    assert "inspect_app" in py_content


def test_claude_skills_use_the_layout_claude_code_discovers(
    tmp_path: Path, monkeypatch
):
    """A flat .md file in .claude/skills/ is never loaded.

    Claude Code looks for a directory per skill containing SKILL.md, and reads
    the YAML frontmatter to find it. The installer used to write
    `.claude/skills/intpot-cli.md` with no frontmatter, so the whole feature was
    inert for Claude Code.
    """
    monkeypatch.chdir(tmp_path)

    runner.invoke(app, ["add", "skills", "--agent", "claude"])

    skills = tmp_path / ".claude" / "skills"
    assert (skills / "intpot-cli" / "SKILL.md").is_file()
    assert (skills / "intpot-python" / "SKILL.md").is_file()
    assert list(skills.glob("*.md")) == [], "flat .md files are not discovered"


def test_claude_skills_carry_discoverable_frontmatter(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    runner.invoke(app, ["add", "skills", "--agent", "claude"])

    for name in ("intpot-cli", "intpot-python"):
        text = (tmp_path / ".claude" / "skills" / name / "SKILL.md").read_text()
        metadata, body = _parse_frontmatter(text)
        assert metadata["name"] == name
        # The description is what the model reads to decide relevance, so it has
        # to say what the skill is for, not just name it.
        description = str(metadata["description"])
        assert len(description) > 60, f"{name} description is too thin to match on"
        assert "intpot" in description
        assert body.strip().startswith("# intpot")


@pytest.mark.parametrize(
    "agent", ["claude", "cursor", "windsurf", "copilot", "cline", "codex"]
)
def test_every_agent_format_contains_both_complete_skills(
    tmp_path: Path, monkeypatch, agent: str
):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["add", "skills", "--agent", agent])
    assert result.exit_code == 0

    generated = "\n".join(
        path.read_text() for path in tmp_path.rglob("*") if path.is_file()
    )
    for command in (
        "intpot init",
        "intpot inspect",
        "intpot serve",
        "intpot eject",
        "intpot to cli",
        "intpot to mcp",
        "intpot to api",
    ):
        assert command in generated, f"{agent} output omits {command}"
    assert "intpot.load" in generated


# ---------------------------------------------------------------------------
# Detection must not fire on ordinary repositories
# ---------------------------------------------------------------------------


def test_an_ordinary_github_repo_is_not_mistaken_for_copilot_and_codex(
    tmp_path: Path, monkeypatch
):
    """A CI workflow and an AGENTS.md are not evidence of any agent.

    `.github/` was the Copilot marker and `AGENTS.md` the Codex one, so a repo
    using no AI tooling at all matched both — and since both writers append,
    248 lines were added to the project's own AGENTS.md.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci\n")
    original = "# AGENTS.md\n\nMy project guidance.\n"
    (tmp_path / "AGENTS.md").write_text(original)

    result = runner.invoke(app, ["add", "skills"])

    assert result.exit_code == 1
    assert "No AI coding agents detected" in result.output
    assert (tmp_path / "AGENTS.md").read_text() == original
    assert not (tmp_path / ".github" / "copilot-instructions.md").exists()


def test_a_github_directory_alone_does_not_imply_copilot(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".github").mkdir()

    result = runner.invoke(app, ["add", "skills"])

    assert result.exit_code == 1
    assert not (tmp_path / ".github" / "copilot-instructions.md").exists()


def test_every_auto_detected_marker_is_agent_specific(tmp_path: Path, monkeypatch):
    """Each marker must appear only when that agent is configured.

    Creating one marker must select exactly one agent — no marker may be a path
    that projects create for unrelated reasons.
    """
    from intpot.commands.add_skills import _AGENT_MARKERS, _detect_agents

    for agent, marker in _AGENT_MARKERS.items():
        root = tmp_path / agent.value
        target = root / marker
        target.parent.mkdir(parents=True, exist_ok=True)
        if Path(marker).suffix:
            target.write_text("# marker\n")
        else:
            target.mkdir(exist_ok=True)

        assert _detect_agents(root) == [agent], f"{marker} selected the wrong agents"


def test_explicitly_requested_agents_still_bypass_detection(
    tmp_path: Path, monkeypatch
):
    """--agent is the escape hatch for anything detection misses."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["add", "skills", "--agent", "copilot"])

    assert result.exit_code == 0
    assert (tmp_path / ".github" / "copilot-instructions.md").exists()
