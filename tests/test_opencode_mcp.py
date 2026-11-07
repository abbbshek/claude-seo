"""OpenCode extension configuration helpers."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import opencode_extensions as ext  # noqa: E402


def test_write_json_is_atomic_and_private(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    ext._write_json(path, {"a": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".config.json.*.tmp"))


def test_read_json_refuses_malformed_without_writing(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    original = '{"a": 1, broken'
    path.write_text(original, encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        ext._read_json(path)
    assert "Nothing was changed" in str(exc.value)
    assert path.read_text(encoding="utf-8") == original


def test_merge_env_preserves_unrelated_keys(tmp_path: Path) -> None:
    path = tmp_path / "claude-seo.env.json"
    ext._write_json(path, {"OTHER": "keep"})
    ext._merge_env(tmp_path, {"FIRECRAWL_API_KEY": "secret"}, dry_run=False)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"OTHER": "keep", "FIRECRAWL_API_KEY": "secret"}


def test_merge_mcp_preserves_unrelated_servers(tmp_path: Path) -> None:
    path = tmp_path / "claude-seo.mcp.json"
    ext._write_json(path, {"servers": {"mine": {"type": "remote", "url": "https://example.com"}}})
    ext._merge_mcp(tmp_path, "firecrawl", {"type": "local", "command": ["npx"]}, dry_run=False)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data["servers"]) == {"mine", "firecrawl"}


def test_dry_run_install_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")
    ext.install(
        "firecrawl",
        config_dir=config_dir,
        runtime_root=runtime_root,
        non_interactive=True,
        dry_run=True,
    )
    assert not config_dir.exists()
    assert not runtime_root.exists()


def test_install_records_extension_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    runtime_root = tmp_path / "runtime"
    monkeypatch.setenv("FIRECRAWL_API_KEY", "test-key")
    ext.install(
        "firecrawl",
        config_dir=config_dir,
        runtime_root=runtime_root,
        non_interactive=True,
        dry_run=False,
    )
    marker = json.loads((config_dir / "claude-seo.extensions.json").read_text(encoding="utf-8"))
    assert marker["extensions"] == ["firecrawl"]


def test_status_does_not_require_installed_extensions(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert ext.status(tmp_path / "config", tmp_path / "runtime") == 0
    output = capsys.readouterr().out
    assert "dataforseo" in output
    assert "unlighthouse" in output


def test_config_and_runtime_paths_respect_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    config_dir = ext._config_dir(None, None)
    assert config_dir == tmp_path / "config" / "opencode"
    assert ext._runtime_root(None, config_dir) == tmp_path / "data" / "claude-seo"
