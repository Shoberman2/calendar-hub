# Provider setup

These are navigation goals, not hardcoded UI selectors. Read the live screen or current official docs; interfaces and institution policies vary.

## Google and Apple

Verify the intended Google hub account. On macOS, inspect Internet Accounts and enable Calendars on the existing account before creating another. Verify the account's native calendar in Apple. On iPhone, have the user check the same account and Calendars switch; do not claim verification without device access or confirmation.

Google subscriptions are created on the web through Add calendar → From URL. Check existing subscriptions first; name them clearly and keep them selected. Do not enable public sharing of the destination Google calendar as part of subscribing. Google controls refresh timing; do not promise a daily freshness deadline.

Official reference: https://support.google.com/calendar/answer/37100

## Canvas and other schools

Use the student's authenticated LMS calendar export/feed if available. In Canvas, Calendar → Calendar Feed is the usual source. No API token is required for an ICS subscription. If the institution disables tokens, do not try to circumvent it. Store the secret feed only locally or in provider subscription settings.

Apple: create a URL subscription, choose iCloud storage when available if the user wants it on other Apple devices, and choose the supported refresh interval. Verify where it is stored, selected calendars, and alert preferences. Google: add the same feed separately. Compare the user's enrollment roster with the feed's actual dated events. LMS enrollment, visible course selection, and feed contents are distinct checks.

An LMS without a feed needs its own supported connector or a manually maintained calendar. Do not advertise automatic support for all schools. Class meeting times usually require the registrar schedule or syllabus; the class generator can handle a verified weekly pattern with exceptions.

## iCloud → Google (optional)

Inventory the actual iCloud calendars. Do not publish birthdays, reminders, or every calendar simply because it exists. After the owner approves the selected calendar's public read-only exposure, use its sharing controls in Apple Calendar or iCloud.com. Copy the link directly into Google's From URL control without exposing it in chat. Save locally only if needed, with restricted permissions. Verify the resulting subscription and sample event.

If the user declines public links, retain native Apple access and report that this method cannot provide a Google view. Private iCloud sharing with another Apple account is not a substitute for Google subscription.

Official reference: https://support.apple.com/guide/icloud/share-a-calendar-mm6b1a9479/icloud

## Microsoft 365 → Google (optional)

Apple uses the existing Exchange account with Calendars enabled. For Google, Outlook on the web's Calendar settings may provide Shared calendars → Publish a calendar. Ask the user which details and range they approve, subject to the available controls. Use the ICS subscription link, not an HTML sharing link. This feature may be disabled by the organization; stop and report that limitation rather than changing sharing policy.

Record the actual publication detail and range. A finite publication window cannot prove historical completeness. Never ship a preconfigured PowerShell script containing somebody else's mailbox or administrator policy changes.

## Invitations and email-derived events

Inspect the current settings before changing invitation behavior. Offer the user's preferred invitation policy; do not universally enable From everyone. Email-derived event detection is separate from formal invitations and can miss meetings. Find the original invitation and latest update for any claimed missing event. Deduplicate by provider ID or iCalendar UID, occurrence, and destination. A matching title alone is insufficient.
