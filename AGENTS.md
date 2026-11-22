# Agent rules

- **Public repository.** No personal value goes into the tree or its history:
  no name, no home path, no vault layout of one user. A value the skill needs
  is a key of the config file and is documented in `README.md`.
- **No em dash** in any file. CI enforces it. Use a comma, a colon,
  parentheses or two sentences.
- **Tests first.** `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s
  skills/journal/tests` from the repository root is the gate, and nothing
  writes `__pycache__`.
- **Hooks never fail a session.** An adapter exits 0 whatever happens, and a
  missing, empty or malformed config file turns off only what needs the key,
  with one line that names it.
- `scripts/frontmatter.py` is a copy of the ai-memory skill's reader. A
  change goes there first and is copied here.
