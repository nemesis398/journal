# tests/test_claude_stop.py
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "adapters" / "claude"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common  # noqa: E402
import stop  # noqa: E402
from subprocess_env import subprocess_env  # noqa: E402


def edit_turn():
    """One user turn whose assistant reply edits a file."""
    return [
        {"type": "user", "message": {"role": "user", "content": "do it"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "/x/y.py"}}]}},
    ]


def quiet_turn():
    return [
        {"type": "user", "message": {"role": "user", "content": "why?"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "Because."}]}},
    ]


SESSION_NOTE = "/home/m/Vault/AI/sessions/2026-10-17 Stop hooks.md"
WRITER = "~/.claude/skills/journal/scripts/session_note.py"


def tool_turn(name, **args):
    """One user turn whose assistant reply makes one tool call."""
    return [
        {"type": "user", "message": {"role": "user", "content": "write it up"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": name, "input": args}]}},
    ]


def journal_turn():
    return tool_turn("Bash", command=(
        f"python3 -B {WRITER} write --title T --domain ai "
        "--description D --body-file /tmp/body.md"))


# Every key the skill stops without, and no `user.name`, which never stops it.
STOP_CONFIG = {"vault": {"root": "/notes/vault"},
               "journal": {"protectedSection": "## Logbook",
                           "languageRule": "English."}}


def goal_record(met: bool):
    return [{"type": "attachment",
             "attachment": {"type": "goal_status", "met": met, "condition": "x"}}]


class StopCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous = os.environ.get("JOURNAL_STATE_ROOT")
        os.environ["JOURNAL_STATE_ROOT"] = os.path.join(self.tmp.name, "state")
        # The reminder points at a skill that stops without its Stop keys, so
        # it stays quiet without them; every case but the config cases has them.
        self.config = Path(self.tmp.name) / "config.json"
        self.config.write_text(json.dumps(STOP_CONFIG), encoding="utf-8")
        self.previous_config = os.environ.get("JOURNAL_CONFIG")
        os.environ["JOURNAL_CONFIG"] = str(self.config)
        self.previous_vault = os.environ.pop("JOURNAL_VAULT", None)
        self.addCleanup(self._restore)

    def _restore(self):
        os.environ.pop("JOURNAL_VAULT", None)
        for name, value in (("JOURNAL_STATE_ROOT", self.previous),
                            ("JOURNAL_CONFIG", self.previous_config),
                            ("JOURNAL_VAULT", self.previous_vault)):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def transcript(self, *groups, entrypoint="cli"):
        """Every record carries `entrypoint`, the way Claude Code writes one:
        "cli" in an interactive session, "sdk-cli" under `claude -p`. None
        leaves the key out."""
        path = Path(self.tmp.name) / "t.jsonl"
        records = [r for group in groups for r in group]
        if entrypoint is not None:
            records = [{**r, "entrypoint": entrypoint} for r in records]
        path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
        return str(path)

    def reason(self):
        """Why the last call stood down. Read once: the record is cleared, so
        a later call that records nothing cannot pass on a stale reason."""
        import journal_state as js
        reason = js.read_standdown(self.tmp.name).get("reason")
        js.standdown_file(self.tmp.name).unlink(missing_ok=True)
        return reason

    def payload(self, transcript, **extra):
        base = {"cwd": self.tmp.name, "session_id": "s1",
                "transcript_path": transcript}
        base.update(extra)
        return base


class TestFires(StopCase):
    def test_fires_after_two_quiet_turns_following_an_edit(self):
        t = self.transcript(edit_turn(), quiet_turn(), quiet_turn())
        out = stop.handle(self.payload(t))
        self.assertIsNotNone(out)
        self.assertEqual(out["hookSpecificOutput"]["additionalContext"], stop.NUDGE)

    def test_the_nudge_names_the_session_note(self):
        t = self.transcript(edit_turn(), quiet_turn(), quiet_turn())
        nudge = stop.handle(self.payload(t))["hookSpecificOutput"]["additionalContext"]
        self.assertIn("session note", nudge)
        self.assertIn("journal skill", nudge)
        self.assertNotIn("daily note", nudge)

    def test_only_once_per_session(self):
        t = self.transcript(edit_turn(), quiet_turn(), quiet_turn())
        self.assertIsNotNone(stop.handle(self.payload(t)))
        self.assertIsNone(stop.handle(self.payload(t)))


class TestWhatCountsAsJournalled(StopCase):
    """Work, then one more turn, then two quiet ones: the nudge fires unless
    that one turn counts as journalled."""

    def wound_down_after(self, turn):
        return self.transcript(edit_turn(), turn, quiet_turn(), quiet_turn())

    def test_a_session_note_write_counts_as_journalled(self):
        for session, turn in (
                ("s-cli", journal_turn()),
                ("s-home", tool_turn("Bash", command=(
                    "cd /x && python3 -B $HOME/.claude/skills/journal/scripts/"
                    "session_note.py write --title T --domain ai"))),
                ("s-write", tool_turn("Write", file_path=SESSION_NOTE, content="# T")),
                ("s-edit", tool_turn("Edit", file_path=SESSION_NOTE,
                                     old_string="a", new_string="b"))):
            with self.subTest(session=session):
                self.assertIsNone(stop.handle(self.payload(
                    self.wound_down_after(turn), session_id=session)))
                self.assertEqual(self.reason(), "already_journalled")

    def test_a_daily_note_edit_no_longer_counts(self):
        daily = "/home/m/Vault/daily-notes/Saturday, 17. Oct 2026 (W42).md"
        for session, turn in (
                ("s-edit", tool_turn("Edit", file_path=daily,
                                     old_string="a", new_string="b")),
                ("s-write", tool_turn("Bash", command=(
                    "python3 -B ~/.claude/skills/journal/scripts/daily_note.py "
                    "write --area A --title T")))):
            with self.subTest(session=session):
                out = stop.handle(self.payload(self.wound_down_after(turn),
                                               session_id=session))
                self.assertIsNotNone(out)

    def test_running_the_writer_without_writing_does_not_count(self):
        # What a session working on the journal skill does all day.
        for session, command in (
                ("s-help", f"python3 -B {WRITER} --help"),
                ("s-cat", f"cat {WRITER}"),
                ("s-grep", 'grep -n "session_note.py write" SKILL.md')):
            with self.subTest(command=command):
                out = stop.handle(self.payload(
                    self.wound_down_after(tool_turn("Bash", command=command)),
                    session_id=session))
                self.assertIsNotNone(out)


class TestOnlyAnInteractiveSessionIsNudged(StopCase):
    def test_a_headless_session_is_never_nudged(self):
        t = self.transcript(edit_turn(), quiet_turn(), quiet_turn(),
                            entrypoint="sdk-cli")
        self.assertIsNone(stop.handle(self.payload(t)))
        self.assertEqual(self.reason(), "not_interactive")

    def test_a_transcript_without_an_entrypoint_is_never_nudged(self):
        missing = str(Path(self.tmp.name) / "missing.jsonl")
        empty = Path(self.tmp.name) / "empty.jsonl"
        empty.write_text("", encoding="utf-8")
        unmarked = self.transcript(edit_turn(), quiet_turn(), quiet_turn(),
                                   entrypoint=None)
        for session, transcript in (("s-unmarked", unmarked),
                                    ("s-empty", str(empty)),
                                    ("s-missing", missing)):
            with self.subTest(session=session):
                self.assertIsNone(stop.handle(self.payload(
                    transcript, session_id=session)))
                self.assertEqual(self.reason(), "not_interactive")

    def test_the_newest_entrypoint_decides(self):
        # A `claude -p --resume` appends headless records to an interactive
        # transcript, and an interactive resume does the reverse.
        def marked(value):
            return {"type": "user", "entrypoint": value}
        unmarked = {"type": "file-history-snapshot"}
        self.assertFalse(_common.is_interactive(
            [marked("cli"), marked("sdk-cli"), unmarked]))
        self.assertTrue(_common.is_interactive(
            [marked("sdk-cli"), marked("cli"), unmarked]))


class TestStandsDown(StopCase):
    def test_not_while_work_is_still_running(self):
        t = self.transcript(edit_turn(), quiet_turn())
        self.assertIsNone(stop.handle(self.payload(t)))

    def test_not_when_nothing_was_modified(self):
        t = self.transcript(quiet_turn(), quiet_turn(), quiet_turn())
        self.assertIsNone(stop.handle(self.payload(t)))

    def test_not_when_the_session_already_journalled(self):
        t = self.transcript(edit_turn(), journal_turn(), quiet_turn(), quiet_turn())
        self.assertIsNone(stop.handle(self.payload(t)))

    def test_not_when_a_stop_hook_is_holding_the_turn_open(self):
        t = self.transcript(edit_turn(), quiet_turn(), quiet_turn())
        self.assertIsNone(stop.handle(self.payload(t, stop_hook_active=True)))

    def test_not_during_a_live_goal_run(self):
        t = self.transcript(edit_turn(), quiet_turn(), quiet_turn(),
                            goal_record(met=False))
        self.assertIsNone(stop.handle(self.payload(t)))

    def test_fires_again_once_the_goal_is_met(self):
        t = self.transcript(edit_turn(), quiet_turn(), quiet_turn(),
                            goal_record(met=True))
        self.assertIsNotNone(stop.handle(self.payload(t)))

    def test_a_missing_transcript_is_silent(self):
        self.assertIsNone(stop.handle(self.payload(None)))

    def test_records_why_it_stood_down(self):
        t = self.transcript(edit_turn(), quiet_turn(), quiet_turn())
        stop.handle(self.payload(t, stop_hook_active=True))
        self.assertEqual(self.reason(), "stop_hook_active")


class TestNeverBreaksTheTurn(StopCase):
    def _drive(self, payload, **env):
        return subprocess.run(
            [sys.executable, "-B", str(ROOT / "adapters" / "claude" / "stop.py")],
            input=json.dumps(payload), capture_output=True, text=True,
            env=subprocess_env(**env))

    def test_garbage_stdin_still_exits_zero(self):
        done = subprocess.run(
            [sys.executable, "-B", str(ROOT / "adapters" / "claude" / "stop.py")],
            input="not json at all", capture_output=True, text=True,
            env=subprocess_env())
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout.strip(), "")

    def test_the_kill_switch_silences_it(self):
        t = self.transcript(edit_turn(), quiet_turn(), quiet_turn())
        done = self._drive(self.payload(t), disabled=True)
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout.strip(), "")


class TestConfig(StopCase):
    """A missing, empty or malformed config file turns the reminder off: exit
    0, nothing injected, and one line on stderr that names the file."""

    def _drive(self, config_text, session="s1", **env):
        if config_text is None:
            self.config.unlink(missing_ok=True)
        else:
            self.config.write_text(config_text, encoding="utf-8")
        t = self.transcript(edit_turn(), quiet_turn(), quiet_turn())
        return subprocess.run(
            [sys.executable, "-B", str(ROOT / "adapters" / "claude" / "stop.py")],
            input=json.dumps(self.payload(t, session_id=session)),
            capture_output=True, text=True,
            env=subprocess_env(JOURNAL_CONFIG=str(self.config),
                               JOURNAL_STATE_ROOT=os.environ["JOURNAL_STATE_ROOT"],
                               **env))

    def without(self, *keys):
        values = json.loads(json.dumps(STOP_CONFIG))
        for key in keys:
            head, tail = key.split(".")
            del values[head][tail]
        return values

    def assert_off(self, done):
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout, "")
        lines = done.stderr.splitlines()
        self.assertEqual(len(lines), 1, done.stderr)
        self.assertIn(str(self.config), lines[0])
        self.assertIn("vault.root", lines[0])

    def test_config_missing(self):
        self.assert_off(self._drive(None))

    def test_config_empty(self):
        self.assert_off(self._drive(""))

    def test_config_malformed(self):
        self.assert_off(self._drive('{"vault": {"root": '))

    def test_any_stop_key_missing_silences_it(self):
        import skill_values as sv
        stop_keys = [key for key, _kind in sv.TEXT_KEYS
                     if key not in sv.OPTIONAL and key not in sv.STEPS]
        self.assertEqual(stop_keys, ["vault.root", "journal.protectedSection",
                                     "journal.languageRule"])
        for key in stop_keys:
            with self.subTest(key=key):
                done = self._drive(json.dumps(self.without(key)), session=f"s-{key}")
                self.assertEqual((done.returncode, done.stdout), (0, ""))
                lines = done.stderr.splitlines()
                self.assertEqual(len(lines), 1, done.stderr)
                self.assertIn(key, lines[0])
                self.assertIn(str(self.config), lines[0])

    def test_the_user_name_never_silences_it(self):
        self.assertNotIn("user", STOP_CONFIG)
        done = self._drive(json.dumps(STOP_CONFIG))
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertIn("hookSpecificOutput", done.stdout)

    def test_the_stderr_line_comes_once_per_session(self):
        first = self._drive("{}", session="s-once")
        self.assertEqual(len(first.stderr.splitlines()), 1, first.stderr)
        again = self._drive("{}", session="s-once")
        self.assertEqual((again.returncode, again.stdout, again.stderr), (0, "", ""))
        other = self._drive("{}", session="s-other")
        self.assertEqual(len(other.stderr.splitlines()), 1, other.stderr)

    def test_journal_vault_stands_in_for_the_vault_root(self):
        done = self._drive(json.dumps(self.without("vault.root")),
                           JOURNAL_VAULT=self.tmp.name)
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertIn("hookSpecificOutput", done.stdout)

    def test_journal_vault_does_not_stand_in_for_the_other_keys(self):
        done = self._drive(json.dumps(self.without("journal.languageRule")),
                           JOURNAL_VAULT=self.tmp.name)
        self.assertEqual(done.stdout, "")
        self.assertIn("journal.languageRule", done.stderr)
        self.assertNotIn("vault.root", done.stderr)

    def test_with_the_config_it_reminds(self):
        done = self._drive(json.dumps(STOP_CONFIG))
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertEqual(json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"],
                         stop.NUDGE)

    def test_daily_off_needs_no_protected_section(self):
        values = self.without("journal.protectedSection")
        values["journal"]["dailyNote"] = False
        done = self._drive(json.dumps(values))
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertEqual(json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"],
                         stop.NUDGE)
        # With the daily note on, the same config still silences it.
        del values["journal"]["dailyNote"]
        done = self._drive(json.dumps(values), session="s-on")
        self.assertEqual(done.stdout, "")
        self.assertIn("journal.protectedSection", done.stderr)

    def test_a_rejected_area_silences_it_and_says_why(self):
        values = json.loads(json.dumps(STOP_CONFIG))
        values["vault"]["area"] = "../x"
        done = self._drive(json.dumps(values))
        self.assertEqual(done.stdout, "")
        self.assertIn("`vault.area`", done.stderr)

    def test_off_records_why(self):
        self.config.write_text("{}", encoding="utf-8")
        t = self.transcript(edit_turn(), quiet_turn(), quiet_turn())
        self.assertIsNone(stop.handle(self.payload(t)))
        self.assertEqual(self.reason(), "no_config")


class TestOtherShapes(StopCase):
    """The writer as a plugin runs it, by a quoted path from
    ${CLAUDE_SKILL_DIR}, or through an interpreter named by its path; and a
    vault committed through the command `vault.commit` names, run as
    `COMMAND MESSAGE PATH...`."""

    def test_a_quoted_plugin_path_counts_as_journalled(self):
        for session, script in (
                ("s-dq", '"/home/a/.claude/plugins/cache/galdr/journal/0.1.0/skills/journal/'
                         'scripts/session_note.py"'),
                ("s-sq", "'/home/a b/plugins/journal/skills/journal/scripts/session_note.py'")):
            with self.subTest(session=session):
                turn = tool_turn("Bash", command=f"python3 -B {script} write --title T")
                path = self.transcript(edit_turn(), turn, quiet_turn(), quiet_turn())
                self.assertIsNone(stop.handle(self.payload(path, session_id=session)))
                self.assertEqual(self.reason(), "already_journalled")

    def test_a_quoted_path_without_the_verb_does_not_count(self):
        turn = tool_turn("Bash", command='python3 -B "/p/scripts/session_note.py" --help')
        path = self.transcript(edit_turn(), turn, quiet_turn(), quiet_turn())
        self.assertIsNotNone(stop.handle(self.payload(path, session_id="s-help")))

    def test_an_interpreter_by_its_path_counts_as_journalled(self):
        turn = tool_turn("Bash", command=(
            "/opt/python3-3.13/bin/python3 -B "
            "/home/a/.claude/skills/journal/scripts/session_note.py write --title T"))
        path = self.transcript(edit_turn(), turn, quiet_turn(), quiet_turn())
        self.assertIsNone(stop.handle(self.payload(path, session_id="s-store")))
        self.assertEqual(self.reason(), "already_journalled")

    def test_an_interpreter_behind_a_prefix_counts_as_journalled(self):
        script = '"/p/skills/journal/scripts/session_note.py"'
        for command in (
                f"JOURNAL_CONFIG=/c/config.json python3 -B {script} write --title T",
                f"A=1 B= python3 {script} write --title T",
                f"cd /x && LANG=C.UTF-8 python3 -B {script} write --title T",
                f"env python3 -B {script} write --title T",
                f"env JOURNAL_CONFIG=/c.json python3 {script} write --title T",
                f"timeout 60 python3 -B {script} write --title T",
                f"timeout 30s /usr/bin/python3 {script} write --title T",
                f"A=1 timeout 60 env B=2 python3 {script} write --title T"):
            with self.subTest(command=command):
                turn = _common.turns(self.transcript(tool_turn("Bash", command=command)))
                self.assertTrue(turn[0]["journalled"])

    def test_mentions_of_the_writer_never_count(self):
        # The probes of the review: reading, searching, printing, asking for
        # help, and naming the command in a commit message.
        script = "skills/journal/scripts/session_note.py"
        for command in (
                f'rg -n "session_note.py write" {script}',
                f"rg -n 'python3 -B {script} write' SKILL.md",
                "rg 'env python3 .*session_note.py write' -n .",
                f"rg -n 'timeout 60 python3 {script} write'",
                f"sed -n 1,40p {script}",
                f"sed -i 's/python3 {script} write/x/' SKILL.md",
                f"cat {script}",
                f"cat {script} | rg write",
                f"python3 -B {script} --help",
                f"env python3 -B {script} --help",
                f"timeout 5 python3 {script} --help",
                f"JOURNAL_CONFIG=/c.json python3 {script} --help",
                'git commit -m "docs: session_note.py write gains --dry-run"',
                f'git commit -m "fix: python3 -B {script} write"',
                f'echo "env python3 {script} write"',
                f"FOO=1 rg 'python3 {script} write'"):
            with self.subTest(command=command):
                turn = _common.turns(self.transcript(tool_turn("Bash", command=command)))
                self.assertFalse(turn[0]["journalled"])

    def test_the_configured_commit_command_counts_as_a_change(self):
        commit = tool_turn("Bash", command="notes-commit 'docs: note' AI/sessions/T.md")
        seen = _common.turns(self.transcript(commit), commit="notes-commit")
        self.assertEqual(seen[0]["modified"], True)

    def test_without_a_commit_command_only_git_commit_counts(self):
        commit = tool_turn("Bash", command="notes-commit 'docs: note' AI/sessions/T.md")
        self.assertEqual(_common.turns(self.transcript(commit))[0]["modified"], False)

    def test_a_mention_of_the_commit_command_does_not_count(self):
        for command in ("rg -n notes-commit .", "notes-committer x", "echo notes-commit"):
            with self.subTest(command=command):
                turn = tool_turn("Bash", command=command)
                seen = _common.turns(self.transcript(turn), commit="notes-commit")
                self.assertEqual(seen[0]["modified"], False)

    def test_a_commit_command_by_its_path_counts(self):
        command = "/opt/bin/notes commit 'docs: note' x.md"
        turn = tool_turn("Bash", command=f"cd /v && {command}")
        seen = _common.turns(self.transcript(turn), commit="/opt/bin/notes commit")
        self.assertEqual(seen[0]["modified"], True)

    def test_a_git_commit_still_counts_as_a_change(self):
        commit = tool_turn("Bash", command="git commit -m x")
        self.assertEqual(_common.turns(self.transcript(commit))[0]["modified"], True)

    def test_a_vault_commit_alone_then_quiet_turns_nudges(self):
        config = dict(STOP_CONFIG, vault={"root": "/notes/vault", "commit": "notes-commit"})
        self.config.write_text(json.dumps(config), encoding="utf-8")
        commit = tool_turn("Bash", command="notes-commit 'docs: note' notes/x.md")
        out = stop.handle(self.payload(self.transcript(commit, quiet_turn(), quiet_turn()),
                                       session_id="s-vc"))
        self.assertIsNotNone(out)


if __name__ == "__main__":
    unittest.main()
