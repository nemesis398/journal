---
max_turns: 4
allowed_tools: [Skill, "Bash(python3:*)"]
---

We just found out why the backup job failed every night: the log said *disk
full*, but the real cause was a stale lock file that made the job retry until
the disk filled. I deleted the lock and added a cleanup step. Journal it.
