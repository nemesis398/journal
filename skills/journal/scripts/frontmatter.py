"""The frontmatter reader of the ai-memory skill, copied so this skill stands
alone as its own plugin.

The ai-memory lint and hooks read every note in the vault's AI area with this
reader, so an append here extends the frontmatter the way they read it. Keep
it identical to `parse_frontmatter` in ai-memory's `scripts/notes.py`; a
change belongs there first.

Stdlib only.
"""
from __future__ import annotations

import json
import re

class FrontmatterError(ValueError):
    """The text has no frontmatter, or frontmatter this reader cannot read."""


_KEY = re.compile(r"(?P<key>[^\s:#][^:]*?)[ \t]*:(?:[ \t]+(?P<value>.*?))?[ \t]*")
_DOUBLE = re.compile(r'"((?:[^"\\]|\\.)*)"(?:\s+#.*)?')
_SINGLE = re.compile(r"'((?:[^']|'')*)'(?:\s+#.*)?")
_COMMENT = re.compile(r"(?:^|\s+)#.*$")
_FLOW_ITEM = re.compile(
    r"""\s*(?P<item>"(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^,"'\[\]{}]*?)\s*(?P<end>[,\]])"""
)
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Characters YAML reserves at the start of a plain value. A backtick is the one
# a memory description is likely to open with.
_RESERVED = "`@|>&*!%{}[],"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split a note into its frontmatter and its body.

    Scalars come back as str, lists as list[str] and a nested key as a dict.
    The body is everything after the closing `---` line, unchanged.
    """
    lines = text.split("\n")
    if lines[0].rstrip() != "---":
        raise FrontmatterError("no frontmatter: the first line is not ---")
    for end in range(1, len(lines)):
        if lines[end].rstrip() == "---":
            break
    else:
        raise FrontmatterError("the frontmatter is never closed with ---")
    rows = []
    for number, raw in enumerate(lines[1:end], start=2):
        raw = raw.rstrip("\r")
        content = raw.lstrip(" ")
        if not content.strip() or content.startswith("#"):
            continue
        if content.startswith("\t"):
            raise FrontmatterError(f"line {number}: indented with a tab")
        rows.append((number, len(raw) - len(content), content.rstrip()))
    meta, _ = _mapping(rows, 0, 0)
    return meta, "\n".join(lines[end + 1:])


def _is_item(content: str) -> bool:
    return content == "-" or content.startswith("- ")


def _mapping(rows: list, i: int, indent: int) -> tuple[dict, int]:
    """Read the keys at one indentation level, starting at rows[i]."""
    meta: dict = {}
    while i < len(rows):
        number, level, content = rows[i]
        if level < indent:
            break
        if level > indent:
            raise FrontmatterError(f"line {number}: unexpected indentation")
        match = _KEY.fullmatch(content)
        if not match or _is_item(content):
            raise FrontmatterError(f"line {number}: cannot read {content!r}")
        key, value = match["key"], match["value"]
        if key in meta:
            raise FrontmatterError(f"line {number}: {key} appears twice")
        i += 1
        if value:
            meta[key] = _value(value, number)
        elif i < len(rows) and rows[i][1] >= indent and _is_item(rows[i][2]):
            items, item_level = [], rows[i][1]
            while i < len(rows) and rows[i][1] == item_level and _is_item(rows[i][2]):
                items.append(_scalar(rows[i][2][1:], rows[i][0]))
                i += 1
            meta[key] = items
        elif i < len(rows) and rows[i][1] > indent:
            meta[key], i = _mapping(rows, i, rows[i][1])
        else:
            meta[key] = ""
    return meta, i


def _value(raw: str, number: int) -> str | list[str]:
    return _flow_list(raw, number) if raw.startswith("[") else _scalar(raw, number)


def _flow_list(raw: str, number: int) -> list[str]:
    items, pos = [], 1
    while True:
        match = _FLOW_ITEM.match(raw, pos)
        if not match:
            raise FrontmatterError(f"line {number}: cannot read the list {raw!r}")
        if match["item"]:
            items.append(_scalar(match["item"], number))
        pos = match.end()
        if match["end"] == "]":
            break
    if _COMMENT.sub("", raw[pos:]).strip():
        raise FrontmatterError(f"line {number}: text after the list {raw!r}")
    return items


def _scalar(raw: str, number: int) -> str:
    raw = raw.strip()
    if raw.startswith('"'):
        match = _DOUBLE.fullmatch(raw)
        if not match:
            raise FrontmatterError(f"line {number}: cannot read the double-quoted value {raw!r}")
        try:
            return json.loads(f'"{match[1]}"', strict=False)
        except ValueError:  # a YAML escape JSON lacks, such as \x41
            return re.sub(r"\\(.)", r"\1", match[1])
    if raw.startswith("'"):
        match = _SINGLE.fullmatch(raw)
        if not match:
            raise FrontmatterError(f"line {number}: cannot read the single-quoted value {raw!r}")
        return match[1].replace("''", "'")
    raw = _COMMENT.sub("", raw)
    if raw and raw[0] in _RESERVED:
        raise FrontmatterError(f"line {number}: a value that starts with {raw[0]} must be quoted")
    if ": " in raw or raw.endswith(":"):
        raise FrontmatterError(f"line {number}: a value that holds ': ' must be quoted")
    return raw

