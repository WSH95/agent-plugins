import { isTerminal } from "./ledger.ts";
import type { TaskStatus } from "./ledger.ts";
import type { Checkpoint, RunView, StageStatus, StripItem } from "./runs.ts";
import { sanitize, span } from "./steps.ts";
import type { Step, Usage } from "./steps.ts";
import type { WatchEvent, WatchedTask } from "./watch.ts";

// `cross-agent watch --web`'s page, the Inspector, rendered on the server (design section
// 10): each event of the follow loop as HTML fragments — a task's entry, its link and its
// head, a step's row and its detail — that the page script only places. Every string a
// stream or a record carries goes through `escapeHtml` before any markup is put around it,
// so the only markup on the page is what this file writes; the page's CSP, which allows no
// inline script, is a second layer under that, not the guarantee.

/**
 * How much of one detail block — an output, a diff, a message, a call's input, a reason —
 * a row shows, in UTF-16 code units. The rest is in `cross-agent log`, which the row names.
 */
export const DETAIL_LIMIT = 256 * 1024;

const ENTITIES: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** Text as a page shows it: each of the five characters markup gives a meaning an entity. */
export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (character) => ENTITIES[character]);
}

/**
 * What a detail block keeps of its text, raw, and how many code units it leaves out: the
 * first `DETAIL_LIMIT`, one fewer where the cut would split a surrogate pair. The kept text
 * is escaped or formatted by its renderer before the notice's markup goes after it.
 */
function clip(text: string): { kept: string; omitted: number } {
  if (text.length <= DETAIL_LIMIT) return { kept: text, omitted: 0 };
  const high = text.charCodeAt(DETAIL_LIMIT - 1);
  const low = text.charCodeAt(DETAIL_LIMIT);
  const end = high >= 0xd800 && high <= 0xdbff && low >= 0xdc00 && low <= 0xdfff ? DETAIL_LIMIT - 1 : DETAIL_LIMIT;
  return { kept: text.slice(0, end), omitted: text.length - end };
}

/** The notice after a cut block, naming the log the rest is in; nothing where nothing was cut. */
function cutNotice(omitted: number, taskId: string): string {
  return omitted === 0 ? "" : `<div class="cut">… ${omitted} more characters not shown: see cross-agent log ${escapeHtml(taskId)}</div>`;
}

/** Text as one preformatted block, cut at the limit. */
function pre(text: string, taskId: string, className?: string): string {
  const { kept, omitted } = clip(text);
  return `<pre${className === undefined ? "" : ` class="${className}"`}>${escapeHtml(kept)}</pre>${cutNotice(omitted, taskId)}`;
}

/** A call's input, or anything else the stream carries as JSON, indented. */
function json(value: unknown, taskId: string): string {
  return pre(JSON.stringify(value, null, 2) ?? String(value), taskId, "json");
}

type Json = Record<string, unknown>;

function isObject(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// The Markdown subset `formatted` reads, a line at a time. No two quantifiers that can
// both take the same run of spaces or tabs sit side by side in a pattern that can still
// fail after them: a line of model output holding a long run would split it every way
// before failing, in time quadratic in its length, on the watcher's one thread. A
// heading's closing run of `#` and a delimiter row's cells are read by string operations.
const FENCE = /^ {0,3}(`{3,}|~{3,})/;
const HEADING = /^ {0,3}(#{1,6})(?:[ \t]|$)/;
const RULE = /^ {0,3}(?:(?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,})$/;
// `s`: a quote's text runs to the end of the line, a carriage return inside it among it.
const QUOTE = /^ {0,3}>[ \t]?(.*)$/s;
// `s`: the text runs to the end of the line whatever it holds, so nothing after the
// marker's spaces can fail and send them back one at a time.
const ITEM = /^([ \t]*)(?:([-*+])|(\d{1,9})[.)])[ \t]+(.*)$/s;
const DELIMITER_CELL = /^:?-+:?$/;

function blank(line: string): boolean {
  return line.trim() === "";
}

/**
 * Escaped text with `**bold**` made `<strong>`: the escape leaves every `*` as it was. It
 * reads as the lazy pattern it replaces did (kept as the reference in
 * `tests/webrender.test.ts#webBoldLinear`), in one pass, built like the code-span scan below:
 * an opener is `**` before a character that is not a space, its closer the first `**` after a
 * character that is not a space at least three on from it, and the closers are found first
 * and walked by a cursor that only moves forward. An opener with no closer left ends the
 * scan, because no later opener could have one either.
 */
function emphasis(text: string): string {
  const escaped = escapeHtml(text);
  const pair = (index: number) => escaped[index] === "*" && escaped[index + 1] === "*";
  const closers: number[] = [];
  for (let index = 1; index + 1 < escaped.length; index++) if (pair(index) && /\S/.test(escaped[index - 1])) closers.push(index);
  let html = "";
  let at = 0;
  let cursor = 0;
  for (let index = 0; index + 2 < escaped.length; index++) {
    if (!pair(index) || !/\S/.test(escaped[index + 2])) continue;
    while (cursor < closers.length && closers[cursor] < index + 3) cursor++;
    if (cursor === closers.length) break;
    const closer = closers[cursor];
    html += `${escaped.slice(at, index)}<strong>${escaped.slice(index + 2, closer)}</strong>`;
    at = closer + 2;
    index = closer + 1;
  }
  return html + escaped.slice(at);
}

/**
 * One line read for code spans: each span's text given to `code`, and the text between
 * them to `outside`. A span opens at a whole run of backticks and closes at the next later
 * run of exactly its length; a run no later run matches is text, given to `outside` with
 * what surrounds it, and the scan goes on after it, never inside it. The runs are found in
 * one pass and each length's runs are walked by a cursor that only moves forward, so a line
 * is read in time linear in its length however its backticks fall.
 */
function spans(text: string, outside: (text: string) => string, code: (text: string) => string): string {
  const runs: Array<{ start: number; length: number }> = [];
  for (let index = 0; index < text.length; index++) {
    if (text[index] !== "`") continue;
    const start = index;
    while (text[index + 1] === "`") index++;
    runs.push({ start, length: index - start + 1 });
  }
  // Each length's runs, by their place among all the runs, and the first of them not yet passed.
  const byLength = new Map<number, number[]>();
  for (const [place, run] of runs.entries()) {
    const same = byLength.get(run.length);
    if (same === undefined) byLength.set(run.length, [place]);
    else same.push(place);
  }
  const cursors = new Map<number, number>();
  let html = "";
  let at = 0;
  for (let place = 0; place < runs.length; place++) {
    const run = runs[place];
    const same = byLength.get(run.length)!;
    let cursor = cursors.get(run.length) ?? 0;
    while (cursor < same.length && same[cursor] <= place) cursor++;
    cursors.set(run.length, cursor);
    if (cursor === same.length) continue;
    const closer = runs[same[cursor]];
    html += `${outside(text.slice(at, run.start))}${code(text.slice(run.start + run.length, closer.start))}`;
    at = closer.start + closer.length;
    place = same[cursor];
  }
  return html + outside(text.slice(at));
}

/** A code span's text as markup: escaped and nothing else. */
function codeSpan(text: string): string {
  return `<code>${escapeHtml(text)}</code>`;
}

/** One line's inline markup: code spans first, then bold on the text between them. */
function inline(text: string): string {
  return spans(text, emphasis, codeSpan);
}

/** A list item: whether it is numbered and its number, how far it is indented, and its text. */
function itemOf(line: string): { ordered: boolean; number: number | null; indent: number; text: string } | null {
  const match = ITEM.exec(line);
  if (match === null) return null;
  return {
    ordered: match[2] === undefined, number: match[3] === undefined ? null : Number(match[3]),
    indent: match[1].replace(/\t/g, "    ").length, text: match[4],
  };
}

/** A table row's cells, its outer pipes dropped and an escaped `\|` kept as a pipe. */
function cellsOf(row: string): string[] {
  let text = row.trim();
  if (text.startsWith("|")) text = text.slice(1);
  if (text.endsWith("|") && !text.endsWith("\\|")) text = text.slice(0, -1);
  return text.split(/(?<!\\)\|/).map((cell) => cell.trim().replace(/\\\|/g, "|"));
}

/** An ATX heading: its level, and its text without the closing run of `#` that follows a space or a tab, or stands alone. */
function headingOf(line: string): { level: number; text: string } | null {
  const opening = HEADING.exec(line);
  if (opening === null) return null;
  const rest = line.slice(opening[0].length).trim();
  let end = rest.length;
  while (end > 0 && rest[end - 1] === "#") end--;
  const text = end === 0 ? "" : rest[end - 1] === " " || rest[end - 1] === "\t" ? rest.slice(0, end).trimEnd() : rest;
  return { level: opening[1].length, text };
}

/** A table's delimiter row: a pipe, and every cell dashes, a colon at either end for its alignment. */
function delimiterRow(line: string): boolean {
  return line.includes("|") && cellsOf(line).every((cell) => DELIMITER_CELL.test(cell));
}

function tableStarts(lines: string[], index: number): boolean {
  return lines[index].includes("|") && index + 1 < lines.length && delimiterRow(lines[index + 1]);
}

/**
 * The run of backticks or tildes that opens a fenced block on `line`, or null where none
 * does: a backtick run with another backtick after it on its line opens a code span, which
 * is text, not a block. A tilde fence's info may hold a backtick.
 */
function fenceOf(line: string): string | null {
  const match = FENCE.exec(line);
  if (match === null) return null;
  return match[1][0] === "`" && line.slice(match[0].length).includes("`") ? null : match[1];
}

/** What closes a block a fence opened: a run of the opening's character at least as long, alone on its line; `\x60` is the backtick. */
function closingFence(fence: string): RegExp {
  return new RegExp(`^ {0,3}${fence[0] === "~" ? "~" : "\\x60"}{${fence.length},}[ \\t]*$`);
}

/** A fenced block's lines as one code block, escaped and nothing else. */
function codeBlock(code: string[]): string {
  return `<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`;
}

/** How many spaces and tabs a line opens with. */
function indentOf(line: string): number {
  return line.length - line.trimStart().length;
}

/** How many columns a line's leading spaces and tabs reach, a tab reaching the next multiple of four as in CommonMark. */
function columnsOf(line: string): number {
  let columns = 0;
  for (const character of line) {
    if (character === " ") columns++;
    else if (character === "\t") columns += 4 - (columns % 4);
    else break;
  }
  return columns;
}

/** Lines with the indentation every line that holds anything shares taken off, a blank line keeping what it has past that. */
function dedent(code: string[]): string[] {
  const common = code.filter((line) => !blank(line)).reduce((least, line) => Math.min(least, indentOf(line)), Infinity);
  return Number.isFinite(common) ? code.map((line) => line.slice(Math.min(common, indentOf(line)))) : code;
}

/** Whether a line opens a block other than a paragraph, and so ends one. */
function opensBlock(lines: string[], index: number): boolean {
  const line = lines[index];
  return fenceOf(line) !== null || HEADING.test(line) || RULE.test(line) || QUOTE.test(line) || itemOf(line) !== null || tableStarts(lines, index);
}

/**
 * Text read as the Markdown subset an engine's messages use: fenced code, ATX headings,
 * rules, pipe tables, flat lists, quotes and paragraphs, with code spans and bold inline.
 * Nothing else is markup: no links, images, italics or HTML of the text's own.
 */
function markdown(text: string): string {
  const lines = text.split("\n").map((line) => (line.endsWith("\r") ? line.slice(0, -1) : line));
  const blocks: string[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (blank(line)) {
      index++;
      continue;
    }
    const fence = fenceOf(line);
    if (fence !== null) {
      const closing = closingFence(fence);
      const code: string[] = [];
      index++;
      while (index < lines.length && !closing.test(lines[index])) code.push(lines[index++]);
      index++;
      blocks.push(codeBlock(code));
      continue;
    }
    const heading = headingOf(line);
    if (heading !== null) {
      blocks.push(`<h${heading.level}>${inline(heading.text)}</h${heading.level}>`);
      index++;
      continue;
    }
    if (RULE.test(line)) {
      blocks.push("<hr>");
      index++;
      continue;
    }
    if (tableStarts(lines, index)) {
      const head = cellsOf(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && !blank(lines[index]) && lines[index].includes("|")) rows.push(cellsOf(lines[index++]));
      // A row's own cells: a long row is cut to the header's count and a short one is not
      // padded, so the table is no larger than its text.
      const cells = (row: string[], tag: string) => row.slice(0, head.length).map((cell) => `<${tag}>${inline(cell)}</${tag}>`).join("");
      const body = rows.map((row) => `<tr>${cells(row, "td")}</tr>`).join("");
      blocks.push(`<table><thead><tr>${cells(head, "th")}</tr></thead><tbody>${body}</tbody></table>`);
      continue;
    }
    const first = itemOf(line);
    if (first !== null) {
      // Flat: a nested item is one more item of this list, and an indented line that is no
      // item continues the item before it — its text, or a fenced block under it, which
      // keeps its lines.
      const items: Array<Array<{ text: string } | { code: string }>> = [[{ text: first.text }]];
      index++;
      while (index < lines.length) {
        if (blank(lines[index])) {
          let next = index;
          while (next < lines.length && blank(lines[next])) next++;
          // An indented fence after the blank lines is a block under the item before them.
          const fenced = next < lines.length && /^[ \t]/.test(lines[next]) && fenceOf(lines[next].trimStart()) !== null;
          const after = next < lines.length ? itemOf(lines[next]) : null;
          if (!fenced && (after === null || (after.indent < 2 && after.ordered !== first.ordered))) break;
          index = next;
          continue;
        }
        const item = itemOf(lines[index]);
        const parts = items[items.length - 1];
        const fence = fenceOf(lines[index].trimStart());
        if (item !== null) {
          if (item.indent < 2 && item.ordered !== first.ordered) break;
          items.push([{ text: item.text }]);
        } else if (/^[ \t]/.test(lines[index]) && fence !== null) {
          const closing = closingFence(fence);
          // A fence indented at most three columns more than this one closes it, the slack
          // CommonMark gives a closing fence, a tab reaching the next multiple of four as it
          // does there; one indented further is the block's own text.
          const opener = columnsOf(lines[index]);
          const code: string[] = [];
          index++;
          while (index < lines.length && !(columnsOf(lines[index]) <= opener + 3 && closing.test(lines[index].trimStart()))) code.push(lines[index++]);
          parts.push({ code: codeBlock(dedent(code)) });
        } else if (/^[ \t]/.test(lines[index])) {
          const last = parts[parts.length - 1];
          if ("text" in last) last.text += ` ${lines[index].trim()}`;
          else parts.push({ text: lines[index].trim() });
        } else {
          break;
        }
        index++;
      }
      const tag = first.ordered ? "ol" : "ul";
      // A numbered list that does not start at 1 says where it starts.
      const start = first.ordered && first.number !== 1 ? ` start="${first.number}"` : "";
      const listed = items.map((parts) => `<li>${parts.map((part) => ("text" in part ? inline(part.text.trim()) : part.code)).join("")}</li>`).join("");
      blocks.push(`<${tag}${start}>${listed}</${tag}>`);
      continue;
    }
    if (QUOTE.test(line)) {
      const quoted: string[] = [];
      while (index < lines.length && QUOTE.test(lines[index])) quoted.push(QUOTE.exec(lines[index++])![1]);
      blocks.push(`<blockquote>${quoted.map((each) => inline(each.trim())).join("<br>")}</blockquote>`);
      continue;
    }
    const paragraph = [line];
    index++;
    while (index < lines.length && !blank(lines[index]) && !opensBlock(lines, index)) paragraph.push(lines[index++]);
    blocks.push(`<p>${paragraph.map((each) => inline(each.trim())).join("<br>")}</p>`);
  }
  return blocks.join("");
}

/**
 * A message or a final result as formatted text: cut at the limit first, then read as the
 * Markdown subset, which builds markup from escaped text only, and the notice after it.
 */
export function formatted(text: string, taskId: string): string {
  const { kept, omitted } = clip(text);
  return `<div class="md">${markdown(kept)}</div>${cutNotice(omitted, taskId)}`;
}

function lineClass(line: string): string {
  switch (line[0]) {
    case "-": return "del";
    case "+": return "add";
    case "@": return "hunk";
    default: return "ctx";
  }
}

/**
 * A diff's lines, each with its prefix — ` `, `-`, `+`, or `@@` on a hunk's header — cut as
 * one block at the limit, and each kept line classed by its first character.
 */
function diffBlock(lines: string[], taskId: string): string {
  const { kept, omitted } = clip(lines.join("\n"));
  const rows = kept.split("\n").map((line) => `<span class="${lineClass(line)}">${escapeHtml(line)}</span>`);
  return `<pre class="diff">${rows.join("")}</pre>${cutNotice(omitted, taskId)}`;
}

function linesOf(text: string): string[] {
  return text === "" ? [] : text.split("\n");
}

/** An edit's old and new text as a diff: the lines both share at the start and the end are context, and the middle is removed and added. */
function editDiff(before: string, after: string, taskId: string): string {
  const old = linesOf(before);
  const next = linesOf(after);
  let start = 0;
  while (start < old.length && start < next.length && old[start] === next[start]) start++;
  let end = 0;
  while (end < old.length - start && end < next.length - start && old[old.length - 1 - end] === next[next.length - 1 - end]) end++;
  return diffBlock([
    ...old.slice(0, start).map((line) => ` ${line}`),
    ...old.slice(start, old.length - end).map((line) => `-${line}`),
    ...next.slice(start, next.length - end).map((line) => `+${line}`),
    ...old.slice(old.length - end).map((line) => ` ${line}`),
  ], taskId);
}

interface Hunk {
  oldStart: number;
  oldLines: number;
  newStart: number;
  newLines: number;
  lines: string[];
}

/** Claude's `structuredPatch`, when a result's payload carries a well-formed one. */
function hunksOf(payload: unknown): Hunk[] | null {
  const patch = isObject(payload) && isObject(payload.toolUseResult) ? payload.toolUseResult.structuredPatch : undefined;
  if (!Array.isArray(patch) || patch.length === 0) return null;
  const wellFormed = patch.every((hunk) => isObject(hunk)
    && (["oldStart", "oldLines", "newStart", "newLines"] as const).every((field) => Number.isSafeInteger(hunk[field]))
    && Array.isArray(hunk.lines) && hunk.lines.every((line) => typeof line === "string"));
  return wellFormed ? patch as Hunk[] : null;
}

/** A structured patch as a diff: each hunk's header, then its lines, which carry their own prefixes. */
function patchDiff(hunks: Hunk[], taskId: string): string {
  return diffBlock(hunks.flatMap((hunk) => [`@@ -${hunk.oldStart},${hunk.oldLines} +${hunk.newStart},${hunk.newLines} @@`, ...hunk.lines]), taskId);
}

/**
 * An edit's detail, by what its input carries: an old and a new text (Claude's `Edit`,
 * Grok's `search_replace`), a list of them (`MultiEdit`), a whole new text (`Write`,
 * `NotebookEdit`), or Codex's paths and kinds, which carry no text at all.
 */
function editDetail(input: unknown, taskId: string): string {
  if (Array.isArray(input) && input.length > 0 && input.every((change) => isObject(change) && typeof change.path === "string" && typeof change.kind === "string")) {
    // One line per change, cut as one block at the limit like every other.
    const { kept, omitted } = clip((input as Array<{ path: string; kind: string }>).map((change) => `${change.kind} ${change.path}`).join("\n"));
    const listed = kept.split("\n").map((line) => `<li>${escapeHtml(line)}</li>`).join("");
    return `<ul class="changes">${listed}</ul>${cutNotice(omitted, taskId)}`;
  }
  if (isObject(input)) {
    if (typeof input.old_string === "string" && typeof input.new_string === "string") return editDiff(input.old_string, input.new_string, taskId);
    const edits = input.edits;
    if (Array.isArray(edits) && edits.length > 0 && edits.every((edit) => isObject(edit) && typeof edit.old_string === "string" && typeof edit.new_string === "string")) {
      return (edits as Array<{ old_string: string; new_string: string }>).map((edit) => editDiff(edit.old_string, edit.new_string, taskId)).join("");
    }
    const content = typeof input.content === "string" ? input.content : typeof input.new_source === "string" ? input.new_source : undefined;
    if (content !== undefined) return diffBlock(linesOf(content).map((line) => `+${line}`), taskId);
  }
  return json(input, taskId);
}

/**
 * The group a row is filtered by: a call's kind, the call a result closes, a message (a
 * final among them) or a thinking. An error and stderr have none, so only All shows them.
 */
export type Group = "command" | "edit" | "message" | "thinking" | "tool";

/**
 * A reader of the follow loop's events that gives each step its group. A command, an edit
 * or a tool call with an id is entered under it, in its own task's map, until the result
 * with that id takes the call's group and removes it; a result with no id, or one whose id
 * no call holds, is a tool. A task's settlement drops its map, so a call whose result never
 * comes is held only until its task settles. One reader per page's follow loop, fed every
 * event in order.
 */
export function stepGroups(): (event: WatchEvent) => Group | null {
  const pending = new Map<string, Map<string, Group>>();
  return (event) => {
    if (event.event === "settled") pending.delete(event.task.id);
    if (event.event !== "step") return null;
    const { step } = event;
    switch (step.kind) {
      case "command": case "edit": case "tool": {
        if (step.id !== null) {
          const calls = pending.get(event.task.id) ?? new Map<string, Group>();
          calls.set(step.id, step.kind);
          pending.set(event.task.id, calls);
        }
        return step.kind;
      }
      case "result": {
        const calls = pending.get(event.task.id);
        const group = step.id === null ? undefined : calls?.get(step.id);
        if (group === undefined) return "tool";
        calls!.delete(step.id!);
        if (calls!.size === 0) pending.delete(event.task.id);
        return group;
      }
      case "message": case "final":
        return "message";
      case "thinking":
        return "thinking";
      default:
        return null;
    }
  };
}

/** A step whose summary is prose — the model's words — and not a command, a call or output. */
type Prose = Extract<Step, { kind: "message" | "thinking" | "final" }>;

function isProse(step: Step): step is Prose {
  return step.kind === "message" || step.kind === "thinking" || step.kind === "final";
}

/** The words a prose summary opens with, as `src/steps.ts` writes them. */
const PROSE_PREFIX = /^(?:says|thinks|finished|failed): /;

/** What a summary ends with where its text has more lines than its first. */
const MORE = " …";

/**
 * A prose summary's text with a delimiter its 200-code-point cut split taken off its end:
 * where the summary ends in a `*` or a backtick and the text's first line, as the summary
 * was made from it, goes on past the cut with the same character, that trailing run is part
 * of a delimiter — half a `**`, or a code span's run cut short — and goes. Any other `*`
 * there is punctuation, and stays.
 */
function uncut(rest: string, text: string): string {
  const last = rest.at(-1);
  if (last !== "*" && last !== "`") return rest;
  const first = text.split("\n").find((line) => line.trim() !== "");
  if (first === undefined) return rest;
  const line = sanitize(first.trimEnd());
  if (rest.length >= line.length || !line.startsWith(rest) || line[rest.length] !== last) return rest;
  let end = rest.length;
  while (end > 0 && rest[end - 1] === last) end--;
  return rest.slice(0, end);
}

/** A line with one leading block marker dropped: a heading's, its closing run with it, a list item's, or a quote's. */
function unblocked(line: string): string {
  const heading = headingOf(line);
  if (heading !== null) return heading.text;
  const item = itemOf(line);
  if (item !== null) return item.text;
  const quote = QUOTE.exec(line);
  return quote === null ? line : quote[1];
}

/** Prose between code spans with its markers dropped: each backtick, which outside a span is a run nothing closes, then each `**`. */
function unmarked(text: string): string {
  return text.replace(/`+/g, "").replace(/\*\*/g, "");
}

/**
 * A prose summary read as the Markdown it was cut from: its prefix and its trailing ` …`
 * kept as they are, and between them a delimiter its cut split, one leading block marker,
 * and every `**` and every backtick outside a code span dropped. Each code span's text is
 * given to `code` and every other part to `plain`, so one reading gives the row's markup
 * and the search's text.
 */
function prose(step: Prose, code: (text: string) => string, plain: (text: string) => string): string {
  const prefix = PROSE_PREFIX.exec(step.summary)?.[0] ?? "";
  let rest = step.summary.slice(prefix.length);
  const more = rest.endsWith(MORE) ? MORE : "";
  rest = unblocked(uncut(rest.slice(0, rest.length - more.length), step.text));
  return `${plain(prefix)}${spans(rest, (text) => plain(unmarked(text)), code)}${plain(more)}`;
}

/**
 * A step's summary as a row and a title show it. Prose — a message's, a thinking's, a
 * final's — loses its Markdown markers, a code span shown as code; every other summary
 * carries a command, a path, a glob or output as it was written, and is escaped and
 * nothing else.
 */
function summaryHtml(step: Step): string {
  return isProse(step) ? prose(step, codeSpan, escapeHtml) : escapeHtml(step.summary);
}

/** A step's summary as the page's search reads it: the words `summaryHtml` shows, with no markup. */
function summaryText(step: Step): string {
  return isProse(step) ? prose(step, (text) => text, (text) => text) : step.summary;
}

/** One icon of the page's sprite, which `pageHtml` draws: decorative, its word beside it. */
function icon(name: string): string {
  return `<svg class="ic" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
}

type StepKind = Exclude<Step["kind"], "thinking-progress">;

/** Each kind's word, as a detail's title names it. */
const KIND_WORDS: Record<StepKind, string> = {
  message: "Message", thinking: "Thinking", command: "Command", result: "Result", edit: "Edit", tool: "Tool", final: "Final", error: "Error", stderr: "Stderr",
};

/** A result's pill: its exit code, ok at 0 and bad otherwise; `ok`, or `failed`, where it has none. Nothing for any other step. */
function pill(step: Step): string {
  if (step.kind !== "result") return "";
  const [tone, word] = step.exitCode !== null ? [step.exitCode === 0 ? "ok" : "bad", `exit ${step.exitCode}`] : step.ok ? ["ok", "ok"] : ["bad", "failed"];
  return `<span class="pill pill-${tone}">${word}</span>`;
}

/**
 * A step's row, the content of its button in the steps pane: its kind's icon and its
 * summary, in mono for a command and for the result that closes one, a result's pill
 * beside its whole summary, and last, where `offset` gives one, how long after its task's
 * start the step was written, in milliseconds, as `+` and the span `watch` spells, none
 * below zero. A still-thinking step is no row: it only marks its task's head.
 */
export function stepRow(step: Step, group: Group | null, offset: number | null = null): string {
  if (step.kind === "thinking-progress") return "";
  const mono = step.kind === "command" || (step.kind === "result" && group === "command");
  const after = offset === null ? "" : `<span class="offset">+${escapeHtml(span(Math.max(0, Math.round(offset / 1000))))}</span>`;
  return `${icon(`kind-${step.kind}`)}<span class="sum k-${step.kind}${mono ? " mono" : ""}">${summaryHtml(step)}</span>${pill(step)}${after}`;
}

/** A block of the detail pane: its label and a Copy button over its text, which the page script copies from the block's `pre`. */
function block(label: string, body: string): string {
  return `<div class="block"><div class="block-head"><span>${label}</span><button type="button" class="copy">Copy</button></div>${body}</div>`;
}

/** The detail's body: the step whole, by its kind. */
function body(step: Step, taskId: string): string {
  switch (step.kind) {
    case "message": case "thinking": case "final":
      return formatted(step.text, taskId);
    case "error": case "stderr":
      return pre(step.text, taskId);
    case "command":
      return `${block("Command", pre(step.command, taskId))}${block("Input", json(step.input, taskId))}`;
    case "edit":
      return editDetail(step.input, taskId);
    case "tool":
      return block("Input", json(step.input, taskId));
    case "result": {
      const hunks = hunksOf(step.payload);
      return `${step.output === "" ? "" : block("Output", pre(step.output, taskId))}${hunks === null ? "" : patchDiff(hunks, taskId)}`;
    }
    case "thinking-progress":
      return "";
  }
}

/**
 * A step's detail, the detail pane's content when the step is selected: a title — its
 * kind's icon and word, its summary as its row shows it, a result's pill, and when its line
 * was written, where `at` gives a time a date can hold, which the page script writes in the
 * viewer's own form — over the step whole: a command and its input, a call's input and a
 * result's output as blocks with Copy, an edit as a diff where its input carries the text,
 * a result's structured patch as one too, and a message, a thinking or a final formatted.
 * `taskId` is what a cut block's notice names.
 */
export function stepDetail(step: Step, taskId: string, at: number | null = null): string {
  if (step.kind === "thinking-progress") return "";
  const when = new Date(at ?? Number.NaN);
  const title = `${icon(`kind-${step.kind}`)}<span class="kind">${KIND_WORDS[step.kind]}</span> `
    + `<span class="sum k-${step.kind}${step.kind === "command" ? " mono" : ""}">${summaryHtml(step)}</span>${pill(step)}`
    + `${Number.isNaN(when.getTime()) ? "" : `<time class="started" datetime="${when.toISOString()}"></time>`}`;
  return `<h2 class="title">${title}</h2>${body(step, taskId)}`;
}

/** What runs a task, as one cell: `engine/model/effort`, `-` for what is not set (as `src/cli.ts` spells it). */
function runsOn(task: { engine: string; model?: string | null; effort?: string | null }): string {
  return `${task.engine}/${task.model ?? "-"}/${task.effort ?? "-"}`;
}

/** A task's role as one cell: `<role>#<seat>` for a seat of a many-seat role (as `src/cli.ts` spells it). */
function roleCell(task: { role: string; seat?: number | null }): string {
  return task.seat === undefined || task.seat === null ? task.role : `${task.role}#${task.seat}`;
}

/** A task's status as an icon and its word, the word coloured by the class its status names. */
function statusCell(status: TaskStatus): string {
  const name = escapeHtml(status);
  return `<span class="st st-${name}">${icon(`status-${name}`)}<span class="word">${name}</span></span>`;
}

/** The engines with a colour of their own; any other is marked as other. */
const ENGINE_CLASSES = new Set(["claude", "codex", "grok"]);

/** A task's engine as its marker and its name. */
function engineCell(engine: string): string {
  return `<span class="eng eng-${ENGINE_CLASSES.has(engine) ? engine : "other"}"><span class="mark" aria-hidden="true"></span>${escapeHtml(engine)}</span>`;
}

/** When a task started and, once it has settled, when it did, which the page script turns into its elapsed time. */
function elapsedCell(task: WatchedTask): string {
  const until = isTerminal(task.status) ? String(task.updatedAt) : "";
  return `<span class="elapsed" data-created="${escapeHtml(String(task.createdAt))}" data-until="${escapeHtml(until)}"></span>`;
}

/** Dollars to the cent, a cost above nothing that is under one `<$0.01`, and `—` for none. */
function costText(cost: number | null): string {
  if (cost === null) return "—";
  return cost > 0 && cost < 0.01 ? "<$0.01" : `$${cost.toFixed(2)}`;
}

const COMPACT = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

/** A count of tokens as a person reads it at a glance: `950`, `52.3K`, `19M`. */
function tokenText(count: number): string {
  return COMPACT.format(count);
}

/** Every token a figure counts, in and out, or `—` where it counts none. */
function tokensText(usage: Usage): string {
  return usage.tokens === null ? "—" : tokenText(usage.tokens.input + usage.tokens.output);
}

/** A task's own figure as its entry shows it: its cost and every token it counts, or `—` for none. */
function usageCell(usage: Usage | null): string {
  return `<span class="usage">${escapeHtml(usage === null ? "—" : `${costText(usage.costUsd)} · ${tokensText(usage)} tokens`)}</span>`;
}

/** A task's own figure as its head shows it: its cost, then its tokens in, the cached part of them, out and the reasoning part of those, where it counts that. */
function usageDetail(usage: Usage | null): string {
  const cost = `cost ${costText(usage?.costUsd ?? null)}`;
  const tokens = usage?.tokens ?? null;
  const text = tokens === null ? `${cost} · tokens —`
    : `${cost} · ${tokenText(tokens.input)} in (${tokenText(tokens.cached)} cached) · ${tokenText(tokens.output)} out`
      + `${tokens.reasoning === null ? "" : ` (${tokenText(tokens.reasoning)} reasoning)`}`;
  return `<span class="usage">${escapeHtml(text)}</span>`;
}

/**
 * A task's entry in the task list, the content of its selection button: its status, its
 * role as `tasks` spells it, its engine, its elapsed time, and the cost and tokens of its
 * own `usage` (`src/steps.ts#ownUsage`), `—` where it has none yet. The round it resumes is
 * `taskLink`'s, beside the button, since a link cannot sit inside one.
 */
export function taskItem(task: WatchedTask, usage: Usage | null = null): string {
  return `${statusCell(task.status)}<span class="label">${escapeHtml(roleCell(task))}</span>${engineCell(task.engine)}${elapsedCell(task)}${usageCell(usage)}`;
}

/**
 * What sits beside a task's entry: for a resume, `resumes` and the first six characters of
 * the round it continues, an in-page link to that round's entry where `resumeLinked` says
 * the page has one and text where it has none; nothing for a task that resumes nothing.
 */
export function taskLink(task: WatchedTask, resumeLinked: boolean): string {
  if (task.resumedFrom === null) return "";
  const short = escapeHtml(task.resumedFrom.slice(0, 6));
  return resumeLinked ? `<a class="resumes" href="#task-${escapeHtml(task.resumedFrom)}">resumes ${short}</a>` : `<span class="resumes-text">resumes ${short}</span>`;
}

/**
 * A task's head in the steps pane: its role under its lead's, the first six characters of
 * its id, what runs it, its status, when it started — a time the page script writes in the
 * viewer's own form, left out where no date can hold the record's `createdAt` — its
 * elapsed time, the cost and tokens of its own `usage` in full, a still-thinking mark the
 * page shows while the task thinks, and a failure's reason.
 */
export function taskHead(task: WatchedTask, usage: Usage | null = null): string {
  const label = `${task.parent === null ? "" : `${roleCell(task.parent)}/`}${roleCell(task)}`;
  const started = new Date(task.createdAt);
  const since = Number.isNaN(started.getTime()) ? "" : `<span class="since">started <time class="started" datetime="${started.toISOString()}"></time></span>`;
  return `<div class="head-line"><h2 class="label">${escapeHtml(label)}</h2><span class="id">${escapeHtml(task.id.slice(0, 6))}</span>`
    + `<span class="runs">${escapeHtml(runsOn(task))}</span>${statusCell(task.status)}${since}${elapsedCell(task)}${usageDetail(usage)}`
    + `<span class="thinking-indicator">${icon("kind-thinking")}thinking…</span></div>`
    + `${task.reason === undefined ? "" : pre(task.reason, task.id, "reason")}`;
}

/**
 * Where a task's entry goes: the run it is in (`src/runs.ts#runIndex`), `""` for none, and
 * the first round of its chain, null for a first round.
 */
export interface Place {
  run: string;
  chain: string | null;
}

/** A task in no run and a first round. */
const UNPLACED: Place = { run: "", chain: null };

/**
 * One event as the page receives it, rendered once on the server: the task it belongs to,
 * that task's lead, its run and the first round of its chain, the step's kind, whether the
 * task is still active and when it was created, which choose the page's default task and
 * order its entry, the task's entry, link and head as they now read, its own figure in the
 * entry and the head, and for a step its group, its summary as the search reads it, its row
 * with its offset from the task's start and its detail with its time, each empty where
 * there is none. A `history` frame is a task built from its record and its stream's last
 * result event, for a task that settled before the watch began: a round a resume
 * continues, or a member of a run the page opens.
 */
export interface Frame {
  event: WatchEvent["event"] | "history";
  id: string;
  parent: string | null;
  run: string;
  chain: string | null;
  kind: Step["kind"] | null;
  active: boolean;
  createdAt: number;
  item: string;
  link: string;
  head: string;
  group: Group | null;
  text: string;
  row: string;
  detail: string;
}

/**
 * An event of the follow loop as its frame: `resumeLinked` says whether the round it
 * resumes has an entry on the page, `group` is the step's, from the page's one
 * `stepGroups` reader, `place` is where the task's entry goes, and `usage` is the task's
 * own figure so far. A step's offset is its time less the record's `createdAt`, the origin
 * of the elapsed clock, and is none where the step has no time or no date can hold the start.
 */
export function frameOf(event: WatchEvent, resumeLinked: boolean, group: Group | null, place: Place = UNPLACED, usage: Usage | null = null): Frame {
  const { task } = event;
  const step = event.event === "step" ? event.step : null;
  const at = event.event === "step" ? event.at ?? null : null;
  const offset = at === null || Number.isNaN(new Date(task.createdAt).getTime()) ? null : at - task.createdAt;
  return {
    event: event.event, id: task.id, parent: task.parent === null ? null : task.parent.id, run: place.run, chain: place.chain,
    kind: step === null ? null : step.kind,
    active: !isTerminal(task.status), createdAt: task.createdAt,
    item: taskItem(task, usage), link: taskLink(task, resumeLinked), head: taskHead(task, usage),
    group: step === null || step.kind === "thinking-progress" ? null : group,
    text: step === null || step.kind === "thinking-progress" ? "" : summaryText(step),
    row: step === null ? "" : stepRow(step, group, offset),
    detail: step === null ? "" : stepDetail(step, task.id, at),
  };
}

/** A task that settled before the watch began, as a task of its own: its entry and its head with its own figure, its link, and a head that points at its log for its steps. */
export function historyFrame(task: WatchedTask, resumeLinked: boolean, place: Place = UNPLACED, usage: Usage | null = null): Frame {
  return {
    event: "history", id: task.id, parent: task.parent === null ? null : task.parent.id, run: place.run, chain: place.chain,
    kind: null, active: false, createdAt: task.createdAt,
    item: taskItem(task, usage), link: taskLink(task, resumeLinked),
    head: `${taskHead(task, usage)}<p class="note">settled before this watch began: see cross-agent log ${escapeHtml(task.id)} for its steps</p>`,
    group: null, text: "", row: "", detail: "",
  };
}

/** A stage's state as a chip or a checkpoint's title shows it: its icon and its word, coloured by the class its status names. */
function stageCell(status: StageStatus, word: string): string {
  return `<span class="st st-${escapeHtml(status)}">${icon(`status-${escapeHtml(status)}`)}<span class="word">${escapeHtml(word)}</span></span>`;
}

/** A run as its section of the task list and its head name it: a lead's by the first six characters of its id, a worktree's by its slug. */
export function runLabel(view: RunView): string {
  const [kind, name] = view.kind === "lead" ? ["Lead", view.name.slice(0, 6)] : ["Worktree", view.name];
  return `<span class="run-kind">${kind}</span><span class="run-name">${escapeHtml(name)}</span>`;
}

/**
 * One item of a run's strip. A task stage with a task is a button naming its first task,
 * with its status, its name, a review round's commit and how many of its tasks are done; a
 * checkpoint is a button naming its view; a stage with no task, or one the data cannot
 * link, is a span; and a separator names the task worktree whose stages follow it.
 */
function stripItem(item: StripItem): string {
  if (item.kind === "separator") return `<li class="seg">${escapeHtml(item.slug)}</li>`;
  const inner = `${stageCell(item.status, item.word)}<span class="chip-name">${escapeHtml(item.name)}</span>`
    + `${item.head === null ? "" : `<span class="id">${escapeHtml(item.head.slice(0, 7))}</span>`}`
    + `${item.count === null ? "" : `<span class="count">${item.count.done}/${item.count.total}</span>`}`;
  if (item.kind === "task" && item.task !== null) return `<li><button type="button" class="chip" data-task="${escapeHtml(item.task)}">${inner}</button></li>`;
  if (item.kind === "checkpoint" && item.checkpoint !== null) return `<li><button type="button" class="chip" data-checkpoint="${escapeHtml(item.checkpoint)}">${inner}</button></li>`;
  return `<li><span class="chip">${inner}</span></li>`;
}

/**
 * A run's figures so far: the sum of its finished members' own figures
 * (`src/steps.ts#sumUsage`), null where none has one, how many have finished and how many
 * it has. A member still active joins the sum once it has finished.
 */
export interface Totals {
  usage: Usage | null;
  finished: number;
  tasks: number;
}

/** A run's totals as its head shows them: so far its cost and tokens, `—` for none, over how many of its tasks have finished. */
function totalsCell(totals: Totals): string {
  const finished = `${totals.finished} of ${totals.tasks} finished`;
  const { usage } = totals;
  return `<span class="totals">${escapeHtml(usage === null ? `so far — · ${finished}` : `so far ${costText(usage.costUsd)} · ${tokensText(usage)} tokens · ${finished}`)}</span>`;
}

/** A run's head over the selected task's: its label and its totals, then its strip, which a run no loop maps has none of. */
export function runHead(view: RunView, totals: Totals): string {
  const strip = view.strip === null ? "" : `<ol class="strip" aria-label="Stages of this run">${view.strip.map(stripItem).join("")}</ol>`;
  return `<div class="run-title">${runLabel(view)}${totalsCell(totals)}</div>${strip}`;
}

/**
 * A gate's or the merge's view in the detail pane: its name, its task worktree and its
 * state, over its milestones — each step's word, `git` with its arguments for any other
 * `git_mutate` call, the first seven characters of the commit it left, and when it ran,
 * which the page writes in the viewer's own form — or why it has none: no milestone yet, no
 * journal yet, no task worktree yet, or a journal that does not read, with the reader's
 * reason.
 */
export function checkpointDetail(checkpoint: Checkpoint): string {
  const slug = checkpoint.slug === null ? "" : escapeHtml(checkpoint.slug);
  const file = `<code>.cross-agent/journal/${slug}.json</code>`;
  const title = `<h2 class="title"><span class="kind">${escapeHtml(checkpoint.name)}</span> `
    + `${checkpoint.slug === null ? "" : `<span class="id">${slug}</span> `}${stageCell(checkpoint.status, checkpoint.word)}</h2>`;
  if (checkpoint.milestones.length > 0) {
    const listed = checkpoint.milestones.map((milestone) => {
      const word = milestone.step === "git" ? ["git", ...(milestone.args ?? [])].join(" ") : milestone.step;
      const when = new Date(milestone.at);
      return `<li><span class="step">${escapeHtml(word)}</span>${milestone.head === null ? "" : `<span class="id">${escapeHtml(milestone.head.slice(0, 7))}</span>`}`
        + `${Number.isNaN(when.getTime()) ? "" : `<time class="started" datetime="${when.toISOString()}"></time>`}</li>`;
    }).join("");
    return `${title}<ol class="milestones">${listed}</ol>`;
  }
  switch (checkpoint.journal) {
    case "none":
      return `${title}<p class="note">No task worktree yet.</p>`;
    case "absent":
      return `${title}<p class="note">No journal yet: ${file} is written by this worktree's first git step.</p>`;
    case "unreadable":
      return `${title}<p class="note">The journal ${file} does not read:</p><pre class="reason">${escapeHtml(checkpoint.reason ?? "")}</pre>`;
    case "read":
      return `${title}<p class="note">This checkpoint has no milestones yet.</p>`;
  }
}

/**
 * A run as the page receives it, rendered once on the server: its key, the label its
 * section of the task list carries, the head shown over a task of it, its totals in it,
 * and each checkpoint's view by its id.
 */
export interface RunFrame {
  event: "run";
  run: string;
  label: string;
  runHead: string;
  checkpoints: Record<string, string>;
}

/** Every frame of the page's stream: a task's, or a run's. */
export type PageFrame = Frame | RunFrame;

/** A run's view and its totals as its frame. */
export function runFrame(view: RunView, totals: Totals): RunFrame {
  return {
    event: "run", run: view.key, label: runLabel(view), runHead: runHead(view, totals),
    checkpoints: Object.fromEntries(Object.entries(view.checkpoints).map(([id, checkpoint]) => [id, checkpointDetail(checkpoint)])),
  };
}

/** The page's icons, 16 pixels, drawn in strokes of the colour around them: each step kind's, each status's, and the page's own. */
const ICONS: Record<string, string> = {
  "kind-message": '<path d="M3 3.5h10a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H7.5L4.5 14v-2.5H3a1 1 0 0 1-1-1v-6a1 1 0 0 1 1-1z"/>',
  "kind-thinking": '<circle cx="4" cy="8" r=".6" stroke-width="2"/><circle cx="8" cy="8" r=".6" stroke-width="2"/><circle cx="12" cy="8" r=".6" stroke-width="2"/>',
  "kind-command": '<path d="M3 4.5 6.5 8 3 11.5M8.5 12H13"/>',
  "kind-result": '<path d="M13 3.5v3a2.5 2.5 0 0 1-2.5 2.5H3.5M6.5 6l-3 3 3 3"/>',
  "kind-edit": '<path d="M10.5 2.5l3 3-8 8h-3v-3zM9 4l3 3"/>',
  "kind-tool": '<path d="M10.5 2.5a3 3 0 0 0-2.8 4.1L2.5 11.8l1.7 1.7 5.2-5.2a3 3 0 0 0 4.1-2.8l-1.8 1.8-1.7-.4-.4-1.7z"/>',
  "kind-final": '<path d="M3.5 14V2.5M3.5 3h8L10 6l1.5 3h-8"/>',
  "kind-error": '<path d="M8 2.5 14 13.5H2zM8 6.5v3M8 11.5v.01"/>',
  "kind-stderr": '<path d="M2.5 3.5h11v9h-11zM8 5.5v3.5M8 10.75v.01"/>',
  "status-launching": '<circle cx="8" cy="8" r="5"/>',
  "status-running": '<circle cx="8" cy="8" r="2.5" stroke-width="5"/>',
  "status-stalled": '<circle cx="8" cy="8" r="5.5"/><path d="M6.5 6v4M9.5 6v4"/>',
  "status-orphaned": '<circle cx="8" cy="8" r="5.5"/><path d="M6.5 6.5a1.5 1.5 0 1 1 2 1.4c-.4.2-.5.5-.5.9v.3M8 10.75v.01"/>',
  "status-cancelling": '<circle cx="8" cy="8" r="5.5"/><path d="M5.5 8h5"/>',
  "status-done": '<path d="M3 8.5l3 3 7-7"/>',
  "status-failed": '<path d="M4 4l8 8M12 4l-8 8"/>',
  "status-cancelled": '<circle cx="8" cy="8" r="5.5"/><path d="M4.1 11.9l7.8-7.8"/>',
  "status-pending": '<circle cx="8" cy="8" r="5.5" stroke-dasharray="2.2 2.1"/>',
  "status-unlinked": '<path d="M6.5 4.5 7.6 3.4a2.5 2.5 0 0 1 3.5 3.5L10 8M6 8 4.9 9.1a2.5 2.5 0 0 0 3.5 3.5L9.5 11.5M2.5 2.5l11 11"/>',
  "status-unreadable": '<path d="M4 2.5h5.5L12 5v8.5H4zM8 6.5v3M8 11.5v.01"/>',
  "brand": '<circle cx="4" cy="4" r="1.75"/><circle cx="12" cy="4" r="1.75"/><circle cx="8" cy="12" r="1.75"/><path d="M5.75 4h4.5M4.9 5.5l2.3 4.9M11.1 5.5l-2.3 4.9"/>',
  "connection": '<circle cx="8" cy="8" r="2" stroke-width="4"/>',
  "theme": '<path d="M13 9.5A5.5 5.5 0 1 1 6.5 3a4.5 4.5 0 0 0 6.5 6.5z"/>',
  "follow": '<path d="M8 2.5v8M4.5 7 8 10.5 11.5 7M3.5 13.5h9"/>',
  "prev": '<path d="M10 3.5 5.5 8l4.5 4.5"/>',
  "next": '<path d="M6 3.5 10.5 8 6 12.5"/>',
};

/** The filters over a task's steps, in the page's order: All, then each group's. */
const FILTERS: Array<[Group | "all", string]> = [["all", "All"], ["command", "Commands"], ["edit", "Edits"], ["message", "Messages"], ["thinking", "Thinking"], ["tool", "Tools"]];

/**
 * The page, the Inspector: a header naming the project with the connection's state and a
 * theme toggle, over three panes — the task list, a section per run under its Unlinked
 * section, which shows once it holds a task; the selected task's run head, or a line saying
 * it is in none, over its steps with their filters, search and Follow latest; and the
 * selected step's detail, or a checkpoint's, with previous and next — and the sprite every
 * fragment's icons use, with the stylesheet and the script linked by absolute path under the
 * token. It holds no inline script, no `style` attribute and no event handler attribute,
 * which the CSP would refuse anyway, and loads nothing else.
 */
export function pageHtml(token: string, root: string): string {
  const base = `/${escapeHtml(token)}`;
  const sprite = Object.entries(ICONS).map(([name, paths]) => `<symbol id="i-${name}" viewBox="0 0 16 16">${paths}</symbol>`).join("");
  const filters = FILTERS.map(([group, word]) => `<button type="button" class="filter" data-group="${group}" aria-pressed="${group === "all"}">${word} <span class="count" id="count-${group}">0</span></button>`).join("");
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>cross-agent watch</title>
<link rel="stylesheet" href="${base}/style.css">
<script src="${base}/app.js" defer></script>
</head>
<body>
<svg class="sprite" aria-hidden="true" focusable="false">${sprite}</svg>
<header class="top"><h1 class="brand">${icon("brand")}cross-agent watch</h1><span class="root">${escapeHtml(root)}</span>`
    + `<span id="connection" data-state="connecting" role="status">${icon("connection")}<span id="connection-text">connecting…</span></span>`
    + `<button type="button" id="theme" aria-pressed="false">${icon("theme")}Dark theme</button></header>
<main id="inspector">
<nav class="pane pane-tasks" aria-label="Tasks"><h2 class="pane-title">Tasks</h2>`
    + `<ul id="tasks"><li id="unlinked" hidden><div class="run-label">Not linked to a run</div><ul id="unlinked-tasks"></ul></li></ul></nav>
<section class="pane pane-steps" aria-label="Steps"><div id="runs"></div><p id="run-none" class="empty" hidden>Not linked to a run.</p>`
    + `<div id="heads"></div><p id="heads-empty" class="empty">No task to show yet.</p>`
    + `<div class="filters" role="group" aria-label="Show steps of one kind">${filters}</div>`
    + `<div class="tools"><label for="search">Search steps</label><input id="search" type="search" autocomplete="off" spellcheck="false">`
    + `<button type="button" id="follow" aria-pressed="true">${icon("follow")}Follow latest</button></div>`
    + `<div id="rows"></div><p id="rows-empty" class="empty">No steps yet.</p></section>
<section class="pane pane-detail" aria-label="Step detail"><div class="detail-nav">`
    + `<button type="button" id="prev" disabled>${icon("prev")}Previous</button><button type="button" id="next" disabled>Next${icon("next")}</button></div>`
    + `<p id="detail-hidden" class="notice" hidden>This step is hidden by the current filter or search.</p><div id="detail"></div><p id="detail-empty" class="empty">No step selected.</p></section></main>
</body>
</html>
`;
}

/**
 * The page's two palettes, the epic's tokens: `ground` under the panes, `surface` the
 * panes, `sunken` code, inputs and the selected row, `line` the hairlines, `text`, `muted`
 * and `accent` for words, `ok` and `bad` for outcomes, and `live` and each engine's colour,
 * which only ever mark — a dot, a stroke, a swatch — and never colour words.
 */
export const THEMES = {
  light: {
    ground: "#F4F4F1", surface: "#FFFFFF", sunken: "#EFEFEA", line: "#DEDED8", text: "#16171A", muted: "#565A61", accent: "#2B55C8",
    live: "#B4530A", ok: "#1D7048", bad: "#B42318", claude: "#C2552C", codex: "#2F5DC4", grok: "#3F4148",
  },
  dark: {
    ground: "#0E0F11", surface: "#16181B", sunken: "#1D2024", line: "#2C3036", text: "#ECEDEF", muted: "#A5AAB2", accent: "#8AA8FF",
    live: "#F0A44B", ok: "#4CC38A", bad: "#F97066", claude: "#EE8A62", codex: "#86A6F5", grok: "#C3C6CD",
  },
};

/** A palette as custom properties. */
function palette(theme: Record<string, string>): string {
  return Object.entries(theme).map(([name, value]) => `--${name}: ${value};`).join(" ");
}

/**
 * The page's stylesheet: the Inspector in either theme — the OS's, unless the viewer chose
 * one, which the page script sets as `data-theme` — in three columns, two up to 1180 pixels
 * with the detail below, and one at 760 and under, where the task list and a run's strip
 * each become a row of buttons scrolling sideways in its own box, the strip positioned so a
 * chip's offset is from its left edge. The rows scroll inside their own box at every width,
 * a long line wraps, a wide table scrolls in its own and, on a wider screen, a run's strip
 * wraps, scrolling in its own past a third of the window's height, so nothing scrolls the
 * page sideways.
 */
export const PAGE_CSS = `:root { color-scheme: light; ${palette(THEMES.light)} }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme=light]) { color-scheme: dark; ${palette(THEMES.dark)} }
}
:root[data-theme=dark] { color-scheme: dark; ${palette(THEMES.dark)} }
[hidden] { display: none !important; }
* { box-sizing: border-box; }
body { display: flex; flex-direction: column; height: 100vh; margin: 0; background: var(--ground); color: var(--text); font-family: ui-sans-serif, system-ui; font-size: 14px; line-height: 1.45; }
code, pre, .mono, .root, .id, .runs, .elapsed, .since, .count, .usage, .totals, .offset, .changes, .run-name, .seg, .milestones .step { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.sprite { position: absolute; width: 0; height: 0; overflow: hidden; }
.ic { flex: none; width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
button, input { min-height: 44px; min-width: 44px; padding: 0 12px; color: inherit; font: inherit; background: var(--surface); border: 1px solid var(--line); border-radius: 6px; }
button { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
button:hover { background: var(--sunken); }
button:disabled { color: var(--muted); background: var(--surface); cursor: default; }
input { background: var(--sunken); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
#tasks button:focus-visible, #rows button:focus-visible, .block-head .copy:focus-visible, .strip button:focus-visible { outline-offset: -3px; }
.top { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; padding: 8px 16px; background: var(--surface); border-bottom: 1px solid var(--line); }
.brand { display: inline-flex; align-items: center; gap: 8px; margin: 0; font-size: 16px; font-weight: 600; }
.root { min-width: 0; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
#connection { display: inline-flex; align-items: center; gap: 6px; min-width: 0; margin-left: auto; color: var(--muted); overflow-wrap: anywhere; }
#connection .ic { stroke: var(--muted); }
#connection[data-state=live] .ic { stroke: var(--ok); }
#connection[data-state=reconnecting] .ic { stroke: var(--live); animation: pulse 1.6s ease-in-out infinite; }
#connection[data-state=stopped] { color: var(--bad); }
#connection[data-state=stopped] .ic { stroke: var(--bad); }
#inspector { flex: 1 1 auto; min-height: 0; display: grid; grid-template-columns: 300px minmax(0, 1fr) 420px; grid-template-rows: minmax(0, 1fr); gap: 12px; padding: 12px; }
.pane { display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow: hidden; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; }
.pane-title { margin: 0; padding: 10px 12px; color: var(--muted); font-size: 12px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; border-bottom: 1px solid var(--line); }
.empty, .notice { margin: 0; padding: 12px; color: var(--muted); }
.notice { border-bottom: 1px solid var(--line); }
#tasks, #tasks ul { margin: 0; padding: 0; list-style: none; }
#tasks { flex: 1 1 auto; min-height: 0; overflow-y: auto; padding: 6px; }
#tasks ul { margin-left: 14px; padding-left: 8px; border-left: 1px solid var(--line); }
#tasks > li > ul { margin-left: 0; padding-left: 0; border-left: 0; }
#tasks > li + li { margin-top: 6px; }
#tasks > li > div { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 6px; padding: 6px 10px 4px; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
.run-kind { font-weight: 600; letter-spacing: .04em; text-transform: uppercase; }
#tasks ul:empty, #tasks li > span:empty { display: none; }
#tasks li > button { flex-wrap: wrap; gap: 2px 8px; width: 100%; padding: 6px 10px; text-align: left; background: transparent; border-color: transparent; }
#tasks li > button[aria-current=true], #rows li > button[aria-current=true] { background: var(--sunken); border-color: var(--accent); }
#tasks .elapsed { margin-left: auto; }
#tasks .usage { flex-basis: 100%; }
.label { font-weight: 600; }
.st { display: inline-flex; align-items: center; gap: 4px; }
.st-launching, .st-cancelling, .st-cancelled { color: var(--muted); }
.st-pending, .st-unlinked { color: var(--muted); }
.st-done { color: var(--ok); }
.st-failed, .st-orphaned { color: var(--bad); }
.st-unreadable { color: var(--bad); }
.st-running .ic, .st-stalled .ic, .st-cancelling .ic { stroke: var(--live); }
.st-running .ic { animation: pulse 1.6s ease-in-out infinite; }
.eng { display: inline-flex; align-items: center; gap: 4px; color: var(--muted); }
.eng .mark { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
.eng-claude .mark { background: var(--claude); }
.eng-codex .mark { background: var(--codex); }
.eng-grok .mark { background: var(--grok); }
.id, .runs, .elapsed, .since, .count, .usage, .totals, .offset { color: var(--muted); font-size: 12px; }
.resumes { display: inline-flex; align-items: center; min-height: 44px; min-width: 44px; padding: 0 8px; margin-left: 12px; color: var(--accent); border-radius: 6px; }
.resumes-text { display: inline-block; padding: 0 8px 6px 22px; color: var(--muted); font-size: 12px; }
#runs > div { padding: 12px; border-bottom: 1px solid var(--line); }
#runs > div:empty { display: none; }
.run-title { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 8px; min-width: 0; }
.run-title .run-kind { color: var(--muted); font-size: 12px; }
.run-title .totals { margin-left: auto; }
.run-name { font-weight: 600; overflow-wrap: anywhere; }
.strip { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; max-height: 30vh; overflow-y: auto; margin: 8px 0 0; padding: 4px; list-style: none; }
.strip li { display: flex; min-width: 0; }
span.chip { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 12px; color: var(--muted); border: 1px dashed var(--line); border-radius: 6px; }
.chip .chip-name { font-weight: 600; }
.strip .seg { flex: 0 0 100%; padding: 6px 2px 0; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
#heads > div { padding: 12px; border-bottom: 1px solid var(--line); }
.head-line { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; min-width: 0; }
.head-line .label { margin: 0; font-size: 18px; overflow-wrap: anywhere; }
.thinking-indicator { display: none; align-items: center; gap: 4px; color: var(--muted); }
#heads > div[data-state=thinking] .thinking-indicator { display: inline-flex; }
.thinking-indicator .ic { stroke: var(--live); animation: pulse 1.2s ease-in-out infinite; }
.reason { max-height: 12em; overflow-y: auto; color: var(--bad); }
.note { margin: 8px 0 0; color: var(--muted); }
.filters, .tools { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 8px 12px 0; }
.tools { padding-bottom: 8px; border-bottom: 1px solid var(--line); }
.tools label { color: var(--muted); }
#search { flex: 1 1 160px; }
.filter[aria-pressed=true], #follow[aria-pressed=true] { background: var(--sunken); border-color: var(--accent); }
#rows { position: relative; flex: 1 1 auto; min-height: 0; overflow-y: auto; }
#rows ol { margin: 0; padding: 4px; list-style: none; }
#rows li > button { align-items: flex-start; gap: 8px; width: 100%; padding: 8px 10px; text-align: left; background: transparent; border-color: transparent; animation: fade-in .2s ease-out; }
#rows li > button > .ic, .title > .ic { margin-top: 2px; }
.sum { flex: 1 1 auto; min-width: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.sum.mono, .sum code { font-size: 12px; }
.sum code, .md code { padding: 0 4px; background: var(--sunken); border: 1px solid var(--line); border-radius: 6px; }
.k-thinking { color: var(--muted); font-style: italic; }
.k-error, .k-stderr { color: var(--bad); }
.k-final { font-weight: 600; }
.pill { flex: none; padding: 0 6px; font-size: 12px; border: 1px solid currentColor; border-radius: 6px; }
.pill-ok { color: var(--ok); }
.pill-bad { color: var(--bad); }
.offset { flex: none; margin-left: auto; }
.detail-nav { display: flex; gap: 8px; padding: 8px 12px; border-bottom: 1px solid var(--line); }
#next { margin-left: auto; }
#detail { flex: 1 1 auto; min-height: 0; overflow-y: auto; padding: 12px; overflow-wrap: anywhere; }
#detail:empty { display: none; }
.title { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 4px 8px; margin: 0 0 12px; font-size: 16px; font-weight: 400; }
.title .kind { font-weight: 600; }
.title time { margin-left: auto; color: var(--muted); font-size: 12px; }
.block { margin: 0 0 12px; overflow: hidden; border: 1px solid var(--line); border-radius: 8px; }
.block-head { display: flex; align-items: center; justify-content: space-between; padding-left: 10px; color: var(--muted); font-size: 12px; border-bottom: 1px solid var(--line); }
.block-head .copy { border-width: 0 0 0 1px; border-radius: 0; }
pre { margin: 0; padding: 8px 10px; background: var(--sunken); white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; }
#detail > pre, .md pre, .reason { margin: 8px 0 0; border-radius: 6px; }
.diff span { display: block; }
.diff .add { background: rgba(29, 112, 72, .16); background: color-mix(in srgb, var(--ok) 16%, transparent); }
.diff .del { background: rgba(180, 35, 24, .16); background: color-mix(in srgb, var(--bad) 16%, transparent); }
.diff .hunk { color: var(--muted); }
.changes { margin: 8px 0; padding-left: 20px; font-size: 12px; }
.cut { padding: 6px 10px; color: var(--muted); font-size: 12px; font-style: italic; }
.milestones { margin: 0; padding: 0; list-style: none; }
.milestones li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 12px; padding: 8px 0; border-bottom: 1px solid var(--line); }
.milestones .step { font-size: 12px; overflow-wrap: anywhere; }
.milestones time { color: var(--muted); font-size: 12px; }
.md { line-height: 1.55; }
.md > :first-child { margin-top: 0; }
.md h1, .md h2, .md h3, .md h4, .md h5, .md h6 { margin: 14px 0 6px; font-size: 15px; }
.md p, .md ul, .md ol, .md blockquote { margin: 8px 0; }
.md pre code { padding: 0; background: none; border: 0; }
.md table { display: block; max-width: 100%; overflow-x: auto; margin: 8px 0; border-collapse: collapse; }
.md th, .md td { padding: 4px 8px; text-align: left; border: 1px solid var(--line); }
.md blockquote { padding-left: 10px; color: var(--muted); border-left: 2px solid var(--line); }
.md hr { border: 0; border-top: 1px solid var(--line); }
@keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
@keyframes pulse { 50% { opacity: .35; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }
@media (max-width: 1180px) {
  body { height: auto; min-height: 100vh; }
  #inspector { flex: none; grid-template-columns: 300px minmax(0, 1fr); grid-template-rows: 70vh auto; }
  .pane-detail { grid-column: 1 / -1; }
}
@media (max-width: 760px) {
  .top { padding: 8px 12px; }
  #connection { margin-left: 0; }
  #inspector { grid-template-columns: minmax(0, 1fr); grid-template-rows: none; gap: 8px; padding: 8px; }
  #tasks { display: flex; flex-direction: row; gap: 8px; overflow-x: auto; overflow-y: hidden; padding: 8px; }
  #tasks li, #tasks ul { display: contents; }
  #tasks > li > div { flex: none; align-self: center; max-width: 40vw; padding: 0 4px; }
  #tasks li > button { flex: none; width: auto; max-width: 80vw; }
  .resumes, .resumes-text { flex: none; align-self: center; margin-left: 0; padding: 0 8px; }
  #rows { max-height: 60vh; }
  .strip { flex-wrap: nowrap; max-height: none; overflow-x: auto; overflow-y: hidden; position: relative; }
  .strip li, .strip .seg { flex: none; }
  .strip .seg { padding-top: 0; }
}
`;
