---
description: "Universal SEO analysis hub"
---

The user invoked `/seo` with:

$ARGUMENTS

If the argument list is empty, load the `seo` skill with the `skill` tool and
show its Quick Reference.

Otherwise parse the first token as the subcommand and the remainder as its
argument. Route it with this table:

| Subcommand | Action |
|---|---|
| `audit` | load the `seo-audit` skill |
| `page` | load the `seo-page` skill |
| `technical` | load the `seo-technical` skill |
| `content` | load the `seo-content` skill |
| `content-brief` | load the `seo-content-brief` skill |
| `schema` | load the `seo-schema` skill |
| `geo` | load the `seo-geo` skill |
| `agentic` | load the `seo-agentic` skill |
| `images` | load the `seo-images` skill |
| `sitemap` | load the `seo-sitemap` skill |
| `plan` | load the `seo-plan` skill |
| `competitor-pages` | load the `seo-competitor-pages` skill |
| `hreflang` | load the `seo-hreflang` skill |
| `programmatic` | load the `seo-programmatic` skill |
| `local` | load the `seo-local` skill |
| `maps` | load the `seo-maps` skill |
| `backlinks` | load the `seo-backlinks` skill |
| `cluster` | load the `seo-cluster` skill |
| `sxo` | load the `seo-sxo` skill |
| `drift` | load the `seo-drift` skill |
| `ecommerce` | load the `seo-ecommerce` skill |
| `flow` | load the `seo-flow` skill |
| `google` | load the `seo-google` skill |
| `image-gen` | load the `seo-image-gen` skill |
| `firecrawl` | load the `seo-firecrawl` skill |
| `dataforseo` | load the `seo-dataforseo` skill |
| `ahrefs` | load the `seo-ahrefs` skill |
| `bing` | load the `seo-bing` skill |
| `matomo` | load the `seo-matomo` skill |
| `profound` | load the `seo-profound` skill |
| `seranking` | load the `seo-seranking` skill |
| `unlighthouse` | load the `seo-unlighthouse` skill |
| `setup` | run `"$SEO_ROOT/scripts/seo" setup` |
| `doctor` | run `"$SEO_ROOT/scripts/seo" doctor --json` |

For a skill route, call the `skill` tool with the mapped skill ID, then follow
that skill exactly using the remainder as the user input. Do not answer from
memory. For `setup` and `doctor`, run the command shown with a 15-minute shell
timeout when setup is involved.

If the subcommand is unknown, load the `seo` skill and explain the available
commands. If a mapped skill is missing, tell the user which optional extension
to install.
