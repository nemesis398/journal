"""skill_values.py, the one reader of the journal's config file.

What it pins: where the file is looked for, that anything other than a JSON
object reads as no values, that a key of the wrong type or an empty string
counts as not set, the one sentence a missing key produces, and the Values
block that `render` prints into SKILL.md when the skill loads.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import skill_values as sv  # noqa: E402

FULL = {
    "user": {"name": "Alice"},
    "vault": {"root": "/notes/vault", "commit": "vault-commit"},
    "journal": {
        "protectedSection": "## Logbook",
        "languageRule": "English for tooling.\nGerman for the client.",
        "check": "notes-check --quiet",
    },
}


class Where(unittest.TestCase):
    def test_the_variable_names_the_file(self):
        with mock.patch.dict(os.environ, {"JOURNAL_CONFIG": "/x/config.json"}):
            self.assertEqual(sv.path(), Path("/x/config.json"))

    def test_without_it_the_xdg_config_home(self):
        env = {"XDG_CONFIG_HOME": "/cfg", "HOME": "/home/tester"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(sv.path(), Path("/cfg/journal/config.json"))

    def test_without_both_the_home_config(self):
        with mock.patch.dict(os.environ, {"HOME": "/home/tester"}, clear=True):
            self.assertEqual(sv.path(), Path("/home/tester/.config/journal/config.json"))

    def test_an_empty_variable_counts_as_unset(self):
        env = {"JOURNAL_CONFIG": "", "XDG_CONFIG_HOME": "", "HOME": "/h"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(sv.path(), Path("/h/.config/journal/config.json"))

    def test_the_variable_is_named_for_the_skill(self):
        self.assertEqual(sv.VARIABLE, "JOURNAL_CONFIG")


class FileCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "config.json"
        # An empty PATH, so no prose-check of the machine leaks in.
        self.bin = Path(self.tmp.name) / "bin"
        self.bin.mkdir()
        patcher = mock.patch.dict(os.environ, {"JOURNAL_CONFIG": str(self.file),
                                               "PATH": str(self.bin)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, text: str) -> None:
        self.file.write_text(text, encoding="utf-8")

    def stub(self, name: str = "prose-check", where: Path | None = None) -> Path:
        target = (where or self.bin) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        target.chmod(0o755)
        return target


class Reading(FileCase):
    def test_a_missing_file_is_no_values(self):
        self.assertEqual(sv.load(), {})

    def test_malformed_json_is_no_values(self):
        self.write("{not json")
        self.assertEqual(sv.load(), {})

    def test_a_list_is_no_values(self):
        self.write("[1, 2]")
        self.assertEqual(sv.load(), {})

    def test_bytes_that_are_not_utf8_are_no_values(self):
        self.file.write_bytes(b"\xff\xfe{}")
        self.assertEqual(sv.load(), {})

    def test_a_directory_is_no_values(self):
        self.file.mkdir()
        self.assertEqual(sv.load(), {})

    def test_a_dotted_key_walks_the_objects(self):
        self.write(json.dumps({"user": {"name": "Alice"}}))
        self.assertEqual(sv.get("user.name"), "Alice")

    def test_a_missing_key_is_none(self):
        self.write(json.dumps({"user": {}}))
        self.assertIsNone(sv.get("user.name"))
        self.assertIsNone(sv.get("nothing.at.all"))

    def test_the_wrong_type_is_none(self):
        self.write(json.dumps({"user": {"name": ["Alice"]}, "n": 3, "flag": True}))
        self.assertIsNone(sv.get("user.name"))
        self.assertIsNone(sv.get("n"))
        self.assertIsNone(sv.get("flag", dict))

    def test_an_empty_or_blank_string_is_not_set(self):
        self.write(json.dumps({"a": "", "b": "  \n"}))
        self.assertIsNone(sv.get("a"))
        self.assertIsNone(sv.get("b"))

    def test_require_names_the_key_and_the_file(self):
        self.write("{}")
        with self.assertRaises(sv.Missing) as caught:
            sv.require("vault.root")
        self.assertEqual(str(caught.exception), f"set `vault.root` in `{self.file}`")
        self.assertEqual(caught.exception.key, "vault.root")

    def test_require_returns_a_value_that_is_set(self):
        self.write(json.dumps({"vault": {"root": "/v"}}))
        self.assertEqual(sv.require("vault.root"), "/v")


class Render(FileCase):
    def lines(self) -> list[str]:
        return sv.render().splitlines()

    def stop_line(self, key: str) -> str:
        return f"**Stop.** Set `{key}` in `{self.file}` before you use this skill."

    def gate_off(self) -> str:
        return (f"**Step prose gate is off** until `journal.proseCheck` is set in "
                f"`{self.file}`: {sv.STEPS['journal.proseCheck']['without']}.")

    def test_a_full_file_prints_every_text_key(self):
        self.write(json.dumps(FULL))
        prose = self.stub()
        out = sv.render()
        self.assertTrue(out.startswith("## Values\n\n"), out)
        self.assertIn("- `user.name`: Alice\n", out)
        self.assertIn("- `vault.root`: /notes/vault\n", out)
        self.assertIn("- `journal.protectedSection`: ## Logbook\n", out)
        # A value over several lines stays inside its list item.
        self.assertIn("- `journal.languageRule`: English for tooling.\n  German for the client.\n", out)
        self.assertIn(f"- `journal.proseCheck`: {prose}\n", out)
        self.assertIn("- `vault.commit`: vault-commit\n", out)
        self.assertIn("- `journal.check`: notes-check --quiet\n", out)
        self.assertNotIn("Stop.", out)
        self.assertNotIn("is off", out)

    def test_every_text_key_has_a_line(self):
        self.write(json.dumps(FULL))
        out = sv.render()
        # The daily note on, the default, needs no line.
        for key, _kind in sv.TEXT_KEYS:
            if key != "journal.dailyNote":
                self.assertIn(f"`{key}`", out)
        self.assertEqual(sv.OPTIONAL - set(sv.SHOWN), {"user.name"})

    def test_a_missing_key_prints_the_stop_line_instead(self):
        values = json.loads(json.dumps(FULL))
        del values["journal"]["protectedSection"]
        self.write(json.dumps(values))
        lines = self.lines()
        self.assertIn(self.stop_line("journal.protectedSection"), lines)
        self.assertFalse([line for line in lines
                          if line.startswith("- `journal.protectedSection`")])
        self.assertIn("- `vault.root`: /notes/vault", lines)

    def test_the_user_name_never_stops_the_skill(self):
        values = json.loads(json.dumps(FULL))
        del values["user"]["name"]
        self.write(json.dumps(values))
        out = sv.render()
        self.assertNotIn("user.name", out)
        self.assertNotIn("Stop.", out)

    def test_the_user_name_is_printed_when_it_is_set(self):
        self.write(json.dumps(FULL))
        self.assertIn("- `user.name`: Alice", self.lines())

    def commit_off(self) -> str:
        return (f"**Step commit is off** until `vault.commit` is set in "
                f"`{self.file}`: {sv.STEPS['vault.commit']['without']}.")

    def test_vault_commit_set_is_printed(self):
        self.write(json.dumps(FULL))
        lines = self.lines()
        self.assertIn("- `vault.commit`: vault-commit", lines)
        self.assertNotIn(self.commit_off(), lines)

    def test_vault_commit_unset_turns_the_commit_step_off(self):
        # Even with a `vault-commit` on the PATH: unset means uncommitted.
        self.stub("vault-commit")
        values = json.loads(json.dumps(FULL))
        del values["vault"]["commit"]
        self.write(json.dumps(values))
        lines = self.lines()
        self.assertIn(self.commit_off(), lines)
        self.assertNotIn(self.stop_line("vault.commit"), lines)
        without = sv.STEPS["vault.commit"]["without"]
        self.assertIn("uncommitted", without)
        self.assertIn("say so", without)
        self.assertIn("never", without)
        self.assertIn("`git commit`", without)

    def check_off(self) -> str:
        return (f"**Step vault check is off** until `journal.check` is set in "
                f"`{self.file}`: {sv.STEPS['journal.check']['without']}.")

    def test_journal_check_set_is_printed(self):
        self.write(json.dumps(FULL))
        lines = self.lines()
        self.assertIn("- `journal.check`: notes-check --quiet", lines)
        self.assertNotIn(self.check_off(), lines)

    def test_journal_check_unset_skips_the_check_and_says_so(self):
        # Even with a `vault-check` on the PATH: unset means no check.
        self.stub("vault-check")
        values = json.loads(json.dumps(FULL))
        del values["journal"]["check"]
        self.write(json.dumps(values))
        lines = self.lines()
        self.assertIn(self.check_off(), lines)
        self.assertNotIn(self.stop_line("journal.check"), lines)
        without = sv.STEPS["journal.check"]["without"]
        self.assertIn("skip", without)
        self.assertIn("say", without)
        self.assertNotIn("journal.check", sv.missing(values))

    def test_missing_names_the_stop_keys_that_are_not_set(self):
        self.assertEqual(sv.missing(FULL), [])
        values = json.loads(json.dumps(FULL))
        del values["user"]["name"]
        del values["journal"]["languageRule"]
        self.assertEqual(sv.missing(values), ["journal.languageRule"])
        self.assertEqual(sv.missing({}), [key for key, _kind in sv.TEXT_KEYS
                                          if key not in sv.OPTIONAL
                                          and key not in sv.STEPS])
        self.assertNotIn("user.name", sv.missing({}))

    def test_a_mistyped_key_counts_as_missing(self):
        values = json.loads(json.dumps(FULL))
        values["vault"]["root"] = ["/notes/vault"]
        self.write(json.dumps(values))
        self.assertIn(self.stop_line("vault.root"), self.lines())

    def test_render_names_area(self):
        self.write(json.dumps(FULL))
        self.assertIn("- `vault.area`: AI", self.lines())
        for value, shown in (("Work/AI/", "Work/AI"), ("", "."), (".", ".")):
            with self.subTest(value=value):
                self.write(json.dumps({**FULL, "vault": {**FULL["vault"], "area": value}}))
                self.assertIn(f"- `vault.area`: {shown}", self.lines())

    def test_area_rejected(self):
        for value in ("/abs", "../x", "a\\b", 7):
            with self.subTest(value=value):
                values = {**FULL, "vault": {**FULL["vault"], "area": value}}
                self.write(json.dumps(values))
                line = next(x for x in self.lines() if x.startswith("- `vault.area`"))
                self.assertTrue(line.startswith(f"- `vault.area`: invalid: `vault.area` in "
                                                f"`{self.file}` must "), line)
                self.assertEqual(sv.needed(values), ["vault.area"])

    def test_daily_on_by_default_prints_no_line(self):
        self.write(json.dumps(FULL))
        self.assertNotIn("dailyNote", sv.render())
        self.assertEqual(sv.needed(FULL), [])
        values = {**FULL, "journal": {"languageRule": "x"}}
        self.assertIn(self.stop_line("journal.protectedSection"), sv.render(values).splitlines())
        self.assertEqual(sv.needed(values), ["journal.protectedSection"])

    def test_daily_off_needs_no_protected_section(self):
        values = json.loads(json.dumps(FULL))
        values["journal"]["dailyNote"] = False
        del values["journal"]["protectedSection"]
        self.write(json.dumps(values))
        self.assertEqual(sv.needed(values), [])
        out = sv.render()
        self.assertIn("- `journal.dailyNote`: off. Skip every step about the daily note\n", out)
        self.assertIn("- `journal.protectedSection`: not needed, the daily note is off\n", out)
        self.assertNotIn("Stop.", out)
        # A protected section that is set still shows.
        values["journal"]["protectedSection"] = "## Logbook"
        self.assertIn("- `journal.protectedSection`: ## Logbook", sv.render(values).splitlines())

    def test_a_daily_note_that_is_not_a_bool_is_refused(self):
        values = {**FULL, "journal": {**FULL["journal"], "dailyNote": "no"}}
        self.assertEqual(sv.needed(values), ["journal.dailyNote"])
        self.assertIn(f"- `journal.dailyNote`: invalid: `journal.dailyNote` in `{self.file}` "
                      "must be true or false: 'no'", sv.render(values).splitlines())

    def test_a_list_or_object_prints_as_compact_json(self):
        self.assertEqual(sv.show({"a": ["b", "ü"]}), '{"a":["b","ü"]}')
        self.assertEqual(sv.show(["x", "y"]), '["x","y"]')

    def test_prose_check_missing_turns_the_gate_off(self):
        self.write(json.dumps(FULL))
        lines = self.lines()
        self.assertIn(self.gate_off(), lines)
        self.assertNotIn(self.stop_line("journal.proseCheck"), lines)

    def test_prose_check_on_the_path_is_the_default(self):
        self.write(json.dumps(FULL))
        prose = self.stub()
        self.assertIn(f"- `journal.proseCheck`: {prose}", self.lines())

    def test_prose_check_from_config_wins_over_the_path(self):
        self.stub()
        named = self.stub("check", Path(self.tmp.name) / "a b" / "prose" / "bin")
        values = json.loads(json.dumps(FULL))
        values["journal"]["proseCheck"] = str(named)
        self.write(json.dumps(values))
        self.assertIn(f"- `journal.proseCheck`: {named}", self.lines())

    def test_prose_check_from_config_expands_the_home(self):
        home = Path(self.tmp.name) / "home"
        named = self.stub("prose-check", home / "tools")
        values = json.loads(json.dumps(FULL))
        values["journal"]["proseCheck"] = "~/tools/prose-check"
        self.write(json.dumps(values))
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            self.assertIn(f"- `journal.proseCheck`: {named}", self.lines())

    def test_prose_check_from_config_that_is_not_there_turns_the_gate_off(self):
        self.stub()
        values = json.loads(json.dumps(FULL))
        values["journal"]["proseCheck"] = str(Path(self.tmp.name) / "nowhere")
        self.write(json.dumps(values))
        self.assertIn(self.gate_off(), self.lines())

    def assert_every_key_missing(self):
        lines = self.lines()
        self.assertEqual(lines[0], "## Values")
        for key, _kind in sv.TEXT_KEYS:
            if key in sv.OPTIONAL or key in sv.STEPS:
                self.assertNotIn(self.stop_line(key), lines)
            else:
                self.assertIn(self.stop_line(key), lines)
        self.assertIn(self.gate_off(), lines)
        self.assertIn(self.commit_off(), lines)

    def test_a_missing_file_is_every_key_missing(self):
        self.assert_every_key_missing()

    def test_an_empty_file_is_every_key_missing(self):
        self.write("")
        self.assert_every_key_missing()

    def test_a_malformed_file_is_every_key_missing(self):
        self.write('{"user": {"name": "Alice"')
        self.assert_every_key_missing()

    def test_the_cli_exits_0_and_prints_the_block(self):
        self.write("{not json")
        done = subprocess.run([sys.executable, "-B", str(SCRIPTS / "skill_values.py"), "render"],
                              capture_output=True, text=True, env=dict(os.environ))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, sv.render())
        self.assertEqual(done.stderr, "")

    def test_a_wrong_verb_is_a_usage_error(self):
        done = subprocess.run([sys.executable, "-B", str(SCRIPTS / "skill_values.py"), "nope"],
                              capture_output=True, text=True, env=dict(os.environ))
        self.assertEqual(done.returncode, 2)
        self.assertIn("usage:", done.stderr)


if __name__ == "__main__":
    unittest.main()
