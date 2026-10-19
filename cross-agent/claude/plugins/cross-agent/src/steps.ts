import { failureText, truncate } from "./engines/text.ts";
import type { FailureLine } from "./engines/text.ts";

/**
 * What one line of a task's engine stream says, as steps a person reads: the role's
 * messages and thinking, the calls it makes and their results, and how its turn ended.
 * The adapters' `parseLine` reads the same lines for the runner and keeps 200 characters
 * of them (`src/engines/text.ts#truncate`); a step keeps everything — a call its whole
 * input, a result its readable `output` and its whole `payload` as the engine recorded it —
 * beside a `summary` of one line, so `cross-agent watch` prints the summary and a richer
 * view reads the rest. `summary` and `output` read the same for every engine; `payload` is
 * the engine's own shape. Nothing here names a mode or a role: every task writes the same
 * stream, whoever delegated it.
 */
export type Step = { summary: string } & (
  | { kind: "message"; text: string }
  | { kind: "thinking"; text: string }
  /** Claude's `system/thinking_tokens`: the model is still thinking, with no text to show. */
  | { kind: "thinking-progress"; estimatedTokens: number | null }
  | { kind: "command"; id: string | null; command: string; input: unknown }
  | { kind: "edit"; id: string | null; tool: string; paths: string[]; input: unknown }
  | { kind: "tool"; id: string | null; name: string; input: unknown }
  | { kind: "result"; id: string | null; ok: boolean; exitCode: number | null; output: string; payload: unknown }
  | { kind: "final"; ok: boolean; text: string }
  | { kind: "error"; text: string }
  | { kind: "stderr"; text: string });

/** One reader per task: it pairs each result with its call, so it reads that task's lines in order. */
export type StepReader = (line: string) => Step[];

/**
 * What a task's engine reported spending, as one result event says it (`docs/probes.md`,
 * anchor `resultFigures`): its cost in dollars, null where the engine reports none, as
 * Codex does, and its tokens, null where the event carries no count of them. `input` is
 * every input token, cache reads and writes included; `cached` the cache reads, a part of
 * it; `output` every output token; and `reasoning` the part of `output` spent reasoning,
 * null where the engine counts none apart. `scope` is what the figure counts: the whole
 * session so far, as Claude's and Codex's do, or its round alone, as Grok's does.
 */
export interface Usage {
  costUsd: number | null;
  tokens: { input: number; cached: number; output: number; reasoning: number | null } | null;
  scope: "session" | "round";
}

/** One line of a task's stream read once: its steps, when it was written where it says so, and the figure a result event reports. */
export interface LineRead {
  steps: Step[];
  at: number | null;
  usage: Usage | null;
}

/** One reader per task, as a `StepReader` is, that reads each line's time and figure beside its steps. */
export type LineReader = (line: string) => LineRead;

type Json = Record<string, unknown>;

/** The prefix the runner gives every chunk the engine wrote on stderr (`src/engines/spawn.ts`, anchor `stderrPrefixed`). */
const STDERR = "stderr ";

/** The input keys a call's summary names, the first value that says anything winning; the first five are paths; a search reads by its pattern first (`summaries`). */
const SUMMARY_KEYS = ["file_path", "notebook_path", "path", "target_file", "target_directory", "pattern", "query", "url", "command", "tool_name", "description", "prompt"];
const PATH_KEYS = new Set(SUMMARY_KEYS.slice(0, 5));

/**
 * The two engines that speak the Messages wire shape: the tool each runs a shell command
 * through, the tools that edit a file, the tools that search files by a pattern, and how
 * each says its run succeeded and where it puts a failure's words — the adapters' own
 * readings (`src/engines/claude.ts`, `src/engines/grok.ts`).
 */
const MESSAGES_ENGINES: Record<string, {
  shell: string; edits: ReadonlySet<string>; searches: ReadonlySet<string>; succeeded(event: Json): boolean; failure: "result" | "errors";
}> = {
  claude: {
    shell: "Bash", edits: new Set(["Edit", "Write", "MultiEdit", "NotebookEdit"]), searches: new Set(["Grep", "Glob"]),
    succeeded: (event) => event.is_error === false && event.subtype === "success", failure: "result",
  },
  grok: {
    shell: "run_terminal_command", edits: new Set(["search_replace"]), searches: new Set(["grep"]),
    succeeded: (event) => event.is_error === false, failure: "errors",
  },
};

function isObject(value: unknown): value is Json {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function idOf(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

/** The first line that holds anything, its trailing blanks trimmed, and ` …` when more text follows it. */
function oneLine(text: string): string {
  const lines = text.split("\n");
  const first = lines.findIndex((line) => line.trim() !== "");
  if (first === -1) return "";
  const more = lines.slice(first + 1).some((line) => line.trim() !== "");
  return `${lines[first].trimEnd()}${more ? " …" : ""}`;
}

/** The C0 controls but tab, line breaks among them, DEL and the C1 controls. */
const CONTROLS = /[\u0000-\u0008\u000a-\u001f\u007f-\u009f]/g;
/** What a summary shows in a control character's place: U+FFFD, the replacement character. */
const STAND_IN = String.fromCodePoint(0xfffd);

/**
 * Text made one line a terminal prints as it is: every control character but tab, a
 * carriage return or an escape sequence from model or tool output among them, one visible
 * stand-in. Every summary goes through it, and so does any other engine text `watch` prints,
 * a failure's reason among it.
 */
export function sanitize(text: string): string {
  return text.replace(CONTROLS, STAND_IN);
}

/** A summary as composed, sanitized and cut whole at 200 code points; the detail beside it keeps the original. */
function summaryOf(text: string): string {
  return truncate(sanitize(text));
}

/**
 * A summary: its prefix and the text's first line, the prefix included in the cut. A text
 * with no line that holds anything leaves the prefix's word alone, the separator after it
 * dropped: `$`, `→ exit 1`, `failed`.
 */
function summarize(prefix: string, text: string): string {
  const line = oneLine(text);
  return line === "" ? summaryOf(prefix.replace(/:? $/, "")) : summaryOf(`${prefix}${line}`);
}

/**
 * Engine text read as a summary is read, with no prefix: its first line that holds anything,
 * sanitized and cut at 200 code points, and ` …` when more follows. `watch` reads a settled
 * task's reason through it, which is the engine's own words.
 */
export function summaryLine(text: string): string {
  return summarize("", text);
}

/** How a task's turn ended. */
function finalStep(ok: boolean, text: string): Step {
  const summary = !ok ? summarize("failed: ", text) : text.trim() === "" ? "finished" : summarize("finished: ", text);
  return { kind: "final", ok, text, summary };
}

/**
 * A result's summary: the exit code of a command, with the command it closes; a failure's
 * first line; or that it succeeded, naming the call it closes where that is neither a
 * command nor an edit, which `watch` leaves out of its text unless it carries an exit code.
 * The call is named by `about`, the prefix within the 200-code-point cut: its own summary
 * or, for a Grok `Web search:` result, the page and pattern `webSearchAbout` read from its
 * record.
 */
function resultSummary(ok: boolean, exitCode: number | null, output: string, command: string | undefined, about?: string): string {
  if (command !== undefined) {
    if (exitCode !== null) return summarize(`→ exit ${exitCode}: `, command);
    if (ok) return "→ ok";
    // A command that never ran, one declined among them, said nothing: its failure names it,
    // and one with no text to name is a failure and nothing more.
    const said = output.trim() === "" ? command : output;
    return said.trim() === "" ? "→ failed" : summarize("→ failed: ", said);
  }
  if (ok) return about === undefined ? "→ ok" : summarize("→ ok: ", about);
  return output.trim() === "" ? "→ failed" : summarize("→ error: ", output);
}

/** Bytes as Grok writes a command's output, a list of numbers, read as UTF-8; a string as it is. */
function bytes(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (Array.isArray(value) && value.every((each) => typeof each === "number")) return Buffer.from(value as number[]).toString("utf8");
  return null;
}

/**
 * What a Grok `Web search:` result is about, read from its record (`docs/probes.md`, anchor
 * `grokToolResults`): an untagged object whose `action` names the page it opened, and the
 * pattern it searched for in it where the record holds one; null for any other payload.
 */
function webSearchAbout(payload: unknown): string | null {
  if (!isObject(payload) || typeof payload.type === "string" || !isObject(payload.action)) return null;
  const { url, pattern } = payload.action;
  if (typeof url !== "string" || url === "") return null;
  return typeof pattern === "string" && pattern.trim() !== "" ? `Web search: ${url} find ${pattern}` : `Web search: ${url}`;
}

/**
 * A call awaiting its result: its kind, and what its result is summarized by — a command's
 * command, or any other call's own summary but an edit's, `about`.
 */
interface Call {
  kind: "command" | "edit" | "tool";
  command?: string;
  about?: string;
}

/** The call a call's step opens, as its result will name it. */
function callOf(step: Step): Call {
  if (step.kind === "command") return { kind: "command", command: step.command };
  if (step.kind === "tool") return { kind: "tool", about: step.summary };
  return { kind: "edit" };
}

/** The summaries of a call, which name paths relative to the task's cwd. */
function summaries(cwd: string) {
  /** A path as a summary names it: relative under the task's cwd, the cwd itself `.` with its trailing slash or without, anything else as it is. */
  const rel = (file: string): string => (file === cwd || file === `${cwd}/` ? "." : file.startsWith(`${cwd}/`) ? file.slice(cwd.length + 1) : file);
  /**
   * A call's name and the first input value that says what it is about, or its input whole
   * where none does. A path is a name and is kept whole, a line break in it one stand-in, as
   * an edit's are; any other value says its first line that holds anything, so one of blanks
   * alone says nothing, as an empty one does.
   */
  const argSummary = (name: string, input: unknown): string => {
    if (isObject(input)) {
      for (const key of SUMMARY_KEYS) {
        const value = input[key];
        if (typeof value !== "string" || value === "") continue;
        const said = PATH_KEYS.has(key) ? rel(value) : oneLine(value);
        if (said !== "") return summaryOf(`${name} ${said}`);
      }
      if (Object.keys(input).length > 0) return summaryOf(`${name} ${JSON.stringify(input)}`);
    }
    return summaryOf(name);
  };
  /**
   * A search's name and the pattern it searched for, with the path it searched in after it
   * where its input names one; its glob and its flags are left to its input. One with no
   * pattern, or a blank one, reads as any other call.
   */
  const searchSummary = (name: string, input: unknown): string => {
    const pattern = isObject(input) && typeof input.pattern === "string" ? oneLine(input.pattern) : "";
    if (!isObject(input) || pattern === "") return argSummary(name, input);
    const where = typeof input.path === "string" && input.path !== "" ? ` in ${rel(input.path)}` : "";
    return summaryOf(`${name} ${pattern}${where}`);
  };
  const editSummary = (paths: string[]): string => summaryOf(paths.length === 0 ? "edits" : `edits ${paths.map(rel).join(", ")}`);
  return { argSummary, editSummary, searchSummary };
}

/**
 * Claude's stream-json and Grok's streaming-messages-json, both in the Anthropic Messages
 * wire shape: an `assistant` line holds the turn's blocks, a `user` line the results of its
 * calls, and a `result` line ends the run.
 */
function messagesReader(engine: string, cwd: string): (event: Json) => Step[] {
  const table = MESSAGES_ENGINES[engine];
  const { argSummary, editSummary, searchSummary } = summaries(cwd);
  const calls = new Map<string, Call>();
  const message = (text: string): Step => ({ kind: "message", text, summary: summarize("says: ", text) });

  /** A call's step, entered in `calls` until its result is read. */
  const call = (block: Json): Step => {
    const id = idOf(block.id);
    const name = asText(block.name);
    const input = block.input;
    let step: Step;
    if (block.type === "tool_use" && name === table.shell) {
      const command = asText(isObject(input) ? input.command : undefined);
      step = { kind: "command", id, command, input, summary: summarize("$ ", command) };
    } else if (block.type === "tool_use" && table.edits.has(name)) {
      const file = isObject(input) ? input.file_path ?? input.notebook_path : undefined;
      const paths = typeof file === "string" ? [file] : [];
      step = { kind: "edit", id, tool: name, paths, input, summary: editSummary(paths) };
    } else {
      step = { kind: "tool", id, name, input, summary: table.searches.has(name) ? searchSummary(name, input) : argSummary(name, input) };
    }
    if (id !== null) calls.set(id, callOf(step));
    return step;
  };

  /** A result's readable text: Claude's content as it is, or its blocks each as text. */
  const contentText = (content: unknown): string => {
    if (typeof content === "string") return content;
    if (!Array.isArray(content)) return content === undefined || content === null ? "" : JSON.stringify(content);
    return content.map((block) => {
      if (isObject(block) && block.type === "text" && typeof block.text === "string") return block.text;
      if (isObject(block) && block.type === "tool_reference" && typeof block.tool_name === "string") return block.tool_name;
      return JSON.stringify(block);
    }).join("\n");
  };

  /**
   * Grok writes a tool's result as JSON in a string (`docs/probes.md`, anchor
   * `grokToolResults`), and its output is the text that JSON holds. A tool's own result is
   * an object tagged by `type`: a command's or a search's bytes in `output` or `stdout`, or
   * else the first entry beside the tag that is a string — a failure's own message — or an
   * object with a string `content`, a file read's, a listing's or a fetch's. An untagged
   * object, a web search's record among them, is read for such bytes alone. The permission
   * layer's refusal is a list of content blocks each holding a text block, read as their
   * texts. Any other shape, an empty list among them, is its content as it came; the exit
   * code is `exit_code`, which `result` keeps for a command's result alone, and the payload
   * the JSON parsed, whole.
   */
  const grokResult = (content: unknown): { output: string; exitCode: number | null; payload: unknown } => {
    if (typeof content !== "string") return { output: contentText(content), exitCode: null, payload: content };
    let parsed: unknown;
    try {
      parsed = JSON.parse(content);
    } catch {
      return { output: content, exitCode: null, payload: content };
    }
    if (Array.isArray(parsed)) {
      const texts = parsed.map((each) => (isObject(each) && each.type === "content" && isObject(each.content) && each.content.type === "text"
        && typeof each.content.text === "string" ? each.content.text : null));
      return { output: texts.length > 0 && texts.every((text) => text !== null) ? texts.join("\n") : content, exitCode: null, payload: parsed };
    }
    if (!isObject(parsed)) return { output: content, exitCode: null, payload: parsed };
    const held = typeof parsed.type !== "string" ? undefined : Object.entries(parsed).flatMap(([key, value]) => {
      if (key === "type") return [];
      if (typeof value === "string") return [value];
      return isObject(value) && typeof value.content === "string" ? [value.content] : [];
    })[0];
    return {
      output: bytes(parsed.output) ?? bytes(parsed.stdout) ?? held ?? content,
      exitCode: typeof parsed.exit_code === "number" ? parsed.exit_code : null,
      payload: parsed,
    };
  };

  const result = (block: Json, toolUseResult: unknown): Step => {
    const id = idOf(block.tool_use_id);
    const paired = id === null ? undefined : calls.get(id);
    if (id !== null) calls.delete(id);
    const ok = block.is_error !== true;
    let output: string;
    let exitCode: number | null;
    let payload: unknown;
    let about = paired?.about;
    if (engine === "grok") {
      ({ output, exitCode, payload } = grokResult(block.content));
      // A search's result carries a code as a command's does, 1 where it matched nothing, but
      // only a command's is read: any other result's code stays in its payload.
      if (paired?.kind !== "command") exitCode = null;
      // A `Web search:` call's input names nothing it searched: its record names the page.
      if (paired === undefined || paired.kind === "tool") about = webSearchAbout(payload) ?? about;
    } else {
      output = contentText(block.content);
      // Claude's results carry no exit code: a command that did not fail exited 0, and one
      // that did says its code first.
      const stated = /^Exit code (\d+)/.exec(output);
      exitCode = paired?.kind !== "command" ? null : ok ? 0 : stated === null ? null : Number(stated[1]);
      payload = { result: block, toolUseResult };
    }
    return { kind: "result", id, ok, exitCode, output, payload, summary: resultSummary(ok, exitCode, output, paired?.command, about) };
  };

  return (event) => {
    switch (event.type) {
      case "system": {
        if (event.subtype !== "thinking_tokens") return [];
        const estimated = typeof event.estimated_tokens === "number" ? event.estimated_tokens : null;
        return [{ kind: "thinking-progress", estimatedTokens: estimated, summary: estimated === null ? "thinking…" : `thinking… (~${estimated} tokens)` }];
      }
      case "assistant": {
        const content = isObject(event.message) ? event.message.content : undefined;
        if (typeof content === "string") return [message(content)];
        if (!Array.isArray(content)) return [];
        const steps: Step[] = [];
        for (const block of content) {
          if (!isObject(block)) continue;
          if (block.type === "text" && typeof block.text === "string") steps.push(message(block.text));
          else if (block.type === "thinking" && typeof block.thinking === "string" && block.thinking.trim() !== "") {
            steps.push({ kind: "thinking", text: block.thinking, summary: summarize("thinks: ", block.thinking) });
          } else if (block.type === "tool_use" || block.type === "server_tool_use") {
            steps.push(call(block));
          } else if (block.type === "web_search_tool_result") {
            const id = idOf(block.tool_use_id);
            const about = id === null ? undefined : calls.get(id)?.about;
            if (id !== null) calls.delete(id);
            const found = Array.isArray(block.content);
            const output = found ? (block.content as unknown[]).map((each) => asText(isObject(each) ? each.url : undefined)).filter((url) => url !== "").join("\n")
              : JSON.stringify(block.content ?? null);
            steps.push({ kind: "result", id, ok: found, exitCode: null, output, payload: block, summary: resultSummary(found, null, output, undefined, about) });
          }
        }
        return steps;
      }
      case "user": {
        const content = isObject(event.message) ? event.message.content : undefined;
        if (!Array.isArray(content)) return [];
        const results = content.filter((block): block is Json => isObject(block) && block.type === "tool_result");
        // The line's own record of the call, whole — a diff, a command's stdout and stderr
        // apart — belongs to its one result; a line of several results cannot say whose it is.
        const toolUseResult = results.length === 1 ? event.tool_use_result ?? null : null;
        return results.map((block) => result(block, toolUseResult));
      }
      case "result": {
        const ok = table.succeeded(event);
        return [finalStep(ok, ok ? asText(event.result) : failureText(event as FailureLine, table.failure, engine))];
      }
      default:
        return [];
    }
  };
}

/**
 * Codex's `exec --json`: a call is announced on `item.started` and closed on
 * `item.completed`, which carries the item whole; `turn.completed` carries no message, so
 * the run's last word is the turn's last `agent_message`.
 */
function codexReader(cwd: string): (event: Json) => Step[] {
  const { argSummary, editSummary } = summaries(cwd);
  const calls = new Map<string, Call>();
  let lastMessage = "";

  /** The step an item that is a call opens with, or null for one that is not a call. */
  const started = (item: Json): Step | null => {
    const id = idOf(item.id);
    switch (item.type) {
      case "command_execution": {
        const command = asText(item.command);
        return { kind: "command", id, command, input: item, summary: summarize("$ ", command) };
      }
      case "file_change": {
        const changes = Array.isArray(item.changes) ? item.changes : [];
        const paths = changes.map((change) => asText(isObject(change) ? change.path : undefined)).filter((file) => file !== "");
        return { kind: "edit", id, tool: "file_change", paths, input: item.changes, summary: editSummary(paths) };
      }
      case "mcp_tool_call": {
        const name = `${asText(item.server)}.${asText(item.tool)}`;
        const input = item.arguments ?? {};
        return { kind: "tool", id, name, input, summary: argSummary(name, input) };
      }
      case "web_search": case "agent_message": case "reasoning": case "error":
        return null;
      default: {
        // An item type this reader has no reading of is still a call the operator sees.
        const name = typeof item.type === "string" ? item.type : "item";
        return { kind: "tool", id, name, input: item, summary: summaryOf(name) };
      }
    }
  };

  const open = (item: Json): Step[] => {
    const step = started(item);
    if (step === null) return [];
    const id = idOf(item.id);
    if (id !== null) calls.set(id, callOf(step));
    return [step];
  };

  const completed = (item: Json): Step[] => {
    const id = idOf(item.id);
    // A completion whose start was never read announces its call first.
    const opening = id !== null && calls.has(id) ? [] : open(item);
    const about = id === null ? undefined : calls.get(id)?.about;
    if (id !== null) calls.delete(id);
    const closed = (ok: boolean, exitCode: number | null, output: string, command?: string): Step[] => [
      ...opening, { kind: "result", id, ok, exitCode, output, payload: item, summary: resultSummary(ok, exitCode, output, command, about) },
    ];
    switch (item.type) {
      case "agent_message": {
        lastMessage = asText(item.text);
        return [{ kind: "message", text: lastMessage, summary: summarize("says: ", lastMessage) }];
      }
      case "reasoning": {
        const text = asText(item.text);
        return text.trim() === "" ? [] : [{ kind: "thinking", text, summary: summarize("thinks: ", text) }];
      }
      case "error": {
        const text = asText(item.message);
        return [{ kind: "error", text, summary: summarize("error: ", text) }];
      }
      case "command_execution": {
        const exitCode = typeof item.exit_code === "number" ? item.exit_code : null;
        // The completed item carries its own command, which is the one it ran.
        return closed(exitCode === 0, exitCode, asText(item.aggregated_output), asText(item.command));
      }
      case "file_change":
        return closed(item.status === "completed", null, "");
      case "mcp_tool_call": {
        const content = isObject(item.result) && Array.isArray(item.result.content) ? item.result.content : [];
        const text = content.filter((block) => isObject(block) && block.type === "text").map((block) => asText((block as Json).text)).join("\n");
        const failure = isObject(item.error) ? asText(item.error.message) : "";
        return closed(item.status === "completed", null, text !== "" ? text : failure);
      }
      case "web_search": {
        const action = isObject(item.action) ? item.action : {};
        const searched = asText(item.query) || asText(action.url);
        const results = Array.isArray(item.results) ? item.results : [];
        const output = results.filter(isObject).map((each) => [asText(each.url), asText(each.snippet)].filter((part) => part !== "").join(" ")).join("\n");
        const search: Step = {
          kind: "tool", id, name: "web_search", input: { query: item.query, action: item.action }, summary: summaryOf(searched === "" ? "web_search" : `web_search ${oneLine(searched)}`),
        };
        return [search, { kind: "result", id, ok: true, exitCode: null, output, payload: item, summary: resultSummary(true, null, output, undefined, search.summary) }];
      }
      default:
        // An item type with no reading of its own — a collaboration call among them — still
        // closes as a result, which keeps the completed item whole; one that carries no
        // status is read as done.
        return closed(item.status === undefined || item.status === "completed", null, "");
    }
  };

  return (event) => {
    switch (event.type) {
      case "turn.started":
        lastMessage = "";
        return [];
      case "item.started": {
        if (!isObject(event.item)) return [];
        // A start read twice announces its call once.
        const id = idOf(event.item.id);
        return id !== null && calls.has(id) ? [] : open(event.item);
      }
      case "item.completed":
        return isObject(event.item) ? completed(event.item) : [];
      case "turn.completed":
        return [finalStep(true, lastMessage)];
      case "turn.failed": {
        const text = isObject(event.error) ? asText(event.error.message) : "";
        return [finalStep(false, text !== "" ? text : "codex reported a failed turn with no message")];
      }
      case "error": {
        const text = asText(event.message);
        return [{ kind: "error", text, summary: summarize("error: ", text) }];
      }
      default:
        return [];
    }
  };
}

/** A count as a result event gives one: a finite number at or above zero, or absent. */
function count(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

/** What each engine's result event is, as its stream names it: the line holds the word before it is parsed. */
const RESULT_EVENTS: Record<string, string> = { claude: "result", codex: "turn.completed", grok: "result" };

/**
 * A parsed line's figure, by its engine's own reading of its result event, a failure's
 * read as a success's is. Claude's cost is `total_cost_usd` and its tokens every model's
 * entry in `modelUsage`, which `total_cost_usd` charges too, where its `usage` counts the
 * main model alone and only since its process's previous result event. Codex's tokens are
 * `turn.completed`'s `usage`, its input holding its cache reads, and it reports no cost.
 * Grok's are its result's `total_cost_usd` and `usage`, whose input leaves the cache
 * reads and writes out. A figure with neither a cost nor tokens is none.
 */
function usageFrom(engine: string, event: Json): Usage | null {
  if (!Object.hasOwn(RESULT_EVENTS, engine) || event.type !== RESULT_EVENTS[engine]) return null;
  const costUsd = engine === "codex" ? null : count(event.total_cost_usd);
  let tokens: Usage["tokens"] = null;
  if (engine === "claude") {
    const entries = isObject(event.modelUsage) ? Object.values(event.modelUsage).filter(isObject) : [];
    if (entries.length > 0) {
      const sum = (field: string) => entries.reduce((total, entry) => total + (count(entry[field]) ?? 0), 0);
      const cached = sum("cacheReadInputTokens");
      tokens = {
        input: sum("inputTokens") + cached + sum("cacheCreationInputTokens"), cached, output: sum("outputTokens"),
        reasoning: entries.some((entry) => count(entry.thinkingTokens) !== null) ? sum("thinkingTokens") : null,
      };
    }
  } else {
    const usage = isObject(event.usage) ? event.usage : {};
    const input = count(usage.input_tokens);
    const output = count(usage.output_tokens);
    if (input !== null && output !== null) {
      tokens = engine === "codex"
        ? { input, cached: count(usage.cached_input_tokens) ?? 0, output, reasoning: count(usage.reasoning_output_tokens) }
        : {
          input: input + (count(usage.cache_read_input_tokens) ?? 0) + (count(usage.cache_creation_input_tokens) ?? 0),
          cached: count(usage.cache_read_input_tokens) ?? 0, output, reasoning: null,
        };
    }
  }
  if (costUsd === null && tokens === null) return null;
  return { costUsd, tokens, scope: engine === "grok" ? "round" : "session" };
}

/**
 * The figure one line of a stream read whole reports: its engine's result event's, or
 * null for any other line, a stderr line, one that does not parse and one of an engine
 * with no reading among them. A line that does not hold the result event's name is not
 * parsed, so a reader scanning a long stream parses its result events alone.
 */
export function usageOf(engine: string, line: string): Usage | null {
  if (!Object.hasOwn(RESULT_EVENTS, engine) || line.startsWith(STDERR) || !line.includes(RESULT_EVENTS[engine])) return null;
  let event: unknown;
  try {
    event = JSON.parse(line);
  } catch {
    return null;
  }
  return isObject(event) ? usageFrom(engine, event) : null;
}

/**
 * A round's own figure, from the figure it `reported` and the one the nearest earlier
 * round of its chain reported, `before`. A session-scoped figure counts every round of
 * the session so far, so the round's own is the difference, field by field, and a field
 * `before` lacks is unknown. `reported` is taken as it is where it counts its round alone,
 * where `before` is none or does not count the session, and where any count it shares
 * with `before` is smaller, which no session that only grows gives.
 */
export function ownUsage(reported: Usage, before: Usage | null): Usage {
  if (reported.scope === "round" || before === null || before.scope !== "session") return reported;
  const pairs: Array<[number | null, number | null]> = [[reported.costUsd, before.costUsd]];
  const [now, then] = [reported.tokens, before.tokens];
  if (now !== null && then !== null) pairs.push([now.input, then.input], [now.cached, then.cached], [now.output, then.output], [now.reasoning, then.reasoning]);
  if (pairs.some(([mine, earlier]) => mine !== null && earlier !== null && mine < earlier)) return reported;
  const less = (mine: number | null, earlier: number | null) => (mine === null || earlier === null ? null : mine - earlier);
  return {
    costUsd: less(reported.costUsd, before.costUsd),
    tokens: now === null || then === null ? null : {
      input: now.input - then.input, cached: now.cached - then.cached, output: now.output - then.output, reasoning: less(now.reasoning, then.reasoning),
    },
    scope: "round",
  };
}

/**
 * Rounds' own figures summed, null for none: dollars over the figures that report a cost,
 * null where none does, and tokens field by field over the figures that carry them, the
 * reasoning over those that count it.
 */
export function sumUsage(figures: readonly Usage[]): Usage | null {
  if (figures.length === 0) return null;
  const costs = figures.flatMap((figure) => (figure.costUsd === null ? [] : [figure.costUsd]));
  const counted = figures.flatMap((figure) => (figure.tokens === null ? [] : [figure.tokens]));
  const reasoned = counted.flatMap((tokens) => (tokens.reasoning === null ? [] : [tokens.reasoning]));
  const sum = (values: number[]) => values.reduce((total, value) => total + value, 0);
  return {
    costUsd: costs.length === 0 ? null : sum(costs),
    tokens: counted.length === 0 ? null : {
      input: sum(counted.map((tokens) => tokens.input)), cached: sum(counted.map((tokens) => tokens.cached)),
      output: sum(counted.map((tokens) => tokens.output)), reasoning: reasoned.length === 0 ? null : sum(reasoned),
    },
    scope: "round",
  };
}

/** What a line with nothing to read gives. */
const NOTHING: LineRead = { steps: [], at: null, usage: null };

/**
 * The reader for one task's stream, each line parsed once: `engine` is the record's, `cwd`
 * the directory its summaries name paths from. A line the runner prefixed as the engine's
 * stderr is that, for every engine; any other line is JSON in the engine's own shape, and
 * one that does not parse, is no object, is of a type no reader knows, or belongs to an
 * engine with no reader gives no step. A reader that throws on a line it misjudged gives
 * none for that line and reads on. Beside its steps, a line gives when it was written,
 * where it carries an ISO `timestamp` as Claude's assistant and user lines do, and the
 * figure a result event reports (`usageOf`).
 */
export function lineReader(engine: string, cwd: string): LineReader {
  const read = engine === "codex" ? codexReader(cwd) : Object.hasOwn(MESSAGES_ENGINES, engine) ? messagesReader(engine, cwd) : null;
  return (line) => {
    if (line.startsWith(STDERR)) {
      const text = line.slice(STDERR.length);
      return { steps: [{ kind: "stderr", text, summary: summarize("stderr: ", text) }], at: null, usage: null };
    }
    if (read === null) return NOTHING;
    let event: unknown;
    try {
      event = JSON.parse(line);
    } catch {
      return NOTHING;
    }
    if (!isObject(event)) return NOTHING;
    let steps: Step[];
    try {
      steps = read(event);
    } catch {
      steps = [];
    }
    const at = typeof event.timestamp === "string" ? Date.parse(event.timestamp) : Number.NaN;
    return { steps, at: Number.isFinite(at) ? at : null, usage: usageFrom(engine, event) };
  };
}

/** The steps of a task's stream, line by line, as `lineReader` reads them. */
export function stepReader(engine: string, cwd: string): StepReader {
  const read = lineReader(engine, cwd);
  return (line) => read(line).steps;
}

/** Seconds as a person reads a span: `45s`, `12m05s`, `3h04m`, `2d03h`. */
export function span(seconds: number): string {
  const two = (value: number) => String(value).padStart(2, "0");
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3_600) return `${Math.floor(seconds / 60)}m${two(seconds % 60)}s`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3_600)}h${two(Math.floor(seconds / 60) % 60)}m`;
  return `${Math.floor(seconds / 86_400)}d${two(Math.floor(seconds / 3_600) % 24)}h`;
}
