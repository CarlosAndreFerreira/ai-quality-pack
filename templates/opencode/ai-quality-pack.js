// AI Quality Pack: server plugin for OpenCode 2 (.opencode/plugins/ai-quality-pack.js).
//
// It connects OpenCode to the same scripts that the Claude Code hooks run:
//   - session digest: `memory.py start`, added to the system text of the session;
//   - formatter: `.claude/hooks/format_on_edit.py` after an edit tool;
//   - guard (opt-in): `.claude/hooks/guard_pack_files.py` before a tool call; a blocked call throws;
//   - completion gate (opt-in): `.claude/hooks/gate_on_stop.py` when the agent has finished its turn.
// The opt-in parts are on when `.opencode/ai-quality-pack.json` says so (`install.py --with-stop-gate`, `--with-guard`).
//
// OpenCode has no hook that stops the agent from finishing. When the gate fails, this plugin sends the gate output
// to the session as a new prompt, one time. If the gate still fails after that, the run log records `released-red`
// and the next session digest reports it. In `opencode run` the process can end before that prompt: use
// `memory.py gated-run --agent-cmd "opencode run --auto"` for unattended work.
import { spawn } from "node:child_process"
import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"

const PYTHON = process.platform === "win32" ? "python" : "python3"
const MEMORY = ".agents/skills/long-horizon/scripts/memory.py"
const HOOKS = ".claude/hooks"
const READ_ONLY = new Set(["read", "grep", "glob", "list", "ls", "webfetch", "websearch", "skill", "task", "subagent",
  "todowrite", "todoread", "lsp", "question"])
const PACK_SUBAGENTS = new Set(["evaluator", "criteria", "triage"])
// The event that OpenCode 2 sends when the agent has finished its turn (seen in OpenCode 2.2.7; there is no `session.idle`).
const TURN_ENDED = "session.execution.succeeded"

// Runs one pack script with a JSON object on stdin. It never throws: a script that cannot run gives code -1.
function run(root, script, args, input, timeoutMs) {
  return new Promise((resolve) => {
    let stdout = "", stderr = "", done = false
    const finish = (code) => { if (!done) { done = true; clearTimeout(timer); resolve({ code, stdout, stderr }) } }
    let child
    try {
      child = spawn(PYTHON, [join(root, script), ...args], { cwd: root, env: { ...process.env, AGENT_PROJECT_DIR: root } })
    } catch {
      return resolve({ code: -1, stdout, stderr })
    }
    const timer = setTimeout(() => { try { child.kill() } catch {} finish(-1) }, timeoutMs)
    child.stdout.on("data", (d) => { stdout += d })
    child.stderr.on("data", (d) => { stderr += d })
    child.on("error", () => finish(-1))
    child.on("close", (code) => finish(code ?? -1))
    child.stdin.on("error", () => {})
    child.stdin.end(JSON.stringify(input ?? {}))
  })
}

export default {
  id: "ai-quality-pack",
  async setup(ctx) {
    const root = ctx.location?.project?.directory ?? ctx.location?.directory ?? process.cwd()
    if (!existsSync(join(root, MEMORY))) return
    let config = {}
    try { config = JSON.parse(readFileSync(join(root, ".opencode", "ai-quality-pack.json"), "utf8")) } catch {}
    const digests = new Map() // session id -> digest text
    const agents = new Map() // session id -> agent name

    // Session digest. This hook runs before each model request: the digest is made one time for each session.
    await ctx.session.hook("context", async (event) => {
      const id = event.sessionID ?? "session"
      if (event.agent) agents.set(id, String(event.agent?.id ?? event.agent?.name ?? event.agent))
      if (!digests.has(id)) {
        digests.set(id, "")
        const r = await run(root, MEMORY, ["start"],
          { session_id: event.sessionID, source: "startup", model: event.model?.id, cwd: root }, 30000)
        if (r.code === 0) digests.set(id, r.stdout.trim())
      }
      if (digests.get(id)) event.system.push({ type: "text", text: digests.get(id) })
    })

    if (config.guard && existsSync(join(root, HOOKS, "guard_pack_files.py"))) {
      await ctx.tool.hook("execute.before", async (event) => {
        if (READ_ONLY.has(String(event.tool).toLowerCase())) return
        const r = await run(root, `${HOOKS}/guard_pack_files.py`, [],
          { tool_name: event.tool, tool_input: event.input ?? {}, cwd: root }, 15000)
        if (r.code === 2) throw new Error(r.stderr.trim() || "Blocked: this file checks the agent's work.")
      })
    }

    if (existsSync(join(root, HOOKS, "format_on_edit.py"))) {
      await ctx.tool.hook("execute.after", async (event) => {
        if (event.status && event.status !== "completed") return
        if (!event.input || READ_ONLY.has(String(event.tool).toLowerCase())) return
        await run(root, `${HOOKS}/format_on_edit.py`, [], { tool_name: event.tool, tool_input: event.input, cwd: root }, 90000)
      })
    }

    if (!config.stop_gate || !existsSync(join(root, HOOKS, "gate_on_stop.py"))) return
    const controller = new AbortController()
    const nudged = new Set() // sessions that got the gate output as a prompt and have not answered with a green gate
    void (async () => {
      try {
        for await (const event of ctx.event.subscribe({ types: [TURN_ENDED], signal: controller.signal })) {
          if (event?.type !== TURN_ENDED) continue
          const id = event.data?.sessionID ?? event.durable?.aggregateID ?? event.sessionID
          if (!id || PACK_SUBAGENTS.has(agents.get(id))) continue // a subagent of the pack does not get the gate
          const r = await run(root, `${HOOKS}/gate_on_stop.py`, [],
            { session_id: id, stop_hook_active: nudged.has(id), cwd: root }, 3 * 60 * 60 * 1000)
          if (r.code === 2 && !nudged.has(id)) {
            nudged.add(id)
            await ctx.session.prompt({ sessionID: id, text: r.stderr.trim() })
          } else {
            nudged.delete(id)
          }
        }
      } catch {}
    })()
    return () => controller.abort()
  },
}
