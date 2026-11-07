"""Static and syntax checks for the native OpenCode plugin."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / ".opencode" / "plugins" / "claude-seo" / "index.ts"


def test_plugin_exports_a_v2_definition() -> None:
    text = PLUGIN.read_text(encoding="utf-8")
    assert 'id: "claude-seo"' in text
    assert "async setup(ctx)" in text
    assert 'ctx.shell.hook("create.before"' in text
    assert 'ctx.tool.hook("execute.before"' in text
    assert 'ctx.tool.hook("execute.after"' in text
    assert "ctx.mcp.transform" in text
    assert "applyModelOverrides" in text
    assert "validate-schema.py" in text


def test_plugin_does_not_use_the_opencode_binary_as_node() -> None:
    text = PLUGIN.read_text(encoding="utf-8")
    assert "process.execPath" not in text


def test_plugin_sets_seo_root_and_skill_dir() -> None:
    text = PLUGIN.read_text(encoding="utf-8")
    assert "event.env.SEO_ROOT = root" in text
    assert "event.env.SEO_SKILLS_DIR" in text
    assert "event.env.SEO_DATA_DIR" in text


def test_plugin_syntax_is_valid_esm() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not available")
    target = PLUGIN.parent / "index.check.mjs"
    try:
        target.write_text(PLUGIN.read_text(encoding="utf-8"), encoding="utf-8")
        result = subprocess.run(
            [node, "--check", str(target)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
    finally:
        target.unlink(missing_ok=True)
