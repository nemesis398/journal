# journal

A [Claude Code](https://claude.com/claude-code) skill that writes a session's
noteworthy work into a session note in an [Obsidian](https://obsidian.md)
vault: a decision whose reasoning will matter later, a non-obvious finding, or
a finished artifact. A Stop hook reminds the session once, when it changed
files and wrote no note.

## What it does

- **Writes one note per session** in `sessions/` under the vault's area,
  `AI/sessions/` by default, under up to
  five fixed sections (`Done`, `Decisions`, `Findings`, `Memory candidates`,
  `Next`). A resumed session extends the note it started, even on a later day.
- **Links the day.** The note links its daily note in `daily-notes/`. To see
  the day's session notes inside the daily note, create an Obsidian base that
  lists the notes in the sessions folder linking to the current file, and
  embed it in your daily note template; the plugin ships no base. With
  `journal.dailyNote` set to `false`, the note links no day and the skill
  never reads or creates a daily note.
- **Checks the prose first.** The entry goes through the `prose` skill's
  checker before it is written.
- **Refuses a headless run.** Only an interactive main session writes a note.
- **Never touches the protected section** of the daily note, the one heading
  that is the user's alone.

## Install

In Claude Code, add the repository as a marketplace and install the plugin:

```text
/plugin marketplace add nemesis398/journal
/plugin install journal@journal
```

It needs `python3` (3.10 or later) on the PATH, and runs on Linux and macOS
only: the scripts lock the notes with `fcntl`, which Windows lacks.

The skill grants itself the one command its first line runs, the values
render (`allowed-tools` in `SKILL.md`), so that line needs no approval of its
own. The skill itself still needs your approval once, the first time it
loads.

## Config

The skill reads its values from the file named by `JOURNAL_CONFIG`, else
`${XDG_CONFIG_HOME:-~/.config}/journal/config.json`. Keys nest:

```json
{
  "user": { "name": "Alice" },
  "vault": { "root": "/home/alice/Notes", "commit": "notes-commit" },
  "journal": {
    "protectedSection": "## Logbook",
    "languageRule": "English for tooling, German for the client.",
    "proseCheck": "~/bin/prose-check",
    "check": "notes-lint"
  }
}
```

| Key | Type | What it is |
| --- | --- | --- |
| `user.name` | string, optional | the user's name, shown in the Values block when set; the skill never stops without it |
| `vault.root` | string, an absolute path, required | the Obsidian vault |
| `vault.area` | string, a relative path, optional | the folder inside the vault that holds `sessions/`; default `AI`, and `""` or `.` is the vault root. A trailing slash is dropped. An absolute path, `..` or a backslash is invalid, and the skill stops on it |
| `vault.commit` | string, a command, optional | what commits the session note, run as `COMMAND MESSAGE PATH...`; the skill then never runs `git commit`. Without it the commit step is off: the note stays uncommitted and the skill says so |
| `journal.dailyNote` | boolean, optional | `false` turns off every step about the daily note: no Day link, no daily note created, and no need for `journal.protectedSection`; default `true` |
| `journal.protectedSection` | string, a heading line, required while the daily note is on | the section of the daily note that is the user's alone: the skill never writes there, and puts its Capture section above it |
| `journal.languageRule` | string, Markdown, required | which language a session note is written in, by subject |
| `journal.proseCheck` | string, a path or a command name | the `prose` checker; default `prose-check` on the PATH |
| `journal.check` | string, a command, optional | what checks the vault after the write, run as is from the vault root. Without it the check is skipped and the skill says so |

When the skill loads, its first line runs `scripts/skill_values.py render`,
which prints the values as a block the model reads. A key that is missing or
of the wrong type prints a line telling the model to stop and which key to
set in which file; a missing, empty or malformed file counts as every key
missing. The skill stops without `vault.root`, `journal.protectedSection` and
`journal.languageRule`, so set all three before its first use; with
`journal.dailyNote` set to `false`, it needs no `journal.protectedSection`.
An invalid `vault.area` or `journal.dailyNote` stops it too. Without a
checker the prose gate alone is off, and the skill says so in its reply. The
Stop hook stays quiet while any key the skill stops without is missing or
invalid (`vault.root`, which `JOURNAL_VAULT` can stand in for,
`journal.protectedSection` while the daily note is on, and
`journal.languageRule`), and says so once per session in one line on stderr
that names the file.

A plugin install of `prose` puts `prose-check` in a versioned folder of the
plugin cache, which changes with every update of that plugin and is not on
the PATH. So set `journal.proseCheck` to a stable path, such as a symlink you
keep pointing at the current version:

```json
{ "journal": { "proseCheck": "/path/to/stable/prose-check" } }
```

The domain list a note's `--domain` is checked against belongs to the
`ai-memory` skill (`memory.domains` in its config).

`JOURNAL_DISABLED=1` turns the Stop hook off. Its run state lives in
`~/.local/state/agent-journal/`, never in the vault.

## Vault layout

The scripts expect the vault's notes in fixed places: the session notes in
`sessions/` under `vault.area` (`AI/sessions/` by default), the daily notes
in `daily-notes/` named in the format `dddd, DD. MMM Y ([W]W)`,
and the daily note's template at `templates/Daily Note.md` (neither is needed with `journal.dailyNote: false`).

When the day has no daily note yet, the skill creates one named
`<Weekday>, DD. Mon YYYY (W<n>).md`, in English and with an unpadded week,
for example `Friday, 13. Feb 2026 (W7).md`. It fills it from the template,
or with a Today and a Capture section when there is none. A note that a
device in another locale named first, such as `Montag, 10. Aug. 2026
(W33).md`, is found and used instead.

## Tests

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s skills/journal/tests
```

The markdownlint case runs when `markdownlint-cli2` is on the PATH or named by
`JOURNAL_MDLINT`. `evals/` holds trigger cases for `claude plugin eval`:

```sh
claude plugin eval . --runs 3 --scaffold --allow-tools 'Bash(python3:*)' --no-publish
```

Each case's `setup.sh` is its config fixture: it writes a complete config
and an empty vault into the run's sandbox, which is why the command needs
`--scaffold`. The values render is a Bash call, so the cases and the command
grant `Bash(python3:*)`, and a Bash-granting eval needs a machine whose
sandbox permits it; Claude Code refuses one, for example, while `~/.ssh`
holds a symbolic link. `--no-publish` keeps the report local instead of
uploading it to your claude.ai account.

CI checks the manifests, the Markdown, that no em dash slipped in, and runs
the tests.

## License

[MIT](LICENSE)
