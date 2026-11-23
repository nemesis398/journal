---
name: journal
description: >-
  Write the session's noteworthy work into its session note in the notes
  vault: a decision whose reasoning will matter later, a non-obvious finding,
  or a finished artifact, under five fixed sections and in the right language.
  Use this whenever a piece of work finishes and before a session ends, in
  every project and from every directory, when a Stop hook asks for it, or
  when the user says journal it, write it up, put that in the daily note, or
  document this. Only an interactive main session writes one. Prefer this
  over leaving the work only in the transcript, because a transcript is not
  searchable a month later and the session note is.
allowed-tools: Bash(python3 -B "${CLAUDE_SKILL_DIR}/scripts/skill_values.py" render)
---

# journal
!`python3 -B "${CLAUDE_SKILL_DIR}/scripts/skill_values.py" render`

The Values block above holds the user's values for this skill. A line that
says **Stop.** names a value that is not set: stop, and tell the user which
value to set in which file, and so does a line that says **invalid**. A line
that says a step is off holds for that step alone. The line
`journal.dailyNote`: off holds for every step about the daily note: skip each
one.

A session note records what one session did that is worth finding again.
Months later the user finds it by search or through the day: the note links
its daily note, which can embed the day's session notes through a base the
user keeps. Agents never journal into the daily note itself. When the daily
note is off, the note links no day and search alone finds it. Your job is
to leave behind the entries that make a fact findable, and nothing else.

## The bar

Write an entry when one of these is true:

- **A decision was made and the reasoning matters.** Not the decision alone.
  Why the alternatives lost is the part that is expensive to reconstruct.
- **Something non-obvious was found**, above all a misdiagnosis you corrected.
  What the error message said and why acting on it would have been wrong is
  worth more than the fix.
- **An artifact was finished.** A script, a note, a config, a document.

Routine edits, chores and questions you answered stay out. So does work you
started and did not finish; that belongs in a handoff, not here.

If you cannot tell, ask the user in the interactive question UI. When no
answer can come, because the user said not to ask or left the session to run
on its own, write it and put `%%journal:unsure%%` on its own line after the
entry, ahead of any `→` line.

**Only an interactive main session writes a session note.** A subagent, a
workflow, a hook, a cron run and `--print` never do. The script refuses a
headless run, but a subagent inherits its parent's session id and would write
into the parent's note, so that half of the rule is yours to keep. A subagent
puts its candidate entry in its report to the parent.

## Never the protected section

When the daily note is off, skip this section: there is no daily note to
protect. The section of the daily note that `journal.protectedSection` in Values names
is the user's alone: the user writes it, and it feeds another document that
is compiled from it, so a line the skill puts there ends up in that document
as if the user had written it. Do not write to it, do not reword it, do not
mirror your entry into it. The scripts never touch it either: a daily note
they create or extend gets its Capture section above it.

## Sections, domain and language

The body is Markdown under up to five `##` headings, in this order, each one
only when it has something in it:

- `## Done`: the artifacts finished, one bullet each.
- `## Decisions`: what was decided and why the alternatives lost.
- `## Findings`: what turned out to be true or false.
- `## Memory candidates`: facts that might earn a note in the memory folder
  of `ai-memory`. They
  are searchable but never injected, and the user decides later which to
  promote. The `ai-memory` skill holds the tests a memory must pass,
  and the form of the one other bullet here: `archive`, for a memory found
  wrong when the user could not be asked.
- `## Next`: what follows, in a line or two. Where unfinished work stands
  belongs in a handoff.

The headings stay English whatever the language of the text under them.

**The domain names the subject.** Pass `--domain` once per domain. A domain
is a key of `memory.domains` in the ai-memory skill's config, such as
`claude-code`, and its lint warns on any other.

**Language follows subject, not folder.** Which subject takes which language
is `journal.languageRule` in Values.

**Write like the entries already there.** Read the two newest notes in the
`sessions/` folder under `vault.area` in Values before your first entry of a
session. Entries are full
sentences, not bullet dumps: what was decided, what was measured, what turned
out to be false. The one sentence that matters most is set in bold, for
example a corrected misdiagnosis or the number that closes a question. An
error message that misled and was rejected is quoted in italics, with the
reasoning for rejecting it stated next to it. Counts and measurements are
exact, not rounded: "1,192 characters", "36 computed colors", "0 violations
of 4,590". A table earns its place when a section holds three or more parallel
rows of the same shape, one column per fact. When a permanent note carries the
detail, close your own text for that section with one link line, several notes
joined by ` · `: `→ [[Backup Plan]] · [[Vault]]`. It comes after any
`%%journal:unsure%%` marker. A later write appends below it, so a section can
hold several `→` lines, one per write, and that is fine. Other tools may
read the line, so keep it bare.

## The prose gate

Every entry is read by a human on a phone. Compose the body in the session's
scratchpad, never in `/tmp` directly or in the vault, check it, fix what it
finds, then write:

```bash
PROSE_CHECK "$SCRATCH/session.md"
```

`PROSE_CHECK` stands for the path of `journal.proseCheck` in Values, the
`prose` skill's checker. When Values says the prose gate is off, follow what
that line says and go on to the write: the gate is off, not the skill.

House rules, and the `prose` skill is where they live: no em dashes in either
language, the spaced en dash as the German Gedankenstrich and sparingly, emoji
only as heading labels, German dates as `09.08.2026` and English as
`2026-08-09`. An exit 2 or an `LT-CHUNK-FAILED` finding is never a clean
run: handle each as the `prose` skill says under its loop, and report what
the final run said.

## Writing it

```bash
python3 -B "${CLAUDE_SKILL_DIR}/scripts/session_note.py" write \
  --title "Questions go in the interactive UI" \
  --domain claude-code \
  --description "Why decisions are asked in the question dialog" \
  --body-file "$SCRATCH/session.md" \
  [--dry-run]
```

The title becomes the note's H1 and, after the date, its filename. Keep it a
plain phrase: no trailing punctuation, which markdownlint flags; no `#word`,
which Obsidian turns into an inline tag that nothing catches; and no wikilink
or Markdown link. The description is one line on what the session did, and it
is what the daily note's embed shows, when the daily note is on. On a later write, pass a description
that covers the whole session, because it replaces the old one.

The script finds the note on its own. A resumed session keeps its session id
and writes into the note it started, even on a later day, and so does a second
write with the same title on the same day. Each section's text goes under its
existing heading. Exit 2 means it refused the input, such as an empty body or
a heading outside the five; fix it and run again. Exit 2 with "set
`vault.root` in" a file, or one that names `vault.area` or
`journal.dailyNote`, means the skill is not set up: stop and tell the user
which value to fix in which file. Exit 3 means a headless run, so write nothing and report the entry
instead.

`--dry-run` prints the resulting note without writing it. Use it when you are
unsure the entry will land where you think. A dry run writes nothing, yet the
Stop hook counts it as the entry, so run the command again without
`--dry-run`.

Then confirm the vault is still sound, from the vault root:

```bash
JOURNAL_CHECK
```

`JOURNAL_CHECK` stands for the value of `journal.check` in Values, the
command that checks the vault. When Values says the vault check is off, skip
it and say in your reply that the vault was not checked.

## Committing it

When Values lists `vault.commit`, commit the session note with that command
and never with `git commit`, as `COMMAND MESSAGE PATH...`, naming the note
the writer printed:

```bash
VAULT_COMMIT "docs(ai): session note" "NOTE_PATH"
```

`VAULT_COMMIT` stands for the value of `vault.commit` in Values, and
`NOTE_PATH` for the path the writer printed. Take it from that line rather
than build it: `vault.area` decides the folder. When Values
says the commit step is off, leave the note uncommitted and say so in your
reply.

## What this skill does not do

It does not move or rename notes; that is Obsidian's job, because only
Obsidian rewrites the links. It does not file knowledge into permanent notes;
that is a later harvest. It does not write memory notes; that is `ai-memory`. It
does not record where work stands for the next session; that is `handoff`. It
writes what happened, in the session it happened.
