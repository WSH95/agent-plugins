import { spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { excludeLedger, isProcessAlive, writeAtomic } from "./ledger.ts";
import type { ProcessIdentity } from "./ledger.ts";
import { identityOf } from "./process.ts";
import { holdsConfig } from "./project.ts";

// `watch_page` (design section 10): the project's one read-only watch page for a host
// session to give its user. The page is `cross-agent watch --web`'s, served by a watcher
// this module starts detached from the project root, which outlives the session that
// started it and ends by itself once it has been idle for `WATCH_IDLE_SECONDS`. Its
// identity and address are kept in `.cross-agent/watch.json`, at 0600 because the token in
// the address is the page's whole key, and the next call answers the same address for as
// long as that watcher is alive and answers. A watcher this module did not start in this
// call is never signalled: a state file proves no more than that its pid was a watcher
// once.

/** How long the watcher waits with no page open and no task active before it ends: 10 minutes. */
export const WATCH_IDLE_SECONDS = 600;

/** How long a new watcher has to say it listens before it is stopped. */
const LISTEN_MS = 15_000;

/** How long a running watcher's page has to answer before it is taken for gone. */
const ANSWER_MS = 5_000;

/** How much of a watcher's output a refusal quotes, in UTF-16 code units. */
const QUOTED = 2048;

/** The only address a state file may name: the page of a watcher on 127.0.0.1, behind its 256-bit token. */
const PAGE_ADDRESS = /^http:\/\/127\.0\.0\.1:(\d+)\/[A-Za-z0-9_-]{43}$/;

const cliPath = fileURLToPath(new URL("./cli.ts", import.meta.url));

export function watchStatePath(projectRoot: string): string {
  return path.join(projectRoot, ".cross-agent", "watch.json");
}

/** `.cross-agent/watch.json`: the watcher's identity, its port and its page's address. */
export interface WatchState extends ProcessIdentity {
  port: number;
  url: string;
}

export type WatchPage =
  /** `started` is true when this call started the watcher, false when it answers one already running. */
  | { ok: true; url: string; port: number; pid: number; started: boolean }
  | { ok: false; reason: string };

/** Whether `url` is a page address and its port is `port`, one a page can listen on: 1 to 65535. */
function isPageAddress(url: string, port: number): boolean {
  const match = PAGE_ADDRESS.exec(url);
  return match !== null && Number(match[1]) === port && port >= 1 && port <= 65_535;
}

/** The state file as a `WatchState`, or null where it is missing, unreadable or of any other shape. */
function readState(file: string): WatchState | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return null;
  const { pid, startTime, bootId, port, url } = parsed as Record<string, unknown>;
  if (typeof pid !== "number" || !Number.isSafeInteger(pid) || pid <= 0) return null;
  if (typeof startTime !== "string" || typeof bootId !== "string") return null;
  if (typeof port !== "number" || typeof url !== "string" || !isPageAddress(url, port)) return null;
  return { pid, startTime, bootId, port, url };
}

/**
 * Whether the page at `url`, a loopback address, answers 200 within `ANSWER_MS`: no agent,
 * so no proxy either. A request that cannot even be made answers nothing.
 */
function answers(url: string): Promise<boolean> {
  return new Promise((resolve) => {
    let request: http.ClientRequest;
    try {
      request = http.get(url, { agent: false, signal: AbortSignal.timeout(ANSWER_MS) }, (response) => {
        response.resume();
        resolve(response.statusCode === 200);
      });
    } catch {
      // A safety net: `readState` admits only a loopback page address, which `http.get`
      // takes, so this catches an address it would still refuse, answered as no page rather
      // than as a failed `watch_page`.
      resolve(false);
      return;
    }
    request.on("error", () => resolve(false));
  });
}

/**
 * A new watcher for the project at `projectRoot`, detached in its own group and session,
 * answered once it says it listens and its state file is written. It starts from the root
 * with no `CROSS_AGENT_*` variable, so it carries no task's marker for any cleanup to take
 * it by. A root holding a config is named to it with `--project`, because a walk from a
 * configured directory can be read elsewhere first — at the main checkout, from a linked
 * worktree with no config at its top. A root with none, which `--project` would refuse, is
 * found from the working directory as the CLI finds a project: the walk that found it.
 */
function start(projectRoot: string, file: string): Promise<WatchPage> {
  const env = Object.fromEntries(Object.entries(process.env).filter(([name]) => !name.startsWith("CROSS_AGENT_")));
  const named = holdsConfig(projectRoot) ? ["--project", projectRoot] : [];
  const child = spawn(process.execPath, [cliPath, "watch", "--web", "--json", "--idle-exit", String(WATCH_IDLE_SECONDS), ...named], {
    cwd: projectRoot, env, detached: true, stdio: ["ignore", "pipe", "ignore"],
  });
  return new Promise((resolve) => {
    let output = "";
    let settled = false;
    const finish = (answer: WatchPage) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(answer);
    };
    // Every signal below goes to the child this call spawned, by its own handle, before this
    // call has answered: that process is provably ours, as no pid read back later is. Its
    // group is signalled only while the child has not exited: between its exit and its
    // `close`, the group it led may already be gone and its id free for another.
    const timer = setTimeout(() => {
      if (child.exitCode === null && child.signalCode === null) {
        try {
          process.kill(-child.pid!, "SIGKILL");
        } catch { /* gone since */ }
      }
      finish({ ok: false, reason: `the watcher did not listen within ${LISTEN_MS / 1000} s, and was stopped` });
    }, LISTEN_MS);
    child.once("error", (error) => finish({ ok: false, reason: `the watcher could not start: ${error.message}` }));
    // `close` rather than `exit`, so everything it printed has been read.
    child.once("close", (code, signal) => {
      const printed = output.trim();
      finish({
        ok: false,
        reason: `the watcher exited ${code ?? signal} before it listened: ${printed.length > QUOTED ? `${printed.slice(0, QUOTED)}…` : printed}`,
      });
    });
    const listened = (url: string, port: number) => {
      const pid = child.pid!;
      const identity = identityOf(pid);
      try {
        if (identity === null) throw new Error(`the watcher ${pid} could not be read in /proc`);
        const state: WatchState = { pid, startTime: identity.startTime, bootId: identity.bootId, port, url };
        // The exclusion before `.cross-agent/` exists, so `git status` never shows it.
        excludeLedger(projectRoot);
        fs.mkdirSync(path.dirname(file), { recursive: true });
        writeAtomic(file, state, 0o600);
      } catch (error) {
        child.kill("SIGTERM");
        finish({ ok: false, reason: `the watcher's state could not be kept, so it was stopped: ${error instanceof Error ? error.message : String(error)}` });
        return;
      }
      // Nothing more is read from it, and nothing of it holds this process open.
      child.stdout!.destroy();
      child.unref();
      finish({ ok: true, url, port, pid, started: true });
    };
    child.stdout!.setEncoding("utf8").on("data", (chunk: string) => {
      if (settled) return;
      output += chunk;
      for (const line of output.split("\n").slice(0, -1)) {
        let event: unknown;
        try {
          event = JSON.parse(line);
        } catch {
          continue;
        }
        const { event: name, url, port } = (event ?? {}) as Record<string, unknown>;
        if (name === "listening" && typeof url === "string" && typeof port === "number" && isPageAddress(url, port)) {
          listened(url, port);
          return;
        }
      }
    });
  });
}

/**
 * The address of the project's watch page: the watcher `.cross-agent/watch.json` names when
 * it is alive, by its identity, and its page answers, or else a new one this call starts,
 * whose state replaces the file. A watcher the file names that is not reused is left as it
 * is: it ends by itself once idle.
 */
export async function watchPage(projectRoot: string): Promise<WatchPage> {
  const file = watchStatePath(projectRoot);
  const state = readState(file);
  if (state !== null && isProcessAlive(state) && await answers(state.url)) {
    return { ok: true, url: state.url, port: state.port, pid: state.pid, started: false };
  }
  return start(projectRoot, file);
}
