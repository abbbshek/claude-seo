"""OpenCode model profile helpers."""

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

import opencode_models as models  # noqa: E402


def test_profiles_have_all_tiers() -> None:
    for profile in models.PROFILES.values():
        assert set(profile) == {"deep", "standard", "fast"}


def test_parse_set_rejects_unknown_agent() -> None:
    with pytest.raises(SystemExit):
        models._parse_set(["not-an-agent=provider/model"], {"seo-technical": {}})


def test_parse_set_accepts_cloudflare_ids() -> None:
    result = models._parse_set(
        ["seo-technical=cloudflare-workers-ai/@cf/zai-org/glm-5.3-flash"],
        {"seo-technical": {}},
    )
    assert result["seo-technical"].startswith("cloudflare-workers-ai/")


def test_write_profile_is_private(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        models,
        "_available_models",
        lambda: set(models.PROFILES["free"].values()),
    )
    rc = models.main(["--config-dir", str(tmp_path), "--profile", "free"])
    assert rc == 0
    path = tmp_path / "claude-seo.models.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["tiers"] == models.PROFILES["free"]
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_profile_and_set_merge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        models,
        "_available_models",
        lambda: set(models.PROFILES["free"].values())
        | {"google-vertex/gemini-4-argon"},
    )
    assert models.main(["--config-dir", str(tmp_path), "--profile", "free"]) == 0
    assert (
        models.main(
            [
                "--config-dir",
                str(tmp_path),
                "--set",
                "seo-content=google-vertex/gemini-4-argon#high",
            ]
        )
        == 0
    )
    data = json.loads((tmp_path / "claude-seo.models.json").read_text(encoding="utf-8"))
    assert data["tiers"] == models.PROFILES["free"]
    assert data["agents"]["seo-content"] == "google-vertex/gemini-4-argon#high"


def test_variant_is_not_treated_as_a_missing_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        models,
        "_available_models",
        lambda: {"google-vertex/gemini-4-argon"},
    )
    models._validate_refs(["google-vertex/gemini-4-argon#high"], strict=True)
