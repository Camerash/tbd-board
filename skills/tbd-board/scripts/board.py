#!/usr/bin/env python3
"""TBD Board helper: keeps a decision board and an add-only decision log.

The board is one HTML file with a JSON data block (default
docs/decisions/board.html). The log is a Markdown file next to it (data field
"log", default log.md). Standard library only. Python 3.8 or newer.

Usage (run from the project root; every command takes --board PATH):

  board.py init [--dir docs/decisions] [--title "Decisions"] [--log log.md]
  board.py ask CARD.json|-        add or replace open cards (one object or a list)
  board.py answer ID --decision "..." [--reason "..."] [--supersedes D-001 ...]
  board.py close Q-ID --reason "..."
  board.py auto --title "..." --decision "..." --reason "..."
  board.py list [--open]
  board.py check
  board.py upgrade

Every command that writes first checks the board and refuses to write when the
board has errors. It adds 1 to "revision", sets "updated" to today, checks the
new data, and writes the file atomically. Only the content of the data block
changes; the rest of the page (the renderer) stays byte for byte the same.
New cards go to the start of "questions", so the newest card is first.
Errors go to stderr as "error: <file>: ..." with exit code 1.
"""
import argparse
import datetime
import json
import os
import re
import secrets
import stat
import string
import sys
import tempfile

VERSION = "1.0.0"
SCHEMA = 1
DEFAULT_BOARD = "docs/decisions/board.html"
DASH = "—"
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(SKILL_DIR, "assets", "board-template.html")

OPEN_TAG = '<script type="application/json" id="tbd-board-data">'
CLOSE_TAG = "</script>"
RENDERER_MARKERS = ('<meta name="generator" content="tbd-board ', '<script id="tbd-board-renderer">')
GENERATOR_RE = re.compile(r'<meta name="generator" content="tbd-board ([^"]*)"')

PRIORITIES = ("blocking", "urgent", "normal", "low")
STATUSES = ("open", "answered", "closed")
TOP_FIELDS = ("schema", "boardId", "revision", "title", "updated", "log", "questions", "autodecided")
CARD_FIELDS = ("id", "title", "priority", "status", "area", "asked", "blocks", "context", "images",
               "options", "recommendation", "decision")
AUTO_FIELDS = ("id", "date", "title", "decision", "reason", "changed")

# [0-9] and fullmatch on purpose: \d matches non-ASCII digits and $ matches before a newline.
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
BOARD_ID_RE = re.compile(r"[a-z0-9]{6,12}")
Q_RE = re.compile(r"Q-[0-9]{3,}")
A_RE = re.compile(r"A-[0-9]{3,}")
D_RE = re.compile(r"D-[0-9]+")
SCHEME_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*:")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
# An entry line of the log: "- **D-013** ...", "* D-013 ...", "### D-013", "| D-013 |", or "D-013".
LOG_ID_RE = re.compile(r"^[ \t]*(?:[-*+]|#{1,6}|\|)?[ \t]*\**(D-[0-9]+)", re.M)

LOG_HEADER = (
    "# Decision log\n\n"
    "This file records each decision. Add new entries at the end. Do not edit or delete a past entry. "
    "To change a decision, add a new entry that supersedes the old one and gives its ID.\n\n"
    "Format: `ID " + DASH + " date " + DASH + " decision. Reason. Links. Source.`\n\n"
)


class BoardError(Exception):
    """An expected problem. Holds the file name and one or more messages."""

    def __init__(self, path, *messages):
        Exception.__init__(self, path, *messages)
        self.path = path
        self.messages = messages


def today():
    return datetime.date.today().isoformat()


# ---------------------------------------------------------------- files

def read_text(path):
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8")
    except FileNotFoundError:
        raise BoardError(path, "file not found")
    except (OSError, UnicodeDecodeError) as e:
        raise BoardError(path, "cannot read: %s" % e)


def write_atomic(path, text):
    """Write text to path: temporary file in the same folder, fsync, then os.replace."""
    shown = path
    path = os.path.realpath(path)
    if os.path.exists(path):
        mode = stat.S_IMODE(os.stat(path).st_mode)
    else:
        umask = os.umask(0)
        os.umask(umask)
        mode = 0o666 & ~umask
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tbd-", suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            f.write(text.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except OSError as e:
        raise BoardError(shown, "cannot write: %s" % e)
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def parse_json(text, name, line_offset=0):
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise BoardError(name, "invalid JSON: %s at line %d, column %d" % (e.msg, e.lineno + line_offset, e.colno))


def dump_block(data):
    """The data block content. '</' and '<!--' are escaped so card text cannot end the script element."""
    text = json.dumps(data, indent=2, ensure_ascii=False)
    # "<!--" becomes "<!--" (valid JSON; "\!" is not).
    text = text.replace("</", "<\\/").replace("<!--", "<\\u0021--")
    return "\n" + text + "\n"


def split_board(text):
    """Split a board file at the data block. Return (head, raw, tail, problems).

    head ends with the opening tag, tail starts with the closing tag. head, raw
    and tail are None when the block cannot be found.
    """
    count = text.count(OPEN_TAG)
    if count != 1:
        return None, None, None, ["data block: the opening tag %s occurs %d times, it must occur once" % (OPEN_TAG, count)]
    start = text.index(OPEN_TAG) + len(OPEN_TAG)
    end = text.find(CLOSE_TAG, start)
    if end < 0:
        return None, None, None, ["data block: no closing %s found" % CLOSE_TAG]
    raw = text[start:end]
    problems = []
    if "</script" in raw.lower():
        problems.append('data block: contains "</script"; write it as "<\\/script"')
    if "<!--" in raw:
        problems.append('data block: contains "<!--"; write it as "<\\u0021--"')
    for marker in RENDERER_MARKERS:
        if marker not in text:
            problems.append("renderer is missing: %s not found" % marker)
    return text[:start], raw, text[end:], problems


def version_of(text):
    match = GENERATOR_RE.search(text)
    return match.group(1) if match else None


def load_template():
    """Return (head, raw, tail) of the template that belongs to this script."""
    text = read_text(TEMPLATE)
    head, raw, tail, problems = split_board(text)
    if problems:
        raise BoardError(TEMPLATE, *problems)
    if version_of(text) != VERSION:
        raise BoardError(TEMPLATE, "template version is %s, board.py version is %s" % (version_of(text), VERSION))
    return head, raw, tail


# ---------------------------------------------------------------- validation

def q(value):
    return json.dumps(value, ensure_ascii=False)


def is_str(value):
    return isinstance(value, str)


def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def is_date(value):
    if not is_str(value) or not DATE_RE.fullmatch(value):
        return False
    try:
        datetime.date(int(value[:4]), int(value[5:7]), int(value[8:]))
    except ValueError:
        return False
    return True


def safe_src(src):
    """The image rule of the contract, plus: no control characters, no leading or trailing space."""
    if CONTROL_RE.search(src) or src != src.strip():
        return False
    if src.startswith("https://"):
        return True
    return not (SCHEME_RE.match(src) or src.startswith(("/", "\\")) or "\\" in src)


def validate(data, folder):
    """Check data against schema 1. Return (errors, warnings), lists of messages."""
    errors, warnings = [], []
    if not isinstance(data, dict):
        return ["the data block must be a JSON object"], warnings
    if is_int(data.get("schema")) and data["schema"] > SCHEMA:
        return ["schema %d was made by a newer version; upgrade the skill" % data["schema"]], warnings

    def text(obj, key, where, optional=False, nonempty=True):
        if key not in obj:
            if not optional:
                errors.append("%s%s is required" % (where, key))
        elif not is_str(obj[key]) or (nonempty and not obj[key].strip()):
            errors.append("%s%s must be %s string" % (where, key, "a non-empty" if nonempty else "a"))

    def unknown(obj, known, where):
        for key in obj:
            if key not in known:
                warnings.append("%sunknown field %s" % (where, q(key)))

    if data.get("schema") != SCHEMA or not is_int(data.get("schema")):
        errors.append("schema must be the integer %d" % SCHEMA)
    if not (is_str(data.get("boardId")) and BOARD_ID_RE.fullmatch(data["boardId"])):
        errors.append("boardId must be 6 to 12 characters from a-z and 0-9")
    if not is_int(data.get("revision")) or data["revision"] < 0:
        errors.append("revision must be an integer, 0 or more")
    text(data, "title", "")
    if not is_date(data.get("updated")):
        errors.append("updated must be a date, YYYY-MM-DD")
    if "log" in data:
        text(data, "log", "")
        if is_str(data["log"]) and (os.path.isabs(data["log"]) or SCHEME_RE.match(data["log"])):
            errors.append("log %s must be a relative path (relative to the board file)" % q(data["log"]))
    unknown(data, TOP_FIELDS, "")

    cards = data.get("questions")
    if not isinstance(cards, list):
        errors.append("questions must be a list")
        cards = []
    seen = set()
    for number, card in enumerate(cards, 1):
        if not isinstance(card, dict):
            errors.append("card #%d must be an object" % number)
            continue
        cid = card.get("id")
        where = "card %s: " % (cid if is_str(cid) and cid else "#%d" % number)
        if not (is_str(cid) and Q_RE.fullmatch(cid)):
            errors.append(where + "id must be Q- and 3 or more digits, for example Q-007")
        elif cid in seen:
            errors.append(where + "duplicate id")
        else:
            seen.add(cid)
        text(card, "title", where)
        if card.get("priority") not in PRIORITIES:
            errors.append(where + "priority %s must be one of %s" % (q(card.get("priority")), ", ".join(PRIORITIES)))
        status = card.get("status")
        if status not in STATUSES:
            errors.append(where + "status %s must be one of %s" % (q(status), ", ".join(STATUSES)))
        text(card, "area", where, optional=True, nonempty=False)
        text(card, "blocks", where, optional=True, nonempty=False)
        text(card, "recommendation", where, optional=True, nonempty=False)
        if not is_date(card.get("asked")):
            errors.append(where + "asked must be a date, YYYY-MM-DD")
        context = card.get("context")
        if not isinstance(context, list) or not all(is_str(item) for item in context):
            errors.append(where + "context must be a list of strings")
        validate_images(card.get("images", []), folder, where, errors)
        validate_options(card.get("options"), where, errors)
        decision = card.get("decision")
        if not is_str(decision):
            errors.append(where + "decision must be a string")
        elif status == "open" and decision != "":
            errors.append(where + "decision must be empty while the card is open")
        elif status == "answered" and not re.match(r"D-[0-9]+: ", decision):
            errors.append(where + 'decision must start with "D-<number>: " when the card is answered')
        elif status == "closed" and not decision.strip():
            errors.append(where + "decision must give the reason when the card is closed")
        unknown(card, CARD_FIELDS, where)

    autos = data.get("autodecided")
    if not isinstance(autos, list):
        errors.append("autodecided must be a list")
        autos = []
    seen = set()
    for number, entry in enumerate(autos, 1):
        if not isinstance(entry, dict):
            errors.append("entry #%d must be an object" % number)
            continue
        aid = entry.get("id")
        where = "entry %s: " % (aid if is_str(aid) and aid else "#%d" % number)
        if not (is_str(aid) and A_RE.fullmatch(aid)):
            errors.append(where + "id must be A- and 3 or more digits, for example A-013")
        elif aid in seen:
            errors.append(where + "duplicate id")
        else:
            seen.add(aid)
        if not is_date(entry.get("date")):
            errors.append(where + "date must be a date, YYYY-MM-DD")
        for key in ("title", "decision", "reason"):
            text(entry, key, where)
        changed = entry.get("changed", "")
        if not is_str(changed) or (changed and not re.match(r"D-[0-9]+: ", changed)):
            errors.append(where + 'changed must be empty or start with "D-<number>: "')
        unknown(entry, AUTO_FIELDS, where)
    return errors, warnings


def validate_images(images, folder, where, errors):
    if not isinstance(images, list):
        errors.append(where + "images must be a list")
        return
    for image in images:
        src = image.get("src") if isinstance(image, dict) else None
        if not is_str(src) or not src:
            errors.append(where + "each image needs a src, a non-empty string")
        elif not safe_src(src):
            errors.append(where + "image src %s is not allowed; use a relative path or an https:// URL" % q(src))
        elif not src.startswith("https://") and not os.path.isfile(os.path.join(folder, src)):
            errors.append(where + "image not found: %s" % src)
        if isinstance(image, dict) and "caption" in image and not is_str(image["caption"]):
            errors.append(where + "image caption must be a string")


def validate_options(options, where, errors):
    if not isinstance(options, list):
        errors.append(where + "options must be a list")
        return
    if len(options) > 6:
        errors.append(where + "options has %d items; 6 is the most" % len(options))
    labels, recommended = set(), 0
    for number, option in enumerate(options, 1):
        if not isinstance(option, dict):
            errors.append(where + "option %d must be an object" % number)
            continue
        label = option.get("label")
        if not is_str(label) or not label.strip():
            errors.append(where + "option %d: label must be a non-empty string" % number)
        elif label in labels:
            errors.append(where + "option %d: duplicate label %s" % (number, q(label)))
        else:
            labels.add(label)
        if "detail" in option and not is_str(option["detail"]):
            errors.append(where + "option %d: detail must be a string" % number)
        if "recommended" in option and not isinstance(option["recommended"], bool):
            errors.append(where + "option %d: recommended must be true or false" % number)
        elif option.get("recommended"):
            recommended += 1
    if recommended > 1:
        errors.append(where + "at most one option can be recommended")


# ---------------------------------------------------------------- the board

class Board(object):
    """A board file: its parts, its data, and the problems found."""

    def __init__(self, path):
        self.path = path
        self.folder = os.path.dirname(os.path.abspath(path))
        text = read_text(path)
        self.head, self.raw, self.tail, self.errors = split_board(text)
        self.warnings = []
        self.data = None
        version = version_of(text)
        if version and version != VERSION:
            self.warnings.append('the board was made by tbd-board %s, this script is %s; run "board.py upgrade"'
                                 % (version, VERSION))
        if self.raw is None:
            return
        try:
            self.data = parse_json(self.raw, path, self.head.count("\n"))
        except BoardError as e:
            self.errors.extend(e.messages)
            return
        errors, warnings = validate(self.data, self.folder)
        self.errors.extend(errors)
        self.warnings.extend(warnings)

    def require_valid(self):
        if self.errors:
            raise BoardError(self.path, *self.errors)

    def log_path(self):
        return os.path.join(os.path.dirname(self.path), self.data.get("log") or "log.md")

    def render(self):
        """Add 1 to revision, set updated, check the new data, return the new file text."""
        self.data["revision"] += 1
        self.data["updated"] = today()
        errors = validate(self.data, self.folder)[0]
        if errors:
            raise BoardError(self.path, *errors)
        return self.head + dump_block(self.data) + self.tail

    def save(self):
        write_atomic(self.path, self.render())

    def find(self, key, ident, noun):
        for item in self.data[key]:
            if item["id"] == ident:
                return item
        raise BoardError(self.path, "%s %s: not found" % (noun, ident))


def load(args):
    board = Board(args.board or DEFAULT_BOARD)
    board.require_valid()
    return board


def number(ident):
    return int(ident[2:])


def next_id(prefix, items):
    """The next free ID: the highest number in the items plus 1, 3 digits or more."""
    found = [number(i["id"]) for i in items if is_str(i["id"]) and re.fullmatch(prefix + "-[0-9]+", i["id"])]
    return "%s-%03d" % (prefix, max(found + [0]) + 1)


def counts(data):
    cards = data["questions"]
    by_status = dict((s, len([c for c in cards if c["status"] == s])) for s in STATUSES)
    blocking = len([c for c in cards if c["status"] == "open" and c["priority"] == "blocking"])
    return len(cards), by_status, blocking, len(data["autodecided"])


def plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


# ---------------------------------------------------------------- the log

def clean(value):
    """One line of text: line breaks become spaces."""
    return re.sub(r"\s*[\r\n]+\s*", " ", value.strip())


def sentence(value):
    return value if value.endswith((".", "!", "?")) else value + "."


def log_entry(d_id, decision, reason, supersedes, link, source):
    parts = []
    if supersedes:
        ids = supersedes[0] if len(supersedes) == 1 else ", ".join(supersedes[:-1]) + " and " + supersedes[-1]
        parts.append("Supersedes %s." % ids)
    parts.append(sentence(decision))
    if reason:
        parts.append("Reason: " + sentence(reason))
    parts.append(link)
    if source:
        parts.append("Source: " + sentence(source))
    return "- **%s** %s %s %s %s\n" % (d_id, DASH, today(), DASH, " ".join(parts))


def next_d_id(log_text, data):
    """Highest D number in the log lines and in the board, plus 1."""
    numbers = [int(i[2:]) for i in LOG_ID_RE.findall(log_text)]
    values = [c["decision"] for c in data["questions"]] + [a.get("changed", "") for a in data["autodecided"]]
    numbers += [int(m.group()[2:]) for m in (D_RE.match(v) for v in values) if m]
    return "D-%03d" % (max(numbers + [0]) + 1)


# ---------------------------------------------------------------- commands

def cmd_init(args):
    path = args.board or os.path.join(args.dir, "board.html")
    folder = os.path.dirname(path)
    if os.path.exists(path):
        raise BoardError(path, "already exists; init does not overwrite a board")
    head, _, tail = load_template()
    alphabet = string.ascii_lowercase + string.digits
    data = {"schema": SCHEMA, "boardId": "".join(secrets.choice(alphabet) for _ in range(6)), "revision": 1,
            "title": args.title, "updated": today(), "log": args.log, "questions": [], "autodecided": []}
    errors = validate(data, os.path.abspath(folder))[0]
    if errors:
        raise BoardError(path, *errors)
    assets = os.path.join(folder, "assets")
    log_path = os.path.join(folder, args.log)
    os.makedirs(assets, exist_ok=True)
    if os.path.exists(log_path):
        log_note = "kept the existing log %s (unchanged)" % log_path
    else:
        os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
        write_atomic(log_path, LOG_HEADER)
        log_note = "created log %s" % log_path
    write_atomic(path, head + dump_block(data) + tail)
    print("ok: created board %s (id %s)" % (path, data["boardId"]))
    print("ok: %s" % log_note)
    print("ok: assets folder %s (put images here)" % assets)


def read_input(source):
    if source == "-":
        try:
            return "stdin", sys.stdin.buffer.read().decode("utf-8")
        except UnicodeDecodeError as e:
            raise BoardError("stdin", "cannot read: %s" % e)
    return source, read_text(source)


def ordered(card):
    """Known fields first, in schema order; other fields after them."""
    known = [(k, card[k]) for k in CARD_FIELDS if k in card]
    return dict(known + [(k, v) for k, v in card.items() if k not in CARD_FIELDS])


def cmd_ask(args):
    board = load(args)
    name, raw = read_input(args.card_file)
    cards = parse_json(raw, name)
    if isinstance(cards, dict):
        cards = [cards]
    if not isinstance(cards, list) or not cards or not all(isinstance(c, dict) for c in cards):
        raise BoardError(name, "expected one card object or a non-empty list of card objects")
    questions = board.data["questions"]
    done = []
    for card in cards:
        card = dict(card)
        for key, value in (("status", "open"), ("priority", "normal"), ("asked", today()), ("decision", ""),
                           ("blocks", ""), ("context", []), ("options", [])):
            card.setdefault(key, value)
        if is_str(card["context"]):
            card["context"] = [card["context"]]
        if "id" not in card:
            card["id"] = next_id("Q", questions)
        if card["status"] != "open":
            raise BoardError(name, "card %s: ask adds open cards only; status is %s" % (card["id"], q(card["status"])))
        card = ordered(card)
        index = next((i for i, c in enumerate(questions) if c["id"] == card["id"]), None)
        if index is None:
            questions.insert(0, card)
            done.append(("added", "to", card))
        elif questions[index]["status"] != "open":
            raise BoardError(board.path, "card %s: is %s (decisions are not edited; add a new card)"
                             % (card["id"], questions[index]["status"]))
        else:
            questions[index] = card
            done.append(("replaced", "in", card))
    board.save()
    for verb, prep, card in done:
        print("ok: %s %s (%s) %s %s, revision %d" % (verb, card["id"], card["priority"], prep, board.path,
                                                      board.data["revision"]))


def cmd_answer(args):
    board = load(args)
    decision, reason = clean(args.decision), clean(args.reason or "")
    if not decision:
        raise BoardError(board.path, "--decision must not be empty")
    supersedes = list(dict.fromkeys(args.supersedes or []))
    is_card = args.id.startswith("Q-")
    target = board.find("questions" if is_card else "autodecided", args.id, "card" if is_card else "entry")
    if is_card and target["status"] == "closed":
        raise BoardError(board.path, "card %s: is closed (decisions are not edited; add a new card)" % args.id)
    if is_card and target["status"] == "answered" and not supersedes:
        raise BoardError(board.path, "card %s: is already answered (%s); to change it, add --supersedes <D-id>"
                         % (args.id, target["decision"].split(":")[0]))
    log_path = board.log_path()
    log_text = read_text(log_path) if os.path.exists(log_path) else LOG_HEADER
    known = LOG_ID_RE.findall(log_text)
    missing = [s for s in supersedes if s not in known]
    if missing:
        raise BoardError(log_path, "%s not found; --supersedes needs an entry in the log" % ", ".join(missing))
    d_id = next_d_id(log_text, board.data)
    entry = log_entry(d_id, decision, reason, supersedes, ("Answers %s." if is_card else "Changes %s.") % args.id,
                      clean(args.source))
    if is_card:
        target["status"], target["decision"] = "answered", "%s: %s" % (d_id, decision)
    else:
        target["changed"] = "%s: %s" % (d_id, decision)
    new_board = board.render()
    new_log = (log_text if not log_text or log_text.endswith("\n") else log_text + "\n") + entry
    write_atomic(log_path, new_log)
    write_atomic(board.path, new_board)
    print("ok: %s answers %s in %s, revision %d" % (d_id, args.id, board.path, board.data["revision"]))
    print("ok: added %s to the end of %s" % (d_id, log_path))


def cmd_close(args):
    board = load(args)
    card = board.find("questions", args.id, "card")
    if card["status"] != "open":
        raise BoardError(board.path, "card %s: is %s; only an open card can be closed" % (args.id, card["status"]))
    card["status"], card["decision"] = "closed", clean(args.reason)
    board.save()
    print("ok: closed %s in %s, revision %d" % (args.id, board.path, board.data["revision"]))


def cmd_auto(args):
    board = load(args)
    autos = board.data["autodecided"]
    entry = {"id": next_id("A", autos), "date": today(), "title": clean(args.title),
             "decision": clean(args.decision), "reason": clean(args.reason), "changed": ""}
    autos.insert(0, entry)
    board.save()
    print("ok: added %s to %s, revision %d" % (entry["id"], board.path, board.data["revision"]))


def cmd_list(args):
    board = load(args)

    def order(card):
        if card["status"] != "open":
            return (1, 0, number(card["id"]))
        return (0, PRIORITIES.index(card["priority"]), number(card["id"]))

    cards = sorted(board.data["questions"], key=order)
    if args.open:
        cards = [c for c in cards if c["status"] == "open"]
    width = max([len(c["id"]) for c in cards] + [5])
    for c in cards:
        print("%-*s  %-8s  %-8s  %s" % (width, c["id"], c["priority"], c["status"], c["title"]))
    total, by_status, blocking, autos = counts(board.data)
    print("%s: %d open (%d blocking), %d answered, %d closed; %d decided for you."
          % (plural(total, "card"), by_status["open"], blocking, by_status["answered"], by_status["closed"], autos))


def warn(path, message):
    print("warning: %s: %s" % (path, message), file=sys.stderr)


def cmd_check(args):
    board = Board(args.board or DEFAULT_BOARD)
    for message in board.warnings:
        warn(board.path, message)
    board.require_valid()
    answered = [c for c in board.data["questions"] if c["status"] == "answered"]
    if answered:
        log_path = board.log_path()
        try:
            known = LOG_ID_RE.findall(read_text(log_path))
        except BoardError as e:
            warn(board.path, "decision log %s: %s" % (log_path, e.messages[0]))
        else:
            for card in answered:
                d_id = D_RE.match(card["decision"]).group()
                if d_id not in known:
                    warn(board.path, "card %s: %s not found in %s" % (card["id"], d_id, log_path))
    total, by_status, _, autos = counts(board.data)
    print("ok: %s: %s (%d open), %d decided for you, revision %d"
          % (board.path, plural(total, "card"), by_status["open"], autos, board.data["revision"]))


def cmd_upgrade(args):
    path = args.board or DEFAULT_BOARD
    text = read_text(path)
    head, raw, _, problems = split_board(text)
    if raw is None:
        raise BoardError(path, *problems)
    data = parse_json(raw, path, head.count("\n"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        schema = data.get("schema") if isinstance(data, dict) else None
        if is_int(schema) and schema > SCHEMA:
            raise BoardError(path, "schema %d was made by a newer version; upgrade the skill" % schema)
        raise BoardError(path, "schema must be the integer %d" % SCHEMA)
    new_head, _, new_tail = load_template()
    new_text = new_head + raw + new_tail
    old_version = version_of(text)
    if new_text == text:
        print("ok: %s is up to date (tbd-board %s)" % (path, VERSION))
        return
    write_atomic(path, new_text)
    print("ok: upgraded %s from tbd-board %s to tbd-board %s" % (path, old_version, VERSION))


# ---------------------------------------------------------------- command line

def d_id_type(value):
    if not D_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("%s is not a decision ID like D-012" % q(value))
    return value


def answer_id_type(value):
    if not (Q_RE.fullmatch(value) or A_RE.fullmatch(value)):
        raise argparse.ArgumentTypeError("%s is not an ID like Q-007 or A-013" % q(value))
    return value


def card_id_type(value):
    if not Q_RE.fullmatch(value):
        raise argparse.ArgumentTypeError("%s is not a card ID like Q-007" % q(value))
    return value


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--board", metavar="PATH", help="board file (default: %s)" % DEFAULT_BOARD)
    parser = argparse.ArgumentParser(prog="board.py", description="Keep a TBD Board and its decision log.")
    parser.add_argument("--version", action="version", version="board.py " + VERSION)
    sub = parser.add_subparsers(dest="command", metavar="command")
    sub.required = True

    def command(name, func, help_text):
        p = sub.add_parser(name, parents=[common], help=help_text, description=help_text)
        p.set_defaults(func=func)
        return p

    p = command("init", cmd_init, "make a new board and log")
    p.add_argument("--dir", default="docs/decisions", help="folder of the new board (ignored with --board)")
    p.add_argument("--title", default="Decisions", help="board title")
    p.add_argument("--log", default="log.md", help="log path, relative to the board folder")
    p = command("ask", cmd_ask, "add or replace open cards from a JSON file")
    p.add_argument("card_file", metavar="CARD.json", help="a card object or a list of card objects; - reads stdin")
    p = command("answer", cmd_answer, "record a decision in the log and on the board")
    p.add_argument("id", type=answer_id_type, metavar="ID", help="a card (Q-007) or a decided-for-you entry (A-013)")
    p.add_argument("--decision", required=True)
    p.add_argument("--reason")
    p.add_argument("--supersedes", nargs="+", action="extend", type=d_id_type, metavar="D-ID",
                   help="decisions that this one replaces")
    p.add_argument("--source", default="user")
    p = command("close", cmd_close, "close an open card without a decision")
    p.add_argument("id", type=card_id_type, metavar="Q-ID")
    p.add_argument("--reason", required=True)
    p = command("auto", cmd_auto, "add a decided-for-you entry")
    for name in ("title", "decision", "reason"):
        p.add_argument("--" + name, required=True)
    p = command("list", cmd_list, "list the cards")
    p.add_argument("--open", action="store_true", help="only open cards")
    command("check", cmd_check, "check the board and the log")
    command("upgrade", cmd_upgrade, "put the board data in this version's page")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except BoardError as e:
        for message in e.messages:
            print("error: %s: %s" % (e.path, message), file=sys.stderr)
        return 1
    except OSError as e:
        print("error: %s: %s" % (e.filename or args.board or DEFAULT_BOARD, e.strerror or e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    sys.exit(main())
