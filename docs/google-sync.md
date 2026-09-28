# Google class sync and daily automation

This integration adds and updates verified class meetings in one dedicated Google calendar. Google/Exchange/iCloud native sync and provider ICS subscriptions continue to handle the other calendars. It does not scrape mail or copy every calendar into a new place.

**Release status:** implemented and tested against synthetic API responses. Live Google OAuth, a real calendar round trip, and macOS launchd activation must still be verified before calling the integration production-ready. Until that happens, use with review and inspect the destination after every initial setup.

## One-time Google setup

Each installation needs a Google Cloud OAuth client. The public repository contains no shared OAuth credentials. Use your own project or an organization-approved app.

1. Follow Google's [Calendar API setup](https://developers.google.com/workspace/calendar/api/quickstart/python) to enable Calendar API and configure the OAuth consent screen.
2. Create a **Desktop app** OAuth client. Download its JSON to the ignored `.calendar-hub/google-client.json` folder after running `python3 calendar_hub.py init`. Keep the client file and connection state private; do not send them to maintainers.
3. For an external app in Testing, add your intended account as a test user. Google normally expires these refresh tokens after seven days; see [Google's OAuth lifecycle guidance](https://developers.google.com/identity/protocols/oauth2). Organization policy and any production verification requirements still apply. Do not bypass Google security warnings or tenant restrictions.
4. Run the connection command yourself and complete browser sign-in and consent:

```sh
python3 google_sync.py connect --client .calendar-hub/google-client.json --account you@example.com --browser safari
```

On Linux, omit `--browser safari` to use your configured browser. The account argument verifies which account you actually authorize. An unexpected account is rejected. The local callback uses PKCE and an unpredictable state value; it listens only on loopback and suppresses request logs. API requests use fixed Google HTTPS endpoints and reject redirects.

Requested scopes are `calendar.app.created` (app-created secondary calendars) and `userinfo.email` (confirm the account). It does not ask for Gmail access or blanket access to existing primary-calendar events. [Google's scope reference](https://developers.google.com/workspace/calendar/api/auth).

Refresh credentials are stored in a 0600 file inside a 0700 local directory. This is **not encrypted storage or Keychain**. Keep the machine and backups protected. Ordinary output contains counts/status, not tokens, account addresses, or event titles. If consent expires, repeat the command with `--reauthorize`, using the same account and client. To revoke access, use your Google Account's connected-app controls; do not publish or share token files.

## Preview and sync

Fill `.calendar-hub/classes.json` using the [verified schedule format](class-schedule.md), then:

```sh
python3 google_sync.py preview
python3 google_sync.py sync --apply
python3 google_sync.py status
```

Preview reads Google state after authentication but makes no calendar/event writes. The first apply creates **School Classes (Calendar Hub)** and records the destination ID privately. It does not import into your primary calendar. Events have deterministic IDs and ownership markers, so repeat runs converge without duplicate imports. Source changes update only managed fields with an ETag precondition; concurrent edits cause a failed request rather than an unconditional overwrite.

If a destination event has been edited manually, has attendees, was canceled, lost its ownership marker, or was removed from the source schedule, the entire event plan stops for review. There are no event-delete or RSVP operations. Removals/holiday corrections after an earlier sync require an explicit review; this version does not silently delete those occurrences. Namespace changes also require term migration review.

After writes, the tool rereads the destination and verifies the plan is satisfied. Network failures may leave some successful writes; a subsequent preview reconciles deterministic IDs. An uncertain calendar-creation response is different: a pending marker blocks repeated creation until you inspect Google and recover its ID. Never erase the state directory to solve a sync error; doing so loses the destination mapping and may create a second calendar.

Do not import the generated ICS in addition to this managed calendar. If you previously imported class events, inspect and resolve that overlap before the first apply. Existing native and subscribed calendars remain unchanged.

## Apple and colors

Enable the same Google account in Apple Calendar on Mac and iPhone, and select the newly created School Classes calendar. Verify a class on both clients. Set its color to school blue in both clients; this integration does not assume calendar-list color permission. Imported source accounts and subscription colors are configured by the setup skill.

## Daily macOS sync

Only install after a successful verified live sync:

```sh
python3 schedule_sync.py --at 07:00
python3 schedule_sync.py --at 07:00 --install
```

The first command checks readiness without installing. The second installs one user LaunchAgent, verifies launchd accepted it, and records its label privately. It runs class sync at 07:00 in the Mac's current local timezone. Keep the checkout/Python executable at their installed paths. The user must be logged in, the machine available, and the network/Google authorization functional. This is not a cloud service and does not force provider subscription refreshes.

Check `python3 google_sync.py status` for the last sync result and inspect the private daily logs for failures. The job does not send notifications itself; ask your assistant to monitor this status if you want notifications. It never installs until `--install` is provided and refuses to replace an existing job file. To disable it, inspect `.calendar-hub/scheduler.json`, then use `launchctl bootout gui/$(id -u)/<recorded-label>`. Remove only the matching LaunchAgent file if you intend to uninstall it. No uninstall command is run by the application.

The daily assistant reconciliation described elsewhere is broader: it can investigate authorized mail invitations and provider gaps. Do not confuse it with this deterministic class-sync job. Both require their respective setup and verification.
