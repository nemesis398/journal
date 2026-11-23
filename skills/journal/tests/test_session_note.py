# tests/test_session_note.py
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))
import session_note as sn  # noqa: E402
from frontmatter import parse_frontmatter  # noqa: E402
from subprocess_env import subprocess_env  # noqa: E402

SESSION = "0b7c9a52-3f1e-4d2a-9c8b-5e6f7a8b9c0d"
D = date(2026, 10, 17)
D2 = date(2026, 10, 18)
DAY = "Saturday, 17. Oct 2026 (W42)"
DAY2 = "Sunday, 18. Oct 2026 (W42)"
TITLE = "Memory system"
REL = "AI/sessions/2026-10-17 Memory system.md"
BODY = "## Done\n\nWrote the writer.\n\n## Next\n\nWire the Stop hook.\n"
TEMPLATE = "## ✅ Today\n\n- [ ] \n\n## \U0001f4dd Capture\n\n"
VAULT_MDLINT_CONFIG = '{"config": {"MD013": false}}\n'
# The keys of a config written before vault.area and journal.dailyNote.
TODAY = {"vault": {"root": "", "commit": "vault-commit"},
         "journal": {"protectedSection": "## Logbook", "languageRule": "English.",
                     "check": "notes-check"}}
# What main wrote at 0b00fcd with TODAY's keys: the note BODY created on D,
# then APPENDED to it by the same session on D2, and the map.
FROZEN_CREATED = (
    '---\ntype: session\ndomain: [claude-code]\nupdated: 2026-10-17\n'
    'description: "Wrote the session note writer."\n'
    'generated: claude/0b7c9a52-3f1e-4d2a-9c8b-5e6f7a8b9c0d\n---\n\n# Memory system\n\n'
    'Day: [[Saturday, 17. Oct 2026 (W42)]]\n\n## Done\n\nWrote the writer.\n\n'
    '## Next\n\nWire the Stop hook.\n')
APPENDED = "## Done\n\nWired the hook.\n\n## Decisions\n\nOnce per session.\n"
FROZEN_APPENDED = (
    '---\ntype: session\ndomain: [claude-code, journal]\nupdated: 2026-10-18\n'
    'description: "Wired the Stop hook."\n'
    'generated: claude/0b7c9a52-3f1e-4d2a-9c8b-5e6f7a8b9c0d\n---\n\n# Memory system\n\n'
    'Day: [[Saturday, 17. Oct 2026 (W42)]], [[Sunday, 18. Oct 2026 (W42)]]\n\n'
    '## Done\n\nWrote the writer.\n\nWired the hook.\n\n## Decisions\n\nOnce per session.\n\n'
    '## Next\n\nWire the Stop hook.\n')
FROZEN_MAP = ('{\n  "0b7c9a52-3f1e-4d2a-9c8b-5e6f7a8b9c0d": '
              '"AI/sessions/2026-10-17 Memory system.md"\n}\n')
# markdownlint-cli2, named by JOURNAL_MDLINT or found on the PATH.
MDLINT = os.environ.get("JOURNAL_MDLINT") or shutil.which("markdownlint-cli2")


class SessionCase(unittest.TestCase):
    """A throwaway vault and state root, so no test touches the real ones."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.vault = self.tmp / "vault"
        self.daily = self.vault / "daily-notes"
        self.daily.mkdir(parents=True)
        (self.vault / "templates").mkdir()
        (self.vault / "templates" / "Daily Note.md").write_text(TEMPLATE, encoding="utf-8")
        self.state = self.tmp / "state"
        self.sessions = self.vault / "AI" / "sessions"
        self.map = self.state / "sessions.json"
        # Today's keys, as a config from before vault.area and
        # journal.dailyNote holds them, so no test reads the real config.
        self.config_file = self.tmp / "config.json"
        self.config()
        patcher = mock.patch.dict(os.environ, {
            "JOURNAL_VAULT": str(self.vault),
            "JOURNAL_STATE_ROOT": str(self.state),
            "JOURNAL_CONFIG": str(self.config_file),
        })
        patcher.start()
        self.addCleanup(patcher.stop)

    def config(self, vault: dict | None = None, journal: dict | None = None) -> None:
        """TODAY's config with the keys of `vault` and `journal` added."""
        values = json.loads(json.dumps(TODAY))
        values["vault"]["root"] = str(self.vault)
        values["vault"].update(vault or {})
        values["journal"].update(journal or {})
        self.config_file.write_text(json.dumps(values), encoding="utf-8")

    def write(self, body=BODY, d=D, title=TITLE, domains=("claude-code",),
              description="Wrote the session note writer.", session=SESSION):
        return sn.write(session, title, list(domains), description, body, d)

    def body_file(self, text: str) -> Path:
        path = self.tmp / "body.md"
        path.write_text(text, encoding="utf-8")
        return path

    def run_cli(self, *args: str, attended: str | None = "1",
                session: str | None = SESSION) -> subprocess.CompletedProcess:
        env = subprocess_env(JOURNAL_VAULT=str(self.vault),
                             JOURNAL_STATE_ROOT=str(self.state),
                             JOURNAL_CONFIG=str(self.config_file),
                             PYTHONDONTWRITEBYTECODE="1")
        # The suite's own shell is an attended session with an id, so both
        # are pinned here, never inherited.
        for name, value in (("CLAUDE_CODE_SESSION_ATTENDED", attended),
                            ("CLAUDE_CODE_SESSION_ID", session)):
            env.pop(name, None)
            if value is not None:
                env[name] = value
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / "session_note.py"), *args],
            capture_output=True, text=True, encoding="utf-8", env=env)

    def cli_write(self, body: str = BODY, *extra: str, **kwargs) -> subprocess.CompletedProcess:
        return self.run_cli("write", "--title", TITLE, "--domain", "claude-code",
                            "--description", "Wrote the session note writer.",
                            "--body-file", str(self.body_file(body)),
                            "--date", D.isoformat(), *extra, **kwargs)

    def text(self, rel: str = REL) -> str:
        return (self.vault / rel).read_text(encoding="utf-8")

    def files(self) -> list[str]:
        """Every file this could have written: the area, the daily notes, the state."""
        found = []
        for root in (self.vault / "AI", self.daily, self.state):
            if root.exists():
                found += [p.relative_to(self.tmp).as_posix() for p in root.rglob("*") if p.is_file()]
        return sorted(found)

    def assertWroteNothing(self):
        self.assertEqual(self.files(), [])
        # Not even a folder: lock_path() alone would make the state root.
        self.assertFalse(self.state.exists())
        self.assertFalse((self.vault / "AI").exists())


class Create(SessionCase):
    def test_a_new_session_creates_the_note_with_the_day_link(self):
        path = self.write()
        self.assertEqual(path, self.vault / REL)
        self.assertEqual(self.text(), (
            "---\n"
            "type: session\n"
            "domain: [claude-code]\n"
            "updated: 2026-10-17\n"
            'description: "Wrote the session note writer."\n'
            f"generated: claude/{SESSION}\n"
            "---\n"
            "\n"
            "# Memory system\n"
            "\n"
            f"Day: [[{DAY}]]\n"
            "\n"
            "## Done\n"
            "\n"
            "Wrote the writer.\n"
            "\n"
            "## Next\n"
            "\n"
            "Wire the Stop hook.\n"
        ))
        # The link must resolve, or a link check fails: the daily note is made
        # from the template when the day has none yet.
        self.assertEqual((self.daily / f"{DAY}.md").read_text(encoding="utf-8"), TEMPLATE)
        self.assertEqual(json.loads(self.map.read_text(encoding="utf-8")), {SESSION: REL})

    def test_the_day_link_names_the_existing_german_daily_note(self):
        # A phone names a day in German when it writes first.
        german = self.daily / "Samstag, 17. Okt. 2026 (W42).md"
        german.write_text("Vom Handy.\n", encoding="utf-8")
        self.write()
        self.assertIn("Day: [[Samstag, 17. Okt. 2026 (W42)]]\n", self.text())
        self.assertEqual(sorted(p.name for p in self.daily.iterdir()), [german.name])
        self.assertEqual(german.read_text(encoding="utf-8"), "Vom Handy.\n")

    def test_the_sections_follow_the_section_order_whatever_the_body_order(self):
        self.write("## Next\n\nLater.\n\n## Done\n\nFirst.\n\n## Done\n\nAlso done.\n")
        self.assertTrue(self.text().endswith(
            f"Day: [[{DAY}]]\n\n## Done\n\nFirst.\n\nAlso done.\n\n## Next\n\nLater.\n"))

    def test_a_new_note_gets_the_vaults_file_mode(self):
        # mkstemp creates at 0600; every other note in the vault is 0644.
        self.assertEqual(self.write().stat().st_mode & 0o777, 0o644)

    def test_the_note_and_the_map_are_replaced_atomically(self):
        real_replace = os.replace
        calls = []

        def spy(src, dst):
            calls.append((Path(src), Path(dst)))
            return real_replace(src, dst)

        with mock.patch("daily_note.os.replace", side_effect=spy):
            path = self.write()
        self.assertEqual([dst for _, dst in calls], [path, self.map])
        for src, dst in calls:
            self.assertEqual(src.parent, dst.parent)
            self.assertTrue(src.name.endswith(".part"), src.name)
            self.assertFalse(src.exists())

    def test_concurrent_sessions_all_land_in_the_map(self):
        # Without the lock across the map's read-modify-write, two sessions
        # read the same map and the second write drops the first one's entry.
        import concurrent.futures as cf
        ids = [f"{i:08d}-0000-4000-8000-000000000000" for i in range(8)]
        with cf.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda s: self.write(session=s, title=f"Topic {s[:8]}"), ids))
        mapped = json.loads(self.map.read_text(encoding="utf-8"))
        self.assertEqual(sorted(mapped), ids)
        self.assertEqual(len(list(self.sessions.iterdir())), 8)


class Frontmatter(SessionCase):
    def test_the_frontmatter_is_flat(self):
        self.write(description='Fixed "the" lint: twice')
        self.write("## Findings\n\nOne.\n", d=D2, domains=("vault",),
                   description='Fixed "the" lint: twice, again')
        meta, _ = parse_frontmatter(self.text())
        self.assertEqual(meta["domain"], ["claude-code", "vault"])
        self.assertEqual(meta["description"], 'Fixed "the" lint: twice, again')
        self.assertFalse([key for key, value in meta.items() if isinstance(value, dict)])

    def test_the_frontmatter_round_trips_through_the_lints_reader(self):
        description = 'Fixed "quoted" text: a colon, a back\\slash and Prüfung – ja'
        path = self.write(description=description, domains=("claude-code", "odd, domain"))
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        self.assertEqual(meta, {
            "type": "session",
            "domain": ["claude-code", "odd, domain"],
            "updated": "2026-10-17",
            "description": description,
            "generated": f"claude/{SESSION}",
        })
        self.assertTrue(body.startswith("\n# Memory system\n"))

    def test_an_append_updates_block_form_frontmatter_and_keeps_other_keys(self):
        # Obsidian rewrites a flow list in block form whenever it saves the
        # frontmatter, so the append has to read and replace both forms.
        path = self.write(description="Old.")
        path.write_text(self.text().replace(
            "domain: [claude-code]\n", "domain:\n  - claude-code\naliases:\n  - MS\n"), encoding="utf-8")
        self.write("## Next\n\nMore.\n", d=D2, domains=("vault", "claude-code"),
                   description='New: "quoted".')
        meta, _ = parse_frontmatter(self.text())
        self.assertEqual(meta, {
            "type": "session",
            "domain": ["claude-code", "vault"],
            "aliases": ["MS"],
            "updated": "2026-10-18",
            "description": 'New: "quoted".',
            "generated": f"claude/{SESSION}",
        })


# Frontmatter shapes both readers must agree on, the ones that fail included.
FRONTMATTER_FIXTURES = (
    "---\ntype: session\ndomain: [claude-code, vault]\nupdated: 2026-10-17\n---\n# T\n",
    "---\ndomain:\n  - claude-code\n  - vault\naliases:\n  - MS\n---\nbody\n",
    '---\ndescription: "Fixed \\"the\\" lint: twice"\nother: \'it\'\'s\'\n---\n',
    "---\nlist: ['a, b', \"c\"]\nempty: []\n---\n",
    "---\n# a comment\nkey: value # trailing\nnested:\n  inner: x\n---\n",
    "---\nkey:\n---\n",
    "---\r\ntype: session\r\n---\r\nbody\r\n",
    "no frontmatter\n",
    "---\ntype: session\n",
    "---\nkey: a: b\n---\n",
    "---\nkey: `code`\n---\n",
    "---\n\tkey: x\n---\n",
    "---\nkey: x\nkey: y\n---\n",
    "---\n  key: x\n---\n",
)


def ai_memory_scripts() -> Path | None:
    """The scripts of an ai-memory checkout: JOURNAL_AI_MEMORY_DIR, else
    ~/Git/ai-memory. None when neither holds notes.py."""
    root = Path(os.environ.get("JOURNAL_AI_MEMORY_DIR")
                or Path.home() / "Git" / "ai-memory").expanduser()
    scripts = root / "skills" / "ai-memory" / "scripts"
    return scripts if (scripts / "notes.py").is_file() else None


# Run in a child of its own, so ai-memory's skill_values never meets this
# skill's module of the same name.
_PARSE_ALL = """
import json, sys
sys.path.insert(0, sys.argv[1])
from {module} import parse_frontmatter
out = []
for text in json.load(sys.stdin):
    try:
        meta, body = parse_frontmatter(text)
        out.append(["ok", meta, body])
    except ValueError as exc:
        out.append([type(exc).__name__, str(exc)])
print(json.dumps(out))
"""


def parse_all(scripts: Path, module: str, texts: list[str]) -> list:
    done = subprocess.run(
        [sys.executable, "-I", "-B", "-c", _PARSE_ALL.format(module=module), str(scripts)],
        input=json.dumps(texts), capture_output=True, text=True, check=True,
        env={**os.environ, "AI_MEMORY_CONFIG": os.devnull + ".absent"})
    return json.loads(done.stdout)


@unittest.skipUnless(ai_memory_scripts(), "no ai-memory checkout: set JOURNAL_AI_MEMORY_DIR")
class FrontmatterMatchesAiMemory(SessionCase):
    """frontmatter.py is a copy of ai-memory's reader. On every fixture, and
    on the notes this writer produces, the two read the same."""

    def test_the_copy_reads_as_ai_memory_reads(self):
        self.write(description='Fixed "quoted" text: a colon – ja')
        written = self.text()
        self.write("## Next\n\nMore.\n", d=D2, domains=("vault",), description="Again.")
        texts = [*FRONTMATTER_FIXTURES, written, self.text()]
        ours = parse_all(SCRIPTS, "frontmatter", texts)
        theirs = parse_all(ai_memory_scripts(), "notes", texts)
        self.assertEqual(len(ours), len(texts))
        for text, mine, other in zip(texts, ours, theirs):
            with self.subTest(text=text):
                self.assertEqual(mine, other)
        # The fixtures reach both outcomes, so agreement is not trivial.
        self.assertTrue(any(r[0] == "ok" for r in ours))
        self.assertTrue(any(r[0] == "FrontmatterError" for r in ours))


class Append(SessionCase):
    def test_the_same_session_appends_under_existing_headings(self):
        self.write("## Done\n\nFirst.\n\n## Next\n\nStep one.\n")
        self.write("## Next\n\nStep two.\n\n## Findings\n\nA finding.\n\n## Done\n\nSecond.\n")
        self.assertTrue(self.text().endswith(
            f"# Memory system\n\nDay: [[{DAY}]]\n\n"
            "## Done\n\nFirst.\n\nSecond.\n\n"
            "## Findings\n\nA finding.\n\n"
            "## Next\n\nStep one.\n\nStep two.\n"), self.text())
        self.assertEqual([p.name for p in self.sessions.iterdir()], ["2026-10-17 Memory system.md"])
        self.assertEqual(json.loads(self.map.read_text(encoding="utf-8")), {SESSION: REL})

    def test_a_resumed_session_on_the_next_day_links_both_days(self):
        self.write("## Done\n\nDay one.\n")
        # A new title on the new day: the map, not the title, finds the note.
        path = self.write("## Done\n\nDay two.\n", d=D2, title="Memory system, day two")
        self.assertEqual(path, self.vault / REL)
        self.assertEqual([p.name for p in self.sessions.iterdir()], ["2026-10-17 Memory system.md"])
        text = self.text()
        self.assertIn(f"\nDay: [[{DAY}]], [[{DAY2}]]\n", text)
        self.assertIn("\nupdated: 2026-10-18\n", text)
        self.assertTrue(text.endswith("## Done\n\nDay one.\n\nDay two.\n"), text)
        self.assertTrue((self.daily / f"{DAY2}.md").exists())
        # The same day again adds no second link.
        self.write("## Done\n\nLater on day two.\n", d=D2)
        self.assertEqual(self.text().count(f"[[{DAY2}]]"), 1)

    def test_another_session_with_the_same_title_on_the_same_day_appends(self):
        self.write("## Done\n\nMine.\n")
        other = "11111111-2222-4333-8444-555555555555"
        path = self.write("## Done\n\nTheirs.\n", session=other)
        self.assertEqual(path, self.vault / REL)
        self.assertTrue(self.text().endswith("## Done\n\nMine.\n\nTheirs.\n"))
        self.assertIn(f"generated: claude/{SESSION}\n", self.text())
        self.assertEqual(json.loads(self.map.read_text(encoding="utf-8")), {SESSION: REL, other: REL})

    def test_an_append_keeps_a_crlf_note_crlf(self):
        path = self.write("## Done\n\nFirst.\n\n## Next\n\nStep one.\n")
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        title = b"# Memory system\r\n"
        self.write("## Findings\n\nOne.\n\n## Next\n\nStep two.\n", d=D2,
                   domains=("vault",), description="Again.")
        after = path.read_bytes()
        self.assertEqual(after.count(b"\n"), after.count(b"\r\n"))
        self.assertIn(b"\r\n" + title, after)
        self.assertTrue(after.endswith(b"Step one.\r\n\r\nStep two.\r\n"), after)

    def test_an_append_puts_back_a_missing_day_line(self):
        path = self.write("## Done\n\nDay one.\n")
        path.write_text(self.text().replace(f"Day: [[{DAY}]]\n\n", ""), encoding="utf-8")
        self.write("## Done\n\nDay two.\n", d=D2)
        self.assertIn(f"\n# Memory system\n\nDay: [[{DAY2}]]\n\n## Done\n", self.text())

    def test_a_stale_or_foreign_map_entry_is_ignored(self):
        outside = self.vault / "Elsewhere.md"
        outside.write_text("Not a session note.\n", encoding="utf-8")
        for rel in ("AI/sessions/2026-10-01 Gone.md", "Elsewhere.md", "../outside.md"):
            with self.subTest(rel=rel):
                self.state.mkdir(exist_ok=True)
                self.map.write_text(json.dumps({SESSION: rel}), encoding="utf-8")
                self.assertEqual(self.write(), self.vault / REL)
                self.assertEqual(json.loads(self.map.read_text(encoding="utf-8")), {SESSION: REL})
                (self.vault / REL).unlink()
        self.assertEqual(outside.read_text(encoding="utf-8"), "Not a session note.\n")

    def test_a_corrupt_map_is_refused_not_overwritten(self):
        self.state.mkdir()
        for broken in ("{not json", "[]"):
            with self.subTest(broken=broken):
                self.map.write_text(broken, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "sessions.json"):
                    self.write()
                self.assertEqual(self.map.read_text(encoding="utf-8"), broken)
                self.assertFalse(self.sessions.exists())

    def test_a_heading_inside_a_fence_stays_in_its_section(self):
        fenced = "## Findings\n\nThe old note read:\n\n```md\n## Done\n```\n"
        self.write(fenced)
        self.write("## Done\n\nReal.\n")
        self.assertTrue(self.text().endswith(
            f"Day: [[{DAY}]]\n\n## Done\n\nReal.\n\n" + fenced), self.text())


class Titles(SessionCase):
    def test_a_hostile_title_is_one_safe_file(self):
        hostile = "Prüfung – Netz/VLAN: #1 [x]|y"
        self.assertEqual(sn.safe_title(hostile), "Prüfung – Netz VLAN 1 x y")
        self.assertEqual(sn.safe_title('a/b\\c:d#e^f[g]h|i?j*k"l<m>n'),
                         "a b c d e f g h i j k l m n")
        path = self.write(title=hostile)
        self.assertEqual(path.name, "2026-10-17 Prüfung – Netz VLAN 1 x y.md")
        self.assertEqual(path.parent, self.sessions)
        self.assertEqual(self.files(), [
            "state/notes.lock",
            "state/sessions.json",
            f"vault/AI/sessions/{path.name}",
            f"vault/daily-notes/{DAY}.md",
        ])
        self.assertIn(f"\n# {hostile}\n", path.read_text(encoding="utf-8"))

    def test_a_title_or_description_with_nothing_left_is_refused(self):
        with self.assertRaisesRegex(ValueError, "title"):
            self.write(title=" /// ")
        with self.assertRaisesRegex(ValueError, "description"):
            self.write(description=" \n ")
        self.assertWroteNothing()

    def test_note_path_is_the_day_and_the_safe_title(self):
        self.assertEqual(sn.note_path(D, "a: b"), self.sessions / "2026-10-17 a b.md")


class Cli(SessionCase):
    def test_a_cli_write_prints_what_it_did(self):
        done = self.cli_write()
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertEqual(done.stdout, f"created {self.vault / REL}\n")
        done = self.cli_write("## Done\n\nMore.\n")
        self.assertEqual(done.stdout, f"appended {self.vault / REL}\n")

    def test_the_session_defaults_to_the_environment(self):
        self.assertEqual(self.cli_write().returncode, 0)
        self.assertIn(f"generated: claude/{SESSION}\n", self.text())
        other = "11111111-2222-4333-8444-555555555555"
        self.assertEqual(self.cli_write("## Done\n\nX.\n", "--session", other).returncode, 0)
        self.assertEqual(sorted(json.loads(self.map.read_text(encoding="utf-8"))),
                         sorted([SESSION, other]))

    def test_an_unknown_heading_is_refused_with_exit_2(self):
        done = self.cli_write("## Done\n\nX.\n\n## Notes\n\nY.\n")
        self.assertEqual(done.returncode, 2)
        self.assertIn("'Notes'", done.stderr)
        self.assertNotIn("Traceback", done.stderr)
        self.assertWroteNothing()

    def test_an_empty_body_a_preamble_or_no_session_id_is_refused_with_exit_2(self):
        cases = {
            "empty": ("", SESSION, "empty"),
            "blank": ("  \n\n", SESSION, "empty"),
            "headings only": ("## Done\n\n## Next\n", SESSION, "empty"),
            "preamble": ("Some text.\n\n## Done\n\nX.\n", SESSION, "before the first"),
            "no session": (BODY, None, "session"),
            "odd session": (BODY, "../x", "session"),
        }
        for name, (body, session, says) in cases.items():
            with self.subTest(name):
                done = self.cli_write(body, session=session)
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn(says, done.stderr)
                self.assertNotIn("Traceback", done.stderr)
                self.assertWroteNothing()

    def test_an_unattended_session_is_refused_with_exit_3(self):
        # A headless `claude -p` run has CLAUDE_CODE_SESSION_ATTENDED=0. Only
        # exactly "1" writes, and the refusal comes before --dry-run.
        for value in ("0", "", "true", " 1", None):
            for extra in ((), ("--dry-run",)):
                with self.subTest(attended=value, extra=extra):
                    done = self.cli_write(BODY, *extra, attended=value)
                    self.assertEqual(done.returncode, 3, done.stderr)
                    self.assertEqual(done.stdout, "")
                    self.assertIn("attended", done.stderr)
                    self.assertWroteNothing()

    def test_dry_run_writes_nothing(self):
        done = self.cli_write(BODY, "--dry-run")
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertTrue(done.stdout.startswith(f"would have created {self.vault / REL}\n"), done.stdout)
        self.assertIn(f"\n# Memory system\n\nDay: [[{DAY}]]\n", done.stdout)
        # Not the note, not the daily note, not even the state directory.
        self.assertWroteNothing()

        self.assertEqual(self.cli_write().returncode, 0)
        before = {rel: (self.tmp / rel).read_bytes() for rel in self.files()}
        done = self.run_cli("write", "--title", "Ignored", "--domain", "vault",
                            "--description", "Day two.", "--body-file",
                            str(self.body_file("## Findings\n\nNew.\n")),
                            "--date", D2.isoformat(), "--dry-run")
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertTrue(done.stdout.startswith(f"would have appended {self.vault / REL}\n"), done.stdout)
        self.assertIn(f"Day: [[{DAY}]], [[{DAY2}]]\n", done.stdout)
        self.assertIn("## Findings\n\nNew.\n", done.stdout)
        self.assertEqual({rel: (self.tmp / rel).read_bytes() for rel in self.files()}, before)


class Markdownlint(SessionCase):
    @unittest.skipUnless(MDLINT and Path(MDLINT).expanduser().exists(),
                         "markdownlint-cli2 is not installed")
    def test_the_note_passes_markdownlint(self):
        (self.vault / ".markdownlint-cli2.jsonc").write_text(VAULT_MDLINT_CONFIG, encoding="utf-8")
        long_line = "A sentence that runs well past the eighty columns MD013 would allow. " * 3
        self.write(f"## Done\n\n{long_line.strip()}\n\n- One item.\n- Another.\n\n"
                   "## Next\n\nStep.\n", title="Prüfung – Netz/VLAN: #1 [x]|y")
        self.write("## Findings\n\n```bash\necho hi\n```\n\n## Next\n\nStep two.\n", d=D2)
        # A note markdownlint must flag, so a clean session note proves the
        # run read the folder rather than nothing at all.
        (self.sessions / "control.md").write_text("No title here.\n", encoding="utf-8")
        done = subprocess.run([str(Path(MDLINT).expanduser()), "AI/sessions/**/*.md"],
                              cwd=self.vault, capture_output=True, text=True, timeout=60)
        flagged = set(re.findall(r"^(AI/sessions/[^:]+\.md):\d+", done.stderr, re.M))
        self.assertEqual(flagged, {"AI/sessions/control.md"}, done.stderr)




class TestWithoutTheVaultValue(SessionCase):
    def test_a_write_without_a_vault_exits_2_and_names_the_key(self):
        env = subprocess_env(JOURNAL_STATE_ROOT=str(self.state), PYTHONDONTWRITEBYTECODE="1",
                             CLAUDE_CODE_SESSION_ATTENDED="1", CLAUDE_CODE_SESSION_ID=SESSION)
        env.pop("JOURNAL_VAULT", None)
        done = subprocess.run(
            [sys.executable, "-B", str(SCRIPTS / "session_note.py"), "write", "--title", TITLE,
             "--domain", "claude-code", "--description", "D",
             "--body-file", str(self.body_file(BODY))],
            capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn(f"set `vault.root` in `{os.devnull}.absent`", done.stderr)
        self.assertFalse(self.sessions.exists())


class DefaultConfig(SessionCase):
    def test_default_config_unchanged(self):
        path = self.write()
        self.assertEqual(path, self.vault / REL)
        self.assertEqual(path.read_bytes(), FROZEN_CREATED.encode("utf-8"))
        self.write(body=APPENDED, d=D2, domains=("journal",), description="Wired the Stop hook.")
        self.assertEqual(path.read_bytes(), FROZEN_APPENDED.encode("utf-8"))
        self.assertEqual(self.map.read_bytes(), FROZEN_MAP.encode("utf-8"))
        self.assertEqual(sorted(p.name for p in self.daily.iterdir()),
                         [f"{DAY}.md", f"{DAY2}.md"])


class DailyOff(SessionCase):
    def setUp(self):
        super().setUp()
        self.config(journal={"dailyNote": False})

    def test_daily_off_no_day_link(self):
        path = self.write()
        self.assertEqual(path.read_text(encoding="utf-8"),
                         FROZEN_CREATED.replace(f"Day: [[{DAY}]]\n\n", ""))
        self.assertNotIn("Day:", path.read_text(encoding="utf-8"))
        self.assertEqual(list(self.daily.iterdir()), [])

    def test_daily_off_append(self):
        path = self.write()
        self.write(body=APPENDED, d=D2, domains=("journal",), description="Wired the Stop hook.")
        self.assertEqual(path.read_text(encoding="utf-8"),
                         FROZEN_APPENDED.replace(f"Day: [[{DAY}]], [[{DAY2}]]\n\n", ""))
        self.assertEqual(list(self.daily.iterdir()), [])

    def test_daily_off_dry_run_reads_no_daily_note(self):
        done = self.run_cli("write", "--title", TITLE, "--domain", "claude-code",
                            "--description", "D", "--body-file", str(self.body_file(BODY)),
                            "--dry-run")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("Day:", done.stdout)

    def test_a_daily_note_value_that_is_not_a_bool_is_refused(self):
        self.config(journal={"dailyNote": "no"})
        with self.assertRaisesRegex(ValueError, "`journal.dailyNote`"):
            self.write()
        self.assertWroteNothing()


class Area(SessionCase):
    def test_area_default_is_ai(self):
        self.assertEqual(sn.sessions_dir(), self.vault / "AI" / "sessions")

    def test_area_empty(self):
        for value in ("", ".", " "):
            with self.subTest(value=value):
                self.config(vault={"area": value})
                path = self.write(session=f"s{len(value)}")
                self.assertEqual(path, self.vault / "sessions" / "2026-10-17 Memory system.md")
                self.assertEqual(json.loads(self.map.read_text(encoding="utf-8"))[f"s{len(value)}"],
                                 "sessions/2026-10-17 Memory system.md")

    def test_area_trailing_slash(self):
        self.config(vault={"area": "AI/"})
        self.assertEqual(self.write(), self.vault / REL)
        self.config(vault={"area": "Work/AI"})
        self.assertEqual(sn.sessions_dir(), self.vault / "Work" / "AI" / "sessions")

    def test_area_rejected(self):
        for value in ("/abs", "../x", "a/../../x", "a\\b", 3, ["AI"]):
            with self.subTest(value=value):
                self.config(vault={"area": value})
                with self.assertRaisesRegex(ValueError, "`vault.area`"):
                    sn.area()
                with self.assertRaisesRegex(ValueError, "`vault.area`"):
                    self.write()
                self.assertWroteNothing()
                self.assertFalse((self.vault / "sessions").exists())

    def test_a_rejected_area_exits_2_and_names_the_key(self):
        self.config(vault={"area": "../x"})
        done = self.cli_write()
        self.assertEqual(done.returncode, 2)
        self.assertIn(f"`vault.area` in `{self.config_file}` must not hold ..", done.stderr)


if __name__ == "__main__":
    unittest.main()
