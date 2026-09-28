# Calendar Hub

Bring school, personal, and work calendars into Apple Calendar and Google Calendar—with Claude guiding setup and checking the result.

**An early, open-source assistant workflow, not a hosted sync service.** The included Python utility builds class calendars locally. Claude performs account setup through whatever authorized browser, desktop, and calendar tools are available in your session. This repository does not give Claude those tools or account access.

| Capability | Current implementation |
| --- | --- |
| Generate class-calendar files | Implemented locally; tested with synthetic schedules |
| Connect Apple, Google, Outlook and LMS accounts | Claude-guided procedure requiring available tools and user sign-in |
| Recover missing emailed invitations | Claude-guided investigation; no email ingestion service in this repo |
| Daily autonomous reconciliation | Procedure for a host scheduler; not installed by cloning |
| Guaranteed complete, real-time, two-way sync | Not implemented or claimed |

## Start with Claude Code

```sh
git clone https://github.com/Shoberman2/calendar-hub.git
cd calendar-hub
claude
```

Then type:

```text
/calendar-hub Set up my school, personal, and work calendars in Apple and Google Calendar. Check all my enrolled classes, include class meeting times, give each category its own color, and help me schedule a daily check.
```

Claude inventories what you already have, asks only for missing information, and uses the account names you provide. You handle sign-ins and MFA. If browser or desktop control is unavailable, it gives you the exact manual step and resumes after verification. Start on your Mac for Apple Calendar setup; phone verification happens on your phone.

For another assistant, open this folder and ask it to follow [the skill](.claude/skills/calendar-hub/SKILL.md). Plain Claude chat can read the instructions, but cannot control your Mac simply because you uploaded them. [Claude Code supports repository skills](https://code.claude.com/docs/en/skills).

## What it covers

| Source | Apple Calendar | Google Calendar |
| --- | --- | --- |
| Google account | Native account | Native calendar |
| iCloud | Native account | Optional published read-only subscription |
| Microsoft 365 / Exchange | Native account | Optional published read-only subscription, if tenant permits |
| Canvas or another LMS with an ICS feed | Subscribe to feed | Subscribe to feed |
| Class meeting times | Through your native Google account | A dedicated School Classes calendar |

Keep one canonical calendar for each source. Avoid subscribing Apple to a Google-side copy of a calendar already available natively. A URL subscription is read-only; edit at the source. Provider refresh timing varies, and a daily agent check cannot force Google to refetch an external feed.

School assignments and class meetings are separate. An LMS feed can omit undated assignments, inactive courses, or lecture times. Claude compares the feed with the actual enrolled-course list and uses the registrar schedule or verified syllabus for lecture/lab times, term dates, and holidays. Unsupported LMS providers remain explicit manual steps.

Default categories: **school blue, work green, second work account purple, personal orange**. Names and colors are configurable per person. Verify colors in both clients because appearance may differ.

## Privacy

The repository contains no calendar credentials, live feeds, student schedules, or example owner's account data. Your local `.calendar-hub/` directory is ignored by Git. It is stored locally, not encrypted; your assistant and enabled tools may still process it under their own policies.

Publishing iCloud or Outlook calendars lets anyone holding the link read the permitted details. Each person chooses whether to publish and what to expose. If they decline, the workflow reports the missing cross-provider view instead of weakening account security. Never paste private feed URLs into issues, screenshots, logs, or public repositories. See [security guidance](SECURITY.md).

## Local class-calendar utility

Requires macOS or Linux, Python 3.10+, and an installed IANA timezone database (standard on macOS). No Python packages, network requests, or account credentials needed. Existing state/output directories must be owned by you and private (0700); existing state files must be private regular files (0600). Unsafe permissions or links are rejected without changing your files.

```sh
python3 calendar_hub.py init
# Fill in .calendar-hub/classes.json using your verified schedule.
python3 calendar_hub.py validate
python3 calendar_hub.py build-classes
python3 -m unittest discover -s tests -v
```

The example course is deliberately **unconfirmed**. The builder refuses to generate events until every course is confirmed and has a source reference. It generates individual UTC occurrences, preserving local class times across daylight saving changes, with stable event IDs and explicit holiday exclusions. It refuses to overwrite a previous export.

Review `.calendar-hub/classes.ics`, then import it once into a dedicated Google School Classes calendar. The CLI does not import anything or install a scheduler. Re-imports are not guaranteed to update existing events: after changes, reconcile the prior manifest and destination events instead of blindly importing again. See [the schedule format](docs/class-schedule.md).

## Daily checks

Ask Claude to configure a supported recurring task using [the daily procedure](.claude/skills/calendar-hub/references/daily.md). This requires a scheduling feature and persistent authorized access in your assistant environment. Unattended desktop workflows may stop when the Mac locks or sign-in expires. The setup must report whether a scheduler was actually created; a prompt file alone is not automation.

The daily task checks new or changed events, confirms course coverage, and reports actionable failures. It does not send RSVPs, invite teammates, delete calendar entries, or publish calendars in the background.

## Release status and contributing

Version 0.1 is a tested local generator plus a documented assistant workflow. Live end-to-end setup across every provider and Claude environment has not been validated. Mail-invitation recovery, provider subscriptions, and daily scheduling are agent-guided, not implemented as API adapters in this CLI. Contributions should add a reproducible provider check and document limitations; use synthetic fixtures, never real account exports.

Run the unit tests before submitting a change. Licensed under MIT.
