"""The generated OpenCode layer must match its canonical sources."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "scripts" / "opencode_sync.py"


def test_opencode_layer_is_in_sync() -> None:
    result = subprocess.run(
        [sys.executable, str(SYNC), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "up to date" in result.stdout


def test_sync_generates_the_same_tree_in_a_temporary_destination(tmp_path: Path) -> None:
    destination = tmp_path / "opencode"
    result = subprocess.run(
        [sys.executable, str(SYNC), "--dest", str(destination)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (destination / "skills" / "seo" / "SKILL.md").is_file()
    assert (destination / "agents" / "seo-technical.md").is_file()
    assert (destination / "commands" / "seo.md").is_file()
    assert (destination / "opencode.json").is_file()


def test_preserve_extension_skips_the_core_mirror(tmp_path: Path) -> None:
    destination = tmp_path / "opencode"
    extension_skill = destination / "skills" / "seo-dataforseo" / "SKILL.md"
    extension_skill.parent.mkdir(parents=True)
    extension_skill.write_text("extension-owned skill\n", encoding="utf-8")
    extension_agent = destination / "agents" / "seo-dataforseo.md"
    extension_agent.parent.mkdir(parents=True)
    extension_agent.write_text("extension-owned agent\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(SYNC),
            "--dest",
            str(destination),
            "--preserve-extension",
            "dataforseo",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert extension_skill.read_text(encoding="utf-8") == "extension-owned skill\n"
    assert extension_agent.read_text(encoding="utf-8") == "extension-owned agent\n"
    assert (destination / "skills" / "seo-audit" / "SKILL.md").is_file()


def test_missing_preserved_extension_falls_back_to_core(tmp_path: Path) -> None:
    destination = tmp_path / "opencode"
    result = subprocess.run(
        [
            sys.executable,
            str(SYNC),
            "--dest",
            str(destination),
            "--preserve-extension",
            "dataforseo",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (destination / "skills" / "seo-dataforseo" / "SKILL.md").is_file()
    assert (destination / "agents" / "seo-dataforseo.md").is_file()
