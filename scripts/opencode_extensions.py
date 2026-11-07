#!/usr/bin/env python3
"""Install optional Claude SEO extensions for OpenCode.

The Claude installers in ``extensions/*/install.sh`` remain untouched. This
script writes the OpenCode equivalents without editing the user's
``opencode.json``:

- skills and agents into the OpenCode config directory
- MCP servers into ``claude-seo.mcp.json``
- API keys into ``claude-seo.env.json``
- Matomo credentials into the existing ``matomo.json`` path

Usage::

    python scripts/opencode_extensions.py list
    python scripts/opencode_extensions.py install dataforseo
    python scripts/opencode_extensions.py install firecrawl
    python scripts/opencode_extensions.py status
    python scripts/opencode_extensions.py remove dataforseo
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "scripts" / "opencode_manifest.json"

EXTENSIONS = {
    "dataforseo": {
        "label": "DataForSEO",
        "skill": "seo-dataforseo",
        "agent": "seo-dataforseo",
        "mcp": "dataforseo",
    },
    "firecrawl": {
        "label": "Firecrawl",
        "skill": "seo-firecrawl",
        "mcp": "firecrawl",
    },
    "ahrefs": {
        "label": "Ahrefs",
        "skill": "seo-ahrefs",
        "mcp": "ahrefs",
    },
    "banana": {
        "label": "Banana image generation",
        "skill": "seo-image-gen",
        "agent": "seo-image-gen",
        "mcp": "nanobanana",
    },
    "matomo": {
        "label": "Matomo",
        "skill": "seo-matomo",
        "agent": "seo-matomo",
    },
    "bing-webmaster": {
        "label": "Bing Webmaster",
        "skill": "seo-bing",
    },
    "profound": {
        "label": "Profound",
        "skill": "seo-profound",
    },
    "seranking": {
        "label": "SE Ranking",
        "skill": "seo-seranking",
    },
    "unlighthouse": {
        "label": "Unlighthouse",
        "skill": "seo-unlighthouse",
    },
}


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _config_dir(explicit: str | None, project: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    if project:
        return Path(project).expanduser() / ".opencode"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "opencode"


def _runtime_root(explicit: str | None, config_dir: Path) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    root_file = config_dir / "claude-seo.root"
    if root_file.is_file():
        value = root_file.read_text(encoding="utf-8").strip()
        if value:
            return Path(value).expanduser()
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "claude-seo"


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON. Nothing was changed: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"{path} must contain a JSON object. Nothing was changed.")
    return value


def _write_json(path: Path, value: dict, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _prompt(
    label: str,
    env_names: tuple[str, ...],
    *,
    secret: bool = False,
    required: bool = True,
    non_interactive: bool = False,
) -> str:
    for name in env_names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    if non_interactive:
        if required:
            raise SystemExit(
                f"{label} is required. Set {env_names[0]} or run interactively."
            )
        return ""
    value = getpass.getpass(f"{label}: ") if secret else input(f"{label}: ").strip()
    if required and not value:
        raise SystemExit(f"{label} cannot be empty.")
    return value


def _merge_env(config_dir: Path, updates: dict[str, str], *, dry_run: bool) -> Path:
    path = config_dir / "claude-seo.env.json"
    if dry_run:
        return path
    data = _read_json(path)
    data.update(updates)
    _write_json(path, data)
    return path


def _merge_mcp(config_dir: Path, name: str, config: dict, *, dry_run: bool) -> Path:
    path = config_dir / "claude-seo.mcp.json"
    if dry_run:
        return path
    data = _read_json(path)
    servers = data.setdefault("servers", {})
    if not isinstance(servers, dict):
        raise SystemExit(f"{path}: 'servers' must be an object. Nothing was changed.")
    servers[name] = config
    _write_json(path, data)
    return path


def _remove_mcp(config_dir: Path, name: str) -> bool:
    path = config_dir / "claude-seo.mcp.json"
    if not path.exists():
        return False
    data = _read_json(path)
    servers = data.get("servers")
    if not isinstance(servers, dict) or name not in servers:
        return False
    del servers[name]
    _write_json(path, data)
    return True


def _remove_env(config_dir: Path, keys: list[str]) -> bool:
    path = config_dir / "claude-seo.env.json"
    if not path.exists():
        return False
    data = _read_json(path)
    changed = False
    for key in keys:
        if key in data:
            del data[key]
            changed = True
    if changed:
        _write_json(path, data)
    return changed


def _copy_tree(source: Path, destination: Path, *, dry_run: bool) -> None:
    if dry_run or not source.is_dir():
        return
    shutil.copytree(source, destination, dirs_exist_ok=True)


def _marker_path(config_dir: Path) -> Path:
    return config_dir / "claude-seo.extensions.json"


def _load_marker(config_dir: Path) -> list[str]:
    path = _marker_path(config_dir)
    if not path.is_file():
        return []
    data = _read_json(path)
    values = data.get("extensions")
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, str)]


def _save_marker(config_dir: Path, values: list[str]) -> None:
    _write_json(_marker_path(config_dir), {"extensions": sorted(set(values))})


def _install_dataforseo(
    config_dir: Path, runtime_root: Path, *, non_interactive: bool, dry_run: bool
) -> tuple[dict[str, str], dict]:
    username = _prompt(
        "DataForSEO username (email)",
        ("DATAFORSEO_USERNAME", "CLAUDE_SEO_USERNAME"),
        non_interactive=non_interactive,
    )
    password = _prompt(
        "DataForSEO password",
        ("DATAFORSEO_PASSWORD", "CLAUDE_SEO_SECRET"),
        secret=True,
        non_interactive=non_interactive,
    )
    field_config = runtime_root / "dataforseo-field-config.json"
    source = ROOT / "extensions" / "dataforseo" / "field-config.json"
    if not dry_run and source.is_file():
        runtime_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, field_config)
    mcp = {
        "type": "local",
        "command": ["npx", "-y", "dataforseo-mcp-server@2.8.10"],
        "environment": {
            "DATAFORSEO_USERNAME": "{env:DATAFORSEO_USERNAME}",
            "DATAFORSEO_PASSWORD": "{env:DATAFORSEO_PASSWORD}",
            "ENABLED_MODULES": (
                "SERP,KEYWORDS_DATA,ONPAGE,DATAFORSEO_LABS,BACKLINKS,"
                "DOMAIN_ANALYTICS,BUSINESS_DATA,CONTENT_ANALYSIS,AI_OPTIMIZATION"
            ),
            "FIELD_CONFIG_PATH": str(field_config),
        },
    }
    return {"DATAFORSEO_USERNAME": username, "DATAFORSEO_PASSWORD": password}, mcp


def _install_firecrawl(
    config_dir: Path, runtime_root: Path, *, non_interactive: bool, dry_run: bool
) -> tuple[dict[str, str], dict]:
    key = _prompt(
        "Firecrawl API key",
        ("FIRECRAWL_API_KEY",),
        secret=True,
        non_interactive=non_interactive,
    )
    mcp = {
        "type": "local",
        "command": ["npx", "-y", "firecrawl-mcp@3.11.0"],
        "environment": {"FIRECRAWL_API_KEY": "{env:FIRECRAWL_API_KEY}"},
    }
    return {"FIRECRAWL_API_KEY": key}, mcp


def _install_ahrefs(
    config_dir: Path, runtime_root: Path, *, non_interactive: bool, dry_run: bool
) -> tuple[dict[str, str], dict]:
    token = _prompt(
        "Ahrefs API token",
        ("AHREFS_API_TOKEN",),
        secret=True,
        non_interactive=non_interactive,
    )
    mcp = {
        "type": "local",
        "command": ["npx", "--yes", "--package=@ahrefs/mcp@0.0.11", "mcp"],
        "environment": {"AHREFS_API_TOKEN": "{env:AHREFS_API_TOKEN}"},
    }
    return {"AHREFS_API_TOKEN": token}, mcp


def _install_banana(
    config_dir: Path, runtime_root: Path, *, non_interactive: bool, dry_run: bool
) -> tuple[dict[str, str], dict]:
    key = _prompt(
        "Google AI API key",
        ("GOOGLE_AI_API_KEY",),
        secret=True,
        non_interactive=non_interactive,
    )
    _copy_tree(
        ROOT / "extensions" / "banana" / "scripts",
        runtime_root / "extensions" / "banana" / "scripts",
        dry_run=dry_run,
    )
    mcp = {
        "type": "local",
        "command": ["npx", "-y", "@ycse/nanobanana-mcp@1.1.1"],
        "environment": {"GOOGLE_AI_API_KEY": "{env:GOOGLE_AI_API_KEY}"},
    }
    return {"GOOGLE_AI_API_KEY": key}, mcp


def _install_matomo(
    config_dir: Path, runtime_root: Path, *, non_interactive: bool, dry_run: bool
) -> tuple[dict[str, str], dict | None]:
    url = _prompt(
        "Matomo URL",
        ("MATOMO_URL",),
        non_interactive=non_interactive,
    )
    site_id = _prompt(
        "Matomo site ID",
        ("MATOMO_SITE_ID",),
        non_interactive=non_interactive,
    )
    token = _prompt(
        "Matomo token_auth",
        ("MATOMO_API_TOKEN", "MATOMO_TOKEN"),
        secret=True,
        non_interactive=non_interactive,
    )
    config_path = Path(
        os.environ.get("SEO_CONFIG_DIR")
        or os.environ.get("CLAUDE_SEO_CONFIG_DIR")
        or Path.home() / ".config" / "claude-seo"
    ) / "matomo.json"
    if not dry_run:
        _write_json(
            config_path,
            {
                "matomo_url": url,
                "matomo_site_id": site_id,
                "matomo_token": token,
            },
        )
    return {}, None


def _install_bing(
    config_dir: Path, runtime_root: Path, *, non_interactive: bool, dry_run: bool
) -> tuple[dict[str, str], dict | None]:
    api_key = _prompt(
        "Bing Webmaster API key",
        ("BING_WEBMASTER_API_KEY",),
        secret=True,
        non_interactive=non_interactive,
    )
    indexnow = _prompt(
        "IndexNow key",
        ("INDEXNOW_KEY",),
        secret=True,
        required=False,
        non_interactive=non_interactive,
    )
    location = _prompt(
        "IndexNow key location URL (optional)",
        ("INDEXNOW_KEY_LOCATION",),
        required=False,
        non_interactive=non_interactive,
    )
    updates = {"BING_WEBMASTER_API_KEY": api_key}
    if indexnow:
        updates["INDEXNOW_KEY"] = indexnow
    if location:
        updates["INDEXNOW_KEY_LOCATION"] = location
    return updates, None


def _install_profound(
    config_dir: Path, runtime_root: Path, *, non_interactive: bool, dry_run: bool
) -> tuple[dict[str, str], dict | None]:
    key = _prompt(
        "Profound API key",
        ("PROFOUND_API_KEY",),
        secret=True,
        non_interactive=non_interactive,
    )
    return {"PROFOUND_API_KEY": key}, None


def _install_seranking(
    config_dir: Path, runtime_root: Path, *, non_interactive: bool, dry_run: bool
) -> tuple[dict[str, str], dict | None]:
    key = _prompt(
        "SE Ranking API key",
        ("SERANKING_API_KEY",),
        secret=True,
        non_interactive=non_interactive,
    )
    return {"SERANKING_API_KEY": key}, None


def _install_unlighthouse(
    config_dir: Path, runtime_root: Path, *, non_interactive: bool, dry_run: bool
) -> tuple[dict[str, str], dict | None]:
    return {}, None


INSTALLERS = {
    "dataforseo": _install_dataforseo,
    "firecrawl": _install_firecrawl,
    "ahrefs": _install_ahrefs,
    "banana": _install_banana,
    "matomo": _install_matomo,
    "bing-webmaster": _install_bing,
    "profound": _install_profound,
    "seranking": _install_seranking,
    "unlighthouse": _install_unlighthouse,
}


def install(
    name: str,
    *,
    config_dir: Path,
    runtime_root: Path,
    non_interactive: bool = False,
    dry_run: bool = False,
) -> int:
    if name not in EXTENSIONS:
        raise SystemExit(f"Unknown extension: {name}")
    info = EXTENSIONS[name]
    manifest = _load_manifest()

    # The generator writes the rewritten skill and agent into the OpenCode tree.
    if not dry_run:
        from opencode_sync import generate_extension

        generate_extension(config_dir, name, manifest)

    env_updates, mcp = INSTALLERS[name](
        config_dir,
        runtime_root,
        non_interactive=non_interactive,
        dry_run=dry_run,
    )
    if env_updates:
        _merge_env(config_dir, env_updates, dry_run=dry_run)
    if mcp:
        _merge_mcp(config_dir, info.get("mcp", name), mcp, dry_run=dry_run)
    if not dry_run:
        _save_marker(config_dir, [*_load_marker(config_dir), name])

    print(f"{info['label']} extension prepared for OpenCode.")
    print(f"  Config: {config_dir}")
    print(f"  Runtime: {runtime_root}")
    if dry_run:
        print("  Dry run: no files were changed.")
    return 0


def remove(name: str, *, config_dir: Path, purge: bool = False) -> int:
    if name not in EXTENSIONS:
        raise SystemExit(f"Unknown extension: {name}")
    info = EXTENSIONS[name]
    removed: list[str] = []
    skill_dir = config_dir / "skills" / info["skill"]
    if skill_dir.is_dir():
        shutil.rmtree(skill_dir)
        removed.append(str(skill_dir))
    agent = info.get("agent")
    if agent:
        agent_path = config_dir / "agents" / f"{agent}.md"
        if agent_path.is_file():
            agent_path.unlink()
            removed.append(str(agent_path))
    if info.get("mcp") and _remove_mcp(config_dir, info["mcp"]):
        removed.append(f"MCP server {info['mcp']}")
    env_keys = {
        "dataforseo": ["DATAFORSEO_USERNAME", "DATAFORSEO_PASSWORD"],
        "firecrawl": ["FIRECRAWL_API_KEY"],
        "ahrefs": ["AHREFS_API_TOKEN"],
        "banana": ["GOOGLE_AI_API_KEY"],
        "bing-webmaster": [
            "BING_WEBMASTER_API_KEY",
            "INDEXNOW_KEY",
            "INDEXNOW_KEY_LOCATION",
        ],
        "profound": ["PROFOUND_API_KEY"],
        "seranking": ["SERANKING_API_KEY"],
    }.get(name, [])
    if env_keys and _remove_env(config_dir, env_keys):
        removed.append("environment keys")
    if purge and name == "matomo":
        config_path = Path(
            os.environ.get("SEO_CONFIG_DIR")
            or os.environ.get("CLAUDE_SEO_CONFIG_DIR")
            or Path.home() / ".config" / "claude-seo"
        ) / "matomo.json"
        if config_path.is_file():
            config_path.unlink()
            removed.append(str(config_path))
    if _marker_path(config_dir).is_file():
        remaining = [value for value in _load_marker(config_dir) if value != name]
        _save_marker(config_dir, remaining)
        removed.append("extension marker")
    if removed:
        print(f"Removed {info['label']}:")
        for item in removed:
            print(f"  {item}")
    else:
        print(f"{info['label']} is not installed in {config_dir}.")
    return 0


def status(config_dir: Path, runtime_root: Path) -> int:
    print(f"OpenCode config: {config_dir}")
    print(f"Runtime: {runtime_root}")
    env = _read_json(config_dir / "claude-seo.env.json")
    mcp = _read_json(config_dir / "claude-seo.mcp.json")
    servers = mcp.get("servers", {}) if isinstance(mcp.get("servers"), dict) else {}
    for name, info in EXTENSIONS.items():
        skill = (config_dir / "skills" / info["skill"] / "SKILL.md").is_file()
        server = info.get("mcp") in servers if info.get("mcp") else False
        keys = {
            "dataforseo": ("DATAFORSEO_USERNAME", "DATAFORSEO_PASSWORD"),
            "firecrawl": ("FIRECRAWL_API_KEY",),
            "ahrefs": ("AHREFS_API_TOKEN",),
            "banana": ("GOOGLE_AI_API_KEY",),
            "bing-webmaster": ("BING_WEBMASTER_API_KEY",),
            "profound": ("PROFOUND_API_KEY",),
            "seranking": ("SERANKING_API_KEY",),
        }.get(name, ())
        configured = all(key in env for key in keys) if keys else True
        print(
            f"  {name:<14} skill={'yes' if skill else 'no':<3} "
            f"mcp={'yes' if server else 'no':<3} env={'yes' if configured else 'no'}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage Claude SEO extensions for OpenCode.")
    parser.add_argument("--config-dir", help="OpenCode config directory")
    parser.add_argument("--project", help="install into a project's .opencode directory")
    parser.add_argument("--runtime", help="managed runtime root")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="read credentials from environment variables only",
    )
    parser.add_argument("--dry-run", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list available extensions")
    install_parser = sub.add_parser("install", help="install one extension")
    install_parser.add_argument("name", choices=sorted(EXTENSIONS))
    remove_parser = sub.add_parser("remove", help="remove one extension")
    remove_parser.add_argument("name", choices=sorted(EXTENSIONS))
    remove_parser.add_argument("--purge", action="store_true")
    sub.add_parser("status", help="show extension status")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_dir = _config_dir(args.config_dir, args.project)
    runtime_root = _runtime_root(args.runtime, config_dir)
    if args.command == "list":
        for name, info in sorted(EXTENSIONS.items()):
            print(f"{name:<14} {info['label']}")
        return 0
    if args.command == "install":
        return install(
            args.name,
            config_dir=config_dir,
            runtime_root=runtime_root,
            non_interactive=args.non_interactive,
            dry_run=args.dry_run,
        )
    if args.command == "remove":
        return remove(args.name, config_dir=config_dir, purge=args.purge)
    if args.command == "status":
        return status(config_dir, runtime_root)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
