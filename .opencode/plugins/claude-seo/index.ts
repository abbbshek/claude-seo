// @ts-nocheck
/**
 * Native OpenCode integration for Claude SEO.
 *
 * Responsibilities:
 * - locate the managed Python runtime and expose it as SEO_ROOT
 * - export OpenCode-managed credentials to shell commands
 * - register MCP servers written by the extension installer
 * - apply optional per-agent model overrides
 * - run the existing JSON-LD validator after edit/write/patch
 *
 * The plugin deliberately does not edit opencode.json or any Claude file.
 */

import { spawnSync } from "node:child_process"
import { readFileSync, statSync } from "node:fs"
import { homedir } from "node:os"
import { dirname, isAbsolute, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const appliedModelRefs = new Map()

const SCHEMA_EXTENSIONS = new Set([
  ".html",
  ".htm",
  ".jsx",
  ".tsx",
  ".vue",
  ".svelte",
  ".php",
  ".ejs",
  ".md",
])

const AGENT_TIERS = {
  "seo-agentic": "standard",
  "seo-backlinks": "standard",
  "seo-cluster": "deep",
  "seo-content": "deep",
  "seo-dataforseo": "standard",
  "seo-drift": "deep",
  "seo-ecommerce": "standard",
  "seo-flow": "standard",
  "seo-geo": "deep",
  "seo-google": "standard",
  "seo-image-gen": "standard",
  "seo-local": "standard",
  "seo-maps": "standard",
  "seo-performance": "standard",
  "seo-schema": "standard",
  "seo-sitemap": "standard",
  "seo-sxo": "deep",
  "seo-technical": "standard",
  "seo-visual": "standard",
}

function xdgConfig() {
  return process.env.XDG_CONFIG_HOME || join(homedir(), ".config")
}

function xdgData() {
  return process.env.XDG_DATA_HOME || join(homedir(), ".local", "share")
}

function isFile(path) {
  try {
    return statSync(path).isFile()
  } catch {
    return false
  }
}

function readText(path) {
  try {
    return readFileSync(path, "utf8").trim()
  } catch {
    return undefined
  }
}

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"))
  } catch {
    return undefined
  }
}


function projectDir(ctx) {
  return (
    ctx?.location?.project?.canonical ||
    ctx?.location?.project?.directory ||
    ctx?.location?.directory ||
    process.cwd()
  )
}

function pluginDir() {
  try {
    return dirname(fileURLToPath(import.meta.url))
  } catch {
    return process.cwd()
  }
}

function findRoot(ctx) {
  const candidates = []
  const explicit = process.env.SEO_ROOT?.trim()
  if (explicit) candidates.push(explicit)

  const globalRoot = readText(join(xdgConfig(), "opencode", "claude-seo.root"))
  if (globalRoot) candidates.push(globalRoot)

  const project = projectDir(ctx)
  const projectRoot = readText(join(project, ".opencode", "claude-seo.root"))
  if (projectRoot) candidates.push(projectRoot)

  candidates.push(project)
  candidates.push(resolve(pluginDir(), "../../.."))
  candidates.push(join(xdgData(), "claude-seo"))

  for (const candidate of candidates) {
    try {
      const root = resolve(candidate)
      if (
        isFile(join(root, "scripts", "seo")) &&
        isFile(join(root, "scripts", "runtime.py"))
      ) {
        return root
      }
    } catch {
      // Ignore malformed or inaccessible candidates.
    }
  }
  return undefined
}

function findSkillsDir(ctx, root) {
  const project = projectDir(ctx)
  const candidates = [
    join(project, ".opencode", "skills"),
    join(xdgConfig(), "opencode", "skills"),
    join(root, "skills"),
  ]
  for (const candidate of candidates) {
    try {
      if (isFile(join(candidate, "seo", "SKILL.md"))) return candidate
    } catch {
      // Keep looking.
    }
  }
  return undefined
}

function configFiles(ctx, name) {
  const files = [join(xdgConfig(), "opencode", name)]
  const project = projectDir(ctx)
  if (project) files.push(join(project, ".opencode", name))
  return files
}

function loadJsonLayers(ctx, name) {
  const merged = {}
  for (const path of configFiles(ctx, name)) {
    const value = readJson(path)
    if (value && typeof value === "object" && !Array.isArray(value)) {
      Object.assign(merged, value)
    }
  }
  return merged
}

function loadMcpServers(ctx) {
  const merged = {}
  for (const path of configFiles(ctx, "claude-seo.mcp.json")) {
    const value = readJson(path)
    if (value && typeof value === "object" && value.servers && typeof value.servers === "object") {
      Object.assign(merged, value.servers)
    }
  }
  return merged
}

function loadModels(ctx) {
  const value = loadJsonLayers(ctx, "claude-seo.models.json")
  return {
    tiers: value.tiers && typeof value.tiers === "object" ? value.tiers : {},
    agents: value.agents && typeof value.agents === "object" ? value.agents : {},
  }
}

function resolveEnvRefs(value, env) {
  if (typeof value === "string") {
    return value.replace(/\{env:([A-Za-z_][A-Za-z0-9_]*)\}/g, (_, name) => {
      return env[name] ?? process.env[name] ?? ""
    })
  }
  if (Array.isArray(value)) return value.map((item) => resolveEnvRefs(item, env))
  if (value && typeof value === "object") {
    const out = {}
    for (const [key, item] of Object.entries(value)) {
      out[key] = resolveEnvRefs(item, env)
    }
    return out
  }
  return value
}

function parseModelRef(ref) {
  if (typeof ref !== "string") return undefined
  const trimmed = ref.trim()
  if (!trimmed) return undefined
  const hash = trimmed.lastIndexOf("#")
  const base = hash > 0 ? trimmed.slice(0, hash) : trimmed
  const variant = hash > 0 ? trimmed.slice(hash + 1) : undefined
  const slash = base.indexOf("/")
  if (slash <= 0 || slash === base.length - 1) return undefined
  const model = {
    providerID: base.slice(0, slash),
    id: base.slice(slash + 1),
  }
  if (variant) model.variant = variant
  return model
}

async function applyModelOverrides(ctx, models, onlyAgent) {
  if (!ctx.agent?.transform) return
  if (onlyAgent) {
    const desired = models.agents[onlyAgent] || models.tiers[AGENT_TIERS[onlyAgent]]
    if (!desired || appliedModelRefs.get(onlyAgent) === desired) return
  }
  await ctx.agent.transform((editor) => {
    const agents = editor.list()
    for (const agent of agents) {
      if (onlyAgent && agent.id !== onlyAgent) continue
      const ref = models.agents[agent.id] || models.tiers[AGENT_TIERS[agent.id]]
      if (!ref) continue
      const parsed = parseModelRef(ref)
      if (!parsed) {
        console.error(`[claude-seo] invalid model reference for ${agent.id}: ${ref}`)
        continue
      }
      editor.update(agent.id, (draft) => {
        draft.model = parsed
      })
    }
  })
  if (onlyAgent) {
    const desired = models.agents[onlyAgent] || models.tiers[AGENT_TIERS[onlyAgent]]
    if (desired) appliedModelRefs.set(onlyAgent, desired)
  }
}

function appendResult(result, text) {
  if (!result || typeof result !== "object") return
  if (typeof result.content === "string") {
    result.content = `${result.content}\n\n${text}`
    return
  }
  if (Array.isArray(result.content)) {
    result.content = [...result.content, { type: "text", text }]
    return
  }
  result.content = text
}

function pathsFromInput(input) {
  if (!input || typeof input !== "object") return []
  const paths = []
  if (typeof input.path === "string") paths.push(input.path)
  if (typeof input.filePath === "string") paths.push(input.filePath)
  if (typeof input.patchText === "string") {
    for (const line of input.patchText.split(/\r?\n/)) {
      const match = line.match(/^\*\*\* (?:Add|Update|Move) File:\s*(.+)$/)
      if (match) paths.push(match[1].trim())
    }
  }
  return [...new Set(paths)]
}

function resolveEditedPath(path, ctx) {
  if (isAbsolute(path)) return path
  return resolve(projectDir(ctx), path)
}

export default {
  id: "claude-seo",
  async setup(ctx) {
    try {
      const root = findRoot(ctx)
      if (!root) {
        console.error(
          "[claude-seo] managed runtime not found. Run install-opencode.sh or set SEO_ROOT.",
        )
        return
      }

      const credentials = loadJsonLayers(ctx, "claude-seo.env.json")
      const skillsDir = findSkillsDir(ctx, root)
      const dataDir =
        process.env.SEO_DATA_DIR ||
        (root.startsWith(resolve(xdgData())) ? root : undefined)
      const validator = join(root, "hooks", "validate-schema.py")

      if (ctx.shell?.hook) {
        await ctx.shell.hook("create.before", (event) => {
          event.env.SEO_ROOT = root
          if (skillsDir) event.env.SEO_SKILLS_DIR = skillsDir
          if (dataDir) event.env.SEO_DATA_DIR = dataDir
          for (const [key, value] of Object.entries(credentials)) {
            if (typeof value !== "string") continue
            if (event.env[key] === undefined || event.env[key] === "") {
              event.env[key] = value
            }
          }
          if (event.env.SEO_PYTHON && !event.env.CLAUDE_SEO_PYTHON) {
            event.env.CLAUDE_SEO_PYTHON = event.env.SEO_PYTHON
          }
        })
      }

      if (ctx.mcp?.transform) {
        const servers = loadMcpServers(ctx)
        await ctx.mcp.transform((editor) => {
          for (const [name, config] of Object.entries(servers)) {
            if (!config || typeof config !== "object") continue
            if (editor.get(name)) continue
            const resolved = resolveEnvRefs(config, credentials)
            if (resolved.type !== "local" && resolved.type !== "remote") {
              console.error(`[claude-seo] skipping MCP server ${name}: unsupported type`)
              continue
            }
            if (resolved.type === "local" && !Array.isArray(resolved.command)) {
              console.error(`[claude-seo] skipping MCP server ${name}: command must be an array`)
              continue
            }
            editor.set(name, resolved)
          }
        })
      }

      if (ctx.tool?.hook) {
        await ctx.tool.hook("execute.before", async (event) => {
          if (event.tool !== "subagent") return
          const agent = event.input?.agent
          if (typeof agent !== "string") return
          const models = loadModels(ctx)
          if (!Object.keys(models.tiers).length && !Object.keys(models.agents).length) return
          try {
            await applyModelOverrides(ctx, models, agent)
          } catch (error) {
            console.error("[claude-seo] model override failed:", error)
          }
        })
      }

      if (ctx.tool?.hook && isFile(validator)) {
        await ctx.tool.hook("execute.after", (event) => {
          if (event.status !== "completed") return
          if (!["edit", "write", "patch"].includes(event.tool)) return
          for (const rawPath of pathsFromInput(event.input)) {
            const path = resolveEditedPath(rawPath, ctx)
            if (!isFile(path)) continue
            const extension = path.slice(path.lastIndexOf(".")).toLowerCase()
            if (!SCHEMA_EXTENSIONS.has(extension)) continue
            let content
            try {
              content = readFileSync(path, "utf8")
            } catch {
              continue
            }
            if (!content.includes("ld+json")) continue
            const pythonCandidates = [
              process.env.SEO_PYTHON,
              process.env.CLAUDE_SEO_PYTHON,
              "python3",
              "python",
            ].filter((value) => typeof value === "string" && value.trim())
            let result
            for (const python of pythonCandidates) {
              result = spawnSync(python, [validator, path], {
                encoding: "utf8",
                timeout: 15000,
                env: { ...process.env, ...credentials, SEO_ROOT: root },
              })
              if (!result.error) break
            }
            if (!result || result.error) {
              continue
            }
            const output = [result.stdout, result.stderr]
              .filter((item) => typeof item === "string" && item.trim())
              .join("\n")
              .trim()
            if (!output) continue
            appendResult(event.result, `[claude-seo schema validation]\n${output}`)
          }
        })
      }
    } catch (error) {
      console.error("[claude-seo] plugin setup failed:", error)
    }
  },
}
