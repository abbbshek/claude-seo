#!/usr/bin/env bash
set -euo pipefail

# Remove the OpenCode layer installed by install-opencode.sh.
#
#   ./uninstall-opencode.sh
#   ./uninstall-opencode.sh --project /path/to/site
#   ./uninstall-opencode.sh --purge
#
# The user's opencode.json is never edited or removed.

main() {
    CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
    DATA_ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/claude-seo"
    PROJECT=""
    PURGE=0

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --project)
                [ "$#" -ge 2 ] || { echo "--project needs a directory" >&2; exit 2; }
                PROJECT="$2"
                shift 2
                ;;
            --purge)
                PURGE=1
                shift
                ;;
            --help|-h)
                sed -n '2,12p' "$0"
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
    fi

    shopt -s nullglob
    removed=0
    for path in \
        "$CONFIG_DIR/skills/seo" \
        "$CONFIG_DIR"/skills/seo-* \
        "$CONFIG_DIR"/agents/seo-*.md \
        "$CONFIG_DIR"/commands/seo*.md \
        "$CONFIG_DIR/plugins/claude-seo" \
        "$CONFIG_DIR/claude-seo.root" \
        "$CONFIG_DIR/claude-seo.env.json" \
        "$CONFIG_DIR/claude-seo.mcp.json" \
        "$CONFIG_DIR/claude-seo.models.json" \
        "$CONFIG_DIR/claude-seo.extensions.json" \
        "$CONFIG_DIR/claude-seo.manifest.json" \
        "$CONFIG_DIR/opencode.json.claude-seo"; do
        if [ -e "$path" ]; then
            rm -rf -- "$path"
            echo "Removed: $path"
            removed=$((removed + 1))
        fi
    done
    shopt -u nullglob

    if [ "$PURGE" -eq 1 ]; then
        if [ -d "$DATA_ROOT" ]; then
            rm -rf -- "$DATA_ROOT"
            echo "Removed runtime: $DATA_ROOT"
            removed=$((removed + 1))
        fi
    else
        echo "Runtime kept at $DATA_ROOT (use --purge to remove it)."
    fi

    if [ "$removed" -eq 0 ]; then
        echo "Nothing to remove in $CONFIG_DIR."
    fi
}

main "$@"
