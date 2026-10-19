"use strict";
// `cross-agent watch --web`'s page script (design section 10), served under the token as
// `app.js`. The server renders every fragment, its text escaped (`src/webrender.ts`); this
// keeps the Inspector's state — the runs, the tasks, their rows, the task and step selected,
// the task the address it loaded with awaits, whether the stream's replay has ended, the
// checkpoint open, the filter, the search, Follow latest, each task's scroll, each run's
// strip's scroll, sideways and down, and the theme — and places only those fragments. The
// only markup it writes is a task frame's own `item`, `link`, `head`, `row` or `detail`, or
// a run frame's own `label`, `runHead` or checkpoint view; every other write is
// `textContent`, a property, or an attribute from a fixed set given a constant, a boolean or
// a server enum; a frame's `text` is only ever searched, and the attributes the server
// writes on a chip are only ever read. It uses only the DOM members
// `tests/webclient.test.ts` models, which refuses every other.

/** The filters, in the page's order: All, then each group a row can have. */
const GROUPS = ["all", "command", "edit", "message", "thinking", "tool"];

const taskList = document.getElementById("tasks");
const unlinkedSection = document.getElementById("unlinked");
const runsBox = document.getElementById("runs");
const runNone = document.getElementById("run-none");
const heads = document.getElementById("heads");
const headsEmpty = document.getElementById("heads-empty");
const rowsBox = document.getElementById("rows");
const rowsEmpty = document.getElementById("rows-empty");
const detailBox = document.getElementById("detail");
const detailHidden = document.getElementById("detail-hidden");
const detailEmpty = document.getElementById("detail-empty");
const previousButton = document.getElementById("prev");
const nextButton = document.getElementById("next");
const followButton = document.getElementById("follow");
const search = document.getElementById("search");
const themeButton = document.getElementById("theme");
const connection = document.getElementById("connection");
const connectionText = document.getElementById("connection-text");
const counts = new Map(GROUPS.map((group) => [group, document.getElementById("count-" + group)]));
const filterButtons = document.querySelectorAll(".filter");
/** Whether the window is 760 pixels wide or less: the stylesheet's phone layout, where a run's strip is one row scrolling sideways. */
const phoneWidth = matchMedia("(max-width: 760px)");

/**
 * Every task on the page by id: its run, its entry — the `<li>`, its selection button, the
 * span its link goes in and the list of the entries nested in it, its resumes and its
 * specialists — its head and its rows' list, the fragments last written into each, whether
 * it is active and when it was created, whether it is thinking, its rows and how many of
 * each group, how many are shown, the row selected in it, the row the viewer last saw
 * selected in it — picked, or shown selected once the viewer had chosen a task or turned
 * Follow off; null before — and the scroll its rows were left at, null while it has never
 * been left, or was last left with no row shown.
 */
const tasks = new Map();

/**
 * Every run on the page by its key: its section of the task list — the list of its entries,
 * and the box its label goes in — its head's box over the selected task's, the label and the
 * head last written, its checkpoints' views by id, the sideways and the downward scroll its
 * strip's scroll events last reported (`scroll`, `top`), the layout its strip was last
 * placed in or took at once at a turn with nothing to give back, true at phone width and
 * null before its first placement (`narrow`), whether the page chose the stage the strip
 * opens on or anything scrolled it first (`revealed`), and whether its head was rewritten,
 * or the replay ended, the window turned to phone width or it turned past 760 pixels with a
 * scroll to give back while it was shown, since the last paint (`rewritten`).
 */
const runs = new Map();

/**
 * Each list of entries is a container: its element and its tasks, kept in the order they
 * were created (`place`). This is the Unlinked section's, for the tasks in no run.
 */
const unlinked = { element: document.getElementById("unlinked-tasks"), entries: [] };

/** The checkpoint whose view is in the detail pane, `{run, id}`, or null for the selected row's. */
let checkpoint = null;

/** The task shown; while nothing is `pinned`, every frame chooses it afresh (`defaultTask`). */
let selected = null;
/** Whether the viewer chose the task — by its entry, a row, a resume's link, a stage's or a checkpoint's chip, or a `hashchange` — or the address the page loaded with opened it. */
let pinned = false;
/**
 * The id the address the page loaded with names, `#task-<id>`, while the page awaits that
 * task's first frame to open it (`receive`); null once it opened, once the viewer chose a
 * task or opened a checkpoint, or a `hashchange` gave it up, and for an address that names
 * none. An id no frame has named stays awaited past the replay's end too, since a later
 * frame may still name it.
 */
let awaited = hashId(location.hash);
/**
 * Whether the replay of the stream's connection has ended (`endReplay`); each opening, a
 * reconnect's too, starts another (`connect`). Until then a run frame may be one the replay
 * brings from long before, so no strip has its stage chosen.
 */
let replayed = false;
/** Follow latest: the selected task's newest row shown is its selected row, as rows arrive. */
let follow = true;
let filter = "all";
let query = search.value.toLowerCase();
/**
 * The tasks whose selected row the next paint scrolls into view if it shows them: each one
 * whose row Follow latest moved, the viewer moved with previous or next, or a filter, a
 * search or Follow turned on put in question. A task switch is not among the reasons: the
 * paint itself knows whether the task it shows changed.
 */
const revealing = new Set();
let scheduled = false;
/**
 * What the last paint left on the page: the task shown, the run whose head is shown, the
 * row whose detail is in the pane, and the checkpoint view in the pane in its place.
 */
const painted = { task: null, run: null, row: null, view: null };
/** The text each element was last given, so an unchanged one is not written again. */
const texts = new Map();

/** Whether `one` sorts after `other`: created later, or by id among tasks created in the same millisecond. */
function later(one, other) {
  return one.createdAt > other.createdAt || (one.createdAt === other.createdAt && one.id > other.id);
}

/** A task's entry put in a container, before the first entry that sorts after it, so every list keeps its tasks in the order they were created. */
function place(container, task) {
  let at = container.entries.length;
  while (at > 0 && later(container.entries[at - 1], task)) at -= 1;
  container.element.insertBefore(task.li, at === container.entries.length ? null : container.entries[at].li);
  container.entries.splice(at, 0, task);
}

/** A run, made the first time any frame names it: its section at the end of the task list, and its head's box, hidden. */
function runOf(key) {
  const known = runs.get(key);
  if (known !== undefined) return known;
  const li = document.createElement("li");
  const labelBox = document.createElement("div");
  const list = document.createElement("ul");
  li.appendChild(labelBox);
  li.appendChild(list);
  taskList.appendChild(li);
  const headBox = document.createElement("div");
  headBox.hidden = true;
  runsBox.appendChild(headBox);
  const run = {
    key, labelBox, headBox, container: { element: list, entries: [] }, label: "", head: "", checkpoints: {}, scroll: 0, top: 0, narrow: null, revealed: false,
    rewritten: false,
  };
  // Scroll does not bubble: the head box hears its strip's, the one box in it that scrolls, in the capture phase.
  headBox.addEventListener("scroll", (event) => {
    // Each layout scrolls the strip one way, and a turn past the phone width clamps the way
    // the new one cannot scroll to 0, its event before the turn's `change` or after the paint
    // the turn asks for: an event keeps the way of the strip's layout alone, and nothing
    // until the strip has the layout the window does.
    if (phoneWidth.matches === run.narrow) {
      if (run.narrow) run.scroll = event.target.scrollLeft;
      else run.top = event.target.scrollTop;
    }
    run.revealed = true;
  }, true);
  runs.set(key, run);
  return run;
}

/**
 * The container a new task's entry goes in: the nested list of its chain's first round, or
 * else of its lead, where that task is on the page in the same run; else its run's list, or
 * the Unlinked section's, which shows once it holds an entry.
 */
function containerOf(frame) {
  for (const id of [frame.chain, frame.parent]) {
    const above = id === null ? undefined : tasks.get(id);
    if (above !== undefined && above.run === frame.run) return above.nested;
  }
  if (frame.run !== "") return runOf(frame.run).container;
  unlinkedSection.hidden = false;
  return unlinked;
}

/** A frame's task, made the first time any frame names it, its entry placed where `containerOf` says. */
function taskOf(frame) {
  const known = tasks.get(frame.id);
  if (known !== undefined) return known;
  const li = document.createElement("li");
  const button = document.createElement("button");
  button.setAttribute("type", "button");
  button.setAttribute("aria-current", "false");
  const linkBox = document.createElement("span");
  const children = document.createElement("ul");
  li.appendChild(button);
  li.appendChild(linkBox);
  li.appendChild(children);
  const headBox = document.createElement("div");
  headBox.hidden = true;
  heads.appendChild(headBox);
  const list = document.createElement("ol");
  list.hidden = true;
  rowsBox.appendChild(list);
  const task = {
    id: frame.id, run: frame.run, li, button, linkBox, nested: { element: children, entries: [] }, headBox, list, item: "", link: "", head: "",
    active: frame.active, createdAt: frame.createdAt, thinking: false, rows: [], counts: Object.fromEntries(GROUPS.map((group) => [group, 0])), shownCount: 0,
    row: null, seen: null, scroll: null,
  };
  place(containerOf(frame), task);
  button.addEventListener("click", () => {
    pin();
    select(task);
    schedule();
  });
  tasks.set(frame.id, task);
  return task;
}

/** Whether a row passes the filter and the search. */
function shows(row) {
  return (filter === "all" || row.group === filter) && (query === "" || row.text.includes(query));
}

/** A frame's row, at the end of its task's list, the filter and the search applied as it arrives. */
function addRow(task, frame) {
  const li = document.createElement("li");
  const button = document.createElement("button");
  button.setAttribute("type", "button");
  button.innerHTML = frame.row;
  li.appendChild(button);
  const row = { task, li, button, group: frame.group, text: frame.text.toLowerCase(), detail: frame.detail, index: task.rows.length, shown: false };
  task.rows.push(row);
  task.counts.all += 1;
  if (row.group !== null && row.group in task.counts) task.counts[row.group] += 1;
  row.shown = shows(row);
  if (row.shown) task.shownCount += 1;
  else li.hidden = true;
  task.list.appendChild(li);
  button.addEventListener("click", () => {
    if (row.task === selected) pick(row, false);
  });
  return row;
}

/**
 * A run's frame: its label and its head, each written only when it changes — rewriting a
 * head replaces its chips and its strip, whose kept scroll the next paint that shows it
 * gives back — and its checkpoints' views, kept for the paint.
 */
function receiveRun(frame) {
  const run = runOf(frame.run);
  if (frame.label !== run.label) {
    run.labelBox.innerHTML = frame.label;
    run.label = frame.label;
  }
  if (frame.runHead !== run.head) {
    run.headBox.innerHTML = frame.runHead;
    run.head = frame.runHead;
    run.rewritten = true;
  }
  run.checkpoints = frame.checkpoints;
  schedule();
}

/**
 * A replay ended, the first or a reconnect's: the frames after it are live, so the strip
 * shown is placed again (`placeShown`).
 */
function endReplay() {
  replayed = true;
  placeShown();
}

/**
 * The window turned past 760 pixels, either way: the strip shown gets back the scroll its
 * run keeps for the way the new layout scrolls at the next paint (`placeStrip`), during a
 * replay too, since giving it back chooses no stage. With none kept that way the strip
 * takes the new layout at once, and only a turn to 760 pixels or narrower once the replay
 * has ended places it again (`placeShown`); a turn during a replay leaves that to the
 * replay's end.
 */
function widthChanged() {
  const run = painted.run;
  if (run === null) return;
  const narrow = phoneWidth.matches;
  if ((narrow ? run.scroll : run.top) !== 0) {
    run.rewritten = true;
    schedule();
    return;
  }
  run.narrow = narrow;
  if (replayed && narrow) placeShown();
}

/**
 * The run whose head is shown, its strip's stage not chosen yet and nothing having
 * scrolled it, has its strip placed again at the next paint (`placeStrip`).
 */
function placeShown() {
  const run = painted.run;
  if (run === null || run.revealed) return;
  run.rewritten = true;
  schedule();
}

/** One frame from the stream: a run's, the replay's end, or its task's entry, link and head as they now read, its row, the task's thinking mark, and the default task or the task the address awaits. */
function receive(message) {
  const frame = JSON.parse(message.data);
  if (frame.event === "run") return receiveRun(frame);
  if (frame.event === "replayed") return endReplay();
  const task = taskOf(frame);
  task.active = frame.active;
  task.createdAt = frame.createdAt;
  // Each written only when it changes: rewriting one replaces every element in it, a
  // resume's link among them, which a click landing between two frames would miss.
  let clocks = false;
  if (frame.item !== task.item) {
    task.button.innerHTML = frame.item;
    task.item = frame.item;
    clocks = true;
  }
  if (frame.link !== task.link) {
    if (frame.link === "") task.linkBox.textContent = "";
    else task.linkBox.innerHTML = frame.link;
    task.link = frame.link;
  }
  if (frame.head !== task.head) {
    task.headBox.innerHTML = frame.head;
    task.head = frame.head;
    clocks = true;
  }
  // A still-thinking step sets the mark and the task's next step clears it; so does a
  // status no step shows, or the task's settlement.
  const thinking = frame.event === "step" ? frame.kind === "thinking-progress" : frame.event === "status" || frame.event === "settled" ? false : task.thinking;
  if (thinking !== task.thinking) {
    task.thinking = thinking;
    task.headBox.setAttribute("data-state", thinking ? "thinking" : "idle");
  }
  const row = frame.row === "" ? null : addRow(task, frame);
  // The address's task opens at its first frame, as a hashchange would open it; until then,
  // and for an id no frame names, the default selection holds.
  if (task.id === awaited) openTask(task);
  else if (!pinned) select(defaultTask());
  if (row !== null && task === selected) reconcile();
  // A fragment just written has empty clocks; the one-second interval refreshes the rest.
  if (clocks) tick();
  schedule();
}

/** The task a viewer who chose none sees: the newest active one, or the newest of all when none is. */
function defaultTask() {
  let best = null;
  for (const task of tasks.values()) {
    if (best === null || (task.active !== best.active ? task.active : task.createdAt >= best.createdAt)) best = task;
  }
  return best;
}

/**
 * The task shown, its rows filtered as the page now filters, and its row chosen as Follow
 * latest says; a checkpoint open on the task left is closed. Under Follow off, a row the
 * viewer never saw selected in the task (`seen`) gives way to its newest row shown.
 */
function select(task) {
  if (task === selected || task === null) return;
  selected = task;
  checkpoint = null;
  refilter(task);
  if (!follow && task.row !== task.seen) task.row = null;
  reconcile();
}

/** A task's rows, each shown or hidden by the filter and the search as they now are. */
function refilter(task) {
  let shown = 0;
  for (const row of task.rows) {
    const now = shows(row);
    if (now !== row.shown) {
      row.shown = now;
      row.li.hidden = !now;
    }
    if (now) shown += 1;
  }
  task.shownCount = shown;
}

/** The newest of a task's rows shown, or null. */
function newestShown(task) {
  for (let index = task.rows.length - 1; index >= 0; index--) if (task.rows[index].shown) return task.rows[index];
  return null;
}

/**
 * The selected task's row, after anything that can move it: a row arriving, a filter or a
 * search, a task switch or Follow latest turned on. With Follow on, its newest row shown,
 * or none when none is. With Follow off, the row the viewer chose stays, even one the
 * filter now hides, which keeps its detail and the notice that it is hidden; a task with
 * no row chosen yet gets its newest row shown.
 */
function reconcile() {
  const task = selected;
  if (task === null) return;
  if (follow) {
    const newest = newestShown(task);
    if (newest !== task.row) {
      task.row = newest;
      revealing.add(task);
    }
  } else if (task.row === null) {
    task.row = newestShown(task);
  }
}

/** The nearest row shown before (`-1`) or after (`1`) the selected row's place, or null. */
function neighbour(direction) {
  const task = selected;
  if (task === null || task.row === null) return null;
  for (let index = task.row.index + direction; index >= 0 && index < task.rows.length; index += direction) {
    if (task.rows[index].shown) return task.rows[index];
  }
  return null;
}

/** A row the viewer picked, by its button or by previous and next: the selection pinned, Follow latest off and the checkpoint closed; `reveal` scrolls it into view. */
function pick(row, reveal) {
  pin();
  setFollow(false);
  checkpoint = null;
  selected.row = row;
  selected.seen = row;
  if (reveal) revealing.add(selected);
  schedule();
}

function move(direction) {
  const row = neighbour(direction);
  if (row !== null) pick(row, true);
}

function setFollow(on) {
  if (on === follow) return;
  follow = on;
  followButton.setAttribute("aria-pressed", String(on));
}

/** Follow latest toggled: turned on, it closes the checkpoint, selects the newest row shown and scrolls to it. */
function toggleFollow() {
  setFollow(!follow);
  if (follow) checkpoint = null;
  if (follow && selected !== null) {
    reconcile();
    revealing.add(selected);
  }
  schedule();
}

/** A filter chosen: one of `GROUPS`, as its button names it. */
function setFilter(group) {
  if (!GROUPS.includes(group) || group === filter) return;
  filter = group;
  for (const button of filterButtons) button.setAttribute("aria-pressed", String(button.getAttribute("data-group") === group));
  narrowed();
}

/** The filter or the search changed: the selected task's rows filtered again, its row reconciled and revealed. */
function narrowed() {
  if (selected !== null) {
    refilter(selected);
    revealing.add(selected);
    reconcile();
  }
  schedule();
}

/** A paint before the browser's next, however many frames and clicks come before it. */
function schedule() {
  if (scheduled) return;
  scheduled = true;
  requestAnimationFrame(paint);
}

/** An element's text, written only when it changes. */
function setText(element, text) {
  if (texts.get(element) === text) return;
  texts.set(element, text);
  element.textContent = text;
}

/**
 * The page as the state now says, once per animation frame: the task shown and the one
 * current in the list, its run's head or the line saying it is in none, the open
 * checkpoint's view while its run has it or else the selected row's detail — each written
 * only when it changed, and no row current while a view is shown — and the notices, the
 * counts, previous and next, and the scroll. Reading a scroll forces a layout, which a
 * reload replaying thousands of frames would pay on every one if each frame painted; here a
 * paint reads the rows' scroll at most once to keep the scroll of the task it stops
 * showing, however many times the selection moved since the last, and once more to reveal
 * the selected row. Only a paint that shows another task than the last is a switch: a task
 * left and come back to since then keeps the scroll it has, and reveals nothing the
 * switches alone asked for. Placing a run's strip shown anew adds no read but the four of
 * its one reveal at phone width, after the rows' (`placeStrip`). A detail written has its
 * own times written in the same paint, and no clock outside it (`writeStarts`).
 */
function paint() {
  scheduled = false;
  const task = selected;
  const left = painted.task;
  const switched = task !== left;
  if (switched) {
    if (painted.task !== null) {
      // A task left with no row shown keeps no scroll: its box held nothing to scroll.
      painted.task.scroll = painted.task.shownCount === 0 ? null : rowsBox.scrollTop;
      painted.task.headBox.hidden = true;
      painted.task.list.hidden = true;
      painted.task.button.setAttribute("aria-current", "false");
    }
    task.headBox.hidden = false;
    task.list.hidden = false;
    task.button.setAttribute("aria-current", "true");
    painted.task = task;
  }
  headsEmpty.hidden = task !== null;
  const run = task === null || task.run === "" ? null : runs.get(task.run) ?? null;
  const anew = run !== null && (run !== painted.run || run.rewritten);
  if (run !== painted.run) {
    if (painted.run !== null) painted.run.headBox.hidden = true;
    if (run !== null) run.headBox.hidden = false;
    painted.run = run;
  }
  runNone.hidden = task === null || run !== null;
  const view = checkpoint !== null && run !== null && checkpoint.run === run.key && Object.hasOwn(run.checkpoints, checkpoint.id) ? run.checkpoints[checkpoint.id] : null;
  const selectedRow = task === null ? null : task.row;
  const row = view === null ? selectedRow : null;
  if (row !== painted.row || view !== painted.view) {
    if (painted.row !== null && painted.row !== row) painted.row.button.setAttribute("aria-current", "false");
    if (view !== null) detailBox.innerHTML = view;
    else if (row === null) detailBox.textContent = "";
    else detailBox.innerHTML = row.detail;
    if (row !== null && row !== painted.row) row.button.setAttribute("aria-current", "true");
    painted.row = row;
    painted.view = view;
    // A detail just written has empty times, a step's or a checkpoint's milestones': this
    // paint writes those, and no clock outside the detail.
    writeStarts(detailBox);
  }
  detailEmpty.hidden = row !== null || view !== null;
  detailHidden.hidden = row === null || row.shown;
  rowsEmpty.hidden = task !== null && task.shownCount > 0;
  setText(rowsEmpty, task === null || task.rows.length === 0 ? "No steps yet." : "No steps match the filter or search.");
  for (const group of GROUPS) setText(counts.get(group), String(task === null ? 0 : task.counts[group]));
  // A focused button turned off drops the focus to the page, so the one the viewer pressed at
  // either end of the rows hands it to the other, where that one is on.
  const focused = document.activeElement;
  const noPrevious = neighbour(-1) === null;
  const noNext = neighbour(1) === null;
  previousButton.disabled = noPrevious;
  nextButton.disabled = noNext;
  if (focused === previousButton && noPrevious && !noNext) nextButton.focus();
  else if (focused === nextButton && noNext && !noPrevious) previousButton.focus();
  // A task switched to shows its rows as the viewer left them under Follow off, and its
  // newest row under Follow on. One with no scroll of its own — never shown, or left with no
  // row shown — starts at the top of its rows under either, the first task the page shows
  // being there already, with its selected row revealed; so, under Follow off, is a row the
  // viewer never saw, which `select` replaced with the newest row shown. A reason to reveal
  // given for the task shown holds either way.
  if (switched && left !== null && (!follow || task.scroll === null)) rowsBox.scrollTop = task.scroll ?? 0;
  if ((switched && (follow || task.scroll === null || task.row !== task.seen)) || revealing.has(task)) reveal(selectedRow);
  revealing.clear();
  if (anew) placeStrip(run);
  // The row is the viewer's once the viewer has chosen a task or turned Follow off; before
  // that, as through the opening replay, it is Follow's.
  if (task !== null && (pinned || !follow)) task.seen = task.row;
}

/**
 * The rows scrolled, inside their own box, just enough to show `row` whole; nothing for no
 * row, or a row the filter hides, which has no place to show. `#rows` is positioned, so a
 * row's `offsetTop` is from its top.
 */
function reveal(row) {
  if (row === null || !row.shown) return;
  const top = row.li.offsetTop;
  const bottom = top + row.li.offsetHeight;
  const scroll = rowsBox.scrollTop;
  const height = rowsBox.clientHeight;
  if (top < scroll) rowsBox.scrollTop = top;
  else if (bottom > scroll + height) rowsBox.scrollTop = bottom - height;
}

/**
 * A run's strip as the paint shows it anew — its head switched to, or rewritten, the replay
 * ended or the window turned past 760 pixels since the last paint — in the layout the
 * window now has, which its scroll events keep the way of from then on (`runOf`). At phone
 * width, the first time it holds a stage with a task once the replay has ended, and before
 * anything scrolled it, it scrolls inside itself just enough to show that stage
 * (`liveStage`) whole, whether the page opened at that width or turned to it
 * (`widthChanged`). Otherwise it gets back the scroll its scroll events last reported the
 * way that layout scrolls it: sideways at phone width, where it is one row, and down on a
 * wider screen, where it wraps in its own box. Only the reveal reads, once per run, after
 * the rows'.
 */
function placeStrip(run) {
  run.rewritten = false;
  run.narrow = phoneWidth.matches;
  const strip = run.headBox.querySelector(".strip");
  if (strip === null) return;
  const chip = run.revealed || !replayed || !run.narrow ? null : liveStage(strip);
  if (chip === null) {
    if (run.narrow) {
      if (run.scroll !== 0) strip.scrollLeft = run.scroll;
    } else if (run.top !== 0) strip.scrollTop = run.top;
    return;
  }
  run.revealed = true;
  const left = chip.offsetLeft;
  const right = left + chip.offsetWidth;
  const scroll = strip.scrollLeft;
  const width = strip.clientWidth;
  if (left < scroll) run.scroll = left;
  else if (right > scroll + width) run.scroll = right - width;
  else return;
  strip.scrollLeft = run.scroll;
}

/** The strip's running stage, the last where several run, or else its latest stage with a task; null where no stage has one. */
function liveStage(strip) {
  const chips = strip.querySelectorAll("[data-task]");
  for (let index = chips.length - 1; index >= 0; index--) if (chips[index].querySelector(".st-running") !== null) return chips[index];
  return chips.length === 0 ? null : chips[chips.length - 1];
}

/**
 * A click in the detail: on a block's Copy, the block's text to the clipboard, and the button
 * says so; where the browser gives the page no clipboard, or refuses it, the text selected
 * for the viewer to copy instead.
 */
function copy(event) {
  const button = event.target.closest("button.copy");
  if (button === null) return;
  const pre = button.closest(".block").querySelector("pre");
  const said = (word) => {
    button.textContent = word;
    setTimeout(() => {
      button.textContent = "Copy";
    }, 1500);
  };
  const selectText = () => {
    const range = document.createRange();
    range.selectNodeContents(pre);
    const selection = getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    said("Selected");
  };
  const clipboard = navigator.clipboard;
  if (clipboard === undefined || clipboard === null) return selectText();
  clipboard.writeText(pre.textContent).then(() => said("Copied"), selectText);
}

/** Where the viewer's theme is kept: per address, so a watcher on another port starts on the OS's. */
const THEME_KEY = "cross-agent-watch-theme";
const darkScheme = matchMedia("(prefers-color-scheme: dark)");

/** The theme the page shows: the viewer's choice, or the OS's while there is none. */
function themeInEffect() {
  const chosen = document.documentElement.getAttribute("data-theme");
  return chosen === "light" || chosen === "dark" ? chosen : darkScheme.matches ? "dark" : "light";
}

/** The toggle pressed while the page is dark. */
function showTheme() {
  themeButton.setAttribute("aria-pressed", String(themeInEffect() === "dark"));
}

/** The other theme than the one in effect, chosen and kept; a browser that keeps nothing for the page still shows it until the page closes. */
function toggleTheme() {
  const theme = themeInEffect() === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Storage refused: the choice lasts as long as the page.
  }
  showTheme();
}

/** A choice kept from before applied at load; with none, the page follows the OS as it changes. */
function applyStoredTheme() {
  let stored = null;
  try {
    stored = localStorage.getItem(THEME_KEY);
  } catch {
    stored = null;
  }
  if (stored === "light" || stored === "dark") document.documentElement.setAttribute("data-theme", stored);
  showTheme();
  darkScheme.addEventListener("change", showTheme);
}

/** The id an address's `#task-<id>` names, or null. */
function hashId(hash) {
  const match = /^#task-(.+)$/.exec(hash ?? "");
  return match === null ? null : match[1];
}

/** The task on the page an address's `#task-<id>` names, if any. */
function taskOfHash(hash) {
  const id = hashId(hash);
  return id === null ? undefined : tasks.get(id);
}

/** The selection pinned, by the viewer's choice or by the task the address awaits opening; an address still awaited is settled — opened or given up — and its hash dropped, so the same address works again. */
function pin() {
  pinned = true;
  if (awaited === null) return;
  awaited = null;
  dropHash();
}

/** A task the viewer opened by a resume's link, its address or a stage's chip: selected and pinned, the checkpoint closed. */
function openTask(task) {
  pin();
  checkpoint = null;
  select(task);
  schedule();
}

/**
 * A checkpoint's chip pressed in the selected task's run head: its view in the detail pane
 * in place of the selected row's, the selection pinned and Follow latest off, as picking a
 * row does, so no arriving row moves the pane.
 */
function openCheckpoint(id) {
  if (selected === null) return;
  pin();
  setFollow(false);
  checkpoint = { run: selected.run, id };
  schedule();
}

/**
 * A click in a run head: on a task stage's chip, the stage's first task opened, where the
 * page has it; on a checkpoint's, its view. A stage that is neither has no attribute to name
 * either, and does nothing. The attributes are the server's, and only read.
 */
function openStage(event) {
  const chip = event.target.closest(".chip");
  if (chip === null) return;
  const id = chip.getAttribute("data-task");
  const view = chip.getAttribute("data-checkpoint");
  if (id !== null) {
    const task = tasks.get(id);
    if (task !== undefined) openTask(task);
  } else if (view !== null) openCheckpoint(view);
}

/**
 * A click in the task list on a resume's link: the round it continues opened here, and the
 * link not followed, since following `#task-<id>` would add an entry to the browser's history
 * for every click. A click with a modifier or another button, to open the address elsewhere,
 * is left to the browser.
 */
function openResume(event) {
  if (event.button !== 0 || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  const link = event.target.closest("a.resumes");
  const task = link === null ? undefined : taskOfHash(link.getAttribute("href"));
  if (task === undefined) return;
  event.preventDefault();
  openTask(task);
}

/**
 * An address typed or opened with `#task-<id>` of a task on the page: the task opened, and
 * the hash dropped, so the same address works again. Any other hash changes nothing. A
 * hashchange, whatever it names, gives up an address the page loaded with: the address now
 * names another.
 */
function openHash() {
  awaited = null;
  const task = taskOfHash(location.hash);
  if (task === undefined) return;
  openTask(task);
  dropHash();
}

/** The address's hash dropped, adding no entry to the browser's history. */
function dropHash() {
  history.replaceState(null, "", location.pathname + location.search);
}

/** Seconds as the CLI spells a span: `45s`, `12m05s`, `3h04m`, `2d03h`. */
function span(seconds) {
  const two = (value) => String(value).padStart(2, "0");
  if (seconds < 60) return seconds + "s";
  if (seconds < 3600) return Math.floor(seconds / 60) + "m" + two(seconds % 60) + "s";
  if (seconds < 86400) return Math.floor(seconds / 3600) + "h" + two(Math.floor(seconds / 60) % 60) + "m";
  return Math.floor(seconds / 86400) + "d" + two(Math.floor(seconds / 3600) % 24) + "h";
}

/** How long a task has run, from an `elapsed` element: to `now` while it is active, to its settlement once it is not. */
function elapsedText(element, now) {
  const created = Number(element.getAttribute("data-created"));
  const until = element.getAttribute("data-until");
  const end = until === null || until === "" ? now : Number(until);
  if (!Number.isFinite(created) || !Number.isFinite(end)) return "";
  return span(Math.max(0, Math.round((end - created) / 1000)));
}

/** When a task started, from a head's `time`, in the viewer's own form. */
function startedText(element) {
  const date = new Date(element.getAttribute("datetime"));
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString();
}

/** Every elapsed time as of now, and every start not yet written. */
function tick() {
  const now = Date.now();
  for (const element of document.querySelectorAll(".elapsed")) element.textContent = elapsedText(element, now);
  writeStarts(document);
}

/** Every start under `root` not yet written. */
function writeStarts(root) {
  for (const element of root.querySelectorAll("time.started")) if (element.textContent === "") element.textContent = startedText(element);
}

/**
 * How many errors in a row, with no open between them, mean the watcher has ended: a
 * watcher that stopped never answers again, and a new one listens at a new address.
 */
const STOPPED_AFTER = 3;

const STOPPED_TEXT = "stopped — the watcher has ended; watch_page or cross-agent watch --web starts a new one at a new address";

/**
 * The page's stream, under the same token as the page: a fresh page gets every frame the
 * server kept, and a reconnect what it missed, each up to its replay's end, which every
 * opening awaits again (`replayed`). Once the watcher has gone — `STOPPED_AFTER`
 * errors in a row, or a stream the browser itself closed — the stream is closed, so the
 * browser stops retrying an address nothing will answer again, and the page says how to
 * get a new one. The connection's state names its icon's colour.
 */
function connect() {
  const source = new EventSource(location.pathname.replace(/\/+$/, "") + "/events");
  const state = (name, text) => {
    connection.setAttribute("data-state", name);
    connectionText.textContent = text;
  };
  let errors = 0;
  source.onopen = () => {
    errors = 0;
    // A reconnect replays first too, until the mark that ends its replay.
    replayed = false;
    state("live", "live");
  };
  source.onerror = () => {
    errors += 1;
    if (source.readyState === EventSource.CLOSED || errors >= STOPPED_AFTER) {
      source.close();
      state("stopped", STOPPED_TEXT);
    } else {
      state("reconnecting", "reconnecting…");
    }
  };
  source.onmessage = receive;
}

for (const button of filterButtons) button.addEventListener("click", () => setFilter(button.getAttribute("data-group")));
search.addEventListener("input", () => {
  const next = search.value.toLowerCase();
  if (next === query) return;
  query = next;
  narrowed();
});
followButton.addEventListener("click", toggleFollow);
previousButton.addEventListener("click", () => move(-1));
nextButton.addEventListener("click", () => move(1));
detailBox.addEventListener("click", copy);
taskList.addEventListener("click", openResume);
runsBox.addEventListener("click", openStage);
themeButton.addEventListener("click", toggleTheme);
phoneWidth.addEventListener("change", widthChanged);
addEventListener("hashchange", openHash);
applyStoredTheme();
connect();
setInterval(tick, 1000);
