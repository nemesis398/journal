# Changelog

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
