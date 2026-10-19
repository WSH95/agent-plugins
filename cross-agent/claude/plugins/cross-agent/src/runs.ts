import fs from "node:fs";
import path from "node:path";
import { loadConfigWithMode } from "./config.ts";
import { isSlug, listJournals, readJournal } from "./journal.ts";
import type { Journal } from "./journal.ts";
import { isTerminal } from "./ledger.ts";
import type { TaskRecord } from "./ledger.ts";
import { CONSULT_ROLE, DEFAULT_GIT_POLICY, gitPolicy } from "./modes.ts";
import { canonicalPath } from "./reservation.ts";

// `cross-agent watch --web`'s runs (design section 10): the Inspector's tasks grouped where
// the data links them — a lead's specialists by `parentTaskId`, one task worktree's tasks by
// slug, and a resume chain's rounds by `resumedFrom` — each run's stages mapped onto the
// dev-team loop, and its gate and merge checkpoints read from the task worktree's git
// journal. Everything here reads; nothing is written, and only `runLayout`, `journalState`
// and `journalWatch` read anything but their arguments.

/** Where the project keeps its task worktrees, canonical, and the role its mode runs a lead as, if any. */
export interface RunLayout {
  worktreeDir: string;
  leadRole: string | null;
}

/**
 * The project's layout as its config says once, read and never written: the mode's worktree
 * directory, canonical, and its lead role. A config that does not load gives this build's
 * implicit directory and no lead role, so a watch never stops for it; a lead is then still
 * known once a specialist names it.
 */
export function runLayout(root: string): RunLayout {
  try {
    const { mode } = loadConfigWithMode(root);
    return { worktreeDir: canonicalPath(path.join(root, gitPolicy(mode).worktreeDir)), leadRole: mode.lead.role ?? null };
  } catch {
    return { worktreeDir: canonicalPath(path.join(root, DEFAULT_GIT_POLICY.worktreeDir)), leadRole: null };
  }
}

/** The task worktree a record works in: the one its record names, or the directory its `cwd` is under the worktree directory. */
export function slugOf(record: TaskRecord, layout: RunLayout): string | null {
  if (isSlug(record.worktree?.slug)) return record.worktree.slug;
  const name = path.basename(record.cwd);
  return path.dirname(record.cwd) === layout.worktreeDir && isSlug(name) ? name : null;
}

/**
 * The round a resume chain starts from: `resumedFrom` walked while the ledger holds the id
 * and the walk has not met it, or null for a record that resumes none the ledger holds.
 */
export function chainOf(record: TaskRecord, byId: ReadonlyMap<string, TaskRecord>): string | null {
  const met = new Set([record.id]);
  let root: string | null = null;
  let id = record.resumedFrom ?? null;
  while (id !== null && !met.has(id)) {
    const next = byId.get(id);
    if (next === undefined) break;
    met.add(id);
    root = id;
    id = next.resumedFrom ?? null;
  }
  return root;
}

/** Every record of the ledger, with the run and the chain each belongs to and the records of each task worktree, oldest first. */
export interface RunIndex {
  byId: ReadonlyMap<string, TaskRecord>;
  /** Each record's run: `lead:<id>`, `worktree:<slug>`, or `""` for a record nothing links. */
  keys: ReadonlyMap<string, string>;
  chains: ReadonlyMap<string, string | null>;
  slugs: ReadonlyMap<string, readonly TaskRecord[]>;
}

/** Oldest first, and by id among records created in the same millisecond: the order of a run's members and of the page's entries. */
export function oldestFirst(left: TaskRecord, right: TaskRecord): number {
  return left.createdAt - right.createdAt || (left.id < right.id ? -1 : left.id > right.id ? 1 : 0);
}

/**
 * The runs of `records`. A record with a lead is in its lead's run: `parentTaskId` walked up
 * to the topmost record the ledger holds, the run named by that record's chain, or by the id
 * the walk could not find. A record with none is a lead itself — its run named by its own
 * chain — when its role is the mode's lead role or some record names its chain as its lead.
 * Any other record is in the run of the task worktree it works in, and one in none is in no
 * run.
 */
export function runIndex(records: readonly TaskRecord[], layout: RunLayout): RunIndex {
  const byId = new Map(records.map((record) => [record.id, record]));
  const chains = new Map(records.map((record) => [record.id, chainOf(record, byId)]));
  const rootOf = (record: TaskRecord) => chains.get(record.id) ?? record.id;
  // Every chain some record names as its lead, by its root; an id the ledger lacks as itself.
  const named = new Set<string>();
  for (const record of records) {
    if (typeof record.parentTaskId !== "string") continue;
    const lead = byId.get(record.parentTaskId);
    named.add(lead === undefined ? record.parentTaskId : rootOf(lead));
  }
  const keyOf = (record: TaskRecord): string => {
    if (typeof record.parentTaskId === "string") {
      const met = new Set([record.id]);
      let top: TaskRecord | undefined;
      let id: string | null = record.parentTaskId;
      while (id !== null && !met.has(id)) {
        const next = byId.get(id);
        // An id the ledger lacks names the run: every record under it agrees.
        if (next === undefined) return `lead:${id}`;
        met.add(id);
        top = next;
        id = next.parentTaskId ?? null;
      }
      // A record that names itself ends the walk before it starts, and its id names the run.
      return `lead:${top === undefined ? record.parentTaskId : rootOf(top)}`;
    }
    const root = rootOf(record);
    if ((layout.leadRole !== null && record.role === layout.leadRole) || named.has(root)) return `lead:${root}`;
    const slug = slugOf(record, layout);
    return slug === null ? "" : `worktree:${slug}`;
  };
  const keys = new Map(records.map((record) => [record.id, keyOf(record)]));
  const slugs = new Map<string, TaskRecord[]>();
  for (const record of [...records].sort(oldestFirst)) {
    const slug = slugOf(record, layout);
    if (slug === null) continue;
    const same = slugs.get(slug);
    if (same === undefined) slugs.set(slug, [record]);
    else same.push(record);
  }
  return { byId, keys, chains, slugs };
}

/** A task worktree's journal as last read: none yet, the journal, or the reader's reason it does not read. */
export type JournalState = { kind: "absent" } | { kind: "read"; journal: Journal } | { kind: "unreadable"; reason: string };

/** `slug`'s journal, read and never repaired: a journal that does not read is a state to show, not a throw. */
export function journalState(root: string, slug: string): JournalState {
  try {
    const journal = readJournal(root, slug);
    return journal === null ? { kind: "absent" } : { kind: "read", journal };
  } catch (error) {
    return { kind: "unreadable", reason: error instanceof Error ? error.message : String(error) };
  }
}

/** How long after the journal directory's time changes its listing is still read on every call, for a filesystem whose clock is coarse. */
const JOURNAL_MARGIN_MS = 2_000;

/**
 * A reader of the project's journal changes. Its first call takes each journal's stamp —
 * its inode, size and time — and reports nothing. Each later call stats the journal
 * directory, and only when the directory's time has changed, or is within two seconds of
 * now, lists it and stats each journal: it reports, sorted, every journal whose stamp is new
 * or different. Every writer here writes a journal by an atomic rename into the directory
 * (`src/ledger.ts#writeAtomic`), which changes the directory's time and gives the file a new
 * inode; an edit in place after the margin waits for the next rename. With no directory it
 * reports nothing and creates nothing.
 */
export function journalWatch(root: string): () => string[] {
  const directory = path.resolve(root, ".cross-agent", "journal");
  let stamps: Map<string, string> | null = null;
  let listedAt: number | null = null;
  return () => {
    let time: number;
    try {
      time = fs.statSync(directory).mtimeMs;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      // No journal yet: every one that appears after this call is new.
      stamps = new Map();
      listedAt = null;
      return [];
    }
    if (stamps !== null && time === listedAt && Date.now() - time >= JOURNAL_MARGIN_MS) return [];
    listedAt = time;
    const next = new Map<string, string>();
    for (const slug of listJournals(root)) {
      try {
        const stat = fs.statSync(path.join(directory, `${slug}.json`));
        next.set(slug, `${stat.ino}:${stat.size}:${stat.mtimeMs}`);
      } catch (error) {
        // A journal removed between the listing and its stat is gone.
        if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
      }
    }
    const previous = stamps;
    stamps = next;
    return previous === null ? [] : [...next].filter(([slug, stamp]) => previous.get(slug) !== stamp).map(([slug]) => slug);
  };
}

/**
 * The roles of the dev-team loop's stages, in its order (`modes/dev-team/SKILL.md`, steps 2
 * to 9): a run with any other member but a lead's consultant maps onto no loop this page
 * knows, and has no strip.
 */
export const LOOP_ROLES: ReadonlySet<string> = new Set(["planner", "plan-reviewer", "implementer", "code-reviewer", "resolver"]);

/** A stage's state: a task stage's, its tasks' together; a checkpoint's, its journal's; or a stage the data cannot link. */
export type StageStatus = "pending" | "running" | "done" | "failed" | "cancelled" | "unlinked" | "unreadable";

/** One journal step of a checkpoint: its name, when it ran, the commit it left or started from, and a `git` step's arguments. */
export interface Milestone {
  step: string;
  at: number;
  head: string | null;
  args: string[] | null;
}

/**
 * One stage of a run's strip. A task stage names its first task, which its chip selects,
 * and how many of its tasks are done; a review round's names the commit it reviewed. A
 * checkpoint names the view its chip opens. A stage the data cannot link is neither.
 */
export interface Chip {
  kind: "task" | "checkpoint" | "unlinked";
  name: string;
  status: StageStatus;
  word: string;
  task: string | null;
  count: { done: number; total: number } | null;
  head: string | null;
  checkpoint: string | null;
}

/** A chip, or the separator before one task worktree's stages in a lead's run. */
export type StripItem = Chip | { kind: "separator"; slug: string };

/** A gate's or the merge's view: its state, the journal it was read from, and its milestones. */
export interface Checkpoint {
  name: string;
  status: StageStatus;
  word: string;
  /** The task worktree, or null for a lead's run with none yet. */
  slug: string | null;
  journal: "none" | "absent" | "read" | "unreadable";
  reason: string | null;
  milestones: Milestone[];
}

/** One run as the page shows it: what it is named by, its strip — null for a run no loop maps — and its checkpoints by id. */
export interface RunView {
  key: string;
  kind: "lead" | "worktree";
  name: string;
  strip: StripItem[] | null;
  checkpoints: Record<string, Checkpoint>;
}

/** The steps that bring a branch to a review: each gate's. */
const GATE_STEPS = new Set(["worktree-created", "committed", "rebased", "tested", "git"]);
/** The steps that merge it and clean up after: the merge's. */
const MERGE_STEPS = new Set(["merged", "tests-passed", "review-waived", "worktree-removed", "branch-deleted"]);

function taskStage(name: string, tasks: readonly TaskRecord[], head: string | null = null): Chip {
  if (tasks.length === 0) return { kind: "task", name, status: "pending", word: "pending", task: null, count: null, head, checkpoint: null };
  const done = tasks.filter((task) => task.status === "done").length;
  const status: StageStatus = tasks.some((task) => !isTerminal(task.status)) ? "running"
    : done === tasks.length ? "done" : tasks.some((task) => task.status === "failed") ? "failed" : "cancelled";
  return { kind: "task", name, status, word: status, task: tasks[0].id, count: { done, total: tasks.length }, head, checkpoint: null };
}

function unlinkedStage(name: string): Chip {
  return { kind: "unlinked", name, status: "unlinked", word: "not linked", task: null, count: null, head: null, checkpoint: null };
}

function milestoneOf(entry: Journal["steps"][number]): Milestone {
  return { step: entry.step, at: entry.at, head: entry.after ?? entry.before ?? null, args: entry.args ?? null };
}

/**
 * One run's view: its strip and its checkpoints, from its members — the records admitted to
 * it, with their statuses as last seen — the ledger's records for their chains, and each
 * task worktree's journal as last read. A run whose members outside its lead's chain all
 * have a role of the loop gets a strip, a lead's consultants left out: they are no stage,
 * and stay listed under the lead. A lead's run opens with its root planners and plan
 * reviewers as Plan and Plan review; a worktree's, whose plan no record links, with the two
 * not linked. Then each task worktree is a segment, in the order of its first member, or a
 * lead's run with none has one empty one: Implement, each review round — its reviewers
 * grouped by the commit they review and the fixes before them — as its gate, its review and
 * the fix after it, a trailing gate and review while a fix is the last stage, and the merge.
 * A gate holds the journal's gate steps after the round before it and up to its own round;
 * the steps after the last round are a trailing gate's, or else the merge's with every merge
 * step.
 */
export function runView(
  key: string, members: Iterable<TaskRecord>, byId: ReadonlyMap<string, TaskRecord>, layout: RunLayout, journals: ReadonlyMap<string, JournalState>,
): RunView {
  const lead = key.startsWith("lead:") ? key.slice("lead:".length) : null;
  const view = { key, kind: lead === null ? "worktree" as const : "lead" as const, name: lead ?? key.slice("worktree:".length) };
  const sorted = [...members].sort(oldestFirst);
  const outside = lead === null ? sorted : sorted.filter((member) => (chainOf(member, byId) ?? member.id) !== lead && member.role !== CONSULT_ROLE);
  if (!outside.every((member) => LOOP_ROLES.has(member.role))) return { ...view, strip: null, checkpoints: {} };

  const strip: StripItem[] = [];
  const checkpoints: Record<string, Checkpoint> = {};
  if (lead === null) strip.push(unlinkedStage("Plan"), unlinkedStage("Plan review"));
  else {
    const root = outside.filter((member) => slugOf(member, layout) === null);
    strip.push(taskStage("Plan", root.filter((member) => member.role === "planner")), taskStage("Plan review", root.filter((member) => member.role === "plan-reviewer")));
  }
  const segments = new Map<string | null, TaskRecord[]>();
  for (const member of outside) {
    const slug = slugOf(member, layout);
    if (slug === null) continue;
    const same = segments.get(slug);
    if (same === undefined) segments.set(slug, [member]);
    else same.push(member);
  }
  if (segments.size === 0 && lead !== null) segments.set(null, []);

  for (const [index, [slug, tasks]] of [...segments].entries()) {
    if (lead !== null && slug !== null) strip.push({ kind: "separator", slug });
    const fixers = tasks.filter((task) => task.role === "implementer" || task.role === "resolver");
    const rounds: Array<{ key: string; head: string | null; start: number; reviewers: TaskRecord[] }> = [];
    for (const reviewer of tasks.filter((task) => task.role === "code-reviewer")) {
      const head = reviewer.underReview ?? null;
      const round = `${head ?? ""}\n${fixers.filter((fixer) => fixer.createdAt < reviewer.createdAt).length}`;
      const found = rounds.find((each) => each.key === round);
      if (found === undefined) rounds.push({ key: round, head, start: reviewer.createdAt, reviewers: [reviewer] });
      else found.reviewers.push(reviewer);
    }
    const starts = rounds.map((round) => round.start);
    const fixes = rounds.map((_, at) => fixers.filter((fixer) => fixer.createdAt >= starts[at] && (at === rounds.length - 1 || fixer.createdAt < starts[at + 1])));
    const trailing = rounds.length === 0 || fixes[rounds.length - 1].length > 0;

    const state: JournalState | null = slug === null ? null : journals.get(slug) ?? { kind: "absent" };
    const steps = state?.kind === "read" ? state.journal.steps : [];
    const last = rounds.length === 0 ? -Infinity : starts[rounds.length - 1];
    const gateSteps = steps.filter((entry) => GATE_STEPS.has(entry.step));
    const checkpointOf = (name: string, id: string, held: Journal["steps"], reached: string, word: string): Chip => {
      const milestones = held.map(milestoneOf);
      const status: StageStatus = state?.kind === "unreadable" ? "unreadable" : held.some((entry) => entry.step === reached) ? "done" : "pending";
      checkpoints[id] = {
        name, status, word: status === "done" ? word : status, slug, journal: state === null ? "none" : state.kind,
        reason: state?.kind === "unreadable" ? state.reason : null, milestones,
      };
      return { kind: "checkpoint", name, status, word: checkpoints[id].word, task: null, count: null, head: null, checkpoint: id };
    };
    const gate = (k: number) => {
      const after = k === 1 ? -Infinity : starts[k - 2];
      const until = k <= rounds.length ? starts[k - 1] : Infinity;
      return checkpointOf(`Gate ${k}`, `${index}/gate/${k}`, gateSteps.filter((entry) => entry.at > after && entry.at <= until), "tested", "passed");
    };

    strip.push(taskStage("Implement", fixers.filter((fixer) => rounds.length === 0 || fixer.createdAt < starts[0])));
    for (const [at, round] of rounds.entries()) {
      strip.push(gate(at + 1), taskStage(`Review ${at + 1}`, round.reviewers, round.head));
      if (fixes[at].length > 0) strip.push(taskStage(`Fix ${at + 1}`, fixes[at]));
    }
    if (trailing) strip.push(gate(rounds.length + 1), taskStage(`Review ${rounds.length + 1}`, []));
    const merging = steps.filter((entry) => MERGE_STEPS.has(entry.step) || (!trailing && GATE_STEPS.has(entry.step) && entry.at > last));
    strip.push(checkpointOf("Merge", `${index}/merge`, merging, "merged", "merged"));
  }
  return { ...view, strip, checkpoints };
}
