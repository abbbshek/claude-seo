# OpenCode

Claude SEO runs natively in OpenCode through the generated `.opencode/` layer.
The canonical `skills/` and `agents/` trees stay Claude-compatible and remain the
source of truth.

## Install

### Global

```bash
git clone --depth 1 https://github.com/AgriciDaniel/claude-seo.git
cd claude-seo
./install-opencode.sh
```

This writes:

- skills to `$XDG_CONFIG_HOME/opencode/skills` (normally `~/.config/opencode/skills`)
- agents to `$XDG_CONFIG_HOME/opencode/agents`
- commands to `$XDG_CONFIG_HOME/opencode/commands`
- the plugin to `$XDG_CONFIG_HOME/opencode/plugins/claude-seo`
- the managed runtime to `$XDG_DATA_HOME/claude-seo` (normally `~/.local/share/claude-seo`)
- `claude-seo.root`, `claude-seo.manifest.json`, and `opencode.json` in the OpenCode config directory

The installer preserves an existing `opencode.json`. It writes a merge snippet
to `opencode.json.claude-seo` and leaves the original file unchanged.

### Project-local

```bash
./install-opencode.sh --project /path/to/site
```

This writes definitions to `/path/to/site/.opencode` and uses the shared runtime.
Add `--portable` to copy the runtime into the project as well.

### Options

| Option | Effect |
|---|---|
| `--skip-browser` | Skip the Playwright Chromium download |
| `--skip-setup` | Copy files without creating the Python runtime |
| `--python PATH` | Select a Python 3.11 to 3.14 interpreter |
| `--portable` | Put the runtime under the project's `.opencode/runtime` |

## Commands

Both forms work:

```text
/seo audit https://example.com
/seo-audit https://example.com
/seo technical https://example.com
/seo-technical https://example.com
/seo doctor
```

`/seo` is a router that maps the first argument to the matching skill. The
`/seo-<command>` aliases are direct OpenCode commands. Setup and doctor run the
managed runtime directly.

## Models

OpenCode subagents inherit the session model selected with `/models`. This works
with free OpenCode models, Cloudflare Workers AI, Google Vertex, or any other
configured provider.

To assign per-agent tiers, write `claude-seo.models.json`:

```bash
python3 scripts/opencode_models.py --profile free
python3 scripts/opencode_models.py --profile cloudflare
python3 scripts/opencode_models.py --profile vertex
python3 scripts/opencode_models.py --set seo-content=provider/model
python3 scripts/opencode_models.py --show
```

The plugin applies the file when a subagent is launched. If you edit the file
while OpenCode is running, reload OpenCode or start a new session.

Profiles use these tiers:

| Tier | Agents |
|---|---|
| `deep` | seo-content, seo-cluster, seo-drift, seo-geo, seo-sxo |
| `standard` | all other core agents |
| `fast` | optional override |

Example model IDs from the current catalog:

| Profile | Deep | Standard | Fast |
|---|---|---|---|
| Free | `opencode/glm-5.3-flash-free` | `opencode/deepseek-v4.1-flash-free` | `opencode/inkling-2-small-free` |
| Cloudflare | `cloudflare-workers-ai/@cf/deepseek-ai/deepseek-v4-pro-0813` | `cloudflare-workers-ai/@cf/zai-org/glm-5.3-flash` | `cloudflare-workers-ai/@cf/google/gemma-4-26b-a4b-it` |
| Vertex | `google-vertex/gemini-4-argon#high` | `google-vertex/gemini-3.8-flash` | `google-vertex/gemini-3.5-flash-lite` |

Model availability changes. The script checks `opencode models` and warns when a
profile ID is not in the current catalog.

## Runtime

Run setup once:

```text
/seo setup
```

Check readiness:

```text
/seo doctor
```

The runtime is isolated. It does not install into the system Python or the user
site-packages. The launcher resolves Python 3.11 to 3.14 and stores the managed
environment under `SEO_DATA_DIR`.

### Fedora

Fedora 43 with Python 3.14 is supported. Install the system libraries needed by
Playwright and WeasyPrint:

```bash
sudo dnf install python3-devel gcc pango cairo gdk-pixbuf2 libffi \
  nss nspr atk at-spi2-atk cups-libs libdrm libxkbcommon \
  libXcomposite libXdamage libXfixes libXrandr mesa-libgbm
```

Playwright may report that Fedora is not an officially supported distribution
and download the Ubuntu fallback build. This is expected and works. If Chromium
still fails, run:

```bash
SEO_DATA_DIR=~/.local/share/claude-seo \
  ~/.local/share/claude-seo/.venv/bin/python -m playwright install chromium
```

If Python 3.14 cannot install a dependency wheel, select Python 3.11:

```bash
./install-opencode.sh --python /usr/bin/python3.11
```

### Environment variables

| Variable | Purpose |
|---|---|
| `SEO_ROOT` | Managed runtime root containing `scripts/seo` |
| `SEO_SKILLS_DIR` | Installed skills directory |
| `SEO_DATA_DIR` | Managed venv, browser, and runtime state |
| `SEO_PYTHON` | Python interpreter override |
| `SEO_CONFIG_DIR` | Credential directory (default `~/.config/claude-seo`) |
| `SEO_CACHE_DIR` | Cache directory (default `~/.cache/claude-seo`) |
| `SEO_LOCAL_TARGETS` | Allow private audit targets for local testing |
| `SEO_GOOGLE_AUTH` | Set to `adc` to prefer gcloud Application Default Credentials |

The legacy `CLAUDE_SEO_*` names remain supported.

## Extensions and MCP

The OpenCode extension installer writes dedicated files instead of editing
`opencode.json`:

- `claude-seo.mcp.json`: MCP server definitions
- `claude-seo.env.json`: API keys exported to shell commands
- `~/.config/claude-seo/matomo.json`: Matomo credentials

```bash
python3 scripts/opencode_extensions.py list
python3 scripts/opencode_extensions.py install dataforseo
python3 scripts/opencode_extensions.py install firecrawl
python3 scripts/opencode_extensions.py install ahrefs
python3 scripts/opencode_extensions.py install banana
python3 scripts/opencode_extensions.py install matomo
python3 scripts/opencode_extensions.py install bing-webmaster
python3 scripts/opencode_extensions.py install profound
python3 scripts/opencode_extensions.py install seranking
python3 scripts/opencode_extensions.py install unlighthouse
python3 scripts/opencode_extensions.py status
```

Credentials can be supplied interactively or through environment variables with
`--non-interactive`. Use `--dry-run` to inspect an install without writing files.

From a repository checkout, the commands above work as written. After a global
install, the same scripts live in `$XDG_DATA_HOME/claude-seo/scripts/`; for
example `python3 ~/.local/share/claude-seo/scripts/opencode_extensions.py status`.

| Extension | OpenCode integration |
|---|---|
| DataForSEO | MCP server `dataforseo`; field config in the runtime |
| Firecrawl | MCP server `firecrawl` |
| Ahrefs | MCP server `ahrefs` |
| Banana | MCP server `nanobanana`; scripts in the runtime and skill |
| Matomo | Credentials in `~/.config/claude-seo/matomo.json` |
| Bing Webmaster | `BING_WEBMASTER_API_KEY`, `INDEXNOW_KEY` in the env file |
| Profound | `PROFOUND_API_KEY` in the env file |
| SE Ranking | `SERANKING_API_KEY` in the env file |
| Unlighthouse | Local `npx` runner; no credentials |

OpenCode exposes MCP tools as `<server>_<tool>`. In Code Mode, call them under
`tools.<server>.<tool>(...)`.

## Plugin behavior

`.opencode/plugins/claude-seo/index.ts` provides:

- `SEO_ROOT`, `SEO_SKILLS_DIR`, and `SEO_DATA_DIR` for every shell command
- credential export from `claude-seo.env.json`
- MCP registration from `claude-seo.mcp.json`
- per-agent model overrides from `claude-seo.models.json`
- JSON-LD validation after `edit`, `write`, and `patch`

The validator is the same `hooks/validate-schema.py` used by the Claude hook.
OpenCode cannot block an edit after it is written, so diagnostics are appended to
the tool result and the model can fix the file.

## Sync workflow

Edit canonical sources only:

- `skills/<id>/SKILL.md` and references
- `agents/seo-*.md`
- `docs/COMMANDS.md`
- `scripts/opencode_manifest.json`

Then regenerate:

```bash
python3 scripts/opencode_sync.py
python3 scripts/opencode_sync.py --check
```

The generated `.opencode/` tree is committed. CI fails when it drifts from the
canonical sources.

Installed extensions are recorded in `claude-seo.extensions.json`.
`install-opencode.sh` reads that file and preserves extension-owned skills and
agents when regenerating the core layer.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/seo` is missing | Confirm `.opencode/commands/seo.md` exists and reload OpenCode |
| Subagents are missing | Run `opencode debug agents`; confirm 19 `seo-*` agents |
| `SEO_ROOT` is empty | Confirm the plugin is loaded with `opencode plugin list` |
| Runtime says setup required | Run `/seo setup` or `"$SEO_ROOT/scripts/seo" setup` |
| Chromium is unavailable | Run the Playwright install command above |
| MCP server is missing | Run `python3 scripts/opencode_extensions.py status` |
| Model override is ignored | Reload OpenCode; confirm `claude-seo.models.json` is valid |
| `opencode.json` was changed | Restore `opencode.json.before-claude-seo` if present and merge `opencode.json.claude-seo` |

## Security

- Credential files are written with mode `0600`.
- API keys are never placed on command lines.
- The installer does not modify `~/.claude.json` or `~/.claude/settings.json`.
- Fetched pages, SERP data, and API responses remain untrusted data.
- The Python runtime keeps the existing SSRF and DNS-rebinding protections.
