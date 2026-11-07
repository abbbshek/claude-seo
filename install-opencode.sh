#!/usr/bin/env bash
set -euo pipefail

# Claude SEO installer for OpenCode.
#
# Global install (default):
#   ./install-opencode.sh
#
# Project-local definitions with the global managed runtime:
#   ./install-opencode.sh --project /path/to/site
#
# Self-contained project runtime:
#   ./install-opencode.sh --project /path/to/site --portable

main() {
    REPO_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
    CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
    DATA_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/claude-seo"
    PROJECT=""
    PORTABLE=0
    SKIP_BROWSER=0
    SKIP_SETUP=0
    PYTHON="${SEO_PYTHON:-}"

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --project)
                [ "$#" -ge 2 ] || { echo "--project needs a directory" >&2; exit 2; }
                PROJECT="$2"
                shift 2
                ;;
            --portable)
                PORTABLE=1
                shift
                ;;
            --skip-browser)
                SKIP_BROWSER=1
                shift
                ;;
            --skip-setup)
                SKIP_SETUP=1
                shift
                ;;
            --python)
                [ "$#" -ge 2 ] || { echo "--python needs an executable" >&2; exit 2; }
                PYTHON="$2"
                shift 2
                ;;
            --help|-h)
                sed -n '2,16p' "$0"
                exit 0
                ;;
            *)
                echo "Unknown argument: $1" >&2
                exit 2
                ;;
        esac
    done

    if [ -n "$PROJECT" ]; then
        CONFIG_DIR="$(CDPATH= cd -- "$PROJECT" && pwd -P)/.opencode"
        if [ "$PORTABLE" -eq 1 ]; then
            DATA_ROOT="$CONFIG_DIR/runtime"
        fi
    fi

    command -v python3 >/dev/null 2>&1 || {
        echo "Python 3.11 to 3.14 is required." >&2
        exit 1
    }

    echo "Claude SEO for OpenCode"
    echo "  Config:  $CONFIG_DIR"
    echo "  Runtime: $DATA_ROOT"
    echo

    # Preserve an unrelated opencode.json rather than silently replacing it.
    config_args=()
    if [ -f "$CONFIG_DIR/opencode.json" ] && [ ! -f "$CONFIG_DIR/claude-seo.manifest.json" ] && ! grep -q 'seo-\*' "$CONFIG_DIR/opencode.json"; then
        backup="$CONFIG_DIR/opencode.json.before-claude-seo"
        cp "$CONFIG_DIR/opencode.json" "$backup"
        config_args+=(--no-config)
        echo "Preserved existing opencode.json; a merge snippet will be written next to it."
    fi

    echo "Generating native OpenCode definitions..."
    preserve_args=()
    marker="$CONFIG_DIR/claude-seo.extensions.json"
    if [ -f "$marker" ]; then
        list_file="$CONFIG_DIR/.claude-seo-extensions.tmp"
        python3 -c 'import json, sys; data = json.load(open(sys.argv[1], encoding="utf-8")); [print(value) for value in data.get("extensions", []) if isinstance(value, str)]' "$marker" > "$list_file" 2>/dev/null || true
        while IFS= read -r extension; do
            [ -n "$extension" ] && preserve_args+=(--preserve-extension "$extension")
        done < "$list_file"
        rm -f "$list_file"
    fi
    python3 "$REPO_DIR/scripts/opencode_sync.py" --dest "$CONFIG_DIR" "${config_args[@]}" "${preserve_args[@]}"
    if [ "${#config_args[@]}" -gt 0 ]; then
        cp "$REPO_DIR/.opencode/opencode.json" "$CONFIG_DIR/opencode.json.claude-seo"
        echo "Merge the permissions from $CONFIG_DIR/opencode.json.claude-seo into your opencode.json."
    fi

    echo "Installing plugin..."
    mkdir -p "$CONFIG_DIR/plugins/claude-seo"
    cp "$REPO_DIR/.opencode/plugins/claude-seo/index.ts" \
        "$CONFIG_DIR/plugins/claude-seo/index.ts"

    echo "Installing managed runtime..."
    mkdir -p "$DATA_ROOT/scripts" "$DATA_ROOT/data" "$DATA_ROOT/schema" "$DATA_ROOT/hooks"
    cp -a "$REPO_DIR/scripts/." "$DATA_ROOT/scripts/"
    cp -a "$REPO_DIR/data/." "$DATA_ROOT/data/"
    cp -a "$REPO_DIR/schema/." "$DATA_ROOT/schema/"
    cp -a "$REPO_DIR/hooks/." "$DATA_ROOT/hooks/"
    cp "$REPO_DIR/requirements.txt" "$DATA_ROOT/requirements.txt"
    cp "$REPO_DIR/.claude-plugin/plugin.json" "$DATA_ROOT/runtime-plugin.json"

    mkdir -p "$DATA_ROOT/extensions"
    cp -a "$REPO_DIR/extensions/." "$DATA_ROOT/extensions/"

    chmod +x "$DATA_ROOT/scripts/seo" "$DATA_ROOT/scripts/claude-seo" 2>/dev/null || true
    chmod +x "$DATA_ROOT/hooks/"*.py 2>/dev/null || true
    printf '%s\n' "$DATA_ROOT" > "$CONFIG_DIR/claude-seo.root"

    python3 - "$CONFIG_DIR" "$DATA_ROOT" <<'PY'
import json
import os
import sys
import tempfile

config_dir, runtime_dir = sys.argv[1:3]
manifest = {
    "version": 1,
    "config_dir": config_dir,
    "runtime_dir": runtime_dir,
}
path = os.path.join(config_dir, "claude-seo.manifest.json")
fd, temporary = tempfile.mkstemp(dir=config_dir, prefix=".manifest.", suffix=".json")
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
except BaseException:
    if os.path.exists(temporary):
        os.unlink(temporary)
    raise
PY

    if [ "$SKIP_SETUP" -eq 0 ]; then
        echo
        echo "Creating the isolated Python runtime..."
        setup_args=()
        if [ "$SKIP_BROWSER" -eq 1 ]; then
            setup_args+=(--skip-browser)
        fi
        set +e
        env_args=(
            "SEO_ROOT=$DATA_ROOT"
            "SEO_DATA_DIR=$DATA_ROOT"
        )
        if [ -n "$PYTHON" ]; then
            env_args+=("SEO_PYTHON=$PYTHON")
        fi
        env "${env_args[@]}" "$DATA_ROOT/scripts/seo" setup "${setup_args[@]}"
        status=$?
        set -e
        if [ "$status" -ne 0 ] && [ "$status" -ne 10 ]; then
            echo "Runtime setup failed. Installation is incomplete." >&2
            exit 1
        fi
        if [ "$status" -eq 10 ]; then
            echo "Core runtime is ready, but Chromium setup is incomplete." >&2
        fi
    fi

    echo
    echo "Installed."
    echo "  Start OpenCode in any project and run /seo doctor"
    echo "  or /seo audit https://example.com"
    echo
    echo "Optional extensions:"
    echo "  python3 $DATA_ROOT/scripts/opencode_extensions.py install dataforseo"
    echo "  python3 $DATA_ROOT/scripts/opencode_extensions.py list"
    echo
    echo "Optional per-agent models:"
    echo "  python3 $DATA_ROOT/scripts/opencode_models.py --profile free"
}

main "$@"
