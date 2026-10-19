import fs from "node:fs";
import { setTimeout as delay } from "node:timers/promises";
import { isTerminal, scan } from "./ledger.ts";
import type { TaskRecord, TaskStatus } from "./ledger.ts";
import { lineReader, usageOf } from "./steps.ts";
import type { LineReader, Step, Usage } from "./steps.ts";

/**
 * A task as `follow` reports it: what its record says, and the lead that delegated it,
 * resolved from the same read of the ledger. A `dev-team-engine` lead's specialists carry
 * it as their `parent`; a task the operator delegated carries null.
 */
export interface WatchedTask {
  id: string;
  role: string;
  /** The seat of a many-seat role, present only on a record that has one. */
  seat?: number;
  engine: string;
  model: string | null;
  effort: string | null;
  status: TaskStatus;
  createdAt: number;
  updatedAt: number;
  parentTaskId: string | null;
  resumedFrom: string | null;
  exitCode: number | null;
  reason?: string;
  parent: { id: string; role: string; seat?: number } | null;
}

export type WatchEvent =
  /** A task already active when the watch began; its recent steps follow it. */
  | { event: "following"; task: WatchedTask }
  /** A task first seen after the watch began, whatever its status by then. */
  | { event: "started"; task: WatchedTask }
  /**
   * One step of the task's stream. `follow` sets `at` and `usage` on every step event, and
   * an absent one reads as null: `at` is when the step's line was written, its own
   * timestamp where it has one and else when the loop read it live, null for a line its
   * first pass read with none; `usage` is the figure the line reports, a result event's
   * (`src/steps.ts#usageOf`), null on any other.
   */
  | { event: "step"; task: WatchedTask; step: Step; at?: number | null; usage?: Usage | null }
  /**
   * The task's status changed with no step to show it — stalled, orphaned, cancelling, or
   * running again — as the last `wait`, `check` or reconciliation wrote it. A task first
   * seen launching that turns running gives none: its start was reported already.
   */
  | { event: "status"; task: WatchedTask }
  /** The task's last step has been read and it is followed no longer. */
  | { event: "settled"; task: WatchedTask };

export interface FollowOptions {
  /** Ends the loop: at its next wait, or before its next event. */
  signal: AbortSignal;
  /** The roles followed, each a role or `<role>#<seat>`; every role when absent. */
  roles?: readonly string[];
  /** How many steps of a task already running are replayed first: 10 unless asked otherwise. */
  recent?: number;
  /** How long the loop waits between two reads of the ledger, in milliseconds: 500 unless asked otherwise. */
  intervalMs?: number;
}

/** One followed task: its record as last read, how far into its stream it has read, and its reader. */
interface Followed {
  record: TaskRecord;
  offset: number;
  reader: LineReader;
}

function followed(record: TaskRecord): Followed {
  return { record, offset: 0, reader: lineReader(record.engine, record.cwd) };
}

/** Oldest first, and by id among records created in the same millisecond, so two reads agree. */
function oldestFirst(records: TaskRecord[]): TaskRecord[] {
  return records.sort((left, right) => left.createdAt - right.createdAt || left.id.localeCompare(right.id));
}

/** Whether a record is one of `roles`, by its role or its `<role>#<seat>`: every record when none are named. */
export function matches(record: TaskRecord, roles: readonly string[] | undefined): boolean {
  if (roles === undefined || roles.length === 0) return true;
  return roles.includes(record.role) || (record.seat !== undefined && roles.includes(`${record.role}#${record.seat}`));
}

export function watched(record: TaskRecord, byId: ReadonlyMap<string, TaskRecord>): WatchedTask {
  const lead = record.parentTaskId === undefined || record.parentTaskId === null ? undefined : byId.get(record.parentTaskId);
  return {
    id: record.id, role: record.role, ...(record.seat === undefined ? {} : { seat: record.seat }),
    engine: record.engine, model: record.model ?? null, effort: record.effort ?? null, status: record.status,
    createdAt: record.createdAt, updatedAt: record.updatedAt,
    parentTaskId: record.parentTaskId ?? null, resumedFrom: record.resumedFrom ?? null, exitCode: record.exitCode ?? null,
    ...(record.reason === undefined ? {} : { reason: record.reason }),
    parent: lead === undefined ? null : { id: lead.id, role: lead.role, ...(lead.seat === undefined ? {} : { seat: lead.seat }) },
  };
}

/**
 * The lines of a task's stream past what was read, each read once: up to the last newline
 * while the task runs, so a line its engine is still writing waits for its end, and to the
 * end of the file once it has settled, when nothing more will be written. A stream smaller
 * than what was read was replaced, and is read again from its start by a fresh reader; one
 * replaced by a file at least as large is read on from the old offset.
 */
function readLines(state: Followed, final: boolean): string[] {
  let handle: number;
  try {
    handle = fs.openSync(state.record.logPath, "r");
  } catch (error) {
    // An engine that has said nothing yet has no stream.
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw error;
  }
  try {
    const size = fs.fstatSync(handle).size;
    if (size < state.offset) {
      state.offset = 0;
      state.reader = lineReader(state.record.engine, state.record.cwd);
    }
    if (size === state.offset) return [];
    const buffer = Buffer.alloc(size - state.offset);
    let filled = 0;
    while (filled < buffer.length) {
      const count = fs.readSync(handle, buffer, filled, buffer.length - filled, state.offset + filled);
      if (count === 0) break;
      filled += count;
    }
    const end = final ? filled : buffer.subarray(0, filled).lastIndexOf(0x0a) + 1;
    state.offset += end;
    return buffer.subarray(0, end).toString("utf8").split("\n")
      .map((line) => (line.endsWith("\r") ? line.slice(0, -1) : line))
      .filter((line) => line !== "");
  } finally {
    fs.closeSync(handle);
  }
}

/**
 * The figure a settled task's stream reports, read whole: its last result event's, the
 * stream scanned from its end, or null where it holds none. A stream that does not read is
 * null too, since a figure must never end a watch.
 */
export function lastUsage(record: TaskRecord): Usage | null {
  let text: string;
  try {
    text = fs.readFileSync(record.logPath, "utf8");
  } catch {
    return null;
  }
  const lines = text.split("\n");
  for (let index = lines.length - 1; index >= 0; index--) {
    const line = lines[index];
    const usage = usageOf(record.engine, line.endsWith("\r") ? line.slice(0, -1) : line);
    if (usage !== null) return usage;
  }
  return null;
}

/**
 * Every active task of the project at `root`, followed until `signal` aborts: each task
 * already running is reported with the last `recent` steps of its stream, still-thinking
 * events left out of them, and then each step its engine writes, read every `intervalMs`.
 * A task first seen after the loop began is reported from its first line, however soon it
 * settled; a task settled before it began is never followed. A followed task whose status
 * changes short of settling is reported once per change, before the steps read with it,
 * but for `launching → running`. The ledger and the streams are only read: nothing is
 * written, locked or settled, so a task whose runner died is followed until something else
 * settles it, and a stall shows once a reader of the stall clock has written it.
 */
// @anchor follow
export async function* follow(root: string, options: FollowOptions): AsyncGenerator<WatchEvent> {
  const { signal, roles, recent = 10, intervalMs = 500 } = options;
  // Every id ever read, so a task settled at the start, or one the roles leave out, is
  // never taken for one that has just started.
  const known = new Set<string>();
  const following = new Map<string, Followed>();

  const first = oldestFirst(scan(root).records);
  const byId = new Map(first.map((record) => [record.id, record]));
  for (const record of first) known.add(record.id);
  for (const record of first) {
    if (isTerminal(record.status) || !matches(record, roles)) continue;
    // The whole stream through its reader, so each result is paired with its call however
    // far back the call was; only the last `recent` steps are kept, each with its line's
    // time, which a line read now and not when it was written has only where it says it.
    const state = followed(record);
    const ring: Array<{ step: Step; at: number | null; usage: Usage | null }> = [];
    for (const line of readLines(state, false)) {
      const { steps, at, usage } = state.reader(line);
      for (const step of steps) {
        if (step.kind === "thinking-progress") continue;
        ring.push({ step, at, usage });
        if (ring.length > recent) ring.shift();
      }
    }
    following.set(record.id, state);
    const task = watched(record, byId);
    if (signal.aborted) return;
    yield { event: "following", task };
    for (const { step, at, usage } of ring) {
      if (signal.aborted) return;
      yield { event: "step", task, step, at, usage };
    }
  }

  while (true) {
    try {
      await delay(intervalMs, undefined, { signal });
    } catch (error) {
      if ((error as Error).name === "AbortError") return;
      throw error;
    }
    const records = oldestFirst(scan(root).records);
    const current = new Map(records.map((record) => [record.id, record]));
    // A record that is gone is followed no longer, and said nothing more.
    for (const id of following.keys()) if (!current.has(id)) following.delete(id);
    for (const record of records) {
      let state = following.get(record.id);
      if (state === undefined) {
        if (known.has(record.id)) continue;
        known.add(record.id);
        if (!matches(record, roles)) continue;
        state = followed(record);
        following.set(record.id, state);
        if (signal.aborted) return;
        yield { event: "started", task: watched(record, current) };
      }
      const was = state.record.status;
      state.record = record;
      const task = watched(record, current);
      // A settled task's stream is whole: its last line is read whether or not it ended.
      const settled = isTerminal(record.status);
      if (!settled && record.status !== was && !(was === "launching" && record.status === "running")) {
        if (signal.aborted) return;
        yield { event: "status", task };
      }
      // A line with no time of its own was written since the last read: it takes this one's.
      const lines = readLines(state, settled);
      const seen = Date.now();
      for (const line of lines) {
        const { steps, at, usage } = state.reader(line);
        for (const step of steps) {
          if (signal.aborted) return;
          yield { event: "step", task, step, at: at ?? seen, usage };
        }
      }
      if (settled) {
        following.delete(record.id);
        if (signal.aborted) return;
        yield { event: "settled", task };
      }
    }
  }
}
