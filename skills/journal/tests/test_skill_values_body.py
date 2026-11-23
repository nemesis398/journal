"""The body of skill_values.py, the part below `# ---- body ----` that is the
same in every skill with values. This file is the same in every such skill
too: it reads the skill's own block (NAME, VARIABLE, TEXT_KEYS, STEPS,
OPTIONAL) from the module and swaps in made-up keys where a test needs them.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "skill_values.py"
sys.path.insert(0, str(SCRIPT.parent))
import skill_values as sv  # noqa: E402

KEYS = [("user.name", str), ("a.text", str), ("a.map", dict),
        ("a.step", str), ("a.tool", str)]
STEPS = {"a.step": {"step": "one", "without": "go on without it"},
         "a.tool": {"step": "two", "command": "the-tool", "without": "skip the tool"}}
FULL = {"user": {"name": "Alice"},
        "a": {"text": "x", "map": {"k": ["v", "ü"]}, "step": "s"}}


class Case(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.file = self.tmp / "config.json"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for patcher in (
            mock.patch.dict(os.environ, {sv.VARIABLE: str(self.file), "PATH": str(self.bin)}),
            mock.patch.object(sv, "TEXT_KEYS", KEYS),
            mock.patch.object(sv, "STEPS", STEPS),
            mock.patch.object(sv, "OPTIONAL", {"user.name"}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def write(self, values) -> None:
        self.file.write_text(values if isinstance(values, str) else json.dumps(values),
                             encoding="utf-8")

    def tool(self, where: Path | None = None, name: str = "the-tool") -> Path:
        target = (where or self.bin) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        target.chmod(0o755)
        return target

    def stop(self, key: str) -> str:
        return f"**Stop.** Set `{key}` in `{self.file}` before you use this skill."

    def off(self, key: str) -> str:
        step = STEPS[key]
        return (f"**Step {step['step']} is off** until `{key}` is set in "
                f"`{self.file}`: {step['without']}.")


class Block(unittest.TestCase):
    def test_the_variable_is_the_name_in_upper_case(self):
        self.assertEqual(sv.VARIABLE, sv.NAME.upper().replace("-", "_") + "_CONFIG")

    def test_steps_and_optional_name_text_keys(self):
        keys = [key for key, _kind in sv.TEXT_KEYS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertLessEqual(set(sv.STEPS) | sv.OPTIONAL, set(keys))
        self.assertEqual(sv.OPTIONAL - set(sv.SHOWN), {"user.name"})
        for key, step in sv.STEPS.items():
            with self.subTest(key=key):
                self.assertLessEqual({"step", "without"}, set(step))
                self.assertFalse(step["without"].endswith("."))

    def test_the_text_keys_have_a_type(self):
        for key, kind in sv.TEXT_KEYS:
            self.assertIsInstance(kind, type, key)


class Where(unittest.TestCase):
    def test_the_variable_names_the_file(self):
        with mock.patch.dict(os.environ, {sv.VARIABLE: "/x/values.json"}):
            self.assertEqual(sv.path(), Path("/x/values.json"))

    def test_without_it_the_xdg_config_home(self):
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/cfg", "HOME": "/h"}, clear=True):
            self.assertEqual(sv.path(), Path("/cfg") / sv.NAME / "config.json")

    def test_an_empty_variable_counts_as_unset(self):
        env = {sv.VARIABLE: "", "XDG_CONFIG_HOME": "", "HOME": "/h"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(sv.path(), Path("/h/.config") / sv.NAME / "config.json")


class Reading(Case):
    def test_anything_but_a_json_object_is_no_values(self):
        for text in (None, "", "{not json", "[1, 2]", '"s"', b"\xff\xfe{}", "dir"):
            with self.subTest(text=text):
                if self.file.is_dir():
                    self.file.rmdir()
                self.file.unlink(missing_ok=True)
                if text == "dir":
                    self.file.mkdir()
                elif isinstance(text, bytes):
                    self.file.write_bytes(text)
                elif text is not None:
                    self.write(text)
                self.assertEqual(sv.load(), {})

    def test_a_dotted_key_walks_the_objects(self):
        self.write(FULL)
        self.assertEqual(sv.get("user.name"), "Alice")
        self.assertEqual(sv.get("a.map", dict), {"k": ["v", "ü"]})
        self.assertEqual(sv.get("a.b", values={"a": {"b": "c"}}), "c")

    def test_not_set_is_none(self):
        self.write({"s": "", "b": " \n", "m": {}, "l": [], "n": 3, "t": True,
                    "x": "v", "y": {"z": 1}})
        for key, kind in (("nothing.at.all", str), ("x.deeper", str), ("s", str),
                          ("b", str), ("m", dict), ("l", list), ("n", str),
                          ("t", int), ("y", list), ("y.z", str)):
            with self.subTest(key=key):
                self.assertIsNone(sv.get(key, kind))
        self.assertEqual(sv.get("n", int), 3)
        self.assertIs(sv.get("t", bool), True)

    def test_require_names_the_key_and_the_file_in_backticks(self):
        self.write({"a": {"text": "x"}})
        self.assertEqual(sv.require("a.text"), "x")
        with self.assertRaises(sv.Missing) as caught:
            sv.require("a.map", dict)
        self.assertEqual(str(caught.exception), f"set `a.map` in `{self.file}`")
        self.assertEqual(caught.exception.key, "a.map")
        self.assertIsInstance(caught.exception, LookupError)


class Show(unittest.TestCase):
    def test_a_list_or_object_is_compact_json(self):
        self.assertEqual(sv.show({"a": ["b", "ü"]}), '{"a":["b","ü"]}')
        self.assertEqual(sv.show(["x", "y"]), '["x","y"]')

    def test_a_string_is_trimmed_and_stays_inside_its_list_item(self):
        self.assertEqual(sv.show("  one\ntwo\n"), "one\n  two")


class Render(Case):
    def lines(self) -> list[str]:
        return sv.render().splitlines()

    def test_a_full_file_prints_every_value_in_order(self):
        self.write(FULL)
        tool = self.tool()
        self.assertEqual(self.lines(), [
            "## Values", "",
            "- `user.name`: Alice",
            "- `a.text`: x",
            '- `a.map`: {"k":["v","ü"]}',
            "- `a.step`: s",
            f"- `a.tool`: {tool}",
        ])

    def test_a_missing_key_prints_the_stop_line_in_its_place(self):
        values = json.loads(json.dumps(FULL))
        del values["a"]["text"]
        values["a"]["map"] = {}
        self.write(values)
        lines = self.lines()
        self.assertEqual(lines[3:5], [self.stop("a.text"), self.stop("a.map")])

    def test_the_optional_key_prints_nothing_when_unset(self):
        values = json.loads(json.dumps(FULL))
        values["user"]["name"] = ["Alice"]
        self.write(values)
        out = sv.render()
        self.assertNotIn("user.name", out)
        self.assertNotIn("**Stop.**", out)

    def test_a_step_key_turns_off_its_step_alone(self):
        values = json.loads(json.dumps(FULL))
        del values["a"]["step"]
        self.write(values)
        lines = self.lines()
        self.assertIn(self.off("a.step"), lines)
        self.assertIn(self.off("a.tool"), lines)
        self.assertNotIn("**Stop.**", "\n".join(lines))

    def test_a_command_key_from_the_file_wins_over_the_path(self):
        self.tool()
        named = self.tool(self.tmp / "a b" / "bin", "other")
        self.write({**FULL, "a": {**FULL["a"], "tool": str(named)}})
        self.assertIn(f"- `a.tool`: {named}", self.lines())

    def test_a_command_key_expands_the_home(self):
        home = self.tmp / "home"
        named = self.tool(home / "tools")
        self.write({**FULL, "a": {**FULL["a"], "tool": "~/tools/the-tool"}})
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            self.assertIn(f"- `a.tool`: {named}", self.lines())

    def test_a_command_that_is_not_there_turns_its_step_off(self):
        self.tool()
        self.write({**FULL, "a": {**FULL["a"], "tool": str(self.tmp / "nowhere")}})
        self.assertIn(self.off("a.tool"), self.lines())

    def test_a_missing_empty_or_malformed_file_is_every_key_missing(self):
        for text in (None, "", '{"user": {"name": "Alice"'):
            with self.subTest(text=text):
                self.file.unlink(missing_ok=True)
                if text is not None:
                    self.write(text)
                self.assertEqual(self.lines(), [
                    "## Values", "", self.stop("a.text"), self.stop("a.map"),
                    self.off("a.step"), self.off("a.tool")])

    def test_render_takes_values_instead_of_the_file(self):
        self.write("{}")
        self.assertIn("- `a.text`: x", sv.render(FULL).splitlines())

    def test_missing_names_the_stop_keys_only(self):
        self.assertEqual(sv.missing(FULL), [])
        self.assertEqual(sv.missing({}), ["a.text", "a.map"])
        self.write({"a": {"map": {"k": []}}})
        self.assertEqual(sv.missing(), ["a.text"])


class Main(Case):
    def test_render_prints_the_block_and_exits_0(self):
        self.write("{not json")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(sv.main(["render"]), 0)
        self.assertEqual(buf.getvalue(), sv.render())

    def test_a_failure_inside_render_prints_a_stop_line(self):
        buf = io.StringIO()
        with mock.patch.object(sv, "render", side_effect=RuntimeError("boom")), \
                contextlib.redirect_stdout(buf):
            self.assertEqual(sv.main(["render"]), 0)
        self.assertTrue(buf.getvalue().startswith("**Stop.**"), buf.getvalue())
        self.assertIn("boom", buf.getvalue())

    def test_the_script_renders_and_exits_0(self):
        self.write("{}")
        done = subprocess.run([sys.executable, "-B", str(SCRIPT), "render"],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertTrue(done.stdout.startswith("## Values\n"), done.stdout)

    def test_a_usage_error_exits_2(self):
        for args in ([], ["bogus"], ["render", "extra"]):
            with self.subTest(args=args):
                done = subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                                      capture_output=True, text=True, timeout=30)
                self.assertEqual(done.returncode, 2)
                self.assertIn("usage:", done.stderr)
                self.assertEqual(done.stdout, "")


if __name__ == "__main__":
    unittest.main()
