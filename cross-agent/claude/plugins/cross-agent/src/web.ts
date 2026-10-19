import { randomBytes, timingSafeEqual } from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import { find, InvalidRecordError, isTaskId, isTerminal, scan } from "./ledger.ts";
import type { TaskRecord } from "./ledger.ts";
import { journalState, journalWatch, oldestFirst, runIndex, runLayout, runView, slugOf } from "./runs.ts";
import type { JournalState, RunIndex } from "./runs.ts";
import { ownUsage, sumUsage } from "./steps.ts";
import type { Usage } from "./steps.ts";
import { follow, lastUsage, matches, watched } from "./watch.ts";
import type { WatchedTask } from "./watch.ts";
import { frameOf, historyFrame, PAGE_CSS, pageHtml, runFrame, stepGroups } from "./webrender.ts";
import type { PageFrame, Place, Totals } from "./webrender.ts";

// `cross-agent watch --web` (design section 10): the follow loop under `watch`, run once
// and served as a read-only live page on 127.0.0.1. Every route is GET and sits under a
// random token; a request whose Host is not this server's own address is refused, so a
// page another site loads into the browser cannot reach it by a rebound name; every
// response carries a CSP that allows no inline script. Each event is rendered once into a
// frame (`src/webrender.ts`), kept in a bounded replay log and written to every open
// stream, so a page that reloads gets every frame again, and every task's entry with it.
// Beside the events, the server keeps the runs their tasks are in (`src/runs.ts`), each
// sent as a frame of its own when it opens and again whenever what it shows changes, and
// the figure each task's engine reported, from which each task's own and each run's totals
// are reckoned.

/**
 * How much rendered SSE text the replay log keeps, in UTF-16 code units. It bounds the
 * replay, not the process: the follow loop's first pass holds every running task's parsed
 * steps while it reads them, and Node buffers whatever a stalled page has not read.
 */
export const REPLAY_LIMIT = 64 * 1024 * 1024;

/**
 * The frames a page that connects gets first. `add` gives a frame the next id and keeps
 * it — but a still-thinking frame, which goes out live with no id and is never kept — and
 * returns the SSE text to write to every open stream; past `limit`, the oldest frames are
 * dropped at once, down to three quarters of it. `since` is the text of every kept frame
 * after `lastEventId`: everything kept for a page that names none, a number that is no id,
 * or one older than the oldest kept.
 */
export function replayLog(limit: number): { add(frame: PageFrame): string; since(lastEventId: string | undefined): string } {
  // Ids are contiguous from 1, so the first kept frame's id places any other.
  const kept: string[] = [];
  let firstId = 1;
  let size = 0;
  return {
    add(frame) {
      const data = `data: ${JSON.stringify(frame)}\n\n`;
      if ("kind" in frame && frame.kind === "thinking-progress") return data;
      const text = `id: ${firstId + kept.length}\n${data}`;
      kept.push(text);
      size += text.length;
      if (size > limit) {
        let drop = 0;
        while (drop < kept.length && size > limit * 0.75) size -= kept[drop++].length;
        kept.splice(0, drop);
        firstId += drop;
      }
      return text;
    },
    since(lastEventId) {
      const last = lastEventId !== undefined && /^\d+$/.test(lastEventId) ? Number(lastEventId) : 0;
      return kept.slice(Math.max(0, last - firstId + 1)).join("");
    },
  };
}

/**
 * What every stream gets right after its replay, a fresh page's or a reconnect's, empty or
 * not: the frame that says the replay has ended, so the page knows the frames after it are
 * live. It has no id, so the replay log never keeps it, it takes none, and the page's
 * `Last-Event-ID` stays where the replay left it.
 */
const REPLAYED = `data: ${JSON.stringify({ event: "replayed" })}\n\n`;

export interface WebWatchOptions {
  /** Ends the watch: the follow loop stops, and the server closes every connection. */
  signal: AbortSignal;
  /** The roles followed, as `follow` takes them; every role when absent. */
  roles?: readonly string[];
  /** The port to listen on; a random free one when absent or 0. */
  port?: number;
  /** How long the follow loop waits between two reads of the ledger, in milliseconds. */
  intervalMs?: number;
  /**
   * How long the watch may go with no page's stream open and no task it follows active
   * before it ends by itself, as an abort ends it, in milliseconds; never when absent.
   */
  idleMs?: number;
}

export interface WebWatch {
  /** `http://127.0.0.1:<port>/<token>`, the page. */
  url: string;
  port: number;
  /** Settles once the watch has stopped and its server has closed: rejected with the follow loop's error when it failed. */
  done: Promise<void>;
}

/** The headers every response carries, a refusal's among them. */
const HEADERS: Record<string, string> = {
  "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "Cache-Control": "no-store",
};

/** A refusal: its code and a fixed body, never anything of the request. */
function refuse(response: http.ServerResponse, status: number, body: string, headers: Record<string, string> = {}): void {
  response.writeHead(status, { "Content-Type": "text/plain; charset=utf-8", ...headers });
  response.end(body);
}

/** One of the page's own files, whole. */
function send(response: http.ServerResponse, type: string, body: string): void {
  response.writeHead(200, { "Content-Type": `${type}; charset=utf-8` });
  response.end(body);
}

/** A record the ledger holds and can read, or null: a file that is gone or does not read is no round to show. */
function readable(root: string, id: string): TaskRecord | null {
  try {
    return find(root, id);
  } catch (error) {
    if (error instanceof InvalidRecordError) return null;
    throw error;
  }
}

/** A record as a task's entry and head read it, its lead resolved from the ledger as `follow` resolves it from a scan. */
function asWatched(root: string, record: TaskRecord): WatchedTask {
  const leadId = record.parentTaskId;
  const lead = typeof leadId === "string" && isTaskId(leadId) ? readable(root, leadId) : null;
  return watched(record, new Map(lead === null ? [] : [[lead.id, lead]]));
}

/**
 * The rounds a resume continues that the page has no entry for, oldest first: its
 * `resumedFrom` chain walked up through the ledger until an id the page has opened, one
 * outside the ledger's alphabet, one met before on this walk, or one no readable record
 * holds. A round still active would have been opened before its resume — `follow` opens
 * every active record oldest first, and a resume has its round's role — so each one here
 * settled before the watch began.
 */
function unopenedRounds(root: string, task: WatchedTask, opened: { has(id: string): boolean }): TaskRecord[] {
  const rounds: TaskRecord[] = [];
  const seen = new Set([task.id]);
  let id = task.resumedFrom;
  while (id !== null && !opened.has(id) && isTaskId(id) && !seen.has(id)) {
    seen.add(id);
    const record = readable(root, id);
    if (record === null) break;
    rounds.unshift(record);
    id = record.resumedFrom ?? null;
  }
  return rounds;
}

/**
 * The project at `root` watched as a page: listening on 127.0.0.1 at `port`, a random free
 * one by default, before anything is followed, and once listening, every active task
 * followed from its first step until `signal` aborts, or, given `idleMs`, until it has been
 * idle that long, and every run its tasks are in kept and sent as it changes. A listen that
 * fails rejects; a follow loop or a journal read that fails closes the server and rejects
 * `done`. Nothing is written.
 */
export async function serveWatch(root: string, options: WebWatchOptions): Promise<WebWatch> {
  const { signal, roles, port = 0, intervalMs, idleMs } = options;
  // Idle is the same end as an abort: the follow loop stops, and the server closes. So is a
  // journal read that failed, which `done` then rejects with.
  const idle = new AbortController();
  const failure = new AbortController();
  let failed: { error: unknown } | null = null;
  const stopped = AbortSignal.any([signal, idle.signal, failure.signal]);
  // Read once, before anything is served: a config changed later needs a new watch.
  const layout = runLayout(root);
  // What keeps the watch from being idle: a page's stream open, or a task it follows that
  // a `following` or `started` event opened and no `settled` event has closed. The clock
  // starts at the listen, and again whenever a request passes the token check, a page
  // leaves or a task settles.
  const active = new Set<string>();
  let quietSince = 0;
  const script = fs.readFileSync(new URL("./webclient.js", import.meta.url), "utf8");
  const token = randomBytes(32).toString("base64url");
  const expected = Buffer.from(token);
  const log = replayLog(REPLAY_LIMIT);
  const subscribers = new Set<http.ServerResponse>();
  // Set once listening, which is before any request can arrive.
  let hosts = new Set<string>();

  const server = http.createServer((request, response) => {
    for (const [name, value] of Object.entries(HEADERS)) response.setHeader(name, value);
    // Host first: a page that reaches this address through a name its site rebound sends that name.
    if (!hosts.has((request.headers.host ?? "").toLowerCase())) return refuse(response, 403, "forbidden\n");
    const match = /^\/([^/]*)(\/.*)?$/.exec(request.url ?? "");
    const given = Buffer.from(match?.[1] ?? "");
    if (match === null || given.length !== expected.length || !timingSafeEqual(given, expected)) return refuse(response, 404, "not found\n");
    // Anyone holding the token is about to watch: a page loading before its stream opens, or
    // `watch_page` checking that the page answers before it hands the address out.
    quietSince = Date.now();
    if (request.method !== "GET") return refuse(response, 405, "method not allowed\n", { Allow: "GET" });
    switch (match[2] ?? "") {
      case "": case "/":
        return send(response, "text/html", pageHtml(token, root));
      case "/app.js":
        return send(response, "text/javascript", script);
      case "/style.css":
        return send(response, "text/css", PAGE_CSS);
      case "/events": {
        response.writeHead(200, { "Content-Type": "text/event-stream; charset=utf-8", Connection: "keep-alive" });
        response.flushHeaders();
        // The replay, its end and the subscription in one synchronous block: no frame
        // broadcast between them is missed, none is sent twice, and every live one follows
        // the end.
        const lastEventId = request.headers["last-event-id"];
        const replay = log.since(typeof lastEventId === "string" ? lastEventId : undefined);
        if (replay !== "") response.write(replay);
        response.write(REPLAYED);
        subscribers.add(response);
        const leave = () => {
          if (subscribers.delete(response)) quietSince = Date.now();
        };
        response.on("close", leave);
        response.on("error", leave);
        return;
      }
      default:
        return refuse(response, 404, "not found\n");
    }
  });

  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", () => {
      server.off("error", reject);
      resolve();
    });
  });
  const bound = (server.address() as { port: number }).port;
  hosts = new Set([`127.0.0.1:${bound}`, `localhost:${bound}`]);
  quietSince = Date.now();
  const timer = idleMs === undefined ? undefined : setInterval(() => {
    if (subscribers.size === 0 && active.size === 0 && Date.now() - quietSince >= idleMs) idle.abort();
  }, Math.min(idleMs, 5_000));
  // The journal reader's timer, set when the follow loop starts.
  let journalTimer: ReturnType<typeof setInterval> | undefined;
  // The timers are cleared here, whatever ended the watch: left running, either alone would
  // keep the process alive after a SIGTERM.
  const close = () => new Promise<void>((resolve) => {
    clearInterval(timer);
    clearInterval(journalTimer);
    server.close(() => resolve());
    server.closeAllConnections();
  });

  const broadcast = (frame: PageFrame) => {
    const text = log.add(frame);
    for (const subscriber of subscribers) subscriber.write(text);
  };
  // Where each task the page has an entry for went, so a resume links its round's entry
  // only where there is one, and no task is sent as history once it has an entry.
  const placeOf = new Map<string, Place>();
  // Each step's group, every result paired with the call it closes: fed every event, in order.
  const groupOf = stepGroups();

  // The runs (design section 10, "Runs"): the ledger indexed, read again when it lacks a
  // task the loop reports and at most once per journal tick; each open run's members, as
  // their records read with the statuses the loop has reported since, and the frame last
  // sent for it; the open runs each task worktree is in; and those worktrees' journals as
  // last read. A run opens when a task in it is first seen, or its journal changes.
  let index: RunIndex = runIndex([], layout);
  const runs = new Map<string, { members: Map<string, TaskRecord>; sent: string }>();
  const slugRuns = new Map<string, Set<string>>();
  const journals = new Map<string, JournalState>();
  // Set as the follow loop starts: a member settled before it has no event, and is sent as history.
  let watchStart = 0;
  const changedJournals = journalWatch(root);
  // The one guard on every member a run takes: the roles the watch follows.
  const admit = (record: TaskRecord) => matches(record, roles);
  const reindex = () => {
    index = runIndex(scan(root).records, layout);
  };
  const recordOf = (id: string): TaskRecord | undefined => {
    if (!index.byId.has(id)) reindex();
    return index.byId.get(id);
  };
  const placeIn = (record: TaskRecord): Place => ({ run: index.keys.get(record.id) ?? "", chain: index.chains.get(record.id) ?? null });
  // Tokens and cost (design section 10): what each task's engine reported, by id — set from
  // the loop's step events, and for a record that settled with none read, its stream's last
  // result event, read once — and from it each task's own figure and each run's totals.
  const reported = new Map<string, Usage | null>();
  const reportedOf = (record: TaskRecord): Usage | null => {
    if (reported.has(record.id)) return reported.get(record.id)!;
    // An active task's figure is none until its loop reads one: its stream is still growing.
    if (!isTerminal(record.status)) return null;
    const read = lastUsage(record);
    reported.set(record.id, read);
    return read;
  };
  // A round's own figure: a round-scoped one as it is, and a session's less the figure of
  // the nearest earlier round of its chain that reported one, rounds with none passed over.
  const ownOf = (record: TaskRecord | undefined): Usage | null => {
    if (record === undefined) return null;
    const usage = reportedOf(record);
    if (usage === null || usage.scope === "round") return usage;
    const seen = new Set([record.id]);
    let id = record.resumedFrom ?? null;
    while (typeof id === "string" && !seen.has(id)) {
      seen.add(id);
      const round = index.byId.get(id);
      if (round === undefined) break;
      const before = reportedOf(round);
      if (before !== null) return ownUsage(usage, before);
      id = round.resumedFrom ?? null;
    }
    return usage;
  };
  // A run's totals, over the members that have finished: a running one joins once it has.
  const totalsOf = (members: Map<string, TaskRecord>): Totals => {
    const finished = [...members.values()].filter((member) => isTerminal(member.status));
    return { usage: sumUsage(finished.map(ownOf).filter((usage): usage is Usage => usage !== null)), finished: finished.length, tasks: members.size };
  };
  const join = (key: string, record: TaskRecord) => {
    if (!admit(record)) return;
    runs.get(key)!.members.set(record.id, record);
    const slug = slugOf(record, layout);
    if (slug === null) return;
    slugRuns.set(slug, (slugRuns.get(slug) ?? new Set()).add(key));
    if (!journals.has(slug)) journals.set(slug, journalState(root, slug));
  };
  // A run's frame, sent only when it differs from the one last sent: a change to its totals
  // alone is one.
  const sendRun = (key: string) => {
    const run = runs.get(key)!;
    const frame = runFrame(runView(key, run.members.values(), index.byId, layout, journals), totalsOf(run.members));
    const text = JSON.stringify(frame);
    if (text === run.sent) return;
    run.sent = text;
    broadcast(frame);
  };
  // A run opened: every record the index puts in it joined and the run sent; what it
  // returns is its members that settled before the watch began and have no entry, oldest
  // first, for the caller to send as history.
  const openRun = (key: string): TaskRecord[] => {
    runs.set(key, { members: new Map(), sent: "" });
    for (const record of index.byId.values()) if (index.keys.get(record.id) === key) join(key, record);
    sendRun(key);
    return [...runs.get(key)!.members.values()]
      .filter((member) => isTerminal(member.status) && member.updatedAt < watchStart && !placeOf.has(member.id))
      .sort(oldestFirst);
  };
  const sendHistory = (record: TaskRecord) => {
    const place = placeIn(record);
    broadcast(historyFrame(watched(record, index.byId), typeof record.resumedFrom === "string" && placeOf.has(record.resumedFrom), place, ownOf(record)));
    placeOf.set(record.id, place);
  };
  // Each changed journal: a run that holds it sent again; one that holds none, and was not
  // closed before the watch began, opens the runs of the tasks the ledger has in its
  // worktree, or joins them to their runs where those are open.
  const readJournals = () => {
    let fresh = false;
    for (const slug of changedJournals()) {
      const state = journalState(root, slug);
      const held = slugRuns.get(slug);
      if (held !== undefined) {
        journals.set(slug, state);
        for (const key of held) sendRun(key);
        continue;
      }
      if (state.kind === "read" && state.journal.steps.some((entry) => entry.step === "branch-deleted" && entry.at < watchStart)) continue;
      if (!fresh) {
        reindex();
        fresh = true;
      }
      journals.set(slug, state);
      const joined = new Set<string>();
      for (const record of index.slugs.get(slug) ?? []) {
        const key = index.keys.get(record.id) ?? "";
        if (key === "" || !admit(record)) continue;
        if (runs.has(key)) {
          join(key, record);
          joined.add(key);
        } else {
          for (const member of openRun(key)) sendHistory(member);
        }
      }
      for (const key of joined) sendRun(key);
      if (!slugRuns.has(slug)) journals.delete(slug);
    }
  };

  const run = async () => {
    watchStart = Date.now();
    changedJournals();
    journalTimer = setInterval(() => {
      try {
        readJournals();
      } catch (error) {
        failed ??= { error };
        failure.abort();
      }
    }, intervalMs ?? 500);
    for await (const event of follow(root, {
      signal: stopped, recent: Infinity, ...(roles === undefined ? {} : { roles }), ...(intervalMs === undefined ? {} : { intervalMs }),
    })) {
      const { task } = event;
      // A result event's figure is the task's from now on, a later one replacing it.
      if (event.event === "step" && event.usage != null) reported.set(task.id, event.usage);
      if (event.event === "following" || event.event === "started") active.add(task.id);
      else if (event.event === "settled") {
        active.delete(task.id);
        quietSince = Date.now();
      }
      let place = placeOf.get(task.id);
      if (place === undefined) {
        // First seen: its run joined, or opened with the history older than it first.
        const record = recordOf(task.id);
        place = record === undefined ? { run: "", chain: null } : placeIn(record);
        let younger: TaskRecord[] = [];
        if (record !== undefined && place.run !== "") {
          if (runs.has(place.run)) join(place.run, record);
          else {
            const history = openRun(place.run).filter((member) => member.id !== task.id);
            for (const member of history) if (oldestFirst(member, record) < 0) sendHistory(member);
            younger = history.filter((member) => oldestFirst(member, record) > 0);
          }
        }
        for (const round of unopenedRounds(root, task, placeOf)) {
          const key = index.keys.get(round.id) ?? "";
          const roundPlace = { run: runs.has(key) ? key : "", chain: index.chains.get(round.id) ?? null };
          broadcast(historyFrame(asWatched(root, round), typeof round.resumedFrom === "string" && placeOf.has(round.resumedFrom), roundPlace, ownOf(round)));
          placeOf.set(round.id, roundPlace);
        }
        broadcast(frameOf(event, task.resumedFrom !== null && placeOf.has(task.resumedFrom), groupOf(event), place, ownOf(record)));
        placeOf.set(task.id, place);
        for (const member of younger) sendHistory(member);
      } else {
        broadcast(frameOf(event, task.resumedFrom !== null && placeOf.has(task.resumedFrom), groupOf(event), place, ownOf(index.byId.get(task.id))));
      }
      // A status the loop reports is the member's from now on, and its run is sent again if
      // that changed what it shows. A step sends no run: a figure a running task's step
      // reports joins its run's totals at the task's settlement.
      if (place.run !== "" && event.event !== "step") {
        const { members } = runs.get(place.run)!;
        const member = members.get(task.id);
        if (member !== undefined) members.set(task.id, { ...member, status: task.status, updatedAt: task.updatedAt });
        sendRun(place.run);
      }
    }
  };
  // An abort before the server listened closes it at once, and nothing is followed.
  const done = stopped.aborted ? close() : run().then(async () => {
    await close();
    if (failed !== null) throw failed.error;
  }, async (error: unknown) => {
    await close();
    throw error;
  });
  return { url: `http://127.0.0.1:${bound}/${token}`, port: bound, done };
}
