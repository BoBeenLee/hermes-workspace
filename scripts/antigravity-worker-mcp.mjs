#!/usr/bin/env node
import { spawn } from "node:child_process";
import { chmod, mkdir, readFile, realpath, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import process from "node:process";

const home = process.env.HOME || "/Users/bobeenlee";
const defaultWorkspace = process.env.HERMES_REMOTE_WORKSPACE || path.join(home, "Workspaces", "hermes-workspace");
const workspacesRoot = path.join(home, "Workspaces");
const agyBin = process.env.ANTIGRAVITY_BIN || path.join(home, ".local", "bin", "agy");
const tmuxBin = process.env.TMUX_BIN || "tmux";
const artifactRoot = process.env.ANTIGRAVITY_ARTIFACT_ROOT || path.join(defaultWorkspace, "artifacts", "antigravity");
const remotePath = process.env.HERMES_REMOTE_PATH || `${home}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin`;

const tools = [
  {
    name: "antigravity_check",
    description: "Check Antigravity worker readiness: workspace, git, tmux, agy, auth, and artifact root.",
    inputSchema: {
      type: "object",
      properties: {
        workspace: { type: "string", description: "Optional target git workspace. Defaults to the Hermes workspace." },
      },
      additionalProperties: false,
    },
  },
  {
    name: "antigravity_start_task",
    description: "Start an isolated Antigravity CLI worker session in a git worktree.",
    inputSchema: {
      type: "object",
      properties: {
        task: { type: "string", description: "Implementation task brief for Antigravity." },
        mode: { type: "string", enum: ["print", "tmux"], default: "print" },
        workspace: { type: "string", description: "Optional target git workspace. Required for standalone product repos outside the default Hermes workspace." },
      },
      required: ["task"],
      additionalProperties: false,
    },
  },
  {
    name: "antigravity_status",
    description: "Return tmux, artifact, git, and sanitized log status for an Antigravity session.",
    inputSchema: {
      type: "object",
      properties: { session: { type: "string" } },
      required: ["session"],
      additionalProperties: false,
    },
  },
  {
    name: "antigravity_stop",
    description: "Stop a running Antigravity tmux session.",
    inputSchema: {
      type: "object",
      properties: { session: { type: "string" } },
      required: ["session"],
      additionalProperties: false,
    },
  },
  {
    name: "antigravity_collect",
    description: "Collect logs, git summary, full diff, and a review-required completion note.",
    inputSchema: {
      type: "object",
      properties: { session: { type: "string" } },
      required: ["session"],
      additionalProperties: false,
    },
  },
];

function sanitize(text) {
  return String(text || "")
    .replace(/code=([^&\s]+)/g, "code=[redacted]")
    .replace(/\b4\/[A-Za-z0-9_-]{20,}\b/g, "[redacted-auth-code]")
    .replace(/\b(sk-[A-Za-z0-9_-]{8})[A-Za-z0-9_-]+/g, "$1[redacted]")
    .replace(/AIza[A-Za-z0-9_-]{20,}/g, "AIza[redacted]");
}

function asTextResult(data, isError = false) {
  const text = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  return { content: [{ type: "text", text: sanitize(text) }], isError };
}

function slugify(text) {
  const slug = String(text).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
  return slug || "task";
}

function shQuote(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

function normalizeWorkspacePath(value) {
  const raw = String(value || defaultWorkspace).trim();
  if (!raw) throw new Error("workspace must not be empty");
  const expanded = raw === "~" ? home : raw.startsWith("~/") ? path.join(home, raw.slice(2)) : raw;
  const resolved = path.resolve(expanded);
  const root = path.resolve(workspacesRoot);
  if (resolved !== root && !resolved.startsWith(`${root}${path.sep}`)) {
    throw new Error(`workspace must be under ${workspacesRoot}: ${resolved}`);
  }
  return resolved;
}

async function resolveWorkspace(value) {
  const resolved = normalizeWorkspacePath(value);
  if (existsSync(resolved)) {
    const real = await realpath(resolved);
    const realRoot = await realpath(workspacesRoot);
    if (real !== realRoot && !real.startsWith(`${realRoot}${path.sep}`)) {
      throw new Error(`workspace real path must stay under ${workspacesRoot}: ${real}`);
    }
  }
  return resolved;
}

function pidRunning(pid) {
  if (!pid) return false;
  try {
    process.kill(Number(pid), 0);
    return true;
  } catch {
    return false;
  }
}

function stopProcessGroup(pid) {
  if (!pid) return false;
  const numericPid = Number(pid);
  if (!Number.isFinite(numericPid)) return false;
  try {
    process.kill(-numericPid, "SIGTERM");
    return true;
  } catch {
    try {
      process.kill(numericPid, "SIGTERM");
      return true;
    } catch {
      return false;
    }
  }
}

function run(command, args = [], options = {}) {
  return new Promise((resolve) => {
    let settled = false;
    const child = spawn(command, args, {
      cwd: options.cwd || defaultWorkspace,
      env: { ...process.env, PATH: remotePath },
      shell: false,
    });
    const timeoutMs = options.timeoutMs || 30000;
    let stdout = "";
    let stderr = "";
    if (child.stdin) child.stdin.end();
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill("SIGTERM");
      resolve({ code: 124, stdout: sanitize(stdout), stderr: sanitize(stderr || `timed out after ${timeoutMs}ms`) });
    }, timeoutMs);
    child.stdout.on("data", (data) => (stdout += data.toString()));
    child.stderr.on("data", (data) => (stderr += data.toString()));
    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ code, stdout: sanitize(stdout), stderr: sanitize(stderr) });
    });
    child.on("error", (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ code: 127, stdout, stderr: error.message });
    });
  });
}

async function readSessionEnv(session) {
  const artifactDir = path.join(artifactRoot, session);
  const envPath = path.join(artifactDir, "session.env");
  const values = { artifactDir };
  if (!existsSync(envPath)) return values;
  const text = await readFile(envPath, "utf8");
  for (const line of text.splitlines?.() || text.split("\n")) {
    const idx = line.indexOf("=");
    if (idx > 0) values[line.slice(0, idx)] = line.slice(idx + 1);
  }
  return values;
}

function sessionArg(args) {
  const session = String(args.session || "").trim();
  if (!session) throw new Error("session is required");
  return session;
}

async function readWorkerExit(env) {
  if (!env.exit_file || !existsSync(env.exit_file)) return null;
  const exitText = await readFile(env.exit_file, "utf8");
  return Object.fromEntries(
    exitText
      .split("\n")
      .filter((line) => line.includes("="))
      .map((line) => {
        const idx = line.indexOf("=");
        return [line.slice(0, idx), line.slice(idx + 1)];
      }),
  );
}

async function readLogTail(env, lines = 80) {
  const logPath = path.join(env.artifactDir, "tmux-pane.log");
  if (!existsSync(logPath)) return "";
  const text = await readFile(logPath, "utf8");
  return sanitize(text.split("\n").slice(-lines).join("\n"));
}

async function captureSessionLog(session, env) {
  const has = await run(tmuxBin, ["has-session", "-t", session]);
  if (has.code === 0) {
    const capture = await run(tmuxBin, ["capture-pane", "-p", "-t", session, "-S", "-3000"]);
    await writeFile(path.join(env.artifactDir, "tmux-capture.txt"), capture.stdout);
  }
  const logPath = path.join(env.artifactDir, "tmux-pane.log");
  if (env.pid && existsSync(logPath)) {
    const log = await readFile(logPath, "utf8");
    await writeFile(path.join(env.artifactDir, "worker-output.txt"), sanitize(log));
  }
}

async function gitSummary(env) {
  const result = { gitStatus: "", diffStat: "", diffNames: "", changedFiles: [] };
  if (!env.worktree || !existsSync(env.worktree)) return result;
  result.gitStatus = (await run("git", ["-C", env.worktree, "status", "--short"])).stdout;
  result.diffStat = (await run("git", ["-C", env.worktree, "diff", "--stat"])).stdout;
  result.diffNames = (await run("git", ["-C", env.worktree, "diff", "--name-only"])).stdout;
  result.changedFiles = result.diffNames.split("\n").filter(Boolean);
  const diff = (await run("git", ["-C", env.worktree, "diff"])).stdout;
  await writeFile(path.join(env.artifactDir, "worktree.diff"), diff);
  return result;
}

async function writeGitSummary(env, summary) {
  const text = ["== git status ==", summary.gitStatus, "== git diff --stat ==", summary.diffStat, "== git diff --name-only ==", summary.diffNames, ""].join("\n");
  await writeFile(path.join(env.artifactDir, "git-summary.txt"), text);
}

async function writeCompletionNote(session, env) {
  const note = [
    "# Antigravity Delegated Implementation Completion",
    "",
    "- task type: delegated-implementation",
    `- Antigravity session id: ${session}`,
    `- branch: ${env.branch || "unknown"}`,
    `- target workspace: ${env.workspace || "unknown"}`,
    `- target git root: ${env.git_root || "unknown"}`,
    `- worktree path: ${env.worktree || "unknown"}`,
    `- changed files or report path: see ${path.join(env.artifactDir, "git-summary.txt")}`,
    "- tests/checks run: verify manually from Antigravity log and rerun required checks",
    `- captured log path: ${path.join(env.artifactDir, "tmux-pane.log")}`,
    "- completion mode: review-required",
    "",
    "Hermes must verify the git diff and checks independently before merge or operational application.",
    "",
  ].join("\n");
  await writeFile(path.join(env.artifactDir, "completion-note.md"), note);
}

async function antigravityCheck(args = {}) {
  const targetWorkspace = await resolveWorkspace(args.workspace);
  const git = await run("git", ["-C", targetWorkspace, "rev-parse", "--show-toplevel"]);
  const gitStatus = await run("git", ["-C", targetWorkspace, "status", "--short"]);
  const tmux = await run(tmuxBin, ["-V"]);
  const agy = await run(agyBin, ["--version"]);
  const models = await run(agyBin, ["models"], { timeoutMs: 15000 });
  return {
    workspace: targetWorkspace,
    defaultWorkspace,
    workspacePresent: existsSync(targetWorkspace),
    gitRoot: git.code === 0 ? git.stdout.trim() : null,
    gitStatus: gitStatus.stdout.trim(),
    tmux: tmux.code === 0 ? tmux.stdout.trim() : null,
    agy: agy.code === 0 ? agy.stdout.trim() : null,
    authenticated: models.code === 0,
    modelsPreview: models.stdout.split("\n").filter(Boolean).slice(0, 5),
    artifactRoot,
    artifactRootPresent: existsSync(artifactRoot),
  };
}

async function antigravityStartTask(args) {
  const task = String(args.task || "").trim();
  if (!task) throw new Error("task is required");
  const mode = args.mode || "print";
  if (!["print", "tmux"].includes(mode)) throw new Error("mode must be print or tmux");
  const targetWorkspace = await resolveWorkspace(args.workspace);

  const readiness = await antigravityCheck({ workspace: targetWorkspace });
  if (!readiness.workspacePresent || !readiness.gitRoot) throw new Error(`workspace is not a git repository: ${targetWorkspace}`);
  if (mode === "tmux" && !readiness.tmux) throw new Error("tmux is missing");
  if (!readiness.agy) throw new Error("Antigravity CLI is missing");
  if (!readiness.authenticated) throw new Error("Antigravity CLI is not authenticated");

  const timestamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..*/, "").replace("T", "-");
  const slug = slugify(task);
  const session = `antigravity-${timestamp}-${slug}`;
  const worktreeRoot = path.join(path.dirname(targetWorkspace), "antigravity-worktrees");
  const worktree = path.join(worktreeRoot, session);
  const artifactDir = path.join(artifactRoot, session);
  const branch = `codex/antigravity/${timestamp}-${slug}`;

  await mkdir(worktreeRoot, { recursive: true });
  await mkdir(artifactDir, { recursive: true });
  const add = await run("git", ["-C", targetWorkspace, "worktree", "add", "-b", branch, worktree, "HEAD"]);
  if (add.code !== 0) throw new Error(add.stderr || add.stdout || "git worktree add failed");

  await writeFile(path.join(artifactDir, "task.txt"), `${task}\n`);
  const sessionEnvPath = path.join(artifactDir, "session.env");
  const sessionEnv = [
    `session=${session}`,
    `branch=${branch}`,
    `workspace=${targetWorkspace}`,
    `git_root=${readiness.gitRoot}`,
    `worktree=${worktree}`,
    `artifact_dir=${artifactDir}`,
    `mode=${mode}`,
    "completion_mode=review-required",
  ];
  await writeFile(
    path.join(artifactDir, "supervisor-instructions.md"),
    [
      "# Hermes Supervisor Policy",
      "",
      "- Antigravity is the implementation worker.",
      "- Hermes must verify git diff and checks independently.",
      `- Target workspace: ${targetWorkspace}`,
      `- Target git root: ${readiness.gitRoot}`,
      "- Keep changes inside this isolated worktree.",
      "- Do not read or print .env, SSH keys, ~/.hermes/auth.json, provider tokens, or copied secret files.",
      "- Destructive commands and remote config/auth changes require human review.",
      "- Completion mode is review-required.",
      "",
    ].join("\n"),
  );

  const prompt = [
    "You are Antigravity CLI acting as an implementation worker under Hermes supervision.",
    `The target repository workspace is: ${targetWorkspace}.`,
    `The target repository git root is: ${readiness.gitRoot}.`,
    `Work only in this isolated worktree: ${worktree}.`,
    "Use automatic approvals only for repo-local implementation and verification commands.",
    "Never inspect, list, read, copy, or print secret-bearing paths or files, including ~/.ssh, ~/.hermes/auth.json, ~/.hermes/.env, .env files, provider token files, OAuth credential files, or private keys.",
    "Do not stage, commit, merge, push, deploy, restart services, edit remote auth/config, or remove worktrees.",
    "If the task is a no-edit or readiness smoke test, only run minimal repo-local checks such as pwd and git status --short, then report the result.",
    `Task: ${task}.`,
    "When done, summarize changed files and checks.",
    "Completion mode must remain review-required.",
  ].join(" ");
  if (mode === "tmux") {
    const newSession = await run(tmuxBin, ["new-session", "-d", "-s", session, "-c", worktree, `${shQuote(agyBin)} --dangerously-skip-permissions`]);
    if (newSession.code !== 0) throw new Error(newSession.stderr || newSession.stdout || "tmux new-session failed");
    await run(tmuxBin, ["pipe-pane", "-t", session, "-o", `cat >> ${shQuote(path.join(artifactDir, "tmux-pane.log"))}`]);
    await run(tmuxBin, ["send-keys", "-t", session, prompt, "C-m"]);
  } else {
    const logPath = path.join(artifactDir, "tmux-pane.log");
    const promptPath = path.join(artifactDir, "prompt.txt");
    const exitPath = path.join(artifactDir, "worker-exit.env");
    const runnerPath = path.join(artifactDir, "run-worker.sh");
    await writeFile(promptPath, `${prompt}\n`);
    await writeFile(logPath, `$ ${agyBin} --dangerously-skip-permissions --print-timeout 10m --print <prompt.txt>\n`);
    await writeFile(
      runnerPath,
      [
        "#!/usr/bin/env bash",
        "set +e",
        `export HOME=${shQuote(home)}`,
        `export PATH=${shQuote(remotePath)}`,
        `cd ${shQuote(worktree)} || exit 1`,
        `echo "worker_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> ${shQuote(exitPath)}`,
        `PROMPT="$(cat ${shQuote(promptPath)})"`,
        `${shQuote(agyBin)} --dangerously-skip-permissions --print-timeout 10m --print "$PROMPT" >> ${shQuote(logPath)} 2>&1`,
        "code=$?",
        `echo "worker_finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> ${shQuote(exitPath)}`,
        `echo "exit_code=$code" >> ${shQuote(exitPath)}`,
        "exit $code",
        "",
      ].join("\n"),
    );
    await chmod(runnerPath, 0o700);
    const child = spawn("/bin/bash", [runnerPath], {
      cwd: worktree,
      env: { ...process.env, HOME: home, PATH: remotePath },
      detached: true,
      stdio: "ignore",
    });
    child.unref();
    sessionEnv.push(`pid=${child.pid}`);
    sessionEnv.push(`runner=${runnerPath}`);
    sessionEnv.push(`exit_file=${exitPath}`);
  }
  await writeFile(sessionEnvPath, `${sessionEnv.join("\n")}\n`);

  return {
    session,
    branch,
    workspace: targetWorkspace,
    gitRoot: readiness.gitRoot,
    worktree,
    artifactDir,
    mode,
    pid: sessionEnv.find((line) => line.startsWith("pid="))?.slice(4) || null,
    status: "started",
    completionMode: "review-required",
  };
}

async function antigravityStatus(args) {
  const session = sessionArg(args);
  const env = await readSessionEnv(session);
  const has = await run(tmuxBin, ["has-session", "-t", session]);
  const list = await run(tmuxBin, ["list-sessions"]);
  const runningPid = pidRunning(env.pid);
  const workerExit = await readWorkerExit(env);
  const gitStatus = env.worktree ? await run("git", ["-C", env.worktree, "status", "--short"]) : { stdout: "", code: 1 };
  return {
    session,
    running: has.code === 0 || runningPid,
    finished: Boolean(workerExit?.exit_code),
    exitCode: workerExit?.exit_code ?? null,
    mode: env.mode || null,
    pid: env.pid || null,
    runner: env.runner || null,
    tmux: sanitize(list.stdout),
    artifactDir: env.artifactDir,
    workspace: env.workspace || null,
    gitRoot: env.git_root || null,
    worktree: env.worktree || null,
    branch: env.branch || null,
    gitStatus: gitStatus.stdout.trim(),
    logTail: await readLogTail(env),
  };
}

async function antigravityStop(args) {
  const session = String(args.session || "").trim();
  if (!session) throw new Error("session is required");
  const has = await run(tmuxBin, ["has-session", "-t", session]);
  const env = await readSessionEnv(session);
  let stoppedPid = false;
  if (pidRunning(env.pid)) {
    stoppedPid = stopProcessGroup(env.pid);
  }
  if (pidRunning(env.pid)) {
    await run("/usr/bin/pkill", ["-TERM", "-f", session], { timeoutMs: 5000 });
    stoppedPid = true;
  }
  if (has.code !== 0) return { session, status: stoppedPid ? "stopped" : "not-running" };
  await run(tmuxBin, ["send-keys", "-t", session, "Escape"]);
  await run(tmuxBin, ["kill-session", "-t", session]);
  return { session, status: "stopped" };
}

async function antigravityCollect(args) {
  const session = sessionArg(args);
  const env = await readSessionEnv(session);
  if (!existsSync(env.artifactDir)) throw new Error(`artifact missing: ${env.artifactDir}`);
  await captureSessionLog(session, env);
  const summary = await gitSummary(env);
  await writeGitSummary(env, summary);
  await writeCompletionNote(session, env);
  return {
    session,
    branch: env.branch || null,
    workspace: env.workspace || null,
    gitRoot: env.git_root || null,
    worktree: env.worktree || null,
    artifactDir: env.artifactDir,
    gitStatus: summary.gitStatus.trim(),
    diffStat: summary.diffStat.trim(),
    changedFiles: summary.changedFiles,
    completionMode: "review-required",
    completionNote: path.join(env.artifactDir, "completion-note.md"),
  };
}

async function callTool(name, args) {
  if (name === "antigravity_check") return antigravityCheck(args || {});
  if (name === "antigravity_start_task") return antigravityStartTask(args || {});
  if (name === "antigravity_status") return antigravityStatus(args || {});
  if (name === "antigravity_stop") return antigravityStop(args || {});
  if (name === "antigravity_collect") return antigravityCollect(args || {});
  throw new Error(`unknown tool: ${name}`);
}

function send(message) {
  const json = JSON.stringify(message);
  if (process.env.MCP_CONTENT_LENGTH === "1") {
    process.stdout.write(`Content-Length: ${Buffer.byteLength(json)}\r\n\r\n${json}`);
  } else {
    process.stdout.write(`${json}\n`);
  }
}

async function handle(request) {
  const { id, method, params } = request;
  try {
    if (method === "initialize") {
      send({ jsonrpc: "2.0", id, result: { protocolVersion: "2024-11-05", capabilities: { tools: {} }, serverInfo: { name: "antigravity-worker", version: "0.1.0" } } });
    } else if (method === "tools/list") {
      send({ jsonrpc: "2.0", id, result: { tools } });
    } else if (method === "tools/call") {
      const result = await callTool(params?.name, params?.arguments || {});
      send({ jsonrpc: "2.0", id, result: asTextResult(result) });
    } else if (method === "ping") {
      send({ jsonrpc: "2.0", id, result: {} });
    } else if (id !== undefined) {
      send({ jsonrpc: "2.0", id, error: { code: -32601, message: `method not found: ${method}` } });
    }
  } catch (error) {
    if (id !== undefined) send({ jsonrpc: "2.0", id, result: asTextResult({ error: sanitize(error.message) }, true) });
  }
}

let buffer = Buffer.alloc(0);
process.stdin.on("data", (chunk) => {
  buffer = Buffer.concat([buffer, chunk]);
  while (buffer.length) {
    const text = buffer.toString("utf8");
    const headerEnd = text.indexOf("\r\n\r\n");
    if (headerEnd >= 0) {
      const header = text.slice(0, headerEnd);
      const match = header.match(/Content-Length:\s*(\d+)/i);
      if (!match) {
        buffer = buffer.subarray(headerEnd + 4);
        continue;
      }
      const length = Number(match[1]);
      const start = Buffer.byteLength(text.slice(0, headerEnd + 4));
      if (buffer.length < start + length) return;
      const body = buffer.subarray(start, start + length).toString("utf8");
      buffer = buffer.subarray(start + length);
      handle(JSON.parse(body));
      continue;
    }
    const newline = text.indexOf("\n");
    if (newline < 0) return;
    const line = text.slice(0, newline).trim();
    buffer = buffer.subarray(Buffer.byteLength(text.slice(0, newline + 1)));
    if (line) handle(JSON.parse(line));
  }
});
