import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { firefox } from "playwright-core";
import { launchOptions } from "camoufox-js";

const userId = process.env.CAMOFOX_LOGIN_USER_ID || "hermes-issue-43";
const targetUrl =
  process.env.DISCORD_LOGIN_URL ||
  "https://discord.com/channels/1511736678371299573/1511955672558997547";
const profileDir =
  process.env.CAMOFOX_PROFILE_DIR || path.join(process.env.HOME, ".camofox", "profiles");
const safeUserDir = crypto.createHash("sha256").update(String(userId)).digest("hex").slice(0, 32);
const userDir = path.join(profileDir, safeUserDir);
const storageStatePath = path.join(userDir, "storage-state.json");
const metaPath = path.join(userDir, "meta.json");

await fs.mkdir(userDir, { recursive: true });

let storageState;
try {
  await fs.access(storageStatePath);
  storageState = storageStatePath;
  console.log(`[discord-login-helper] restoring ${storageStatePath}`);
} catch {
  console.log("[discord-login-helper] no existing storage state");
}

const options = await launchOptions({
  headless: false,
  os: "macos",
  humanize: true,
  enable_cache: true,
});

console.log("[discord-login-helper] launching headed Camoufox");
const browser = await firefox.launch(options);
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  storageState,
});
const page = await context.newPage();
await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 45_000 }).catch((err) => {
  console.error(`[discord-login-helper] navigation failed ${targetUrl}: ${err.message}`);
});
await page.bringToFront().catch(() => {});

async function save(reason) {
  const tmpStorage = `${storageStatePath}.tmp-${process.pid}`;
  const tmpMeta = `${metaPath}.tmp-${process.pid}`;
  await context.storageState({ path: tmpStorage });
  await fs.rename(tmpStorage, storageStatePath);
  await fs.writeFile(
    tmpMeta,
    JSON.stringify({ userId, updatedAt: new Date().toISOString(), reason, storageStatePath }, null, 2),
  );
  await fs.rename(tmpMeta, metaPath);
  console.log(`[discord-login-helper] saved ${reason} -> ${storageStatePath}`);
}

const interval = setInterval(() => {
  save("interval").catch((err) => console.error(`[discord-login-helper] save failed: ${err.message}`));
}, 15_000);

async function shutdown(signal) {
  console.log(`[discord-login-helper] ${signal} received`);
  clearInterval(interval);
  await save(signal).catch((err) => console.error(`[discord-login-helper] final save failed: ${err.message}`));
  await browser.close().catch(() => {});
  process.exit(0);
}

process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));

console.log("[discord-login-helper] ready. Log in via Screen Sharing, then tell Codex when done.");
await new Promise(() => {});
