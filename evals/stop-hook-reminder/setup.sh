#!/usr/bin/env bash
# The config fixture every case runs with: an empty vault in the workspace and
# a complete config in the run's own home, where the skill looks for it
# (XDG_CONFIG_HOME). A case cannot set JOURNAL_CONFIG: its env takes EVAL_*
# keys only. Runs only under `claude plugin eval --scaffold`.
set -euo pipefail
vault="$PWD/vault"
mkdir -p "$vault/AI/sessions" "$vault/daily-notes" "$vault/templates" \
  "$HOME/.config/journal"
cat > "$HOME/.config/journal/config.json" <<JSON
{
  "vault": { "root": "$vault" },
  "journal": {
    "protectedSection": "## Logbook",
    "languageRule": "English for every subject."
  }
}
JSON
