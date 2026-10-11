"""Repository checks: one version everywhere, valid manifests, and an installable skill folder."""
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "skills", "tbd-board")
SPEC_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
AGENT_PLUGINS_KEYS = {"$schema", "name", "version", "description", "author", "homepage", "repository",
                      "license", "keywords", "extensions"}


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def frontmatter(text):
    """The SKILL.md frontmatter as {key: raw value}. Values here are one line each."""
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    fields = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


class RepoTest(unittest.TestCase):
    def test_one_version_everywhere(self):
        versions = {
            ".claude-plugin/plugin.json": json.loads(read(".claude-plugin", "plugin.json"))["version"],
            "plugin.json": json.loads(read("plugin.json"))["version"],
            "board.py": re.search(r'^VERSION = "([^"]+)"', read("skills", "tbd-board", "scripts", "board.py"), re.M).group(1),
            "board-template.html": re.search(r'content="tbd-board ([^"]+)"',
                                             read("skills", "tbd-board", "assets", "board-template.html")).group(1),
            "CHANGELOG.md": re.search(r"^## \[?([0-9][^\] ]*)", read("CHANGELOG.md"), re.M).group(1),
        }
        self.assertEqual(len(set(versions.values())), 1, versions)

    def test_skill_frontmatter_uses_spec_fields_only(self):
        fields = frontmatter(read("skills", "tbd-board", "SKILL.md"))
        self.assertLessEqual(set(fields), SPEC_FIELDS)
        self.assertEqual(fields["name"], os.path.basename(SKILL))
        description = json.loads(fields["description"])  # quoted in double quotes, no escapes needed
        self.assertTrue(0 < len(description) <= 1024, len(description))
        self.assertNotRegex(description, r"<[^>]+>")
        self.assertNotIn("CLAUDE_SKILL_DIR", read("skills", "tbd-board", "SKILL.md"))

    def test_skill_body_is_short(self):
        self.assertLess(len(read("skills", "tbd-board", "SKILL.md").splitlines()), 500)

    def test_manifests_agree(self):
        claude = json.loads(read(".claude-plugin", "plugin.json"))
        market = json.loads(read(".claude-plugin", "marketplace.json"))
        root = json.loads(read("plugin.json"))
        self.assertEqual(market["name"], "camerash")
        self.assertEqual([p["name"] for p in market["plugins"]], ["tbd-board"])
        self.assertEqual(market["plugins"][0]["source"], "./")
        self.assertEqual(claude["name"], "tbd-board")
        self.assertEqual(claude["skills"], ["./skills/tbd-board"])
        self.assertLessEqual(set(root), AGENT_PLUGINS_KEYS)
        self.assertEqual(root["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        self.assertEqual(root["name"], claude["name"])

    def test_codex_icons_exist(self):
        text = read("skills", "tbd-board", "agents", "openai.yaml")
        for path in re.findall(r'icon_(?:small|large): "([^"]+)"', text):
            self.assertTrue(os.path.isfile(os.path.join(SKILL, path)), path)

    def test_no_symlinks(self):
        for folder, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", "_handover", "node_modules")]
            for name in dirs + files:
                self.assertFalse(os.path.islink(os.path.join(folder, name)), os.path.join(folder, name))


if __name__ == "__main__":
    unittest.main()
