"""The personal values of the journal skill, read from its config file.

The file is the one `JOURNAL_CONFIG` names, else
`${XDG_CONFIG_HOME:-~/.config}/journal/config.json`: one JSON object whose
keys nest (`{"user": {"name": "Alice"}}` holds `user.name`), values only,
never a secret.

A key that is missing, of another type, an empty string, or an empty object
or list counts as not set. A file that is missing, empty or not a JSON object
reads as no values at all. Nothing here raises except `require`, whose
message is the one sentence a script or hook stops with.

`render` prints the Values block SKILL.md opens with: one line per key of
TEXT_KEYS, or instead the sentence that says what to set where; for a key of
STEPS the step that is off and how to go on without it, for a key of OPTIONAL
nothing at all. It exits 0 whatever the file holds, and an error inside it
prints a Stop line. Any other argument is a usage error and exits 2.
`missing` names the keys whose absence prints a Stop line.

The block above the body line is this skill's own; the body below it is the
same in every skill with values. Stdlib only and no work at import time:
hooks import it on every turn.
"""
from __future__ import annotations

NAME = "journal"
VARIABLE = "JOURNAL_CONFIG"

# The keys the skill's text uses, each with the type it must have, in the
# order the Values block shows them. STEPS and OPTIONAL name some of them.
TEXT_KEYS = [
    ("user.name", str),
    ("vault.root", str),
    ("vault.area", str),
    ("journal.dailyNote", bool),
    ("journal.protectedSection", str),
    ("journal.languageRule", str),
    ("journal.proseCheck", str),
    ("vault.commit", str),
    ("journal.check", str),
]

# Keys whose absence turns off one step, not the skill: the step's name, how
# to go on without it, and for a key that names an executable, `command`, the
# name looked up on the PATH when the key is not set.
STEPS = {
    "journal.proseCheck": {
        "step": "prose gate",
        "command": "prose-check",
        "without": "write the entry without the check, and say in your reply "
                   "that the prose check did not run",
    },
    # Run as `COMMAND MESSAGE PATH...`, naming each file.
    "vault.commit": {
        "step": "commit",
        "without": "leave the session note uncommitted and say so in your "
                   "reply; never commit it with `git commit`",
    },
    # Run as is, after the write, from the vault root.
    "journal.check": {
        "step": "vault check",
        "without": "skip the check after the write, and say in your reply "
                   "that the vault was not checked",
    },
}

# Keys that never stop anything: printed when set, left out when not.
OPTIONAL = {"user.name", "vault.area", "journal.dailyNote"}

DAILY_KEY = "journal.dailyNote"
PROTECTED_KEY = "journal.protectedSection"


def _area(values: dict) -> str:
    """The folder inside the vault that holds the sessions folder; `.` is
    the vault root. A bad value shows its message."""
    import session_note

    try:
        return session_note.area(values).as_posix()
    except session_note.BadArea as exc:
        return f"invalid: {exc}"


def _daily(values: dict) -> str | None:
    """No line while the daily note is on, the default; when off, the line
    that frames every step about it."""
    import session_note

    try:
        on = session_note.daily_note(values)
    except session_note.BadDailyNote as exc:
        return f"invalid: {exc}"
    return None if on else "off. Skip every step about the daily note"


def _protected(values: dict) -> str | None:
    """The protected section, needed only while the daily note is on."""
    value = get(PROTECTED_KEY, str, values)
    if value is None and get(DAILY_KEY, bool, values) is False:
        return "not needed, the daily note is off"
    return value


# Keys that show a value of their own, also when the key is not set.
SHOWN = {"vault.area": _area, DAILY_KEY: _daily, PROTECTED_KEY: _protected}


def needed(values: dict | None = None) -> list[str]:
    """What the skill stops on: `missing` without the protected section when
    the daily note is off, then `vault.area` and `journal.dailyNote` when
    their value is refused. The Stop hook stays quiet while this is not empty."""
    import session_note

    values = load() if values is None else values
    found = [key for key in missing(values)
             if not (key == PROTECTED_KEY and _protected(values) is not None)]
    for key, check in (("vault.area", session_note.area),
                       (DAILY_KEY, session_note.daily_note)):
        try:
            check(values)
        except ValueError:
            found.append(key)
    return found

# ---- body ----
# Everything below this line is the same in every skill that has values.

import json
import os
import shutil
import sys
from pathlib import Path

MISSING = "set `{key}` in `{path}`"


class Missing(LookupError):
    """A value the skill needs is not set."""

    def __init__(self, key: str) -> None:
        super().__init__(MISSING.format(key=key, path=path()))
        self.key = key

    def __str__(self) -> str:
        return MISSING.format(key=self.key, path=path())


def path() -> Path:
    named = os.environ.get(VARIABLE)
    if named:
        return Path(named)
    config = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config) / NAME / "config.json"


def load() -> dict:
    try:
        loaded = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def get(key: str, kind: type = str, values: dict | None = None):
    """The value at the dotted `key`, or None when it is not set as `kind`."""
    node = load() if values is None else values
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    if kind is not bool and isinstance(node, bool):
        return None
    if not isinstance(node, kind):
        return None
    if isinstance(node, str) and not node.strip():
        return None
    if isinstance(node, (dict, list)) and not node:
        return None
    return node


def require(key: str, kind: type = str, values: dict | None = None):
    """The value at `key`, or raise Missing naming it."""
    value = get(key, kind, values)
    if value is None:
        raise Missing(key)
    return value


def show(value) -> str:
    """A value as its Values line shows it: a string trimmed, each further
    line indented into the list item; a list or object as compact JSON."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value).strip().replace("\n", "\n  ")


def command(key: str, values: dict | None = None) -> str | None:
    """Where the executable that the step key names is, or None. The key
    holds a path or a name on the PATH; unset, the step's `command` is the
    name."""
    named = get(key, str, values) or STEPS[key]["command"]
    return shutil.which(os.path.expanduser(named.strip()))


def current(key: str, kind: type, values: dict) -> object:
    """What the Values line of `key` shows, or None when it is not set."""
    if key in SHOWN:
        return SHOWN[key](values)
    if "command" in STEPS.get(key, {}):
        return command(key, values)
    return get(key, kind, values)


def missing(values: dict | None = None) -> list[str]:
    """The keys of TEXT_KEYS that are not set and print a Stop line."""
    values = load() if values is None else values
    return [key for key, kind in TEXT_KEYS
            if key not in OPTIONAL and key not in STEPS
            and get(key, kind, values) is None]


def render(values: dict | None = None) -> str:
    """The Values block: a line per text key, or what to set where."""
    values = load() if values is None else values
    where = path()
    lines = ["## Values", ""]
    for key, kind in TEXT_KEYS:
        shown = current(key, kind, values)
        if shown is not None:
            lines.append(f"- `{key}`: {show(shown)}")
        elif key in OPTIONAL:
            continue
        elif key in STEPS:
            step = STEPS[key]
            lines.append(f"**Step {step['step']} is off** until `{key}` is set in "
                         f"`{where}`: {step['without']}.")
        else:
            lines.append(f"**Stop.** Set `{key}` in `{where}` before you use this skill.")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if argv != ["render"]:
        print("usage: skill_values.py render", file=sys.stderr)
        return 2
    try:
        sys.stdout.write(render())
    except Exception as exc:  # noqa: BLE001  the skill still has to load
        print(f"**Stop.** The values could not be read: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
