/**
 * Hermes Workspace Operational Dashboard
 * Interactive Terminal and Control Interface
 */

// Simulated Target Profile Configs
const targetProfiles = {
  "bobeen-mac": {
    name: "bobeen-mac",
    os: "macos",
    serviceManager: "launchd",
    computerUse: "ENABLED (cua-driver)",
    permissions: "Accessibility: GRANTED | Screen Recording: GRANTED",
    kanban: "ENABLED (dispatch_in_gateway: true)",
    root: "/Users/bobeenlee/Workspaces/hermes-workspace",
    sshAlias: "bobeen"
  },
  "linux-target": {
    name: "linux-target",
    os: "linux",
    serviceManager: "systemd",
    computerUse: "DISABLED (none)",
    permissions: "Accessibility: N/A | Screen Recording: N/A",
    kanban: "ENABLED (dispatch_in_gateway: true)",
    root: "/home/bobeenlee/hermes-workspace",
    sshAlias: "bobeen-linux"
  }
};

let currentTarget = "bobeen-mac";

// Command Output Database
const mockOutputs = {
  "config": `HERMES_TARGET={TARGET_NAME}
HERMES_REMOTE_HOST=bobeen
HERMES_REMOTE_USER=bobeenlee
HERMES_REMOTE_HOME=/Users/bobeenlee
HERMES_REMOTE_OS={TARGET_OS}
HERMES_SERVICE_MANAGER={TARGET_SERVICE_MANAGER}
HERMES_COMPUTER_USE_BACKEND={TARGET_CU_BACKEND}
HERMES_BIN={TARGET_ROOT}/.local/bin/hermes
HERMES_CONFIG=/Users/bobeenlee/.hermes/config.yaml
HERMES_WORKSPACE_ROOT={TARGET_ROOT}
HERMES_WORKSPACE_REPO=git@github.com:BoBeenLee/hermes-workspace.git
HERMES_WORKSPACE_BRANCH=main
SSH_CONNECT_TIMEOUT=8`,

  "check-ssh": `{TARGET_HOST_ALIAS}
bobeenlee
Sun Jun  7 21:45:12 KST 2026
hermes-agent v0.12.4
{CU_VERSION}
[SUCCESS] SSH Connection verified to {TARGET_NAME}.`,

  "status": `== host ==
{TARGET_HOST_ALIAS}
bobeenlee
Sun Jun  7 21:45:15 KST 2026
target: {TARGET_NAME}
os: {TARGET_OS}
service manager: {TARGET_SERVICE_MANAGER}
computer_use backend: {TARGET_CU_BACKEND}

== hermes status ==
Hermes Agent is running.
Config load: OK (~/.hermes/config.yaml)

== gateway ==
Gateway service 'ai.hermes.gateway' is active.
Uptime: 2d 14h 32m
Listening on: 127.0.0.1:9090

== computer_use ==
{CU_STATUS}

== kanban ==
Board: default
Total Tasks: 12
Running: 0
Pending: 2
Completed: 10

== dashboard ==
Dashboard is running at http://127.0.0.1:9119

== processes ==
  PID STAT COMMAND
58212 S    /Users/bobeenlee/.local/bin/hermes gateway run
{CU_PROCESS}`,

  "gateway-restart": `Stopping Hermes gateway...
Gateway service stopped.
Starting Hermes gateway...
Gateway service started successfully.

== gateway ==
Gateway service 'ai.hermes.gateway' is active.
Uptime: 0s
Listening on: 127.0.0.1:9090`,

  "verify-computer-use": `{CU_VERIFY_OUTPUT}`,

  "is-working": `== recent thread log ==
2026-06-07 21:40:02 [inbound message] thread=1512760172660129933 user=bobeenlee "Redesign landing page"
2026-06-07 21:40:03 [agent:start] worker=58412 branch=workspace-landing
2026-06-07 21:41:22 [agent:step] run command "git status"
2026-06-07 21:41:30 [agent:step] write file "pages/index.html"
2026-06-07 21:42:15 [agent:done] worker=58412 status=success duration=132s
2026-06-07 21:42:16 [response ready] thread=1512760172660129933
2026-06-07 21:42:17 [gateway] Sending response to Discord thread...

== processes ==
  PID STAT COMMAND
58212 S    /Users/bobeenlee/.local/bin/hermes gateway run

== sessions ==
No active sessions.

== kanban ==
Board: default
Total Tasks: 12
Running: 0
Pending: 2
Completed: 10
No tasks currently running.

Result: Active work is complete. Target thread is DONE.`,

  "logs": `== gateway ==
2026-06-07 21:30:00 [gateway] Starting daemon listener on port 9090...
2026-06-07 21:30:01 [gateway] Connected to database ~/.hermes/kanban.db
2026-06-07 21:40:02 [gateway] Inbound Discord webhook for thread 1512760172660129933
2026-06-07 21:40:02 [gateway] Dispatching to kanban queue...
2026-06-07 21:42:17 [gateway] Sending response to thread 1512760172660129933

== agent ==
2026-06-07 21:40:03 [agent:start] Spawning agent process (PID: 58412)
2026-06-07 21:40:05 [agent] Initializing workspace in {TARGET_ROOT}
2026-06-07 21:42:15 [agent] Finished task successfully.

== errors ==
(empty)`
};

// Fill template tags according to selected profile
function formatOutput(command, profileName) {
  const profile = targetProfiles[profileName];
  let output = mockOutputs[command];
  if (!output) return "Unknown command";

  // Replacements
  output = output.replace(/{TARGET_NAME}/g, profile.name);
  output = output.replace(/{TARGET_OS}/g, profile.os);
  output = output.replace(/{TARGET_SERVICE_MANAGER}/g, profile.serviceManager);
  output = output.replace(/{TARGET_ROOT}/g, profile.root);
  output = output.replace(/{TARGET_HOST_ALIAS}/g, profile.sshAlias);

  if (profile.os === "macos") {
    output = output.replace(/{TARGET_CU_BACKEND}/g, "cua-driver");
    output = output.replace(/{CU_VERSION}/g, "cua-driver v0.8.2");
    output = output.replace(/{CU_STATUS}/g, "cua-driver: ACTIVE\nAPI Endpoint: http://127.0.0.1:8080\n\n== cua permissions ==\nAccessibility: GRANTED\nScreen Recording: GRANTED\nSource: driver-daemon");
    output = output.replace(/{CU_PROCESS}/g, "58215 S    /Users/bobeenlee/.local/bin/cua-driver serve");
    output = output.replace(/{CU_VERIFY_OUTPUT}/g, `Opening CuaDriver (serve)...
Waiting for initialization...
== permissions ==
Accessibility: GRANTED
Screen Recording: GRANTED

== check_permissions ==
All Accessibility and Screen Recording permissions are valid.

== mcp ==
Found 3 tools:
- get_screen_size
- list_windows
- computer_action

== screen ==
Display: 1920x1080

== visible windows sample ==
[58291] Visual Studio Code - hermes-workspace
[58292] Terminal - hermes-remote status
[58293] Discord`);
  } else {
    output = output.replace(/{TARGET_CU_BACKEND}/g, "none");
    output = output.replace(/{CU_VERSION}/g, "");
    output = output.replace(/{CU_STATUS}/g, "cua-driver: UNSUPPORTED (none)");
    output = output.replace(/{CU_PROCESS}/g, "");
    output = output.replace(/{CU_VERIFY_OUTPUT}/g, `Unsupported command for target '${profile.name}': computer_use backend is 'none' on 'linux'.
This command requires macos with HERMES_COMPUTER_USE_BACKEND=cua-driver.`);
  }

  return output;
}

// Terminal Emulation
const terminalLinesEl = document.getElementById("terminal-lines");
const consoleButtons = document.querySelectorAll(".console-btn");

function runCommandOnTerminal(commandName, fullCommandString) {
  // Clear and show typing state
  terminalLinesEl.innerHTML = `<span class="term-prompt">visitor@control-mac ~ %</span> <span class="term-input"></span><span class="cursor">_</span>`;
  const inputEl = terminalLinesEl.querySelector(".term-input");
  
  // Disable buttons during typing
  consoleButtons.forEach(btn => btn.disabled = true);

  let i = 0;
  function typeChar() {
    if (i < fullCommandString.length) {
      inputEl.textContent += fullCommandString.charAt(i);
      i++;
      setTimeout(typeChar, 15 + Math.random() * 20); // typing speed jitter
    } else {
      // Typing done, show output loader
      inputEl.nextElementSibling.remove(); // remove cursor
      const loaderEl = document.createElement("div");
      loaderEl.className = "term-loader";
      loaderEl.textContent = "Connecting to target and executing command...";
      terminalLinesEl.appendChild(loaderEl);

      setTimeout(() => {
        loaderEl.remove();
        // Print output lines
        const outputText = formatOutput(commandName, currentTarget);
        const preEl = document.createElement("pre");
        preEl.className = "term-output-text";
        preEl.textContent = outputText;
        terminalLinesEl.appendChild(preEl);

        // Add next prompt line
        const nextPrompt = document.createElement("div");
        nextPrompt.className = "term-prompt-line";
        nextPrompt.innerHTML = `<span class="term-prompt">visitor@control-mac ~ %</span> <span class="cursor animate-pulse">_</span>`;
        terminalLinesEl.appendChild(nextPrompt);

        // Auto-scroll terminal
        const termBody = document.getElementById("terminal-body");
        termBody.scrollTop = termBody.scrollHeight;

        // Re-enable buttons
        consoleButtons.forEach(btn => btn.disabled = false);
      }, 500); // execution delay
    }
  }
  
  typeChar();
}

// Event Listeners for Console Buttons
consoleButtons.forEach(btn => {
  btn.addEventListener("click", () => {
    // Remove active state from others
    consoleButtons.forEach(b => b.classList.remove("active"));
    btn.classList.add("active");

    const cmdName = btn.dataset.command;
    const cmdStr = btn.dataset.exec;
    runCommandOnTerminal(cmdName, cmdStr);
  });
});

// Target Selector Interaction
const profileBadges = document.querySelectorAll(".profile-badge-btn");
const hostBadgeText = document.getElementById("active-target-badge");
const targetInfoText = document.getElementById("active-target-info");

function switchTarget(profileName) {
  currentTarget = profileName;
  const profile = targetProfiles[profileName];

  // Update UI indicators
  profileBadges.forEach(btn => {
    if (btn.dataset.profile === profileName) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });

  if (hostBadgeText) {
    hostBadgeText.textContent = profileName;
  }
  if (targetInfoText) {
    targetInfoText.textContent = `${profile.os.toUpperCase()} | ${profile.computerUse}`;
  }

  // Update top KPI cards
  document.getElementById("kpi-os").textContent = profile.os.toUpperCase();
  document.getElementById("kpi-cu").textContent = profile.computerUse.split(" ")[0];
  document.getElementById("kpi-root").textContent = profile.root.replace("/Users/bobeenlee", "~").replace("/home/bobeenlee", "~");

  // Re-run currently selected terminal command if any
  const activeBtn = document.querySelector(".console-btn.active");
  if (activeBtn) {
    runCommandOnTerminal(activeBtn.dataset.command, activeBtn.dataset.exec);
  }
}

profileBadges.forEach(btn => {
  btn.addEventListener("click", () => {
    switchTarget(btn.dataset.profile);
  });
});

// Pipeline Interactive Details
const pipelineSteps = document.querySelectorAll(".pipeline-step-card");
const pipelineDetailBox = document.getElementById("pipeline-detail-content");

const pipelineDetails = {
  "trigger": {
    title: "1. Trigger Request (Discord / CLI Gateway)",
    desc: "Tasks are submitted externally via a Discord message link or directly via CLI. The Discord handler triggers webhooks, which bind directly to the Hermes Gateway service running under user-level launchd.",
    metric: "Source: Discord Channel or CLI Prompt",
    check: "Verified: Gateway receives webhook & generates a unique Thread ID."
  },
  "triage": {
    title: "2. Profile Triage & Remote Verification",
    desc: "The workspace manager <code>bin/hermes-remote</code> resolves the target environment using the target profile env files under <code>config/targets/</code>. It runs connection smoke tests and checks availability.",
    metric: "Default Target: bobeen-mac (configured in local SSH)",
    check: "Command: <code>bin/hermes-remote config</code> & <code>check-ssh</code>"
  },
  "isolation": {
    title: "3. Worktree Isolation (Workspace Branch)",
    desc: "The agent spawns isolated git worktrees or branches. Antigravity worker actions must ALWAYS operate within this strict worktree directory to ensure clean environment changes without messing up the main repository.",
    metric: "Path: /Users/bobeenlee/Workspaces/antigravity-worktrees/&lt;task-slug&gt;",
    check: "Rule: Never modify files directly in main branch without worktree isolation."
  },
  "execution": {
    title: "4. Antigravity Worker Execution under Hermes",
    desc: "Antigravity CLI is invoked acting as an implementation worker under Hermes supervision. The agent handles code generation, file edits, and tools operations. During market research, it must maintain a source ledger.",
    metric: "Supervised mode: NO secret inspections, NO external deployments",
    check: "Durable logs: <code>~/.hermes/logs/agent.log</code>"
  },
  "verification": {
    title: "5. Repo-Local Verification & Smoke Tests",
    desc: "Before finishing, the worker executes repo-local tests (e.g. bash syntax check, git status check). Only repo-local verification and compilation commands are eligible for automatic approvals.",
    metric: "Eligible commands: git status --short, bash -n, tests/checks",
    check: "Command: <code>bash -n bin/hermes-remote && git diff --stat</code>"
  },
  "gate": {
    title: "6. Completion Mode Evaluation",
    desc: "The task completion state is classified: <b>done</b> for report-only/read-only tasks, or <b>review-required</b> for code, scripts, configs, restarts, or credentials. It prevents accidental commits or service restarts.",
    metric: "Status: review-required (needs manual human verification)",
    check: "Review list: edits to scripts, gateway status, remote launchd config."
  }
};

pipelineSteps.forEach(step => {
  step.addEventListener("click", () => {
    // Remove active state
    pipelineSteps.forEach(s => s.classList.remove("active"));
    step.classList.add("active");

    const stepId = step.dataset.step;
    const details = pipelineDetails[stepId];

    if (details && pipelineDetailBox) {
      pipelineDetailBox.innerHTML = `
        <h4 class="text-color-cyan font-bold text-lg mb-2">${details.title}</h4>
        <p class="text-gray-300 text-sm mb-4 leading-relaxed">${details.desc}</p>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2 pt-3 border-t border-white-08">
          <div>
            <span class="text-xs text-gray-500 uppercase block font-semibold">Active State / Metric</span>
            <span class="text-sm font-mono text-white">${details.metric}</span>
          </div>
          <div>
            <span class="text-xs text-gray-500 uppercase block font-semibold">Verification Method</span>
            <span class="text-sm font-mono text-color-green">${details.check}</span>
          </div>
        </div>
      `;
    }
  });
});

// Artifact Explorer Interactive Folder Clicker
const folderItems = document.querySelectorAll(".folder-item");
const explorerDetails = document.getElementById("explorer-details");

const folderData = {
  "tasks": {
    title: "tasks/ Directory",
    desc: "Stores task handoffs, workspace orchestration guidelines, durable task logs, and execution summaries.",
    allowed: "Task instructions, task checklists, execution workflows.",
    forbidden: "Secrets, passwords, raw credentials, local path overrides."
  },
  "reports": {
    title: "reports/ Directory",
    desc: "Contains final synthesized reports, task outcomes, and reports generated upon task completion. Used as the main deliverable path.",
    allowed: "Research reports, incident post-mortems, status updates, markdown files.",
    forbidden: "Executable scripts, raw data dumps, secret files."
  },
  "briefs": {
    title: "research/briefs/ Directory",
    desc: "Contains research briefs outlining questions, scope, regions, exclusions, output formatting, and freshness requirements.",
    allowed: "Fresh research briefs (*.md format) mapping out specific analysis queries.",
    forbidden: "Personal credentials, unverified code fragments."
  },
  "sources": {
    title: "research/sources/ Directory",
    desc: "Durable evidence list for research tasks. Standardized JSONL file format representing verified web sources (Source Ledger).",
    allowed: "JSONL files matching structure: <code>{url, title, publisher, retrieved_at, relevance, trust_note}</code>.",
    forbidden: "Plain URLs list without details, local directory dumps."
  },
  "notes": {
    title: "research/notes/ Directory",
    desc: "Scribbles, informal observations, conflicting evidence analysis, notes on uncertain claims, and source conflicts discovered during web verification.",
    allowed: "Markdown memos, source analysis scratch notes.",
    forbidden: "SSH keys, credential files."
  },
  "artifacts": {
    title: "artifacts/ Directory",
    desc: "Holds general assets, temporary files, visual mockups, and non-secret outputs that do not fit standard report or research paths.",
    allowed: "Static images, UI mockups, non-sensitive JSON configurations.",
    forbidden: "<code>.env</code>, SSH keys, <code>auth.json</code>, raw database files."
  }
};

folderItems.forEach(item => {
  item.addEventListener("click", () => {
    folderItems.forEach(fi => fi.classList.remove("active"));
    item.classList.add("active");

    const folderId = item.dataset.folder;
    const data = folderData[folderId];

    if (data && explorerDetails) {
      explorerDetails.innerHTML = `
        <h4 class="text-white font-bold text-lg mb-2 flex items-center gap-2">
          <svg class="w-5 h-5 text-color-cyan" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"></path>
          </svg>
          ${data.title}
        </h4>
        <p class="text-gray-300 text-sm mb-4 leading-relaxed">${data.desc}</p>
        
        <div class="mb-3">
          <span class="text-xs text-color-green uppercase font-semibold block mb-1">✓ Allowed Content</span>
          <div class="text-xs bg-green-900-10 border border-green-800-20 rounded p-2 text-green-300 font-mono">
            ${data.allowed}
          </div>
        </div>

        <div>
          <span class="text-xs text-color-red uppercase font-semibold block mb-1">⚠ Forbidden Outputs</span>
          <div class="text-xs bg-red-900-10 border border-red-800-20 rounded p-2 text-red-300 font-mono">
            ${data.forbidden}
          </div>
        </div>
      `;
    }
  });
});

// Initialize on window load
window.addEventListener("DOMContentLoaded", () => {
  // Select first terminal command to run automatically
  const initialBtn = document.querySelector(".console-btn[data-command='status']");
  if (initialBtn) {
    initialBtn.click();
  }

  // Select first step in pipeline
  const initialStep = document.querySelector(".pipeline-step-card[data-step='trigger']");
  if (initialStep) {
    initialStep.click();
  }

  // Select first folder in explorer
  const initialFolder = document.querySelector(".folder-item[data-folder='tasks']");
  if (initialFolder) {
    initialFolder.click();
  }
});
