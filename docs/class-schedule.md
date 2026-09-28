# Verified class schedules

Run `python3 calendar_hub.py init`. Edit `.calendar-hub/classes.json`, never the public examples to hold real data.

```json
{
  "timezone": "America/New_York",
  "namespace": "my-school-fall-2026",
  "courses": [
    {
      "id": "example101-lecture-a",
      "title": "EXAMPLE101 — Lecture",
      "confirmed": true,
      "source": "Registrar timetable, verified 2026-08-20",
      "start_date": "2026-08-24",
      "end_date": "2026-12-04",
      "days": ["MO", "WE"],
      "start_time": "09:00",
      "end_time": "09:50",
      "location": "Example Hall 100",
      "exclude_dates": ["2026-11-25"]
    }
  ]
}
```

This is fictional, not a university timetable. Use an opaque namespace unique to your term and school; do not change namespace or course IDs after import. IDs plus local date generate stable occurrence UIDs. Create separate entries for labs or distinct weekly time patterns. End dates are inclusive. Exclusions must fall on an actual meeting date. For a one-off meeting, use identical start/end dates and the matching weekday. Split patterns when class times change mid-term. Overnight classes and ambiguous/nonexistent DST local times are rejected; enter those manually with the actual offset.

`confirmed: true` means you checked the actual registered section, date range, timezone, and exceptions. The CLI cannot check the truth of the source reference. `source` should be a short local reference, not a secret URL. The source note does not appear inside exported events.

Run:

```sh
python3 calendar_hub.py validate
python3 calendar_hub.py build-classes
```

Outputs are private local `.calendar-hub/classes.ics` and `.calendar-hub/classes.manifest.json`. The manifest contains the schedule hash and occurrence IDs for reconciliation. The ICS uses CRLF, escaped/folded text, and UTC start/end times calculated for each local date. No invitations, attendees, alarms, or meeting emails are generated. Color is set on the destination calendar after import.

For a reviewed new export, use `--output .calendar-hub/revised.ics`. Existing outputs are never overwritten. Stable UIDs help compare versions but do not guarantee provider import deduplication. Never use repeated imports as synchronization. Match the manifest against events using a supported connector or inspect manually before applying changes.
