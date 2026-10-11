#!/usr/bin/env node
// Makes the demo board and the README media of TBD Board. Zero dependencies.
// Needs Node 22+ (global WebSocket), Chrome, python3 and ffmpeg.
// Usage, from any folder:  node tools/make_media.mjs
// Chrome path: env CHROME_PATH, else the macOS app, else "google-chrome".
// Reads:  tests/fixtures/hearth.json, skills/tbd-board/scripts/board.py and its page template,
//         docs/media/icon-light.svg
// Writes: examples/hearth/board.html, examples/hearth/log.md, examples/hearth/assets/*.png (card images),
//         docs/media/board-*.png, docs/media/tap-option.gif, docs/media/icon-{128,256,512}.png,
//         skills/tbd-board/assets/icon.png
// Chrome and the temp folder are removed in all cases. Run it again at any time; it overwrites its outputs.
import { execFileSync, spawn } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const at = (...parts) => join(root, ...parts);
const boardPy = at("skills/tbd-board/scripts/board.py");
const boardFile = at("examples/hearth/board.html");
const assetsDir = at("examples/hearth/assets");
const mediaDir = at("docs/media");
const work = mkdtempSync(join(tmpdir(), "tbd-board-media-"));
const profileDir = join(work, "profile");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const KB = 1000;

// ---- Decision log of the demo board (fictional). Dates run from 2026-10-06 to 2026-10-09. ----
const LOG = [
  { id: "D-001", date: "2026-10-06", decision: "Hearth 1.0 is a phone app for iOS and Android. There is no web version.", reason: "Households plan chores on the phone.", link: "Answers Q-001." },
  { id: "D-002", date: "2026-10-06", decision: "Each chore has one owner and an optional repeat: daily, weekly, or monthly.", reason: "This covers the chores in the interviews. Shared chores can come later.", link: "Answers Q-002." },
  { id: "D-003", date: "2026-10-07", decision: "Keep the chore history for 90 days.", reason: "It is enough for a monthly review and the storage stays small.", link: "Changes A-004." },
  { id: "D-004", date: "2026-10-07", decision: "Invite codes last 7 days.", reason: "It gives time to share a code with the whole household.", link: "Changes A-006." },
  { id: "D-005", date: "2026-10-07", decision: "Show the chores in one list, sorted by due day.", reason: "People open the app to see what is due today.", link: "Changes A-007." },
  { id: "D-006", date: "2026-10-08", decision: "Hearth 1.0 ships in English only. Other languages come later.", reason: "It keeps the first release small.", link: "Changes A-008." },
  { id: "D-007", date: "2026-10-08", decision: "Any member of a household can mark any chore as done.", reason: "It matches how households work. The history shows who did it.", link: "Changes A-009." },
  { id: "D-008", date: "2026-10-08", decision: "Chore names stay as typed. Hearth does not translate them.", reason: "Translation changes the meaning of short words.", link: "Changes A-010." },
  { id: "D-009", date: "2026-10-09", decision: "Invite codes last 24 hours.", reason: "A code often goes into a group chat, so a short life is safer.", supersedes: ["D-004"], link: "Changes A-006." },
  { id: "D-010", date: "2026-10-09", decision: "A week starts on the day that the phone setting says.", reason: "The phone setting is right for most people.", link: "Changes A-011." },
  { id: "D-011", date: "2026-10-09", decision: "A chore that is not done by the end of its day shows in red the next day.", reason: "It is a clear sign and it needs no extra screen.", link: "Changes A-005." },
  { id: "D-012", date: "2026-10-09", decision: "Push notifications, asked after the first chore is done. One reminder a day at most.", reason: "Reminders are the main reason people open a chores app.", link: "Answers Q-003." }
];

// Python builds the board and the log, so the file format comes from board.py itself.
// Arguments: board.py, fixture, board output, log output. The log entries come on stdin as JSON.
const BUILD_PY = `
import importlib.util, json, sys
board_py, fixture, out_board, out_log = sys.argv[1:5]
spec = importlib.util.spec_from_file_location("board", board_py)
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)
def write(path, text):
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))
with open(fixture, encoding="utf-8") as f:
    data = json.load(f)
head, _, tail = board.load_template()
write(out_board, head + board.dump_block(data) + tail)
log = board.LOG_HEADER
for e in json.load(sys.stdin):
    board.today = lambda day=e["date"]: day
    log += board.log_entry(e["id"], e["decision"], e["reason"], e.get("supersedes", []), e["link"], "user")
write(out_log, log)
`;

function buildBoard() {
  execFileSync("python3", ["-B", "-I", "-c", BUILD_PY, boardPy, at("tests/fixtures/hearth.json"), boardFile, at("examples/hearth/log.md")],
    { input: JSON.stringify(LOG), stdio: ["pipe", "inherit", "inherit"] });
}
// The check needs the card images, so it runs after they exist.
const checkBoard = () => execFileSync("python3", ["-B", boardPy, "check", "--board", boardFile], { stdio: "inherit" });

// ---- Chrome and the DevTools protocol (same approach as tests/browser_check.mjs) ----
let chrome = null;
let browser = null;
async function startChrome() {
  const bin = process.env.CHROME_PATH ||
    (process.platform === "darwin" ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" : "google-chrome");
  const args = ["--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profileDir}`, "--hide-scrollbars",
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

// A tab in its own browser context, so each scene has its own storage (no saved drafts or filters).
async function withTab(options, run) {
  const { width, height, scale = 1, mobile = false, transparent = false, preload } = options;
  let contextId;
  try {
    ({ browserContextId: contextId } = await browser.send("Target.createBrowserContext"));
    const { targetId } = await browser.send("Target.createTarget", { url: "about:blank", browserContextId: contextId });
    const { sessionId } = await browser.send("Target.attachToTarget", { targetId, flatten: true });
    const send = (method, params) => browser.send(method, params, sessionId);
    const tab = { send };
    let onLoad = null;
    browser.on((m) => {
      if (m.sessionId === sessionId && m.method === "Page.loadEventFired" && onLoad) { onLoad(); onLoad = null; }
    });
    await send("Page.enable");
    await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: scale, mobile });
    if (transparent) await send("Emulation.setDefaultBackgroundColorOverride", { color: { r: 0, g: 0, b: 0, a: 0 } });
    if (preload) await send("Page.addScriptToEvaluateOnNewDocument", { source: preload });
    // Go to a page and wait for the load event. A broken image is an error: the card images must show.
    tab.goto = async (url) => {
      const loaded = new Promise((r) => { onLoad = r; });
      await send("Page.navigate", { url });
      await loaded;
      // The board images are lazy. Load them all now; decode() rejects when an image is broken.
      await tab.eval(`Promise.all([...document.images].map((i) => { i.loading = "eager"; return i.decode(); })).then(() => 0)`);
      await sleep(150);
    };
    tab.eval = async (expression) => {
      const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true, userGesture: true });
      if (r.exceptionDetails) throw new Error(`eval failed: ${r.exceptionDetails.exception?.description || r.exceptionDetails.text}\n${expression}`);
      return r.result.value;
    };
    // Real mouse click at the centre of the element. The page scrolls only when the element is not in view.
    tab.click = async (elementExpr) => {
      const [x, y] = await tab.eval(`(() => {
        const el = ${elementExpr};
        if (!el) throw new Error("no element for click");
        el.scrollIntoView({ block: "nearest", inline: "nearest" });
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
    tab.shot = async (file) => {
      const { data } = await send("Page.captureScreenshot", { format: "png" });
      writeFileSync(file, Buffer.from(data, "base64"));
    };
    await run(tab);
  } finally {
    if (contextId) await browser.send("Target.disposeBrowserContext", { browserContextId: contextId }).catch(() => {});
  }
}

// Open a page, take one screenshot of the viewport, and check the size limit.
async function render(options, url, file, maxBytes) {
  await withTab(options, async (tab) => {
    await tab.goto(url);
    await tab.shot(file);
  });
  report(file, maxBytes);
}
function report(file, maxBytes) {
  const size = statSync(file).size;
  console.log(`${size > maxBytes ? "FAIL" : "ok  "} ${file.slice(root.length + 1)} ${(size / KB).toFixed(1)} KB (limit ${maxBytes / KB} KB)`);
  if (size > maxBytes) throw new Error(`${file} is larger than ${maxBytes} bytes`);
}

// ---- Card images: flat drawings in inline SVG ----
const INK = "#2d3236", PAPER = "#efe9df", LINE = "#d6d0c4", BOX = "#b9b2a5", PEACH = "#f1c9b8", PEACH_DARK = "#e8a98f", ACCENT = "#cf5a36";
const rect = (x, y, w, h, fill, r = 4, extra = "") => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" ${extra}/>`;
const dots = (cx, y, on) => [0, 1, 2].map((i) => `<circle cx="${cx + (i - 1) * 14}" cy="${y}" r="4" fill="${i === on ? INK : LINE}"/>`).join("");
const phone = (x, y, w, h, inner) => `<g transform="translate(${x} ${y})">${rect(0, 0, w, h, INK, 24)}${rect(8, 8, w - 16, h - 16, "#fff", 17)}${inner}</g>`;
const button = (x, y, w, h, label, size) => `${rect(x, y, w, h, ACCENT, 10)}<text x="${x + w / 2}" y="${y + h / 2 + size * 0.35}" text-anchor="middle" font-size="${size}" font-weight="700" fill="#fff">${label}</text>`;
const checkbox = (x, y, done) => done
  ? `${rect(x, y, 22, 22, ACCENT, 6)}<path d="M${x + 6} ${y + 11} l5 5 l8 -10" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`
  : rect(x + 1, y + 1, 20, 20, "#fff", 6, `stroke="${BOX}" stroke-width="2"`);
const title = (x, y) => rect(x, y, 64, 12, INK, 6);

const onboardingThree = `${rect(0, 0, 600, 400, PAPER, 0)}
  ${phone(38, 30, 150, 340, `${title(22, 34)}<circle cx="75" cy="128" r="40" fill="${PEACH}"/>${rect(22, 192, 106, 8, LINE)}${rect(22, 208, 80, 8, LINE)}${dots(75, 298, 0)}`)}
  ${phone(225, 30, 150, 340, `${title(22, 34)}${[84, 124, 164].map((y) => checkbox(22, y, y === 84) + rect(54, y + 7, 72, 8, LINE)).join("")}${dots(75, 298, 1)}`)}
  ${phone(412, 30, 150, 340, `${title(22, 34)}<circle cx="62" cy="120" r="26" fill="${PEACH}"/><circle cx="90" cy="120" r="26" fill="${PEACH_DARK}"/>${rect(22, 170, 106, 8, LINE)}${rect(22, 186, 80, 8, LINE)}${button(22, 232, 106, 40, "Invite", 17)}${dots(75, 298, 2)}`)}`;

const onboardingOne = `${rect(0, 0, 600, 400, PAPER, 0)}
  ${phone(190, 20, 220, 360, `${button(24, 36, 172, 44, "Invite", 18)}${rect(24, 104, 72, 8, LINE)}${["Dishes", "Bins", "Laundry", "Plants"].map((label, i) => {
    const y = 128 + i * 50;
    return `${checkbox(24, y, i === 0)}<text x="60" y="${y + 17}" font-size="15" fill="${INK}">${label}</text><circle cx="186" cy="${y + 11}" r="9" fill="${i % 2 ? PEACH_DARK : PEACH}"/>${rect(24, y + 36, 172, 2, LINE, 0)}`;
  }).join("")}`)}`;

const icon = (bg, glyph) => `${rect(8, 8, 496, 496, bg, 112)}${glyph}`;
const white = `fill="#fff"`;
const stroke = (w) => `fill="none" stroke="#fff" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"`;
const kettle = icon("#cf5a36", `<g transform="translate(256 256) scale(1.12) translate(-264 -296)">
  <path ${white} d="M150 372 C150 286 190 246 256 246 C322 246 362 286 362 372 Q362 392 342 392 L170 392 Q150 392 150 372 Z"/>
  ${rect(206, 224, 100, 26, "#fff", 13)}<circle cx="256" cy="208" r="14" ${white}/>
  <path ${white} d="M346 304 C382 300 402 272 414 248 Q420 238 432 244 Q444 252 438 264 C424 306 404 352 350 368 Z"/>
  <path ${stroke(20)} d="M166 296 C96 276 92 380 160 358"/></g>`);
const house = icon("#b8741a", `
  <path ${stroke(36)} d="M110 266 L256 132 L402 266"/>
  ${rect(318, 150, 32, 50, "#fff", 4)}
  <path ${white} d="M150 270 L256 174 L362 270 L362 392 L150 392 Z"/>
  ${rect(232, 306, 48, 86, "#b8741a", 6)}`);
const check = icon("#3d7a5a", `<circle cx="256" cy="256" r="150" ${stroke(26)}/><path ${stroke(40)} d="M184 262 L240 318 L334 200"/>`);

const svgPage = (w, h, body) => `<!doctype html><meta charset="utf-8"><style>html,body{margin:0;background:transparent}svg{display:block}</style>
<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" font-family="Helvetica Neue, Helvetica, Arial, sans-serif">${body}</svg>`;

async function cardImages() {
  const images = [["onboarding-three", 600, 400, onboardingThree], ["onboarding-one", 600, 400, onboardingOne],
    ["icon-kettle", 512, 512, kettle], ["icon-house", 512, 512, house], ["icon-check", 512, 512, check]];
  for (const [name, w, h, body] of images) {
    const page = join(work, `${name}.html`);
    writeFileSync(page, svgPage(w, h, body));
    await render({ width: w, height: h, transparent: true }, pathToFileURL(page).href, join(assetsDir, `${name}.png`), 60 * KB);
  }
}

// ---- Icon PNGs: the light icon on a transparent background ----
async function icons() {
  const svg = readFileSync(at("docs/media/icon-light.svg"), "utf8");
  const page = join(work, "icon.html");
  for (const size of [128, 256, 512]) {
    writeFileSync(page, `<!doctype html><meta charset="utf-8"><style>html,body{margin:0;background:transparent}svg{display:block;width:${size}px;height:${size}px}</style>${svg}`);
    await render({ width: size, height: size, transparent: true }, pathToFileURL(page).href, join(mediaDir, `icon-${size}.png`), 300 * KB);
  }
  copyFileSync(join(mediaDir, "icon-256.png"), at("skills/tbd-board/assets/icon.png"));
}

// ---- Board screenshots and the GIF ----
const board = (theme) => `${pathToFileURL(boardFile).href}?theme=${theme}`;
const Q = (id) => `document.querySelector('article[data-id="${id}"]')`;
const opt = (id, label) => `[...${Q(id)}.querySelectorAll('.opt')].find((b) => b.querySelector('strong').textContent === ${JSON.stringify(label)})`;
const btn = (scope, label) => `[...${scope}.querySelectorAll('button')].find((b) => b.textContent.trim() === ${JSON.stringify(label)})`;
const scrollTo = (tab, expr) => tab.eval(`window.scrollTo(0, ${expr})`);
const SHOT_LIMIT = 300 * KB;

// A fixed clock, so the time in the copied text matches the date of the board and every run gives the same image.
const FIXED_CLOCK = `(() => { const T = new Date(2026, 9, 11, 9, 30).getTime(), D = Date;
  Date = class extends D { constructor(...a) { super(...(a.length ? a : [T])); } static now() { return T; } }; })()`;

async function boardShots() {
  await render({ width: 1280, height: 900 }, board("light"), join(mediaDir, "board-light.png"), SHOT_LIMIT);
  await render({ width: 390, height: 844, scale: 2, mobile: true }, board("dark"), join(mediaDir, "board-phone-dark.png"), SHOT_LIMIT);

  await withTab({ width: 1280, height: 900 }, async (tab) => {
    await tab.goto(board("light"));
    await tab.click(`[...document.querySelectorAll('#chips-a button')].find((b) => b.textContent === "UX")`);
    // Scroll so the filter panel is at the top and the result card below it.
    await scrollTo(tab, `document.getElementById('filters').getBoundingClientRect().top + scrollY - 12`);
    await tab.shot(join(mediaDir, "board-filtered.png"));
  });
  report(join(mediaDir, "board-filtered.png"), SHOT_LIMIT);

  await withTab({ width: 1280, height: 900, preload: FIXED_CLOCK }, async (tab) => {
    await tab.goto(board("light"));
    await tab.click(opt("Q-007", "A. Local-first"));
    await tab.type(", but keep the export button.");
    await tab.click(opt("Q-006", "One screen"));
    await tab.click(btn(Q("Q-004"), "Decide later"));
    await tab.click(`document.getElementById('copy-all')`);
    // Make the box of the copied text as high as its text, so the whole text is in view (like a drag on its resize handle).
    await tab.eval(`(() => { const t = document.getElementById('out-text'); t.style.height = "auto"; t.style.height = t.scrollHeight + 4 + "px"; })()`);
    await scrollTo(tab, "0");
    await tab.shot(join(mediaDir, "board-answers.png"));
  });
  report(join(mediaDir, "board-answers.png"), SHOT_LIMIT);
}

// The GIF: tap an option, the answer box fills, then a few words are typed. One screenshot per step.
async function tapGif() {
  const framesDir = join(work, "frames");
  mkdirSync(framesDir);
  const frames = []; // [file, seconds]
  await withTab({ width: 640, height: 470 }, async (tab) => {
    await tab.goto(board("light"));
    // Start at the last context paragraph, so the options and the answer box fit under it.
    await scrollTo(tab, `[...${Q("Q-007")}.querySelectorAll('p')].at(-1).getBoundingClientRect().top + scrollY - 2`);
    const snap = async (seconds) => {
      const file = join(framesDir, `f${String(frames.length).padStart(3, "0")}.png`);
      await tab.shot(file);
      frames.push([file, seconds]);
    };
    await snap(1.2);
    await tab.click(opt("Q-007", "A. Local-first"));
    await snap(1.0);
    for (const chunk of [", b", "ut ", "kee", "p t", "he ", "exp", "ort", " bu", "tto", "n."]) {
      await tab.type(chunk);
      await snap(0.12);
    }
    frames.at(-1)[1] = 2.0;
  });
  // The concat list needs the last file twice, because it ignores the duration of the last entry.
  const list = frames.map(([f, s]) => `file '${f}'\nduration ${s}`).join("\n") + `\nfile '${frames.at(-1)[0]}'\n`;
  const listFile = join(work, "frames.txt");
  writeFileSync(listFile, list);
  const out = join(mediaDir, "tap-option.gif");
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listFile, "-vf",
    "fps=10,split[a][b];[a]palettegen=max_colors=64:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle", "-loop", "0", out]);
  report(out, 300 * KB);
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
// A normal run takes about 10 seconds. A stuck run stops with an error instead of waiting for ever.
setTimeout(() => { console.error("make_media timed out after 3 minutes"); cleanup().finally(() => process.exit(1)); }, 180 * 1000).unref();

let failure = null;
try {
  mkdirSync(assetsDir, { recursive: true });
  mkdirSync(mediaDir, { recursive: true });
  buildBoard();
  browser = await connect(await startChrome());
  await cardImages();
  checkBoard();
  await boardShots();
  await icons();
  await tapGif();
} catch (e) {
  failure = e;
} finally {
  await cleanup();
}
if (failure) {
  console.error(`make_media failed\n${failure.stack || failure}`);
  process.exit(1);
}
