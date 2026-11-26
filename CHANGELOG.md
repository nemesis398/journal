# Changelog

## 0.3.0

- `session_note.py write` takes an optional, repeatable `--project NAME`: a
  new note gets `project:` with one `"[[NAME]]"` line per hub, and a later
  call adds hubs to it. With none, there is no `project` key. The skill says
  to pick the name from the vault's `type: project` notes and never to invent
  one.
- The frontmatter follows the vault's style: lists one item per line (`domain`
  was `[a, b]`, also when a later call adds a domain), keys in the order
  `type`, `project`, `domain`, `updated`, `description`, `generated`. A key an older note lacks is added where the vault's key order
  puts it, not after `description`.

## 0.2.0

- `vault.area` places the session notes: they go to `sessions/` under it,
  `AI` by default, and `""` or `.` is the vault root. An absolute path, `..`
  or a backslash is invalid: the Values block says so, the writer refuses it
  with exit 2, and the Stop reminder stays quiet.
- `journal.dailyNote` set to `false` turns the daily note off: a session note
  gets no Day link, no daily note is read or created, and
  `journal.protectedSection` is no longer needed by the skill or the Stop
  reminder. It defaults to `true`, so a config without either key works as
  before.

## 0.1.0

- The journal skill as a plugin of its own: the session note writer, the
  daily note mechanics, and the Stop reminder as a plugin hook.
- The user's values come from `JOURNAL_CONFIG`, else
  `${XDG_CONFIG_HOME:-~/.config}/journal/config.json`, and reach the skill's
  text as a Values block when it loads.
- The prose gate runs the checker that `journal.proseCheck` names, else
  `prose-check` on the PATH; without one the gate is off and says so.
- The Stop reminder stays quiet while any key the skill stops without is
  missing, and says why in one line on stderr, once per session.
- `vault.commit` names the command that commits the session note; without it
  the note stays uncommitted. `user.name` never stops the skill.
- `journal.check` names the command that checks the vault after a write;
  without it the check is skipped and the skill says so.
- The skill grants itself its values render in `allowed-tools`, and the Stop
  hook's command ends in `|| true`, so a missing script never blocks a stop.
