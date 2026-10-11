#!/usr/bin/env node
// Browser check for the TBD Board page (skills/tbd-board/assets/board-template.html).
// Zero dependencies. Needs Node 22+ (global WebSocket and fetch) and Chrome.
// Chrome path: env CHROME_PATH, else the macOS app, else "google-chrome".
// It starts headless Chrome, drives it over the DevTools protocol, prints PASS or FAIL per check,
// and exits with code 1 when a check fails. Chrome and the temp files are removed in all cases.
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const template = readFileSync(join(root, "skills/tbd-board/assets/board-template.html"), "utf8");
const fixture = JSON.parse(readFileSync(join(root, "tests/fixtures/hearth.json"), "utf8"));
const work = mkdtempSync(join(tmpdir(), "tbd-board-check-"));
const profileDir = join(work, "profile");
const pagesDir = join(work, "pages");
mkdirSync(pagesDir);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---- Test pages: the template with its data block content replaced (contract writer rules) ----
const OPEN_TAG = '<script type="application/json" id="tbd-board-data">';
function writePage(name, data, rawJson) {
  const json = rawJson ?? JSON.stringify(data, null, 2).replaceAll("</", "<\\/").replaceAll("<!--", "<\\u0021--");
  const start = template.indexOf(OPEN_TAG) + OPEN_TAG.length;
  const end = template.indexOf("</script>", start);
  const file = join(pagesDir, name + ".html");
  writeFileSync(file, template.slice(0, start) + "\n" + json + "\n" + template.slice(end));
  return pathToFileURL(file).href;
}

// ---- Results ----
const results = [];
function check(name, ok, detail = "") {
  results.push(ok);
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${ok ? "" : "\n     " + detail}`);
}
const eq = (name, actual, expected) =>
  check(name, JSON.stringify(actual) === JSON.stringify(expected), `got ${JSON.stringify(actual)}\n     expected ${JSON.stringify(expected)}`);

// ---- Chrome and the DevTools protocol ----
let chrome = null;
let browser = null;
async function startChrome() {
  const bin = process.env.CHROME_PATH ||
    (process.platform === "darwin" ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : "google-chrome");
  const args = ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profileDir}`,
    "--no-first-run", "--no-default-browser-check", "about:blank"];
  if (process.getuid?.() === 0) args.push("--no-sandbox"); // Chrome refuses to run as root without it
  let spawnError = null;
  chrome = spawn(bin, args, { stdio: "ignore" });
  chrome.once("error", (e) => { spawnError = e; });
  const portFile = join(profileDir, "DevToolsActivePort");
  // The file has two lines (port, path). Wait for both, because Chrome can still be writing it.
  const portLines = () => (existsSync(portFile) ? readFileSync(portFile, "utf8").trim().split("\n") : []);
  for (let i = 0; i < 150 && portLines().length < 2; i++) {
    if (spawnError) throw new Error(`Cannot start Chrome (${bin}): ${spawnError.message}`);
    await sleep(100);
  }
  const [port, path] = portLines();
  if (!path) throw new Error("Chrome did not write DevToolsActivePort");
  return `ws://127.0.0.1:${port}${path}`;
}
function connect(url) {
  const ws = new WebSocket(url);
  let nextId = 0;
  const pending = new Map();
  const handlers = new Set();
  ws.addEventListener("message", (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id === undefined) return handlers.forEach((h) => h(m));
    const p = pending.get(m.id);
    pending.delete(m.id);
    if (p) m.error ? p.reject(new Error(`${p.method}: ${m.error.message}`)) : p.resolve(m.result);
  });
  const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, { resolve, reject, method });
    ws.send(JSON.stringify({ id, method, params, sessionId }));
  });
  return new Promise((resolve, reject) => {
    ws.addEventListener("open", () => resolve({ send, ws, on: (h) => handlers.add(h) }));
    ws.addEventListener("error", () => reject(new Error("Cannot connect to Chrome DevTools")));
  });
}

// A tab in its own browser context, so each scenario has its own storage.
const IMAGE_URL = /\.(png|jpe?g|gif|webp|svg|ico)(\?|#|$)/i;
async function withTab(label, options, run) {
  const { width = 1280, height = 900, mobile = false, preload, media } = options;
  let contextId;
  try {
    ({ browserContextId: contextId } = await browser.send("Target.createBrowserContext"));
    const { targetId } = await browser.send("Target.createTarget", { url: "about:blank", browserContextId: contextId });
    const { sessionId } = await browser.send("Target.attachToTarget", { targetId, flatten: true });
    const send = (method, params) => browser.send(method, params, sessionId);
    const tab = { errors: [], dialogs: [], send };
    let onLoad = null;
    browser.on((m) => {
      if (m.sessionId !== sessionId) return;
      const p = m.params;
      if (m.method === "Runtime.exceptionThrown") tab.errors.push("exception: " + (p.exceptionDetails.exception?.description || p.exceptionDetails.text));
      else if (m.method === "Runtime.consoleAPICalled" && p.type === "error") tab.errors.push("console.error: " + p.args.map((a) => a.value ?? a.description).join(" "));
      else if (m.method === "Log.entryAdded" && p.entry.level === "error" && !(p.entry.source === "network" && IMAGE_URL.test(p.entry.url || ""))) tab.errors.push(`log: ${p.entry.text} ${p.entry.url || ""}`);
      else if (m.method === "Page.javascriptDialogOpening") { tab.dialogs.push(p.message); send("Page.handleJavaScriptDialog", { accept: true }).catch(() => {}); }
      else if (m.method === "Page.loadEventFired" && onLoad) { onLoad(); onLoad = null; }
    });
    for (const d of ["Page", "Runtime", "Log"]) await send(d + ".enable");
    await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 1, mobile });
    if (media) await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: media }] });
    if (preload) await send("Page.addScriptToEvaluateOnNewDocument", { source: preload });
    // Go to a page and wait for the load event. Late messages (failed images) get a short time to arrive.
    tab.goto = async (url) => {
      tab.errors.length = 0;
      const loaded = new Promise((r) => { onLoad = r; });
      await send("Page.navigate", { url });
      await loaded;
      await sleep(250);
    };
    tab.eval = async (expression) => {
      const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true, userGesture: true });
      if (r.exceptionDetails) throw new Error(`eval failed: ${r.exceptionDetails.exception?.description || r.exceptionDetails.text}\n${expression}`);
      return r.result.value;
    };
    // Real mouse click at the centre of the element; fails when another element covers it.
    tab.click = async (elementExpr) => {
      const [x, y] = await tab.eval(`(() => {
        const el = ${elementExpr};
        if (!el) throw new Error("no element for click");
        el.scrollIntoView({ block: "center", inline: "center" });
        const r = el.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
        const top = document.elementFromPoint(x, y);
        if (!top || (top !== el && !el.contains(top))) throw new Error("click target is covered: " + (el.textContent || "").slice(0, 40));
        return [x, y];
      })()`);
      await send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
      await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
      await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
    };
    tab.type = (text) => send("Input.insertText", { text });
    tab.tab = async () => {
      await send("Input.dispatchKeyEvent", { type: "rawKeyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
      await send("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    };
    await run(tab);
  } catch (e) {
    check(`${label}: scenario ran to the end`, false, e.stack || String(e));
  } finally {
    if (contextId) await browser.send("Target.disposeBrowserContext", { browserContextId: contextId }).catch(() => {});
  }
}

// ---- Page helpers (JavaScript source text that runs in the page) ----
const Q = (id) => `document.querySelector('article[data-id="${id}"]')`;
const box = (id) => `${Q(id)}.querySelector('textarea')`;
const opt = (id, label) => `[...${Q(id)}.querySelectorAll('.opt')].find((b) => b.querySelector('strong').textContent === ${JSON.stringify(label)})`;
const btn = (scope, label) => `[...${scope}.querySelectorAll('button')].find((b) => b.textContent.trim() === ${JSON.stringify(label)})`;
const pressed = (id) => `[...${Q(id)}.querySelectorAll('.opt')].map((b) => b.getAttribute('aria-pressed'))`;
const VISIBLE = `[...document.querySelectorAll('article.card, .auto')].filter((e) => !e.closest('[hidden]')).map((e) => e.querySelector('.id').textContent)`;
const HEADINGS = `['h-open', 'h-auto', 'h-closed'].map((i) => document.getElementById(i).textContent)`;
const setBox = (tab, id, value) => tab.eval(`(() => { const t = ${box(id)}; t.value = ${JSON.stringify(value)}; t.dispatchEvent(new Event("input", { bubbles: true })); })()`);
const filterChip = (label) => `[...document.querySelectorAll('#filters button[data-group]')].find((b) => b.textContent === ${JSON.stringify(label)})`;
const PROGRESS = `document.getElementById('progress').textContent`;
const ERROR_HINT = "Ask your agent to run board.py check (the TBD Board helper) to find the problem.";
const SUMMARY = `document.getElementById('filters-summary')`;

// ---- Test data ----
const evil = {
  id: "Q-100", title: "</script><img src=x onerror=alert(1)>", priority: "urgent", status: "open", area: "<u>area</u>",
  asked: "2026-10-11", blocks: "<b>stop</b>",
  context: ["https://example.invalid/" + "a".repeat(200), "<img src=x onerror=alert(1)>"],
  images: [
    { src: "javascript:alert(1)", caption: "<i>bad</i>" },
    { src: "data:text/html,<script>alert(1)</script>", caption: "data" },
    { src: " javascript:alert(1)", caption: "space" },
    { src: "java\tscript:alert(1)", caption: "tab" },
    { src: "//example.invalid/x.png", caption: "protocol-relative" },
    { src: "https://example.invalid/ok.png", caption: "https ok" },
    { src: "assets/ok.png", caption: "relative ok" }
  ],
  options: [{ label: "</b><img src=x onerror=alert(1)>", detail: "x" }, { label: "L".repeat(120), detail: "d" }],
  recommendation: "<script>alert(1)</script>", decision: ""
};
const adversarial = {
  ...fixture, title: "<i>Evil</i> board",
  questions: [...fixture.questions, evil],
  autodecided: [{ id: "A-100", date: "2026-10-11", title: "T", decision: "D", reason: "R", changed: "D-020: changed it" }, ...fixture.autodecided]
};
const PRIORITIES = ["blocking", "urgent", "normal", "low"];
const generated = {
  ...fixture, boardId: "perf200",
  questions: [
    ...Array.from({ length: 200 }, (_, i) => ({
      id: `Q-${String(i + 1).padStart(3, "0")}`, title: `Generated card ${i + 1}: ${i % 7 === 0 ? "needle" : "hay"}`,
      priority: PRIORITIES[i % 4], status: "open", area: `Area ${i % 5}`, asked: "2026-10-11", blocks: i % 4 === 0 ? "Some work" : "",
      context: [`Paragraph one for card ${i + 1} with enough words to wrap on more than one line of text.`, "Paragraph two."],
      images: i % 10 === 0 ? [{ src: `assets/shot-${i}.png`, caption: "Shot" }] : [],
      options: [{ label: "A. First", detail: "First detail", recommended: true }, { label: "B. Second", detail: "Second detail" }],
      recommendation: "Recommendation text.", decision: ""
    })),
    ...Array.from({ length: 10 }, (_, i) => ({ id: `Q-${300 + i}`, title: `Closed ${i}`, priority: "low", status: "closed", area: "Old", asked: "2026-10-01", context: [], decision: "Not needed." }))
  ],
  autodecided: Array.from({ length: 10 }, (_, i) => ({ id: `A-${100 + i}`, date: "2026-10-01", title: `Auto ${i}`, decision: "Done.", reason: "Small." }))
};
const smallBoard = (blocking, total) => ({
  ...fixture, boardId: "small1",
  questions: Array.from({ length: total }, (_, i) => ({ id: `Q-${String(i + 1).padStart(3, "0")}`, title: `T${i}`, priority: i < blocking ? "blocking" : "low", status: "open", asked: "2026-10-11", context: [], decision: "" })),
  autodecided: []
});

// ---- Scenarios ----
async function mainScenario() {
  const url = writePage("main", fixture);
  await withTab("main page", {}, async (tab) => {
    await tab.goto(url);
    check("no console errors or exceptions on load", tab.errors.length === 0, tab.errors.join("\n     "));
    eq("heading, title and footer", await tab.eval(`[document.querySelector('h1').textContent, document.title, document.getElementById('foot').textContent, document.getElementById('updated').textContent]`),
      ["Hearth decisions", "Hearth decisions", "TBD Board 1.0.0Board k7f3q2, revision 14", "Updated: 2026-10-11"]);
    eq("priority counts", await tab.eval(`[...document.querySelectorAll('#counts .chip')].map((c) => c.textContent)`), ["1 blocking", "1 urgent", "1 normal", "1 low"]);
    eq("sections: open, decided-for-you, closed", await tab.eval(`[document.querySelectorAll('#open article.card').length, document.querySelectorAll('#auto .auto').length, document.querySelectorAll('#closed article.card').length]`), [4, 3, 1]);
    eq("open order: blocking, urgent, normal, low", await tab.eval(`[...document.querySelectorAll('#open article.card')].map((c) => c.dataset.id)`), ["Q-007", "Q-006", "Q-005", "Q-004"]);
    eq("headings without a filter", await tab.eval(HEADINGS), ["Open (4)", "Decided for you (3)", "Answered and closed (1)"]);
    eq("card content: blocks line, recommended marker, agent recommendation", await tab.eval(`(() => { const c = ${Q("Q-007")}; return [c.querySelector('.blocks').textContent, c.querySelector('.star').textContent, c.querySelector('.rec').textContent.startsWith('Agent recommendation:')]; })()`),
      ["Work stopped until you answer: The data layer and the sign-in screens.", "Recommended: ", true]);
    eq("closed card: decision and no answer box", await tab.eval(`(() => { const c = ${Q("Q-003")}; return [c.querySelectorAll('textarea').length, c.querySelectorAll('.opt').length, [...c.querySelectorAll('.rec')].pop().textContent]; })()`),
      [0, 0, "Decision: D-012: push notifications, asked after the first chore is done. One reminder a day at most."]);
    eq("images: links open in a new tab, 150 px thumbnails in a scrolling row", await tab.eval(`(() => { const c = ${Q("Q-006")}; return [[...c.querySelectorAll('a')].map((a) => [a.getAttribute('href'), a.target, a.rel]), c.querySelector('figure').getBoundingClientRect().width, getComputedStyle(c.querySelector('.imgs')).overflowX]; })()`),
      [[["assets/onboarding-three.png", "_blank", "noopener"], ["assets/onboarding-one.png", "_blank", "noopener"]], 150, "auto"]);
    eq("cards are labelled by their title heading", await tab.eval(`(() => { const a = [...document.querySelectorAll('article.card')]; return [a.length, a.every((c) => { const t = document.getElementById(c.getAttribute('aria-labelledby')); return !!t && t === c.querySelector('h3'); })]; })()`), [5, true]);
    eq("decided-for-you entries are labelled by their title", await tab.eval(`[...document.querySelectorAll('article.auto')].map((a) => document.getElementById(a.getAttribute('aria-labelledby')).textContent)`), ["Date formats", "Lint rules", "Test runner"]);
    eq("Copy this answer keeps its text and is described by the card title", await tab.eval(`(() => { const b = [...document.querySelectorAll('button[data-copy]')]; return [b.length, b.every((x) => x.textContent === 'Copy this answer' && document.getElementById(x.getAttribute('aria-describedby')) === x.closest('article').querySelector('h3'))]; })()`), [4, true]);
    await tab.tab();
    eq("keyboard focus shows a 3 px outline", await tab.eval(`(() => { const s = getComputedStyle(document.activeElement); return [document.activeElement.id, s.outlineStyle, s.outlineWidth]; })()`), ["copy-all", "solid", "3px"]);

    eq("progress with no answers", await tab.eval(PROGRESS), "0 of 4 open cards answered. 1 blocking card has no answer.");

    // Tap an option (Q-007). The correction rule: a second tap on a chosen option removes the label and the separators after it.
    await tab.click(opt("Q-007", "A. Local-first"));
    eq("tap A. Local-first", await tab.eval(`${box("Q-007")}.value`), "A. Local-first");
    eq("tap sets pressed states", await tab.eval(pressed("Q-007")), ["true", "false", "false"]);
    eq("tap focuses the box and puts the cursor at the end", await tab.eval(`(() => { const t = ${box("Q-007")}; return [document.activeElement === t, t.selectionStart, t.selectionEnd, t.value.length]; })()`), [true, 14, 14, 14]);
    eq("progress after the blocking card is answered", await tab.eval(PROGRESS), "1 of 4 open cards answered.");
    await tab.type(", but keep the export button");
    eq("typing keeps the pressed state", await tab.eval(pressed("Q-007")), ["true", "false", "false"]);
    await tab.click(opt("Q-007", "B. Hosted database"));
    eq("tap B replaces A and keeps the rest", await tab.eval(`${box("Q-007")}.value`), "B. Hosted database, but keep the export button");
    eq("pressed states follow the text", await tab.eval(pressed("Q-007")), ["false", "true", "false"]);
    await tab.click(opt("Q-007", "B. Hosted database"));
    eq("tap B again removes the label and the leading separators", await tab.eval(`${box("Q-007")}.value`), "but keep the export button");
    eq("no option is pressed after the toggle", await tab.eval(pressed("Q-007")), ["false", "false", "false"]);
    await tab.click(opt("Q-007", "A. Local-first"));
    eq("tap A on text without a label", await tab.eval(`${box("Q-007")}.value`), "A. Local-first, but keep the export button");

    // Label boundary: "One screenful" does not start with the label "One screen".
    await tab.eval(`${box("Q-006")}.focus()`);
    await tab.type("One screenful");
    await tab.click(opt("Q-006", "One screen"));
    eq("label must not be followed by a letter", await tab.eval(`${box("Q-006")}.value`), "One screen, One screenful");
    await setBox(tab, "Q-006", "");
    await tab.click(opt("Q-006", "One screen"));
    eq("tap One screen", await tab.eval(`${box("Q-006")}.value`), "One screen");
    eq("different option texts do not both press", await tab.eval(pressed("Q-006")), ["true", "false"]);

    // Decide later (Q-004, Q-005).
    await tab.eval(`${box("Q-004")}.focus()`);
    await tab.type("keep plain");
    await tab.click(btn(Q("Q-004"), "Decide later"));
    eq("Decide later writes Later", await tab.eval(`[${box("Q-004")}.value, ${btn(Q("Q-004"), "Decide later")}.getAttribute('aria-pressed')]`), ["Later", "true"]);
    await tab.click(btn(Q("Q-004"), "Decide later"));
    eq("second press restores the text", await tab.eval(`[${box("Q-004")}.value, ${btn(Q("Q-004"), "Decide later")}.getAttribute('aria-pressed')]`), ["keep plain", "false"]);
    await tab.click(btn(Q("Q-004"), "Decide later"));
    await tab.click(btn(Q("Q-005"), "Decide later"));
    await tab.click(btn(Q("Q-005"), "Decide later"));
    eq("second press on an empty box restores empty", await tab.eval(`${box("Q-005")}.value`), "");
    eq("progress after three answers", await tab.eval(PROGRESS), "3 of 4 open cards answered.");

    // Drafts survive a reload.
    await tab.goto(url);
    eq("drafts and states restored after reload", await tab.eval(`[${box("Q-007")}.value, ${box("Q-006")}.value, ${box("Q-004")}.value, ${box("Q-005")}.value, ${pressed("Q-007")}, ${btn(Q("Q-004"), "Decide later")}.getAttribute('aria-pressed'), ${PROGRESS}]`),
      ["A. Local-first, but keep the export button", "One screen", "Later", "", ["true", "false", "false"], "true", "3 of 4 open cards answered."]);

    // Copy all answers.
    await tab.click(`document.getElementById('copy-all')`);
    const out = await tab.eval(`(() => { const b = document.getElementById('out-text'); return { value: b.value, shown: !document.getElementById('out').hidden, selected: [b.selectionStart, b.selectionEnd, b.value.length], focus: document.activeElement === b, status: document.getElementById('copy-all-status').textContent }; })()`);
    const [head, ...paras] = out.value.split("\n\n");
    check("copy all: line 1", /^TBD Board answers: Hearth decisions \(board k7f3q2, rev 14\), \d{4}-\d\d-\d\d \d\d:\d\d, 3 of 4 open cards answered\.$/.test(head), head);
    const t = /, (\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d), /.exec(head);
    check("copy all: time is the local time", !!t && Math.abs(new Date(+t[1], t[2] - 1, +t[3], +t[4], +t[5]) - Date.now()) < 3 * 60 * 1000, head);
    eq("copy all: card paragraphs in open order", paras, [
      "Q-007 (Sync: local-first, or a hosted database?): A. Local-first, but keep the export button",
      "Q-006 (Onboarding: three short screens, or one screen?): One screen",
      "Q-004 (Release notes: playful or plain?): Later",
      "(Agent: record these answers with the tbd-board skill.)"]);
    check("copy all: box is visible, focused and selected", out.shown && out.focus && out.selected[0] === 0 && out.selected[1] === out.selected[2], JSON.stringify(out));
    check("copy all: status text tells the result", out.status.length > 0, JSON.stringify(out));

    // Copy this answer.
    await tab.click(btn(Q("Q-006"), "Copy this answer"));
    const one = await tab.eval(`document.getElementById('out-text').value`);
    eq("copy this answer: same header, only that card", one.split("\n\n").slice(1), ["Q-006 (Onboarding: three short screens, or one screen?): One screen", "(Agent: record these answers with the tbd-board skill.)"]);
    check("copy this answer: header has the board totals", one.startsWith("TBD Board answers: Hearth decisions (board k7f3q2, rev 14), ") && one.split("\n")[0].endsWith(", 3 of 4 open cards answered."), one);
    await tab.click(btn(Q("Q-005"), "Copy this answer"));
    eq("copy this answer with no answer", await tab.eval(`[document.getElementById('out-text').value, ${Q("Q-005")}.querySelector('.copied').textContent]`), ["(no answers written yet)", "No answers written yet."]);

    // Search and filter chips.
    eq("filter panel is open on a wide screen", await tab.eval(`document.getElementById('filters').open`), true);
    eq("filter UI at start", await tab.eval(`[document.getElementById('clear').hidden, document.getElementById('shown').textContent, [...document.querySelectorAll('#chips-a button')].map((b) => b.textContent), document.getElementById('group-a').hidden]`),
      [true, "", ["Architecture", "Brand", "Copy", "Product", "UX"], false]);
    await tab.eval(`document.getElementById('search').focus()`);
    await tab.type("kettle");
    eq("search kettle shows only Q-005", await tab.eval(VISIBLE), ["Q-005"]);
    eq("headings and count while filtered", await tab.eval(`[${HEADINGS}, document.getElementById('shown').textContent, document.getElementById('clear').hidden]`),
      [["Open (1 of 4)", "Decided for you (0 of 3)", "Answered and closed (0 of 1)"], "1 of 8 shown", false]);
    await tab.goto(url);
    eq("search text and result are kept after reload", await tab.eval(`[document.getElementById('search').value, ${VISIBLE}]`), ["kettle", ["Q-005"]]);
    await tab.click(`document.getElementById('clear')`);
    eq("Clear filters resets search, chips and counts", await tab.eval(`[document.getElementById('search').value, ${VISIBLE}.length, ${HEADINGS}[0], document.getElementById('shown').textContent, document.getElementById('clear').hidden, localStorage.getItem('tbd-board:k7f3q2:filter')]`),
      ["", 8, "Open (4)", "", true, null]);
    await tab.click(filterChip("blocking"));
    eq("chip blocking shows only Q-007", await tab.eval(`[${VISIBLE}, ${filterChip("blocking")}.getAttribute('aria-pressed')]`), [["Q-007"], "true"]);
    await tab.click(filterChip("urgent"));
    eq("chips in one group are OR (decided-for-you entries do not match)", await tab.eval(VISIBLE), ["Q-007", "Q-006", "Q-003"]);
    await tab.click(filterChip("UX"));
    eq("chips in two groups are AND", await tab.eval(VISIBLE), ["Q-006"]);
    await tab.click(`document.getElementById('clear')`);
    await tab.eval(`document.getElementById('search').focus()`);
    await tab.type("INTL");
    eq("search is not case sensitive and finds decided-for-you entries", await tab.eval(VISIBLE), ["A-014"]);
    await tab.click(`document.getElementById('clear')`);
    await tab.eval(`document.getElementById('search').focus()`);
    await tab.type("reminders");
    eq("a match in the closed section opens it", await tab.eval(`[${VISIBLE}, document.querySelector('#closed details').open]`), [["Q-003"], true]);
    await tab.click(`document.getElementById('clear')`);
    await tab.eval(`document.getElementById('search').focus()`);
    await tab.type("zzzz-no-match");
    eq("empty result shows a message and Clear filters", await tab.eval(`[${VISIBLE}.length, document.getElementById('no-match').hidden, document.getElementById('no-match').textContent, document.getElementById('clear').hidden, document.getElementById('shown').textContent]`),
      [0, false, "Nothing matches the filters.", false, "0 of 8 shown"]);
    await tab.click(`document.getElementById('clear')`);
    eq("Clear filters hides the empty message", await tab.eval(`[document.getElementById('no-match').hidden, ${VISIBLE}.length]`), [true, 8]);
    check("no console errors after all steps", tab.errors.length === 0, tab.errors.join("\n     "));
  });
}

async function themeScenario() {
  const url = writePage("theme", fixture);
  const probe = `[document.documentElement.getAttribute('data-theme'), getComputedStyle(document.documentElement).colorScheme, getComputedStyle(document.body).backgroundColor]`;
  await withTab("theme", { media: "light" }, async (tab) => { // fixed system theme, so the result does not depend on this machine
    await tab.goto(url + "?theme=dark");
    eq("?theme=dark sets data-theme and the dark colours", await tab.eval(probe), ["dark", "dark", "rgb(20, 25, 23)"]);
    await tab.goto(url + "?theme=light");
    eq("?theme=light sets data-theme and the light colours", await tab.eval(probe), ["light", "light", "rgb(238, 241, 238)"]);
    await tab.goto(url + "?theme=purple");
    eq("other theme values are ignored", await tab.eval(probe), [null, "light", "rgb(238, 241, 238)"]);
  });
  await withTab("theme with a dark system", { media: "dark" }, async (tab) => {
    await tab.goto(url);
    eq("system dark is used without a parameter", await tab.eval(probe), [null, "dark", "rgb(20, 25, 23)"]);
    await tab.goto(url + "?theme=light");
    eq("?theme=light wins over a dark system", await tab.eval(probe), ["light", "light", "rgb(238, 241, 238)"]);
  });
}

async function narrowScenario() {
  const url = writePage("adversarial", adversarial);
  await withTab("360 px", { width: 360, height: 800, mobile: true }, async (tab) => {
    await tab.goto(url);
    const width = () => tab.eval(`[document.documentElement.scrollWidth, document.body.scrollWidth, innerWidth]`);
    const small = `[...document.querySelectorAll('button, summary, input[type=search]')].filter((e) => e.offsetParent !== null).filter((e) => e.getBoundingClientRect().height < 43.5).map((e) => (e.textContent || e.type).trim().slice(0, 30))`;
    let w = await width();
    check("360 px: no sideways page scroll", w[0] <= 360, JSON.stringify(w));
    eq("360 px: filter panel starts closed", await tab.eval(`document.getElementById('filters').open`), false);
    eq("360 px: touch targets are 44 px high (the filter summary is one of them)", await tab.eval(`[${small}, ${SUMMARY}.offsetParent !== null, ${SUMMARY}.getBoundingClientRect().height >= 43.5]`), [[], true, true]);
    await tab.click(SUMMARY);
    await sleep(100);
    w = await width();
    check("360 px: no sideways page scroll with the filter panel open", w[0] <= 360, JSON.stringify(w));
    eq("360 px: touch targets with the filter panel open (chips and search)", await tab.eval(`[document.getElementById('filters').open, ${small}, [...document.querySelectorAll('#filters button[data-group]')].filter((b) => b.offsetParent !== null).length === document.querySelectorAll('#filters button[data-group]').length]`), [true, [], true]);
    await tab.click(`document.querySelector('#closed summary')`);
    w = await width();
    check("360 px: no sideways page scroll with the closed section open", w[0] <= 360, JSON.stringify(w));
    eq("360 px: touch targets (closed section open)", await tab.eval(small), []);
    check("360 px: no console errors", tab.errors.length === 0, tab.errors.join("\n     "));
  });
}

async function panelScenario() {
  const url = writePage("panel", fixture);
  const seed = (filter) => `localStorage.setItem("tbd-board:k7f3q2:filter", ${JSON.stringify(JSON.stringify(filter))});`;
  const phone = { width: 360, height: 800, mobile: true };
  await withTab("panel, saved filter", { ...phone, preload: seed({ q: "kettle", p: [], a: [] }) }, async (tab) => {
    await tab.goto(url);
    eq("saved filter opens the panel on a phone", await tab.eval(`[document.getElementById('filters').open, ${SUMMARY}.textContent, ${VISIBLE}]`), [true, "Search and filter", ["Q-005"]]);
    await tab.click(SUMMARY);
    await sleep(100);
    eq("closed panel with a filter: summary shows the count", await tab.eval(`[document.getElementById('filters').open, ${SUMMARY}.textContent]`), [false, "Search and filter (1 of 8 shown)"]);
    await tab.click(SUMMARY);
    await sleep(100);
    eq("open panel: summary shows no count", await tab.eval(`${SUMMARY}.textContent`), "Search and filter");
    check("panel, saved filter: no console errors", tab.errors.length === 0, tab.errors.join("\n     "));
  });
  await withTab("panel, empty result", { ...phone, preload: seed({ q: "zzzz-no-match", p: [], a: [] }) }, async (tab) => {
    await tab.goto(url);
    await tab.click(SUMMARY);
    await sleep(100);
    eq("closed panel: message and Clear filters stay visible", await tab.eval(`[document.getElementById('filters').open, ${SUMMARY}.textContent, document.getElementById('no-match').offsetParent !== null, document.getElementById('no-match').textContent, document.getElementById('clear').offsetParent !== null]`),
      [false, "Search and filter (0 of 8 shown)", true, "Nothing matches the filters.", true]);
    await tab.click(`document.getElementById('clear')`);
    eq("Clear filters with a closed panel resets and moves focus to the summary", await tab.eval(`[document.getElementById('search').value, ${VISIBLE}.length, document.getElementById('no-match').hidden, document.getElementById('clear').hidden, ${SUMMARY}.textContent, document.getElementById('filters').open, document.activeElement === ${SUMMARY}]`),
      ["", 8, true, true, "Search and filter", false, true]);
  });
}

async function storageScenario() {
  const url = writePage("storage", fixture);
  const block = `Object.defineProperty(window, "localStorage", { get() { throw new DOMException("blocked", "SecurityError"); } });`;
  await withTab("storage blocked", { preload: block }, async (tab) => {
    await tab.goto(url);
    check("storage blocked: no exception on load", tab.errors.length === 0, tab.errors.join("\n     "));
    eq("storage blocked: cards render", await tab.eval(`document.querySelectorAll('#open article.card').length`), 4);
    await tab.click(opt("Q-007", "A. Local-first"));
    await tab.type(", fast");
    await tab.eval(`document.getElementById('search').focus()`);
    await tab.type("kettle");
    await tab.click(`document.getElementById('copy-all')`);
    eq("storage blocked: tap, type, filter and copy work", await tab.eval(`[${VISIBLE}, document.getElementById('out-text').value.split("\\n\\n").slice(1)]`),
      [["Q-005"], ["Q-007 (Sync: local-first, or a hosted database?): A. Local-first, fast", "(Agent: record these answers with the tbd-board skill.)"]]);
    check("storage blocked: no exception after use", tab.errors.length === 0, tab.errors.join("\n     "));
  });
}

async function draftScenario() {
  const url = writePage("drafts", fixture);
  const seed = `localStorage.setItem("tbd-board:k7f3q2:draft:Q-005", "mine");
    localStorage.setItem("tbd-board:k7f3q2:draft:Q-003", "closed card");
    localStorage.setItem("tbd-board:k7f3q2:draft:Q-999", "unknown card");
    localStorage.setItem("tbd-board:other:draft:Q-003", "other board");
    localStorage.setItem("tbd-board:k7f3q2:filter", "{not json");
    localStorage.setItem("unrelated", "x");`;
  await withTab("draft clean-up", { preload: seed }, async (tab) => {
    await tab.goto(url);
    eq("draft clean-up removes drafts of closed and unknown cards only", await tab.eval(`Object.keys(localStorage).filter((k) => !k.endsWith(":filter")).sort()`),
      ["tbd-board:k7f3q2:draft:Q-005", "tbd-board:other:draft:Q-003", "unrelated"]);
    eq("draft of an open card is restored; a bad saved filter is ignored", await tab.eval(`[${box("Q-005")}.value, ${VISIBLE}.length]`), ["mine", 8]);
    check("draft clean-up: no console errors", tab.errors.length === 0, tab.errors.join("\n     "));
  });
}

async function safetyScenario() {
  const url = writePage("safety", adversarial);
  await withTab("unsafe text", {}, async (tab) => {
    await tab.goto(url);
    check("unsafe text: no exception and no alert", tab.errors.length === 0 && tab.dialogs.length === 0, tab.errors.concat(tab.dialogs).join("\n     "));
    const q = (s) => `${Q("Q-100")}.querySelectorAll(${JSON.stringify(s)})`;
    eq("unsafe text: title, area and blocks stay text", await tab.eval(`[${Q("Q-100")}.querySelector('h3').textContent, ${Q("Q-100")}.querySelector('.head').textContent.includes('<u>area</u>'), ${q("u, b, i, script")}.length]`),
      [evil.title, true, 0]);
    eq("unsafe text: no injected image and no javascript link", await tab.eval(`[document.querySelectorAll('img[src="x"], img[onerror]').length, document.querySelectorAll('a[href^="javascript" i], img[src^="javascript" i]').length]`), [0, 0]);
    eq("unsafe images: only https and relative addresses become links and images", await tab.eval(`[[...${q("a")}].map((a) => a.getAttribute('href')), [...${q("img")}].map((i) => i.getAttribute('src'))]`),
      [["https://example.invalid/ok.png", "assets/ok.png"], ["https://example.invalid/ok.png", "assets/ok.png"]]);
    eq("unsafe images: caption and notice are shown as text", await tab.eval(`[...${q("figcaption")}].map((f) => f.textContent)`),
      ["<i>bad</i> (image not shown: unsafe address)", "data (image not shown: unsafe address)", "space (image not shown: unsafe address)",
        "tab (image not shown: unsafe address)", "protocol-relative (image not shown: unsafe address)", "https ok", "relative ok"]);
    eq("unsafe text: board title is text", await tab.eval(`[document.querySelector('h1').textContent, document.title]`), ["<i>Evil</i> board", "<i>Evil</i> board"]);
    eq("decided-for-you entry with a change shows it", await tab.eval(`[...document.querySelectorAll('.auto')].find((a) => a.textContent.includes('A-100')).textContent.includes('Changed: D-020: changed it')`), true);
    // The unsafe option label is a text button; tapping it must not run anything.
    await tab.click(`${Q("Q-100")}.querySelector('.opt')`);
    check("unsafe text: tapping an unsafe option runs nothing", tab.errors.length === 0 && tab.dialogs.length === 0 && (await tab.eval(`${box("Q-100")}.value`)) === evil.options[0].label, tab.errors.join("\n     "));
  });
}

async function dataScenario() {
  await withTab("odd data", {}, async (tab) => {
    const odd = { schema: 1, title: 5, questions: [null, 5, "x", { id: "Q-001", title: "T1", priority: "weird", status: "open", options: "nope", context: "str", images: [null, { src: ["a.png"] }] },
      { id: "Q-003", title: "T3", priority: "low", status: "open", options: [{ label: "" }, { label: "A", detail: null, recommended: "yes" }] },
      { id: "Q-002", title: "T2", priority: null, status: "open" }], autodecided: { a: 1 } };
    await tab.goto(writePage("odd", odd));
    check("odd data: no exception", tab.errors.length === 0, tab.errors.join("\n     "));
    eq("odd data: unknown priority sorts last and is shown as written", await tab.eval(`[...document.querySelectorAll('#open article.card')].map((c) => [c.dataset.id, c.querySelector('.chip').textContent])`),
      [["Q-003", "low"], ["Q-001", "weird"], ["Q-002", "no priority"]]);
    await tab.goto(writePage("bad-json", null, '{ "schema": 1, '));
    eq("bad JSON: error box with the check command, nothing else shown", await tab.eval(`[document.getElementById('error').hidden, document.getElementById('error').textContent.includes(${JSON.stringify(ERROR_HINT)}), document.getElementById('board').hidden]`), [false, true, true]);
    check("bad JSON: no uncaught exception", tab.errors.length === 0, tab.errors.join("\n     "));
    await tab.goto(writePage("not-object", null, "[1, 2]"));
    eq("data that is not an object: error box", await tab.eval(`[document.getElementById('error').hidden, document.getElementById('error').textContent.includes(${JSON.stringify(ERROR_HINT)})]`), [false, true]);
  });
  await withTab("progress wording", {}, async (tab) => {
    await tab.goto(writePage("one", smallBoard(1, 1)));
    eq("progress: one open card, one blocking", await tab.eval(PROGRESS), "0 of 1 open card answered. 1 blocking card has no answer.");
    await tab.goto(writePage("two", smallBoard(2, 3)));
    eq("progress: two blocking cards", await tab.eval(PROGRESS), "0 of 3 open cards answered. 2 blocking cards have no answer.");
  });
}

async function emptyScenario() {
  const url = pathToFileURL(join(pagesDir, "empty.html")).href;
  writeFileSync(join(pagesDir, "empty.html"), template);
  await withTab("empty board", {}, async (tab) => {
    await tab.goto(url);
    check("empty board: no exception", tab.errors.length === 0, tab.errors.join("\n     "));
    eq("empty board: empty states and footer", await tab.eval(`[...['open', 'auto', 'closed'].map((i) => document.getElementById(i).textContent), document.getElementById('foot').textContent, ${PROGRESS}, document.getElementById('group-a').hidden]`),
      ["No open questions.", "Nothing yet.", "Nothing yet.", "TBD Board 1.0.0Board (not set), revision 0", "0 of 0 open cards answered.", true]);
    await tab.click(`document.getElementById('copy-all')`);
    eq("empty board: copy all says there are no answers", await tab.eval(`[document.getElementById('out-text').value, document.getElementById('copy-all-status').textContent]`), ["(no answers written yet)", "No answers written yet."]);
  });
}

async function perfScenario() {
  const url = writePage("perf", generated);
  await withTab("200 cards", {}, async (tab) => {
    await tab.goto(url);
    check("200 cards: no exception", tab.errors.length === 0, tab.errors.join("\n     "));
    const load = await tab.eval(`Math.round(performance.getEntriesByType('navigation')[0].loadEventEnd)`);
    console.log(`INFO 200 cards: load event ${load} ms after navigation start`);
    const steps = await tab.eval(`(() => {
      const s = document.getElementById('search'), times = [];
      for (const v of ['n', 'ne', 'nee', 'need', 'needl', 'needle']) {
        const t0 = performance.now();
        s.value = v;
        s.dispatchEvent(new Event('input', { bubbles: true }));
        document.body.offsetHeight; // force style and layout, so the time includes the page update
        times.push(performance.now() - t0);
      }
      return times;
    })()`);
    const worst = Math.max(...steps);
    console.log(`INFO 200 cards: search steps ${steps.map((t) => t.toFixed(1)).join(", ")} ms (worst ${worst.toFixed(1)} ms)`);
    check("200 cards: one filter step takes less than 100 ms", worst < 100, `worst ${worst.toFixed(1)} ms`);
    eq("200 cards: filter result is right", await tab.eval(`[${HEADINGS}[0], ${VISIBLE}.length]`), ["Open (29 of 200)", 29]);
    const chip = await tab.eval(`(() => { const b = ${filterChip("blocking")}, t0 = performance.now(); b.click(); document.body.offsetHeight; return performance.now() - t0; })()`);
    console.log(`INFO 200 cards: chip step ${chip.toFixed(1)} ms`);
    check("200 cards: a chip step takes less than 100 ms", chip < 100, `${chip.toFixed(1)} ms`);
  });
}

// ---- Run ----
async function cleanup() {
  try { browser?.ws.close(); } catch { /* already closed */ }
  if (chrome && chrome.exitCode === null) {
    const exited = new Promise((r) => chrome.once("exit", r));
    chrome.kill("SIGTERM");
    await Promise.race([exited, sleep(3000)]);
    if (chrome.exitCode === null) { chrome.kill("SIGKILL"); await Promise.race([exited, sleep(2000)]); }
  }
  rmSync(work, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => cleanup().finally(() => process.exit(130)));

let fatal = null;
try {
  browser = await connect(await startChrome());
  for (const scenario of [mainScenario, themeScenario, narrowScenario, panelScenario, storageScenario, draftScenario, safetyScenario, dataScenario, emptyScenario, perfScenario]) await scenario();
} catch (e) {
  fatal = e;
} finally {
  await cleanup();
}
if (fatal) console.log(`FAIL browser check could not run\n     ${fatal.stack || fatal}`);
const failed = results.filter((ok) => !ok).length + (fatal ? 1 : 0);
console.log(`\n${results.length - results.filter((ok) => !ok).length} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
