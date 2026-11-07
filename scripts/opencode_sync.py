#!/usr/bin/env python3
"""Generate the native OpenCode layer from the canonical Claude SEO sources.

The canonical ``skills/``, ``agents/``, and ``docs/COMMANDS.md`` files stay
Claude-compatible. This script writes the OpenCode-native copies under
``.opencode/`` (or an installer-supplied directory) with portable runtime
paths and OpenCode frontmatter.

Usage::

    python scripts/opencode_sync.py
    python scripts/opencode_sync.py --check
    python scripts/opencode_sync.py --dest ~/.config/opencode
    python scripts/opencode_sync.py --extension dataforseo --dest ~/.config/opencode
"""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "scripts" / "opencode_manifest.json"
DEFAULT_DEST = ROOT / ".opencode"

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
PLUGIN_SKILLS_RE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/skills/([A-Za-z0-9_./{}~-]+)")
SKILL_REFERENCES_RE = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/references/([A-Za-z0-9_./{}-]+)")
SKILL_SCRIPTS_RE = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/scripts/([A-Za-z0-9_./{}-]+)")
BARE_SCHEMA_RE = re.compile(r"(?<![A-Za-z0-9_./-])schema/templates\.json")

RUNTIME_NOTE = """**Runtime:** Run bundled Python tools through
`"$SEO_ROOT/scripts/seo" run <script.py>`. The OpenCode plugin sets
`SEO_ROOT` for every shell command and points it at the managed runtime.
Never invoke bundled scripts with a bare Python interpreter."""

OPENCODE_RUNTIME_NOTE = (
    "> **OpenCode runtime:** use `\"$SEO_ROOT/scripts/seo\" run ...`. If it "
    "reports that setup is required, run `/seo setup` and retry. Do not "
    "substitute a bare `python3` invocation.\n\n"
)

EXTENSION_NOTE = (
    "\n> **OpenCode note:** MCP tools are exposed as `<server>_<tool>`; in Code "
    "Mode call `tools.<server>.<tool>(...)`. Credentials are exported by the "
    "claude-seo plugin from `~/.config/opencode/claude-seo.env.json`.\n"
)


def _rel(target: Path, start: Path) -> str:
    return os.path.relpath(target, start=start).replace(os.sep, "/")


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _strip_inline_comment(value: str) -> str:
    return value.split("#", 1)[0].strip()


MCP_DATA_AGENTS = {
    "seo-backlinks",
    "seo-cluster",
    "seo-geo",
    "seo-local",
    "seo-maps",
}


def _permissions_for_tools(
    tools: list[str], agent_id: str | None = None
) -> list[tuple[str, str, str]]:
    rules: list[tuple[str, str, str]] = [("*", "*", "deny")]
    wanted: list[tuple[str, str, str]] = []

    def add(action: str, resource: str = "*") -> None:
        rule = (action, resource, "allow")
        if rule not in wanted:
            wanted.append(rule)

    if "Read" in tools:
        add("read")
    if "Bash" in tools:
        add("shell")
    if "Write" in tools:
        add("edit")
    if "Glob" in tools:
        add("glob")
    if "Grep" in tools:
        add("grep")
    if "WebFetch" in tools:
        add("webfetch")
    if "WebSearch" in tools:
        add("websearch")
    if any(tool.startswith("mcp__dataforseo") for tool in tools) or (
        agent_id in MCP_DATA_AGENTS
    ):
        add("dataforseo_*")
        add("execute")
    add("skill", "seo-*")
    add("external_directory")

    rules.extend(wanted)
    if "Read" in tools:
        rules.append(("read", "*.env", "ask"))
        rules.append(("read", "*.env.*", "ask"))
    return rules


def _yaml_permissions(rules: list[tuple[str, str, str]]) -> str:
    lines = ["permissions:"]
    for action, resource, effect in rules:
        lines.append(f'  - action: "{action}"')
        lines.append(f'    resource: "{resource}"')
        lines.append(f'    effect: "{effect}"')
    return "\n".join(lines)


def rewrite_markdown(
    text: str,
    *,
    source: Path,
    destination: Path,
    dest_root: Path,
    skill_id: str | None,
    extension: str | None = None,
) -> str:
    """Rewrite Claude path tokens to OpenCode-native portable paths."""

    # Launcher. Replace the quoted form first so the quotes survive.
    text = text.replace(
        '"${CLAUDE_PLUGIN_ROOT}/scripts/claude-seo"',
        '"$SEO_ROOT/scripts/seo"',
    )
    text = text.replace(
        "${CLAUDE_PLUGIN_ROOT}/scripts/claude-seo",
        "$SEO_ROOT/scripts/seo",
    )

    # Cross-skill reference paths become paths relative to the generated file.
    def plugin_skill(match: re.Match[str]) -> str:
        target = dest_root / "skills" / match.group(1)
        return _rel(target, destination.parent)

    text = PLUGIN_SKILLS_RE.sub(plugin_skill, text)

    # A skill's own references are relative; its scripts are under the skills root.
    def skill_reference(match: re.Match[str]) -> str:
        if not skill_id:
            return match.group(0)
        target = dest_root / "skills" / skill_id / "references" / match.group(1)
        return _rel(target, destination.parent)

    text = SKILL_REFERENCES_RE.sub(skill_reference, text)

    def skill_script(match: re.Match[str]) -> str:
        if not skill_id:
            return match.group(0)
        return f"$SEO_SKILLS_DIR/{skill_id}/scripts/{match.group(1)}"

    text = SKILL_SCRIPTS_RE.sub(skill_script, text)
    if skill_id:
        text = text.replace("${CLAUDE_SKILL_DIR}", f"$SEO_SKILLS_DIR/{skill_id}")

    # Bare schema template references become relative paths.
    def schema_template(_: re.Match[str]) -> str:
        target = dest_root / "skills" / "seo" / "schema" / "templates.json"
        return _rel(target, destination.parent)

    text = BARE_SCHEMA_RE.sub(schema_template, text)

    # Remaining plugin-root tokens are shell environment references.
    text = text.replace("${CLAUDE_PLUGIN_ROOT}", "$SEO_ROOT")

    # Claude-specific installation paths.
    text = text.replace("~/.claude/skills/", "~/.config/opencode/skills/")
    text = text.replace("~/.claude/agents/", "~/.config/opencode/agents/")
    text = text.replace("~/.claude/settings.json", "~/.config/opencode/claude-seo.env.json")
    text = text.replace("~/.claude.json", "~/.config/opencode/claude-seo.mcp.json")
    text = text.replace(
        "~/.claude/plugins/cache/*/claude-blog/*/skills/blog/SKILL.md",
        ".opencode/skills/blog/SKILL.md",
    )
    text = text.replace("(manual install)", "(global OpenCode install)")
    text = text.replace("(plugin install)", "(project OpenCode install)")

    # Native OpenCode terminology.
    text = text.replace("maxTurns", "steps")

    # Harness references, without touching Anthropic product names.
    for old, new in (
        ("the standalone AI image generation skill for Claude Code", "the standalone AI image generation skill for OpenCode"),
        ("Session context resets between Claude Code conversations", "Session context resets between OpenCode conversations"),
        ("Example usage in Claude Code", "Example usage in OpenCode"),
        ("Restart Claude Code", "Reload OpenCode"),
        ("Start Claude Code", "Start OpenCode"),
        ("start Claude Code", "start OpenCode"),
        ("Claude Code session", "OpenCode session"),
        ("Claude Code conversations", "OpenCode conversations"),
    ):
        text = text.replace(old, new)

    if skill_id == "seo" and source.name == "SKILL.md":
        text = text.replace(
            "**Invocation:** `/seo $1 $2` where `$1` is the command and `$2` is the URL or argument.",
            "**Invocation:** `/seo <command> <argument>` or `/seo-<command> <argument>`.",
        )
        text = re.sub(
            r"\*\*Runtime:\*\*.*?(?=\n\n)",
            RUNTIME_NOTE,
            text,
            count=1,
            flags=re.DOTALL,
        )

    if extension:
        match = FRONTMATTER_RE.match(text)
        if match:
            text = text[: match.end()] + EXTENSION_NOTE + text[match.end() :]
    return text


def _strip_skill_frontmatter(text: str) -> str:
    """Remove Claude-only invocation fields from a SKILL.md frontmatter block."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return text
    kept: list[str] = []
    for line in match.group(1).splitlines():
        if re.match(r"^(user-invocable|argument-hint):", line):
            continue
        kept.append(line)
    return f"---\n{chr(10).join(kept)}\n---\n{text[match.end():]}"


def _copy_skill(source: Path, destination: Path, dest_root: Path, extension: str | None) -> None:
    skill_id = source.name
    destination.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".md":
            text = path.read_text(encoding="utf-8")
            if path.name == "SKILL.md":
                text = _strip_skill_frontmatter(text)
            rewritten = rewrite_markdown(
                text,
                source=path,
                destination=target,
                dest_root=dest_root,
                skill_id=skill_id,
                extension=extension,
            )
            if path.name == "SKILL.md":
                match = FRONTMATTER_RE.match(rewritten)
                if match:
                    rewritten = (
                        rewritten[: match.end()]
                        + OPENCODE_RUNTIME_NOTE
                        + rewritten[match.end() :]
                    )
            target.write_text(rewritten, encoding="utf-8")
        else:
            shutil.copy2(path, target)


def _process_agent(source: Path, destination: Path, dest_root: Path) -> None:
    text = source.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"{source}: missing YAML frontmatter")
    frontmatter = match.group(1)
    body = text[match.end() :]

    max_turns_match = re.search(r"(?m)^maxTurns:\s*(\d+)\s*$", frontmatter)
    max_turns = int(max_turns_match.group(1)) if max_turns_match else 30
    tools_match = re.search(r"(?m)^tools:\s*(.+)$", frontmatter)
    tools = []
    if tools_match:
        tools = [
            item.strip()
            for item in _strip_inline_comment(tools_match.group(1)).split(",")
            if item.strip()
        ]

    kept_lines: list[str] = []
    for line in frontmatter.splitlines():
        if re.match(r"^(name|model|maxTurns|tools):", line):
            continue
        kept_lines.append(line)

    permissions = _yaml_permissions(_permissions_for_tools(tools, source.stem))
    new_frontmatter = "\n".join(
        [
            *kept_lines,
            "mode: subagent",
            f"steps: {max_turns}",
            permissions,
        ]
    )
    rewritten_body = rewrite_markdown(
        body,
        source=source,
        destination=destination,
        dest_root=dest_root,
        skill_id=None,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        f"---\n{new_frontmatter}\n---\n{OPENCODE_RUNTIME_NOTE}{rewritten_body}",
        encoding="utf-8",
    )


def generate_core(
    dest: Path,
    manifest: dict,
    preserve_extensions: set[str] | None = None,
    write_config: bool = True,
) -> None:
    dest = dest.resolve()
    skills_root = dest / "skills"
    agents_root = dest / "agents"
    commands_root = dest / "commands"
    skills_root.mkdir(parents=True, exist_ok=True)
    agents_root.mkdir(parents=True, exist_ok=True)
    commands_root.mkdir(parents=True, exist_ok=True)

    preserved_skills: set[str] = set()
    preserved_agents: set[str] = set()
    for extension in preserve_extensions or set():
        info = manifest.get("extensions", {}).get(extension, {})
        if info.get("skill"):
            preserved_skills.add(info["skill"])
        if info.get("agent"):
            preserved_agents.add(info["agent"])

    for source in sorted((ROOT / "skills").iterdir()):
        if source.is_dir() and (source / "SKILL.md").is_file():
            if source.name in preserved_skills and (
                skills_root / source.name / "SKILL.md"
            ).is_file():
                continue
            _copy_skill(source, skills_root / source.name, dest, extension=None)

    # Schema templates are referenced relatively from generated skills.
    schema_target = skills_root / "seo" / "schema"
    shutil.copytree(ROOT / "schema", schema_target, dirs_exist_ok=True)

    for source in sorted((ROOT / "agents").glob("seo-*.md")):
        if source.stem in preserved_agents and (
            agents_root / source.name
        ).is_file():
            continue
        _process_agent(source, agents_root / source.name, dest)

    generate_commands(commands_root, dest, manifest)
    if write_config:
        write_opencode_config(dest, manifest)
    write_generated_readme(dest)


def generate_extension(dest: Path, extension: str, manifest: dict) -> None:
    dest = dest.resolve()
    extension_root = ROOT / "extensions" / extension
    if not extension_root.is_dir():
        raise ValueError(f"unknown extension: {extension}")

    skills_root = dest / "skills"
    agents_root = dest / "agents"
    skill_dirs = [
        path
        for path in sorted(extension_root.glob("skills/*"))
        if path.is_dir() and (path / "SKILL.md").is_file()
    ]
    for source in skill_dirs:
        target = skills_root / source.name
        _copy_skill(source, target, dest, extension=extension)
        references = extension_root / "references"
        if references.is_dir():
            shutil.copytree(references, target / "references", dirs_exist_ok=True)
            for path in sorted((target / "references").glob("*.md")):
                text = path.read_text(encoding="utf-8")
                path.write_text(
                    rewrite_markdown(
                        text,
                        source=path,
                        destination=path,
                        dest_root=dest,
                        skill_id=source.name,
                        extension=extension,
                    ),
                    encoding="utf-8",
                )
        scripts = extension_root / "scripts"
        if scripts.is_dir():
            shutil.copytree(scripts, target / "scripts", dirs_exist_ok=True)

    for source in sorted(extension_root.glob("agents/*.md")):
        _process_agent(source, agents_root / source.name, dest)

    # Core generation already writes opencode.json and GENERATED.md.


def _command_body(entry: dict) -> str:
    if entry.get("action") == "setup":
        return (
            'Run `"$SEO_ROOT/scripts/seo" setup` with a 15-minute shell timeout.\n'
            "Report core runtime and Chromium status separately. Do not fall back\n"
            "to global or user package installation."
        )
    if entry.get("action") == "doctor":
        return (
            'Run `"$SEO_ROOT/scripts/seo" doctor --json` and summarize readiness,\n'
            "Python version, Chromium status, and any reasons setup is required."
        )
    skill = entry["skill"]
    extension = entry.get("extension")
    lines = [
        f"Use the `skill` tool to load the `{skill}` skill, then follow its",
        "instructions exactly for:",
        "",
        "$ARGUMENTS",
        "",
    ]
    if extension:
        lines.extend(
            [
                f"If the `{skill}` skill is not available, explain that the optional",
                f"`{extension}` extension must be installed first:",
                f'`python3 "$SEO_ROOT/scripts/opencode_extensions.py" install {extension}`.',
            ]
        )
    else:
        lines.extend(
            [
                f"If the `{skill}` skill is not available, tell the user to run",
                "`python3 scripts/opencode_sync.py` from the repository and reload OpenCode.",
            ]
        )
    return "\n".join(lines)


def _router_body(manifest: dict) -> str:
    rows = []
    for entry in manifest["commands"]:
        if entry.get("action") == "setup":
            action = 'run `"$SEO_ROOT/scripts/seo" setup`'
        elif entry.get("action") == "doctor":
            action = 'run `"$SEO_ROOT/scripts/seo" doctor --json`'
        else:
            action = f'load the `{entry["skill"]}` skill'
        rows.append(f"| `{entry['name']}` | {action} |")
    table = "\n".join(rows)
    return f"""The user invoked `/seo` with:

$ARGUMENTS

If the argument list is empty, load the `seo` skill with the `skill` tool and
show its Quick Reference.

Otherwise parse the first token as the subcommand and the remainder as its
argument. Route it with this table:

| Subcommand | Action |
|---|---|
{table}

For a skill route, call the `skill` tool with the mapped skill ID, then follow
that skill exactly using the remainder as the user input. Do not answer from
memory. For `setup` and `doctor`, run the command shown with a 15-minute shell
timeout when setup is involved.

If the subcommand is unknown, load the `seo` skill and explain the available
commands. If a mapped skill is missing, tell the user which optional extension
to install."""


def generate_commands(commands_root: Path, dest: Path, manifest: dict) -> None:
    commands_root.mkdir(parents=True, exist_ok=True)
    (commands_root / "seo.md").write_text(
        "---\n"
        'description: "Universal SEO analysis hub"\n'
        "---\n\n"
        f"{_router_body(manifest)}\n",
        encoding="utf-8",
    )
    for entry in manifest["commands"]:
        path = commands_root / f"seo-{entry['name']}.md"
        path.write_text(
            "---\n"
            f"description: {json.dumps(entry['description'])}\n"
            "---\n\n"
            f"{_command_body(entry)}\n",
            encoding="utf-8",
        )


def write_opencode_config(dest: Path, manifest: dict) -> None:
    config = {
        "$schema": "https://opencode.ai/config.json",
        "permissions": [
            {"action": "skill", "resource": "seo-*", "effect": "allow"},
            {"action": "subagent", "resource": "seo-*", "effect": "allow"},
        ],
    }
    (dest / "opencode.json").write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
    )


def write_generated_readme(dest: Path) -> None:
    (dest / "GENERATED.md").write_text(
        "# Generated OpenCode layer\n\n"
        "Do not edit these files directly. Edit the canonical `skills/`,\n"
        "`agents/`, or `docs/COMMANDS.md` sources, then run:\n\n"
        "```bash\n"
        "python3 scripts/opencode_sync.py\n"
        "```\n\n"
        "The plugin in `plugins/claude-seo/` is hand-written and is not\n"
        "regenerated by this script.\n",
        encoding="utf-8",
    )


def _compare_tree(expected: Path, actual: Path, relative: str) -> list[str]:
    expected_root = expected / relative
    actual_root = actual / relative
    if not expected_root.exists():
        return []
    if not actual_root.exists():
        return [f"missing: {relative}"]
    differences: list[str] = []
    expected_files = {
        path.relative_to(expected_root).as_posix()
        for path in expected_root.rglob("*")
        if path.is_file()
    }
    actual_files = {
        path.relative_to(actual_root).as_posix()
        for path in actual_root.rglob("*")
        if path.is_file()
    }
    for name in sorted(expected_files - actual_files):
        differences.append(f"missing: {relative}/{name}")
    for name in sorted(actual_files - expected_files):
        differences.append(f"unexpected: {relative}/{name}")
    for name in sorted(expected_files & actual_files):
        if not filecmp.cmp(expected_root / name, actual_root / name, shallow=False):
            differences.append(f"changed: {relative}/{name}")
    return differences


def check(dest: Path, manifest: dict) -> int:
    dest = dest.resolve()
    if not dest.exists():
        print(f"OpenCode layer is missing: {dest}", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="claude-seo-opencode-") as tmp:
        expected = Path(tmp)
        generate_core(expected, manifest)
        differences: list[str] = []
        for relative in ("skills", "agents", "commands", "opencode.json", "GENERATED.md"):
            differences.extend(_compare_tree(expected, dest, relative))
        if differences:
            print("OpenCode layer is out of date:", file=sys.stderr)
            for difference in differences:
                print(f"  {difference}", file=sys.stderr)
            print("Run: python3 scripts/opencode_sync.py", file=sys.stderr)
            return 1
    print("OpenCode layer is up to date.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the OpenCode-native layer from the canonical sources."
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_DEST,
        help="destination directory (default: .opencode)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that the destination matches the canonical sources",
    )
    parser.add_argument(
        "--extension",
        help="also generate one optional extension skill and agent",
    )
    parser.add_argument(
        "--preserve-extension",
        action="append",
        default=[],
        help="keep an installed extension's generated skill and agent",
    )
    parser.add_argument(
        "--no-config",
        action="store_true",
        help="generate definitions without writing opencode.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = load_manifest()
    dest = args.dest
    if args.check:
        return check(dest, manifest)
    generate_core(
        dest,
        manifest,
        set(args.preserve_extension),
        write_config=not args.no_config,
    )
    if args.extension:
        generate_extension(dest, args.extension, manifest)
    print(f"Generated OpenCode layer in {dest.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
