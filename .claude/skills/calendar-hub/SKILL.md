---
name: calendar-hub
description: Set up and reconcile school, personal, and work calendars across Apple Calendar and Google Calendar, including verified class meeting times and category colors. Use for calendar unification or its daily maintenance.
---

# Calendar Hub

Help this user see their authorized calendars in their chosen clients. Use the repository's local CLI for class exports and the session's authorized tools for provider actions. The skill does not provide browser control, credentials, calendar APIs, or a scheduler.

## Resume and inventory

1. Read existing conversation decisions and `.calendar-hub/status.md` before acting. If absent, run `python3 calendar_hub.py init` from the repository root. Never overwrite existing state.
2. Record the user's timezone, devices, preferred browser, Google hub account, actual source accounts, all enrolled courses/sections, category colors, and which tools are usable. Retrieve already-available information before asking the user. Do not assume the example course or the original author's providers apply.
3. Inventory actual calendars by account and provider ID, not just display name. Record native connections, existing subscriptions, and which calendars are selected. A calendar named Calendar may be Exchange, not iCloud. Inspect existing account toggles before adding duplicate accounts.
4. Keep state local in `.calendar-hub/`. Record each operation as pending, attempted, verified, blocked, or skipped with timestamp and evidence. Do not mark an attempted click or successful API write as verified destination sync.

## Set up sources

Read [providers.md](references/providers.md) for applicable providers only. Choose one canonical source for each calendar. Use native Google/Exchange/iCloud accounts in Apple where available; URL subscriptions are read-only views in Google. Avoid adding those Google-side copies back into Apple. Verify account identity before each mutation.

Passwords and MFA stay with the user. Publishing a calendar requires that user's explicit approval for the particular calendar and exposure. Explain that anyone possessing its link can read the published details. A teammate's or repo author's approval never carries over. Respect institution restrictions; if API tokens are disabled, use supported ICS feeds rather than trying to create tokens. Never alter tenant sharing policy as a workaround.

Keep feed links out of chat, tool logs, shell arguments, screenshots, and tracked files. Use approved tool secret handling or have the user paste the link directly into the destination when the tool would expose it. Do not inspect or display a secret file merely to report status.

## School completeness

Compare the registrar/enrollment list with all LMS courses; do not mistake the only course with dated items for the complete schedule. Check each course's visible assignments, announcements, and syllabus within the authorized scope. Report undated or unsupported items explicitly.

Class times require an authoritative schedule: course/section, meeting days, start/end time, timezone, first/last meeting dates, holiday exceptions, labs, and location if available. Never infer times from section letters or homework deadlines. Resolve conflicting syllabus dates against the current registrar record or ask only for the missing fact.

Use `docs/class-schedule.md` to fill `.calendar-hub/classes.json`. Keep courses unconfirmed until checked. Run validate, then build-classes. Review the export before importing once into a dedicated School Classes calendar in the user's Google hub. Prefer supported authenticated event APIs with source-ID tracking when available. Subsequent changes need reconciliation, not repeated imports. Verify a sample before and after any DST change and at the term boundary.

## Invitations and colors

For a missing meeting, search the authorized mailbox/calendar using its name and participants. Compare latest invitation UID, updates, cancellations, timezone, and existing destination events. Recover only a confirmed missing event; never infer agreement from a proposal. Importing an invitation can trigger provider behavior: use an import/copy path without notifications where available. If tools cannot guarantee no RSVP or attendee notification, hand off that step. Do not send mail or RSVP without explicit instruction.

Use configurable category colors (defaults school blue, work green, second work purple, personal orange). Set calendar colors in both clients and verify. Do not change someone else's shared event just to recolor it.

## Maintenance and finish

If requested, read [daily.md](references/daily.md) and configure an available supported scheduler. Report unavailable scheduling plainly; do not claim a saved prompt is active automation.

Verify each source in both destinations using event identity and time, including at least one future event and one recurrence or class exception where present. A subscription appearing in a sidebar does not establish feed completeness. Record last observed source update separately from last successful agent check. List unresolved sources and manual iPhone steps. No blanket claim that everything is present without a bounded audit and evidence.

When UI is unavailable, refresh observation and try one reasonable recovery. Stop dependent mutations if the page/account changes unexpectedly, the device locks, or authentication is required. Preserve completed work and ask for the specific unblock. Never delete/unsubscribe calendars or silently replace existing events to make the audit pass.
