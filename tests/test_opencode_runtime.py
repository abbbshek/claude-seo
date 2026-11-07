"""Runtime aliases and Fedora-friendly launcher checks."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location("seo_runtime_test", SCRIPTS / "runtime.py")
assert SPEC and SPEC.loader
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


def test_seo_launcher_help_works_without_a_runtime() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPTS / "seo"), "doctor", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHON_COLORS": "0", "NO_COLOR": "1"},
    )
    assert result.returncode == 0, result.stderr
    assert "usage: claude-seo doctor" in result.stdout


def test_seo_launcher_is_executable() -> None:
    if os.name != "posix":
        pytest.skip("POSIX mode bits only")
    assert (SCRIPTS / "seo").stat().st_mode & 0o111


def test_runtime_accepts_seo_data_dir_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_SEO_DATA_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    monkeypatch.setenv("SEO_DATA_DIR", str(tmp_path / "data"))
    data_dir, mode = runtime._data_dir(tmp_path)
    assert data_dir == (tmp_path / "data").resolve()
    assert mode == "override"


def test_runtime_keeps_claude_data_dir_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEO_DATA_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    monkeypatch.setenv("CLAUDE_SEO_DATA_DIR", str(tmp_path / "legacy"))
    data_dir, mode = runtime._data_dir(tmp_path)
    assert data_dir == (tmp_path / "legacy").resolve()
    assert mode == "override"


def test_sync_flow_accepts_seo_skills_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sync_flow

    monkeypatch.setenv("SEO_SKILLS_DIR", str(tmp_path))
    assert sync_flow.skills_root(tmp_path / "repo") == tmp_path


def test_url_safety_accepts_seo_local_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    import url_safety

    monkeypatch.delenv("CLAUDE_SEO_LOCAL_TARGETS", raising=False)
    monkeypatch.setenv("SEO_LOCAL_TARGETS", "localhost:3000")
    assert url_safety._local_targets() == (("localhost", 3000),)
