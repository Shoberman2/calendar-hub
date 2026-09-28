# Calendar Hub

Use `.claude/skills/calendar-hub/SKILL.md` for calendar setup or reconciliation.
Read existing `.calendar-hub/status.md` before continuing prior work. Keep account details, feed URLs, schedules, event IDs, and evidence there, never in tracked files.

For code changes: Python standard library only. Run `python3 -m unittest discover -s tests -v`. Preserve stable occurrence UIDs, reject unconfirmed schedules, handle DST correctly, and never overwrite existing exports implicitly.

No real provider credentials or calendars are needed for tests. Do not run live account mutations as tests. This repo grants no blanket permission to publish calendars, send mail/invites, or install recurring jobs.
