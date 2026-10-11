"""Tests for skills/tbd-board/scripts/board.py.

Run from the repository root: python3 -m unittest discover -s tests
"""
import contextlib
import copy
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "skills", "tbd-board", "scripts", "board.py")
TEMPLATE = os.path.join(ROOT, "skills", "tbd-board", "assets", "board-template.html")
HEARTH = os.path.join(ROOT, "tests", "fixtures", "hearth.json")
OPEN_TAG = '<script type="application/json" id="tbd-board-data">'
EM = "\u2014"

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(SCRIPT))
import board  # noqa: E402


def read(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))


def split(text):
    """(before, raw, after): the page around the data block, found without board.py."""
    i = text.index(OPEN_TAG) + len(OPEN_TAG)
    j = text.index("</script>", i)
    return text[:i], text[i:j], text[j:]


def hearth():
    with open(HEARTH, encoding="utf-8") as f:
        return json.load(f)


class BoardTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = os.path.realpath(tmp.name)
        self.folder = os.path.join(self.dir, "docs", "decisions")
        self.path = os.path.join(self.folder, "board.html")
        self.log = os.path.join(self.folder, "log.md")
        self.today = board.today()

    def cli(self, *args, stdin=None, code=0):
        source = {"input": stdin} if stdin is not None else {"stdin": subprocess.DEVNULL}
        proc = subprocess.run([sys.executable, SCRIPT] + list(args), cwd=self.dir, capture_output=True, text=True,
                              encoding="utf-8", **source)
        self.assertNotIn("Traceback", proc.stderr)
        if code is not None:
            self.assertEqual(proc.returncode, code, "stdout: %s\nstderr: %s" % (proc.stdout, proc.stderr))
        return proc

    def init(self, *args):
        return self.cli("init", *args)

    def ask(self, *cards, code=0):
        return self.cli("ask", "-", stdin=json.dumps(list(cards)), code=code)

    def data(self):
        return json.loads(split(read(self.path))[1])

    def card(self, cid):
        return [c for c in self.data()["questions"] if c["id"] == cid][0]

    def write_board(self, data):
        head, _, tail = board.load_template()
        write(self.path, head + board.dump_block(data) + tail)

    def write_raw_block(self, raw):
        head, _, tail = board.load_template()
        write(self.path, head + raw + tail)

    def hearth_board(self, with_log=True):
        data = hearth()
        for card in data["questions"]:
            for image in card.get("images", []):
                write(os.path.join(self.folder, image["src"]), "\x89PNG\r\n\x1a\n")
        self.write_board(data)
        if with_log:
            write(self.log, board.LOG_HEADER + "- **D-012** %s 2026-10-10 %s Push notifications. Answers Q-003.\n" % (EM, EM))
        return data

    def log_lines(self):
        return [line for line in read(self.log).splitlines() if line.startswith("- **D-")]


class InitTest(BoardTestCase):
    def test_init_makes_board_log_and_assets(self):
        proc = self.init()
        data = self.data()
        self.assertRegex(data["boardId"], r"^[a-z0-9]{6}$")
        self.assertEqual((data["schema"], data["revision"], data["title"], data["updated"], data["log"]),
                         (1, 1, "Decisions", self.today, "log.md"))
        self.assertEqual((data["questions"], data["autodecided"]), ([], []))
        self.assertEqual(read(self.log), board.LOG_HEADER)
        self.assertTrue(read(self.log).startswith("# Decision log\n\nThis file records each decision."))
        self.assertIn("Format: `ID %s date %s decision. Reason. Links. Source.`\n\n" % (EM, EM), read(self.log))
        self.assertTrue(os.path.isdir(os.path.join(self.folder, "assets")))
        for shown in ("docs/decisions/board.html", "docs/decisions/log.md", "docs/decisions/assets"):
            self.assertIn(shown, proc.stdout)
        self.assertEqual(self.cli("check").returncode, 0)

    def test_init_options_and_log_outside_the_board_folder(self):
        self.init("--dir", "other/place", "--title", "Hearth", "--log", "../decisions.md")
        path = os.path.join(self.dir, "other", "place", "board.html")
        data = json.loads(split(read(path))[1])
        self.assertEqual((data["title"], data["log"]), ("Hearth", "../decisions.md"))
        self.assertTrue(os.path.isfile(os.path.join(self.dir, "other", "decisions.md")))

    def test_init_uses_the_template_renderer_unchanged(self):
        self.init()
        template = split(read(TEMPLATE))
        page = split(read(self.path))
        self.assertEqual((page[0], page[2]), (template[0], template[2]))

    def test_init_refuses_to_overwrite_a_board(self):
        self.init()
        before = read(self.path)
        proc = self.cli("init", code=1)
        self.assertIn("error: docs/decisions/board.html: already exists", proc.stderr)
        self.assertEqual(read(self.path), before)

    def test_init_keeps_an_existing_log(self):
        write(self.log, "# My log\n\n- **D-007** old entry\n")
        proc = self.init()
        self.assertEqual(read(self.log), "# My log\n\n- **D-007** old entry\n")
        self.assertIn("kept the existing log", proc.stdout)


class AskTest(BoardTestCase):
    def setUp(self):
        super().setUp()
        self.init()

    def test_ask_fills_defaults_and_first_id(self):
        proc = self.ask({"title": "T1", "context": "one paragraph"})
        card = self.data()["questions"][0]
        self.assertEqual(card, {"id": "Q-001", "title": "T1", "priority": "normal", "status": "open", "asked": self.today,
                                "blocks": "", "context": ["one paragraph"], "options": [], "decision": ""})
        self.assertEqual(proc.stdout, "ok: added Q-001 (normal) to docs/decisions/board.html, revision 2\n")

    def test_ask_list_adds_ids_and_puts_new_cards_first(self):
        self.ask({"title": "a", "priority": "low"}, {"title": "b", "priority": "blocking"}, {"id": "Q-020", "title": "c"})
        self.assertEqual([c["id"] for c in self.data()["questions"]], ["Q-020", "Q-002", "Q-001"])
        proc = self.ask({"title": "d"})
        self.assertIn("added Q-021 (normal)", proc.stdout)
        self.assertEqual(self.data()["questions"][0]["id"], "Q-021")

    def test_ask_reads_a_file_and_a_single_object(self):
        write(os.path.join(self.dir, "card.json"), json.dumps({"title": "from file"}))
        self.cli("ask", "card.json")
        self.assertEqual(self.data()["questions"][0]["title"], "from file")

    def test_ask_replaces_an_open_card_in_place(self):
        self.ask({"title": "a"}, {"title": "b"})
        proc = self.ask({"id": "Q-001", "title": "a2", "priority": "urgent"})
        self.assertIn("replaced Q-001 (urgent) in docs/decisions/board.html", proc.stdout)
        cards = self.data()["questions"]
        self.assertEqual([(c["id"], c["title"]) for c in cards], [("Q-002", "b"), ("Q-001", "a2")])

    def test_ask_refuses_to_replace_answered_and_closed_cards(self):
        self.ask({"title": "a"}, {"title": "b"})
        self.cli("answer", "Q-001", "--decision", "Yes")
        self.cli("close", "Q-002", "--reason", "No longer needed")
        for cid in ("Q-001", "Q-002"):
            before = read(self.path)
            proc = self.ask({"id": cid, "title": "again"}, code=1)
            self.assertIn("card %s: is " % cid, proc.stderr)
            self.assertIn("decisions are not edited; add a new card", proc.stderr)
            self.assertEqual(read(self.path), before)

    def test_ask_refuses_a_card_that_is_not_open(self):
        proc = self.ask({"title": "x", "status": "answered", "decision": "D-001: y"}, code=1)
        self.assertIn("ask adds open cards only", proc.stderr)

    def test_ask_writes_nothing_when_one_card_is_bad(self):
        before = read(self.path)
        proc = self.ask({"title": "good"}, {"title": "bad", "priority": "high"}, code=1)
        self.assertIn('error: docs/decisions/board.html: card Q-002: priority "high" must be one of '
                      "blocking, urgent, normal, low", proc.stderr)
        self.assertEqual(read(self.path), before)

    def test_ask_checks_image_files(self):
        before = read(self.path)
        proc = self.ask({"title": "x", "images": [{"src": "assets/a.png", "caption": "A"}]}, code=1)
        self.assertIn("card Q-001: image not found: assets/a.png", proc.stderr)
        write(os.path.join(self.folder, "assets", "a.png"), "x")
        self.ask({"title": "x", "images": [{"src": "assets/a.png", "caption": "A"}]})
        self.assertNotEqual(read(self.path), before)

    def test_ask_bad_input(self):
        proc = self.cli("ask", "-", stdin='{"title": ', code=1)
        self.assertRegex(proc.stderr, r"error: stdin: invalid JSON: .* at line \d+, column \d+")
        self.assertIn("file not found", self.cli("ask", "missing.json", code=1).stderr)
        self.assertIn("expected one card object", self.cli("ask", "-", stdin="[]", code=1).stderr)
        self.assertIn("expected one card object", self.cli("ask", "-", stdin="[1]", code=1).stderr)

    def test_unknown_card_fields_are_kept(self):
        self.ask({"title": "x", "notes": "agent note"})
        self.cli("auto", "--title", "t", "--decision", "d", "--reason", "r")
        self.assertEqual(self.card("Q-001")["notes"], "agent note")


class AnswerTest(BoardTestCase):
    def setUp(self):
        super().setUp()
        self.init()
        self.ask({"title": "Sync", "priority": "blocking"}, {"title": "Icon"})

    def test_answer_card_writes_the_exact_log_line(self):
        proc = self.cli("answer", "Q-001", "--decision", "A. Local-first", "--reason", "Offline use matters!")
        self.assertEqual(self.log_lines(), ["- **D-001** %s %s %s A. Local-first. Reason: Offline use matters! "
                                            "Answers Q-001. Source: user." % (EM, self.today, EM)])
        self.assertTrue(read(self.log).endswith("Source: user.\n"))
        card = self.card("Q-001")
        self.assertEqual((card["status"], card["decision"]), ("answered", "D-001: A. Local-first"))
        self.assertIn("ok: D-001 answers Q-001 in docs/decisions/board.html, revision 3", proc.stdout)

    def test_answer_without_reason_and_with_another_source(self):
        self.cli("answer", "Q-002", "--decision", "Kettle.\nSecond line", "--source", "the designer")
        self.assertEqual(self.log_lines(), ["- **D-001** %s %s %s Kettle. Second line. Answers Q-002. Source: the designer."
                                            % (EM, self.today, EM)])

    def test_answer_writes_the_log_before_the_board(self):
        with mock.patch.object(board, "write_atomic", wraps=board.write_atomic) as spy:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(board.main(["answer", "Q-001", "--decision", "x", "--board", self.path]), 0)
        self.assertEqual([c[0][0] for c in spy.call_args_list], [self.log, self.path])

    def test_answer_answered_card_needs_supersedes(self):
        self.cli("answer", "Q-001", "--decision", "First")
        proc = self.cli("answer", "Q-001", "--decision", "Second", code=1)
        self.assertIn("card Q-001: is already answered (D-001)", proc.stderr)
        self.cli("answer", "Q-001", "--decision", "Second", "--supersedes", "D-001")
        self.assertEqual(self.log_lines()[1], "- **D-002** %s %s %s Supersedes D-001. Second. Answers Q-001. Source: user."
                         % (EM, self.today, EM))
        self.assertEqual(self.card("Q-001")["decision"], "D-002: Second")

    def test_answer_several_supersedes(self):
        self.cli("answer", "Q-001", "--decision", "One")
        self.cli("answer", "Q-002", "--decision", "Two")
        self.cli("answer", "Q-001", "--decision", "Three", "--supersedes", "D-001", "D-002")
        self.assertIn("%s Supersedes D-001 and D-002. Three." % EM, self.log_lines()[2])
        self.cli("answer", "Q-001", "--decision", "Four", "--supersedes", "D-001", "--supersedes", "D-002", "D-003")
        self.assertIn("%s Supersedes D-001, D-002 and D-003. Four." % EM, self.log_lines()[3])

    def test_answer_unknown_supersedes_changes_nothing(self):
        self.cli("answer", "Q-001", "--decision", "First")
        before = (read(self.path), read(self.log))
        proc = self.cli("answer", "Q-002", "--decision", "x", "--supersedes", "D-099", code=1)
        self.assertIn("error: docs/decisions/log.md: D-099 not found", proc.stderr)
        self.assertEqual((read(self.path), read(self.log)), before)

    def test_answer_refuses_a_closed_card(self):
        self.cli("close", "Q-002", "--reason", "Dropped")
        before = (read(self.path), read(self.log))
        proc = self.cli("answer", "Q-002", "--decision", "x", "--supersedes", "D-001", code=1)
        self.assertIn("card Q-002: is closed", proc.stderr)
        self.assertEqual((read(self.path), read(self.log)), before)

    def test_answer_decided_for_you_entry(self):
        self.cli("auto", "--title", "Font", "--decision", "System font", "--reason", "No license")
        proc = self.cli("answer", "A-001", "--decision", "Use Inter", "--reason", "Brand")
        self.assertEqual(self.log_lines(), ["- **D-001** %s %s %s Use Inter. Reason: Brand. Changes A-001. Source: user."
                                            % (EM, self.today, EM)])
        entry = self.data()["autodecided"][0]
        self.assertEqual((entry["id"], entry["decision"], entry["changed"]), ("A-001", "System font", "D-001: Use Inter"))
        self.assertIn("D-001 answers A-001", proc.stdout)

    def test_answer_unknown_id_and_bad_usage(self):
        self.assertIn("error: docs/decisions/board.html: card Q-099: not found",
                      self.cli("answer", "Q-099", "--decision", "x", code=1).stderr)
        self.assertIn("entry A-099: not found", self.cli("answer", "A-099", "--decision", "x", code=1).stderr)
        self.assertIn("--decision", self.cli("answer", "Q-001", code=2).stderr)
        self.assertIn("not an ID", self.cli("answer", "X-1", "--decision", "x", code=2).stderr)
        self.assertIn("not a decision ID", self.cli("answer", "Q-001", "--decision", "x", "--supersedes", "foo", code=2).stderr)
        self.assertIn("must not be empty", self.cli("answer", "Q-001", "--decision", "  ", code=1).stderr)

    def test_next_d_id_follows_an_existing_log_and_the_board(self):
        write(self.log, "# Project decisions\n\n* D-040 old\n## D-041 older\n1. text\n- **D-009** mid\n")
        self.cli("answer", "Q-001", "--decision", "x")
        self.assertEqual(self.card("Q-001")["decision"], "D-042: x")
        self.ask({"title": "third"})
        data = self.data()
        [c for c in data["questions"] if c["id"] == "Q-002"][0].update(status="answered", decision="D-100: from the board")
        self.write_board(data)
        self.cli("answer", "Q-003", "--decision", "y")
        self.assertEqual(self.card("Q-003")["decision"], "D-101: y")

    def test_answer_adds_a_missing_final_newline_and_creates_a_missing_log(self):
        write(self.log, "# Log\n\n- **D-001** old")
        self.cli("answer", "Q-001", "--decision", "x")
        self.assertEqual(read(self.log).splitlines()[2], "- **D-001** old")
        self.assertTrue(read(self.log).splitlines()[3].startswith("- **D-002**"))
        os.unlink(self.log)
        self.cli("answer", "Q-002", "--decision", "y")
        self.assertTrue(read(self.log).startswith("# Decision log"))
        self.assertEqual(len(self.log_lines()), 1)


def hearth_data_without_images():
    data = hearth()
    for card in data["questions"]:
        card.pop("images", None)
    return data


class CloseAutoListTest(BoardTestCase):
    def setUp(self):
        super().setUp()
        self.init()

    def test_close(self):
        self.ask({"title": "x"})
        proc = self.cli("close", "Q-001", "--reason", "Not needed any more")
        card = self.card("Q-001")
        self.assertEqual((card["status"], card["decision"]), ("closed", "Not needed any more"))
        self.assertEqual(proc.stdout, "ok: closed Q-001 in docs/decisions/board.html, revision 3\n")
        self.assertIn("card Q-001: is closed; only an open card can be closed", self.cli("close", "Q-001", "--reason", "x", code=1).stderr)
        self.assertIn("card Q-005: not found", self.cli("close", "Q-005", "--reason", "x", code=1).stderr)

    def test_auto_ids_and_order(self):
        first = self.cli("auto", "--title", "One", "--decision", "d1", "--reason", "r1")
        self.cli("auto", "--title", "Two", "--decision", "d2", "--reason", "r2")
        autos = self.data()["autodecided"]
        self.assertEqual([a["id"] for a in autos], ["A-002", "A-001"])
        self.assertEqual(autos[0], {"id": "A-002", "date": self.today, "title": "Two", "decision": "d2", "reason": "r2", "changed": ""})
        self.assertEqual(first.stdout, "ok: added A-001 to docs/decisions/board.html, revision 2\n")

    def test_auto_continues_after_the_highest_id(self):
        self.write_board(hearth_data_without_images())
        self.cli("auto", "--title", "t", "--decision", "d", "--reason", "r")
        self.assertEqual(self.data()["autodecided"][0]["id"], "A-015")

    def test_list_order_and_summary(self):
        self.ask({"title": "low one", "priority": "low"}, {"title": "normal one"}, {"title": "blocking one", "priority": "blocking"},
                 {"title": "urgent one", "priority": "urgent"}, {"title": "normal two"}, {"title": "to answer", "priority": "blocking"})
        self.cli("answer", "Q-006", "--decision", "yes")
        self.cli("close", "Q-001", "--reason", "no")
        self.cli("auto", "--title", "t", "--decision", "d", "--reason", "r")
        self.assertEqual(self.cli("list").stdout.splitlines(), [
            "Q-003  blocking  open      blocking one",
            "Q-004  urgent    open      urgent one",
            "Q-002  normal    open      normal one",
            "Q-005  normal    open      normal two",
            "Q-001  low       closed    low one",
            "Q-006  blocking  answered  to answer",
            "6 cards: 4 open (1 blocking), 1 answered, 1 closed; 1 decided for you."])
        open_lines = self.cli("list", "--open").stdout.splitlines()
        self.assertEqual([line.split()[0] for line in open_lines[:-1]], ["Q-003", "Q-004", "Q-002", "Q-005"])

    def test_list_matches_the_demo_board(self):
        self.hearth_board()
        lines = self.cli("list").stdout.splitlines()
        self.assertEqual(lines[0], "Q-007  blocking  open      Sync: local-first, or a hosted database?")
        self.assertEqual([l.split()[0] for l in lines[:-1]], ["Q-007", "Q-006", "Q-005", "Q-004", "Q-003"])
        self.assertEqual(lines[-1], "5 cards: 4 open (1 blocking), 1 answered, 0 closed; 3 decided for you.")
        self.assertEqual(self.cli("list", "--open").stdout.splitlines()[-2].split()[0], "Q-004")

    def test_list_is_read_only(self):
        self.ask({"title": "x"})
        before = read(self.path)
        self.cli("list")
        self.cli("check")
        self.assertEqual(read(self.path), before)


class CheckTest(BoardTestCase):
    def test_check_demo_board(self):
        self.hearth_board()
        proc = self.cli("check")
        self.assertEqual(proc.stdout, "ok: docs/decisions/board.html: 5 cards (4 open), 3 decided for you, revision 14\n")
        self.assertEqual(proc.stderr, "")

    def test_check_warns_about_the_log_but_passes(self):
        self.hearth_board(with_log=False)
        proc = self.cli("check")
        self.assertIn("warning: docs/decisions/board.html: decision log docs/decisions/log.md: file not found", proc.stderr)
        write(self.log, "# Log\n\n- **D-011** other\n")
        self.assertIn("card Q-003: D-012 not found in docs/decisions/log.md", self.cli("check").stderr)

    def test_check_warns_about_unknown_fields(self):
        data = hearth_data_without_images()
        data["questions"][0]["notes"] = "agent note"
        self.write_board(data)
        write(self.log, "- **D-012** x\n")
        proc = self.cli("check")
        self.assertIn('warning: docs/decisions/board.html: card Q-007: unknown field "notes"', proc.stderr)

    def test_check_reports_bad_values_and_collects_all_problems(self):
        data = hearth_data_without_images()
        data["questions"][0]["priority"] = "high"
        data["questions"][1]["id"] = "Q-007"
        data["boardId"] = "BAD"
        self.write_board(data)
        proc = self.cli("check", code=1)
        lines = proc.stderr.splitlines()
        self.assertIn('error: docs/decisions/board.html: card Q-007: priority "high" must be one of blocking, urgent, normal, low', lines)
        self.assertIn("error: docs/decisions/board.html: card Q-007: duplicate id", lines)
        self.assertIn("error: docs/decisions/board.html: boardId must be 6 to 12 characters from a-z and 0-9", lines)
        self.assertTrue(all(l.startswith("error: ") for l in lines))

    def test_check_javascript_and_data_image_sources(self):
        for src in ("javascript:alert(1)", "data:image/png;base64,AAAA"):
            data = hearth_data_without_images()
            data["questions"][0]["images"] = [{"src": src, "caption": "x"}]
            self.write_board(data)
            proc = self.cli("check", code=1)
            self.assertIn("card Q-007: image src %s is not allowed" % json.dumps(src), proc.stderr)

    def test_check_missing_image_file(self):
        self.hearth_board()
        os.unlink(os.path.join(self.folder, "assets", "icon-kettle.png"))
        proc = self.cli("check", code=1)
        self.assertIn("card Q-005: image not found: assets/icon-kettle.png", proc.stderr)

    def test_check_bad_json_gives_line_and_column(self):
        self.init()
        broken = read(self.path).replace('"schema": 1,', '"schema": 1 "oops",', 1)
        write(self.path, broken)
        line = broken.count("\n", 0, broken.index('"oops"')) + 1
        proc = self.cli("check", code=1)
        self.assertIn("error: docs/decisions/board.html: invalid JSON: Expecting ',' delimiter at line %d, column " % line, proc.stderr)
        self.assertRegex(proc.stderr, r"line \d+, column \d+")

    def test_check_file_structure(self):
        self.init()
        text = read(self.path)
        cases = [
            (text.replace(OPEN_TAG, "", 1), "occurs 0 times"),
            (text.replace("</script>", "</scrip>"), "no closing"),
            (text + OPEN_TAG, "occurs 2 times"),
            (text.replace('<script id="tbd-board-renderer">', "<script>"), "renderer is missing"),
            (text.replace('<meta name="generator" content="tbd-board ', '<meta name="x" content="'), "renderer is missing"),
        ]
        for broken, expected in cases:
            write(self.path, broken)
            self.assertIn(expected, self.cli("check", code=1).stderr)
        before, raw, after = split(text)
        for evil in ("</SCRIPT >", "<!-- x -->"):
            write(self.path, before + raw.replace('"Decisions"', '"a %s b"' % evil) + after)
            self.assertIn("data block: contains", self.cli("check", code=1).stderr)

    def test_check_missing_file(self):
        proc = self.cli("check", "--board", "nothing.html", code=1)
        self.assertEqual(proc.stderr, "error: nothing.html: file not found\n")

    def test_top_level_must_be_an_object(self):
        self.init()
        self.write_raw_block("\n[1, 2]\n")
        self.assertIn("must be a JSON object", self.cli("check", code=1).stderr)

    def test_newer_schema_is_refused(self):
        self.init()
        data = self.data()
        data["schema"] = 2
        self.write_board(data)
        before = read(self.path)
        for command in (["check"], ["list"], ["ask", "-"], ["close", "Q-001", "--reason", "x"], ["upgrade"]):
            proc = self.cli(*command, stdin="[]", code=1)
            self.assertIn("schema 2 was made by a newer version; upgrade the skill", proc.stderr)
        self.assertEqual(read(self.path), before)


class ValidateTest(unittest.TestCase):
    """The schema rules, called in process on the demo data."""

    def errors(self, mutate):
        data = hearth()
        with tempfile.TemporaryDirectory() as folder:
            for card in data["questions"]:  # the demo images exist; the mutation comes after
                for image in card.get("images", []):
                    write(os.path.join(folder, image["src"]), "x")
            mutate(data)
            return board.validate(data, folder)[0]

    def assert_error(self, mutate, expected):
        errors = self.errors(mutate)
        self.assertTrue(any(expected in e for e in errors), "%r not in %r" % (expected, errors))

    def test_demo_data_is_valid(self):
        self.assertEqual(self.errors(lambda d: None), [])

    def test_top_level_rules(self):
        self.assert_error(lambda d: d.update(schema="1"), "schema must be")
        self.assert_error(lambda d: d.update(revision=-1), "revision must be")
        self.assert_error(lambda d: d.update(revision=True), "revision must be")
        self.assert_error(lambda d: d.update(title=" "), "title must be a non-empty string")
        self.assert_error(lambda d: d.update(updated="2026-02-30"), "updated must be a date")
        self.assert_error(lambda d: d.update(updated=""), "updated must be a date")
        self.assert_error(lambda d: d.update(boardId=""), "boardId must be")
        self.assert_error(lambda d: d.update(boardId="abcde"), "boardId must be")
        self.assert_error(lambda d: d.update(log="/etc/log.md"), "relative path")
        self.assert_error(lambda d: d.update(questions={}), "questions must be a list")
        self.assert_error(lambda d: d.pop("autodecided"), "autodecided must be a list")

    def test_card_rules(self):
        self.assert_error(lambda d: d["questions"][0].update(id="Q-7"), "id must be Q-")
        self.assert_error(lambda d: d["questions"][0].update(title=""), "title must be a non-empty string")
        self.assert_error(lambda d: d["questions"][0].update(status="done"), 'status "done" must be one of')
        self.assert_error(lambda d: d["questions"][0].update(asked="yesterday"), "asked must be a date")
        self.assert_error(lambda d: d["questions"][0].update(context="text"), "context must be a list of strings")
        self.assert_error(lambda d: d["questions"][0].pop("options"), "options must be a list")
        self.assert_error(lambda d: d["questions"][0].update(area=3), "area must be a string")
        self.assert_error(lambda d: d["questions"][1].update(id="Q-007"), "duplicate id")

    def test_decision_rules_per_status(self):
        self.assert_error(lambda d: d["questions"][0].update(decision="x"), "must be empty while the card is open")
        self.assert_error(lambda d: d["questions"][4].update(decision="D-12 yes"), "must start with")
        self.assert_error(lambda d: d["questions"][4].update(status="closed", decision=" "), "must give the reason")
        self.assertEqual(self.errors(lambda d: d["questions"][4].update(status="closed", decision="Dropped")), [])

    def test_option_rules(self):
        option = lambda n: {"label": "L%d" % n}
        self.assert_error(lambda d: d["questions"][0].update(options=[option(i) for i in range(7)]), "6 is the most")
        self.assert_error(lambda d: d["questions"][0].update(options=[option(1)] * 2), "duplicate label")
        self.assert_error(lambda d: d["questions"][0].update(options=[{"label": " "}]), "label must be a non-empty string")
        self.assert_error(lambda d: d["questions"][0].update(options=[{"label": "a", "recommended": True}, {"label": "b", "recommended": True}]),
                          "at most one option can be recommended")
        self.assert_error(lambda d: d["questions"][0].update(options=[{"label": "a", "recommended": "yes"}]), "recommended must be")
        self.assertEqual(self.errors(lambda d: d["questions"][0].update(options=[option(i) for i in range(6)])), [])
        self.assertEqual(self.errors(lambda d: d["questions"][0].update(options=[])), [])

    def test_image_rules(self):
        bad = ["javascript:alert(1)", "JavaScript:alert(1)", "data:image/png;base64,AA", "http://example.com/a.png",
               "file:///etc/passwd", "//host/a.png", "/abs/a.png", "\\abs\\a.png", "assets\\a.png", " javascript:x",
               "java\tscript:x", "HTTPS://example.com/a.png", "C:/a.png"]
        for src in bad:
            self.assert_error(lambda d: d["questions"][0].update(images=[{"src": src, "caption": "c"}]), "is not allowed")
        self.assert_error(lambda d: d["questions"][0].update(images=[{"src": "assets/none.png"}]), "image not found: assets/none.png")
        self.assert_error(lambda d: d["questions"][0].update(images=[{"caption": "c"}]), "needs a src")
        self.assertEqual(self.errors(lambda d: d["questions"][0].update(images=[{"src": "https://example.com/a.png", "caption": "c"}])), [])

    def test_autodecided_rules(self):
        self.assert_error(lambda d: d["autodecided"][0].update(id="A-1"), "id must be A-")
        self.assert_error(lambda d: d["autodecided"][1].update(id="A-014"), "duplicate id")
        self.assert_error(lambda d: d["autodecided"][0].update(date="2026-13-01"), "date must be a date")
        self.assert_error(lambda d: d["autodecided"][0].update(reason=""), "reason must be a non-empty string")
        self.assert_error(lambda d: d["autodecided"][0].pop("title"), "title is required")
        self.assert_error(lambda d: d["autodecided"][0].update(changed="yes"), "changed must be")
        self.assertEqual(self.errors(lambda d: d["autodecided"][0].update(changed="D-020: Other")), [])

    def test_unknown_fields_are_warnings(self):
        data = hearth()
        data["extra"] = 1
        data["autodecided"][0]["note"] = "x"
        errors, warnings = board.validate(data, tempfile.gettempdir())
        self.assertEqual(sorted(warnings), ['entry A-014: unknown field "note"', 'unknown field "extra"'])


class WriteSafetyTest(BoardTestCase):
    def setUp(self):
        super().setUp()
        self.init()

    def test_escape_of_script_end_and_comment_start(self):
        title = "</script><script>alert(1)</script>"
        self.ask({"title": title, "context": ["<!-- x", "</SCRIPT>", "back\\slash </ and <!--"], "recommendation": "<!--"})
        text = read(self.path)
        raw = split(text)[1]
        self.assertNotIn("</script", raw.lower())
        self.assertNotIn("<!--", raw)
        self.assertEqual(text.lower().count("</script>"), read(TEMPLATE).lower().count("</script>"))
        card = self.data()["questions"][0]
        self.assertEqual(card["title"], title)
        self.assertEqual(card["context"], ["<!-- x", "</SCRIPT>", "back\\slash </ and <!--"])
        self.cli("close", "Q-001", "--reason", "<!-- </script>")
        self.assertEqual(self.card("Q-001")["decision"], "<!-- </script>")
        self.assertEqual(self.cli("check").returncode, 0)

    def test_non_ascii_text_is_kept_as_it_is(self):
        self.ask({"title": "Caf\u00e9 \u2014 \u65e5\u672c\u8a9e"})
        self.assertIn("Caf\u00e9 \u2014 \u65e5\u672c\u8a9e", read(self.path))

    def test_atomic_write_failure_keeps_the_old_file_and_leaves_no_temp_file(self):
        write(os.path.join(self.dir, "card.json"), json.dumps({"title": "x"}))
        before = read(self.path)
        listing = sorted(os.listdir(self.folder))
        err = io.StringIO()
        with mock.patch.object(os, "replace", side_effect=OSError("disk full")), contextlib.redirect_stderr(err):
            code = board.main(["ask", os.path.join(self.dir, "card.json"), "--board", self.path])
        self.assertEqual(code, 1)
        self.assertIn("error: %s: cannot write: disk full" % self.path, err.getvalue())
        self.assertEqual(read(self.path), before)
        self.assertEqual(sorted(os.listdir(self.folder)), listing)

    def test_a_failed_log_write_keeps_the_board_unchanged(self):
        self.ask({"title": "x"})
        before = (read(self.path), read(self.log))
        with mock.patch.object(os, "replace", side_effect=OSError("disk full")), contextlib.redirect_stderr(io.StringIO()):
            code = board.main(["answer", "Q-001", "--decision", "y", "--board", self.path])
        self.assertEqual(code, 1)
        self.assertEqual((read(self.path), read(self.log)), before)

    def test_write_keeps_the_file_mode(self):
        os.chmod(self.path, 0o640)
        self.ask({"title": "x"})
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o640)

    def test_revision_and_updated_change_on_each_write(self):
        steps = [
            ("ask", lambda: self.ask({"title": "a"}, {"title": "b"})),
            ("close", lambda: self.cli("close", "Q-001", "--reason", "x")),
            ("auto", lambda: self.cli("auto", "--title", "t", "--decision", "d", "--reason", "r")),
            ("answer", lambda: self.cli("answer", "Q-002", "--decision", "y")),
        ]
        revision = self.data()["revision"]
        for name, step in steps:
            data = self.data()
            data["updated"] = "2000-01-01"
            self.write_board(data)
            step()
            revision += 1
            now = self.data()
            self.assertEqual((now["revision"], now["updated"]), (revision, self.today), name)

    def test_failed_commands_do_not_change_revision(self):
        before = read(self.path)
        self.cli("close", "Q-001", "--reason", "x", code=1)
        self.ask({"title": "x", "priority": "nope"}, code=1)
        self.assertEqual(read(self.path), before)

    def test_renderer_is_byte_for_byte_the_same_after_writes(self):
        before = split(read(self.path))
        self.ask({"title": "a"})
        self.cli("answer", "Q-001", "--decision", "x")
        self.cli("auto", "--title", "t", "--decision", "d", "--reason", "r")
        after = split(read(self.path))
        self.assertEqual((after[0], after[2]), (before[0], before[2]))
        self.assertNotEqual(after[1], before[1])

    def test_data_block_format(self):
        raw = split(read(self.path))[1]
        self.assertTrue(raw.startswith("\n{\n  \"schema\": 1,"))
        self.assertTrue(raw.endswith("}\n"))


class UpgradeTest(BoardTestCase):
    def old_board(self, raw):
        head, _, tail = split(read(TEMPLATE))
        head = head.replace('content="tbd-board %s"' % board.VERSION, 'content="tbd-board 0.9.0"')
        tail = tail.replace('<script id="tbd-board-renderer">', '<script id="tbd-board-renderer">\n// old renderer 0.9.0')
        write(self.path, head + raw + tail)

    def test_upgrade_keeps_the_data_block_and_replaces_the_renderer(self):
        raw = '\n{"schema":1,"boardId":"abcdef","revision":5,"title":"Old <b>","updated":"2026-01-01","log":"log.md",  "questions":[],"autodecided":[]}\n'
        self.old_board(raw)
        self.assertIn("run \"board.py upgrade\"", self.cli("check").stderr)
        proc = self.cli("upgrade")
        template = split(read(TEMPLATE))
        page = split(read(self.path))
        self.assertEqual(page, (template[0], raw, template[2]))
        self.assertIn("from tbd-board 0.9.0 to tbd-board %s" % board.VERSION, proc.stdout)
        data = self.data()
        self.assertEqual((data["revision"], data["updated"]), (5, "2026-01-01"))
        self.assertEqual(self.cli("check").stderr, "")
        self.assertIn("up to date", self.cli("upgrade").stdout)

    def test_upgrade_refuses_without_a_data_block_or_with_bad_json(self):
        write(self.path, "<html><body>no board here</body></html>")
        self.assertIn("opening tag", self.cli("upgrade", code=1).stderr)
        self.old_board("\n{not json}\n")
        before = read(self.path)
        self.assertIn("invalid JSON", self.cli("upgrade", code=1).stderr)
        self.assertEqual(read(self.path), before)

    def test_upgrade_refuses_a_missing_file(self):
        self.assertIn("file not found", self.cli("upgrade", code=1).stderr)


class VersionTest(unittest.TestCase):
    def test_version_matches_the_template(self):
        match = re.search(r'<meta name="generator" content="tbd-board ([^"]+)">', read(TEMPLATE))
        self.assertEqual(match.group(1), board.VERSION)
        self.assertEqual(board.VERSION, "1.0.0")

    def test_version_option(self):
        proc = subprocess.run([sys.executable, SCRIPT, "--version"], capture_output=True, text=True)
        self.assertEqual(proc.stdout.strip(), "board.py " + board.VERSION)

    def test_usage_error_exit_code(self):
        proc = subprocess.run([sys.executable, SCRIPT], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
