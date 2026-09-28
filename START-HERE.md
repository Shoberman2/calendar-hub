# Set up your calendars with Claude or Codex

1. Download and extract the Calendar Hub release ZIP. Keep the extracted folder somewhere permanent on your Mac, such as Documents. Do not run it from inside the ZIP or move it after installing the skill.
2. Double-click **Start Calendar Hub.command**. It needs Python 3.10+ already installed. If unavailable, use the installer from [python.org](https://www.python.org/downloads/) or your organization's approved installation method. If macOS blocks a downloaded script, do not bypass security warnings; open this folder in your assistant and ask it to inspect the files and guide the approved setup. You can also run `python3 onboard.py start` in a terminal after reviewing the code.
3. Answer the local questions: your accounts, timezone, devices, colors/categories, preferred browser, and which assistant(s) to install. No password, token, feed URL, or paid API key is requested by this wizard.
4. Start a **local** Claude Code or Codex session with access to the folder. Restart the app if the skill does not appear. Use:

   Claude Code: `/calendar-hub Set up and verify all my calendars using my private profile. Use computer tools when available and allowed.`

   Codex: `$calendar-hub Set up and verify all my calendars using my private profile. Use computer tools when available and allowed.`

5. Stay available for sign-in, MFA, and any public-calendar sharing approval. The assistant uses official account connections, supported connectors, or its available computer/browser tools. It must verify each source in Apple and Google rather than simply check that a calendar name appears.

The local wizard is functional. It does **not** connect your accounts by itself. A plain chat session without local file access or computer/calendar tools cannot perform the setup. This package cannot grant those capabilities. The assistant must identify that limitation and give precise manual steps instead of claiming success.

## What both assistants remember

The installed skill points to this one local folder. `.calendar-hub/profile.json` contains your account inventory and preferences; `status.md` carries decisions and unresolved work; `connections.json` records evidence per source and device. Both assistants read the same files when invoked. These are local files, not shared cloud memory or automatic background access in every conversation.

`python3 onboard.py doctor` checks local readiness. `python3 onboard.py status` shows which connections are pending, attempted, verified, blocked, or skipped. A new profile starts entirely pending. Changing the profile invalidates prior observations until the affected setup is checked again. Verification records are observations, not independent live probes or permission grants. Your private files stay out of the public repository and out of the installed skill instructions.

## How synchronization works

Native account sync handles Google/Exchange/iCloud in Apple. The Google hub can display LMS and approved published feeds as read-only subscriptions; provider refresh timing varies. Classes are added from a verified registrar timetable or syllabus. The assistant checks email invitation settings and can investigate confirmed missing invites if its tools and your authorization allow it. Arbitrary email text is not automatically converted into commitments.

Google Cloud OAuth is **optional** for the extra class-sync command. Normal agent-guided native/subscription setup does not need your own Google developer project. For the optional connector, follow [Google sync setup](docs/google-sync.md).

Public iCloud/Outlook feed links expose permitted event details to anyone holding them. Each teammate must approve their own sharing. No teammate receives another person's credentials, calendar contents, or consent.

If you request a daily check, the assistant configures an available host scheduler and verifies it actually exists. It reports any awake-machine/sign-in dependencies. The optional macOS scheduler only maintains class events; it is not a complete mail/calendar ingestion service.

## Availability and remaining validation

The local wizard, installer, state reports, exporter, and sync safety logic have automated tests. Live setup across every Google/Apple/Outlook/LMS combination and every Claude/Codex computer-use environment has **not** been validated. No universal one-click, real-time, two-way sync is claimed. Your installation is complete only after each desired connection is verified with actual event samples and the remaining gaps are resolved.

Official skill locations: [Claude Code](https://code.claude.com/docs/en/skills), [Codex](https://learn.chatgpt.com/docs/build-skills). The installer adds a Calendar Hub symlink under the assistant's user skill directory, preserving unrelated skills and settings. To uninstall the discovery link, inspect and remove only that symlink; keep private state if you want to resume later. No uninstall or credential revocation is performed automatically.
