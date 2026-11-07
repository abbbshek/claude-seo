"""Layout and parity checks for the generated OpenCode layer."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENCODE = ROOT / ".opencode"
MANIFEST = json.loads((ROOT / "scripts" / "opencode_manifest.json").read_text(encoding="utf-8"))


def _frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---", text, re.DOTALL)
    assert match, f"{path} has no frontmatter"
    return match.group(1)


def test_core_skill_count_and_ids() -> None:
    dirs = {
        path.name
        for path in (OPENCODE / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }
    canonical = {
        path.name
        for path in (ROOT / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }
    assert dirs == canonical
    assert len(dirs) == 26


def test_agent_count_and_ids() -> None:
    generated = {
        path.stem for path in (OPENCODE / "agents").glob("seo-*.md")
    }
    canonical = {
        path.stem for path in (ROOT / "agents").glob("seo-*.md")
    }
    assert generated == canonical
    assert len(generated) == 19


def test_command_count_and_names() -> None:
    generated = {path.stem for path in (OPENCODE / "commands").glob("seo*.md")}
    expected = {"seo"} | {
        f"seo-{entry['name']}" for entry in MANIFEST["commands"]
    }
    assert generated == expected
    assert len(generated) == 35


def test_agents_are_native_subagents() -> None:
    for path in (OPENCODE / "agents").glob("seo-*.md"):
        frontmatter = _frontmatter(path)
        assert "mode: subagent" in frontmatter, path
        assert re.search(r"(?m)^steps:\s*\d+\s*$", frontmatter), path
        assert "permissions:" in frontmatter, path
        assert not re.search(r"(?m)^(name|model|maxTurns|tools):", frontmatter), path
        assert not re.search(r"(?im)^\s*model:\s*(sonnet|opus|haiku)\s*$", frontmatter), path


def test_skills_have_no_claude_only_invocation_fields() -> None:
    for path in (OPENCODE / "skills").glob("*/SKILL.md"):
        frontmatter = _frontmatter(path)
        assert "user-invocable" not in frontmatter, path
        assert "argument-hint" not in frontmatter, path
        assert re.search(r"(?m)^name:\s*seo", frontmatter), path
        assert re.search(r"(?m)^description:", frontmatter), path


def test_no_claude_plugin_tokens_remain() -> None:
    offenders: list[str] = []
    for path in OPENCODE.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        for token in ("${CLAUDE_PLUGIN_ROOT}", "${CLAUDE_SKILL_DIR}", "scripts/claude-seo"):
            if token in text:
                offenders.append(f"{path.relative_to(ROOT)}: {token}")
    assert not offenders, offenders


def test_schema_templates_are_available_relative_to_skills() -> None:
    assert (OPENCODE / "skills" / "seo" / "schema" / "templates.json").is_file()
    schema_skill = (OPENCODE / "skills" / "seo-schema" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "../seo/schema/templates.json" in schema_skill


def test_launcher_references_resolve() -> None:
    assert (ROOT / "scripts" / "seo").is_file()
    offenders = []
    for path in OPENCODE.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        if "$SEO_ROOT/scripts/seo" in text:
            assert (ROOT / "scripts" / "seo").is_file()
    assert not offenders


def test_router_lists_every_command() -> None:
    router = (OPENCODE / "commands" / "seo.md").read_text(encoding="utf-8")
    for entry in MANIFEST["commands"]:
        assert f"`{entry['name']}`" in router, entry["name"]


def test_commands_use_arguments() -> None:
    for entry in MANIFEST["commands"]:
        path = OPENCODE / "commands" / f"seo-{entry['name']}.md"
        text = path.read_text(encoding="utf-8")
        assert 'description: "' in text
        if entry.get("action"):
            assert "SEO_ROOT/scripts/seo" in text
        else:
            assert "$ARGUMENTS" in text


def test_mcp_capable_agents_can_reach_dataforseo() -> None:
    for name in ("seo-backlinks", "seo-cluster", "seo-geo", "seo-local", "seo-maps", "seo-dataforseo"):
        frontmatter = _frontmatter(OPENCODE / "agents" / f"{name}.md")
        assert 'action: "dataforseo_*"' in frontmatter, name
        assert 'action: "execute"' in frontmatter, name


def test_opencode_config_allows_seo_skills_and_subagents() -> None:
    config = json.loads((OPENCODE / "opencode.json").read_text(encoding="utf-8"))
    assert config["$schema"] == "https://opencode.ai/config.json"
    rules = {(rule["action"], rule["resource"], rule["effect"]) for rule in config["permissions"]}
    assert ("skill", "seo-*", "allow") in rules
    assert ("subagent", "seo-*", "allow") in rules


def test_generated_marker_and_plugin_exist() -> None:
    assert "Do not edit" in (OPENCODE / "GENERATED.md").read_text(encoding="utf-8")
    plugin = OPENCODE / "plugins" / "claude-seo" / "index.ts"
    assert plugin.is_file()
    text = plugin.read_text(encoding="utf-8")
    assert 'id: "claude-seo"' in text
    assert "async setup(ctx)" in text
