"""The plugin around the skill: the hook wiring, the Values line of SKILL.md,
and that nothing personal or left over from a render step is in the text."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPO = SKILL.parents[1]
RENDER = '!`python3 -B "${CLAUDE_SKILL_DIR}/scripts/skill_values.py" render`'
# The `!` line is not read-only, so a session that has not granted it would
# deny it and load the skill without its values: the skill grants it itself.
GRANT = 'allowed-tools: Bash(python3 -B "${CLAUDE_SKILL_DIR}/scripts/skill_values.py" render)'
# A sync tool may be named as one example; nothing else that is one user's.
# Built from halves, so the pattern does not match its own line.
PERSONAL = re.compile("|".join(a + b for a, b in (
    ("junior ", "academy"), ("iph", "one"), ("next", "cloud"),
    ("this ", "machine"), ("this ", "vault"))), re.I)
SYNC_EXAMPLE = re.compile("sync tool such as " + "Next" + "cloud")


def code_files():
    for path in sorted(REPO.rglob("*")):
        if ".git" in path.parts or not path.is_file():
            continue
        if path.suffix in {".py", ".json", ".md", ".yml", ".yaml"}:
            yield path


class Hooks(unittest.TestCase):
    def test_stop_runs_the_adapter_from_the_plugin_root(self):
        hooks = json.loads((REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(set(hooks["hooks"]), {"Stop"})
        [entry] = hooks["hooks"]["Stop"]
        [hook] = entry["hooks"]
        self.assertEqual(hook["type"], "command")
        # `|| true`: a missing script must not block the stop with exit 2.
        self.assertEqual(hook["command"], 'python3 -B "${CLAUDE_PLUGIN_ROOT}/skills/journal/'
                                          'adapters/claude/stop.py" || true')
        self.assertEqual(hook["timeout"], 30)


class SkillText(unittest.TestCase):
    def setUp(self):
        self.text = (SKILL / "SKILL.md").read_text(encoding="utf-8")

    def test_the_first_line_after_the_title_renders_the_values(self):
        lines = self.text.splitlines()
        title = lines.index("# journal")
        self.assertEqual(lines[title + 1], RENDER)

    def test_the_frontmatter_grants_the_values_command(self):
        front = self.text.split("\n---\n", 1)[0].splitlines()
        self.assertIn(GRANT, front)
        # It grants exactly the command the first line runs, and nothing else.
        self.assertEqual(GRANT[len("allowed-tools: Bash("):-1], RENDER[2:-1])

    def test_no_placeholder_is_left(self):
        # A render placeholder, two braces; the Obsidian template token
        # for the week is the one pair that belongs in the text.
        self.assertNotIn("\x7b\x7b", self.text.replace("\x7b\x7bdate:", ""))

    def test_the_description_names_no_person_and_no_path(self):
        front = self.text.split("\n---\n", 1)[0]
        description = front.split("description:", 1)[1].split("\nallowed-tools:", 1)[0]
        self.assertIn("the user", description)
        self.assertNotRegex(description, r"[~/]\w|\$\{|\bAlice\b")

    def test_every_value_the_text_uses_is_rendered(self):
        import sys
        sys.path.insert(0, str(SKILL / "scripts"))
        import skill_values as sv
        named = set(re.findall(r"`((?:user|vault|journal)\.[A-Za-z.]+)` in Values", self.text))
        rendered = {key for key, _ in sv.TEXT_KEYS} | set(sv.STEPS)
        self.assertTrue(named, "the text names no value")
        self.assertLessEqual(named, rendered)


class Public(unittest.TestCase):
    def test_no_build_tree_name_and_no_em_dash(self):
        for path in code_files():
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=str(path.relative_to(REPO))):
                self.assertNotIn("rav" + "nix", text.lower())
                self.assertNotIn(chr(0x2014), text)

    def test_no_personal_value(self):
        for path in code_files():
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if PERSONAL.search(SYNC_EXAMPLE.sub("", line)):
                    self.fail(f"{path.relative_to(REPO)}:{number}: {line.strip()}")

    def test_no_home_path_in_the_scripts(self):
        for path in (SKILL / "scripts").glob("*.py"):
            with self.subTest(path=path.name):
                self.assertNotIn("/home/", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
