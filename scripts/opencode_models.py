#!/usr/bin/env python3
"""Write optional per-agent model overrides for the OpenCode layer.

OpenCode subagents inherit the parent session model by default. This script
lets you assign a provider/model to a tier or to one agent without editing the
generated agent files.

The plugin reads ``claude-seo.models.json`` and applies the values through
``ctx.agent.transform``. User configuration remains untouched.

Usage::

    python scripts/opencode_models.py --profile free
    python scripts/opencode_models.py --profile cloudflare
    python scripts/opencode_models.py --profile vertex
    python scripts/opencode_models.py --set seo-content=provider/model
    python scripts/opencode_models.py --show
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "scripts" / "opencode_manifest.json"

PROFILES = {
    "free": {
        "deep": "opencode/glm-5.3-flash-free",
        "standard": "opencode/deepseek-v4.1-flash-free",
        "fast": "opencode/inkling-2-small-free",
    },
    "cloudflare": {
        "deep": "cloudflare-workers-ai/@cf/deepseek-ai/deepseek-v4-pro-0813",
        "standard": "cloudflare-workers-ai/@cf/zai-org/glm-5.3-flash",
        "fast": "cloudflare-workers-ai/@cf/google/gemma-4-26b-a4b-it",
    },
    "vertex": {
        "deep": "google-vertex/gemini-4-argon#high",
        "standard": "google-vertex/gemini-3.8-flash",
        "fast": "google-vertex/gemini-3.5-flash-lite",
    },
}


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _config_dir(explicit: str | None, project: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    if project:
        return Path(project).expanduser() / ".opencode"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "opencode"


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _available_models() -> set[str]:
    try:
        result = subprocess.run(
            ["opencode", "models"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _validate_refs(refs: list[str], *, strict: bool) -> None:
    available = _available_models()
    if not available:
        print(
            "Warning: could not read `opencode models`; model availability was not checked.",
            file=sys.stderr,
        )
        return
    missing = [
        ref
        for ref in refs
        if ref.split("#", 1)[0] not in available
    ]
    if missing:
        message = "Models not found in the current OpenCode catalog:\n  " + "\n  ".join(missing)
        if strict:
            raise SystemExit(message)
        print(f"Warning: {message}", file=sys.stderr)


def _parse_set(values: list[str], agents: dict) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"Expected agent=provider/model, got: {value}")
        agent, ref = value.split("=", 1)
        agent = agent.strip()
        ref = ref.strip()
        if agent not in agents:
            raise SystemExit(f"Unknown SEO agent: {agent}")
        if not ref or "/" not in ref:
            raise SystemExit(f"Invalid model reference for {agent}: {ref}")
        overrides[agent] = ref
    return overrides


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write OpenCode per-agent model overrides for Claude SEO."
    )
    parser.add_argument("--profile", choices=sorted(PROFILES))
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="AGENT=PROVIDER/MODEL",
        help="override one agent; repeatable",
    )
    parser.add_argument("--config-dir", help="OpenCode config directory")
    parser.add_argument("--project", help="write into a project's .opencode directory")
    parser.add_argument("--show", action="store_true", help="print the current overrides")
    parser.add_argument("--strict", action="store_true", help="fail if a model is unavailable")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = _manifest()
    config_dir = _config_dir(args.config_dir, args.project)
    path = config_dir / "claude-seo.models.json"

    if args.show:
        if not path.is_file():
            print(f"No model overrides configured at {path}.")
            return 0
        print(path.read_text(encoding="utf-8"), end="")
        return 0

    if not args.profile and not args.set:
        raise SystemExit("Choose --profile, --set, or --show.")

    tiers: dict[str, str] = {}
    if args.profile:
        tiers = dict(PROFILES[args.profile])
    agents = _parse_set(args.set, manifest["agents"])
    refs = [*tiers.values(), *agents.values()]
    if refs:
        _validate_refs(refs, strict=args.strict)

    payload: dict[str, object] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path} is not valid JSON. Nothing was changed: {exc}") from exc
        if isinstance(existing, dict):
            payload.update(existing)
    if tiers:
        payload["tiers"] = tiers
    if agents:
        current_agents = payload.get("agents")
        merged_agents = dict(current_agents) if isinstance(current_agents, dict) else {}
        merged_agents.update(agents)
        payload["agents"] = merged_agents
    _write_json(path, payload)
    print(f"Wrote {path}")
    if args.profile:
        print(f"Profile: {args.profile}")
    if agents:
        print("Agent overrides:")
        for agent, ref in sorted(agents.items()):
            print(f"  {agent}: {ref}")
    print("Reload OpenCode to apply the new agent models.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
