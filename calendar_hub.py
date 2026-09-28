#!/usr/bin/env python3
"""Local-only verified class schedule exporter. No provider or network access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WEEKDAYS = ('MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU')
UTC = timezone.utc
LOCAL = Path('.calendar-hub')


class ScheduleError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ScheduleError(message)


def text_field(obj, key, optional=False):
    value = obj.get(key, '' if optional else None)
    require(isinstance(value, str) and (optional or value.strip()), f'{key}: expected text')
    require(len(value) <= 1000 and not any(ord(c) < 32 for c in value),
            f'{key}: use a single line of at most 1000 characters')
    return value


def parse_date(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value),
            'Dates must be YYYY-MM-DD')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ScheduleError('Invalid calendar date') from None


def parse_time(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{2}:\d{2}', value),
            'Times must be HH:MM in 24-hour notation')
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise ScheduleError('Invalid clock time') from None


def utc_instant(day, clock, zone):
    naive = datetime.combine(day, clock)
    valid = set()
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=zone, fold=fold).astimezone(UTC)
        if candidate.astimezone(zone).replace(tzinfo=None) == naive:
            valid.add(candidate)
    require(len(valid) == 1, 'Ambiguous or nonexistent daylight-saving time; resolve manually')
    return valid.pop()


def occurrences(data):
    require(isinstance(data, dict), 'Schedule must be an object')
    zone_name = text_field(data, 'timezone')
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ScheduleError('Unknown timezone or missing IANA timezone database') from None
    namespace = text_field(data, 'namespace')
    courses = data.get('courses')
    require(isinstance(courses, list) and 0 < len(courses) <= 100,
            'Provide 1–100 course meeting patterns')
    seen, result = set(), []
    for course in courses:
        require(isinstance(course, dict), 'Each course must be an object')
        cid = text_field(course, 'id')
        require(cid not in seen, 'Course IDs must be unique')
        seen.add(cid)
        require(course.get('confirmed') is True, 'Every course must be confirmed against its source')
        text_field(course, 'source')
        title = text_field(course, 'title')
        location = text_field(course, 'location', optional=True)
        first, last = parse_date(course.get('start_date')), parse_date(course.get('end_date'))
        require(0 <= (last - first).days <= 370, 'Course range must be ordered and at most 371 days')
        start, end = parse_time(course.get('start_time')), parse_time(course.get('end_time'))
        require(start < end, 'End time must follow start on the same day')
        days = course.get('days')
        require(isinstance(days, list) and days and all(isinstance(d, str) and d in WEEKDAYS for d in days),
                'days must contain weekday codes MO through SU')
        require(len(set(days)) == len(days), 'Duplicate weekday')
        excluded = course.get('exclude_dates', [])
        require(isinstance(excluded, list), 'exclude_dates must be a list')
        exclusions = {parse_date(d) for d in excluded}
        require(len(exclusions) == len(excluded), 'Duplicate exclusion date')
        require(all(first <= d <= last and WEEKDAYS[d.weekday()] in days for d in exclusions),
                'Exclusions must be actual meeting dates inside the course range')
        count = 0
        for n in range((last - first).days + 1):
            day = first + timedelta(days=n)
            if WEEKDAYS[day.weekday()] not in days or day in exclusions:
                continue
            key = json.dumps([namespace, cid, day.isoformat()], ensure_ascii=False)
            uid = hashlib.sha256(key.encode()).hexdigest() + '@calendar-hub.local'
            beginning, ending = utc_instant(day, start, zone), utc_instant(day, end, zone)
            require(beginning < ending, 'Meeting end must be later than start in UTC')
            result.append(dict(uid=uid, course_id=cid, date=day.isoformat(), title=title,
                               location=location, start=beginning, end=ending))
            count += 1
        require(count > 0, 'A course pattern has no meeting occurrences')
    return sorted(result, key=lambda e: (e['start'], e['uid']))


def escape(value):
    return value.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')


def fold_line(line):
    # RFC 5545: 75 octets including the continuation-space prefix.
    chunks, current, size = [], '', 0
    for char in line:
        width = len(char.encode('utf-8'))
        if size + width > 75:
            chunks.append(current)
            current, size = ' ', 1
        current += char
        size += width
    chunks.append(current)
    return '\r\n'.join(chunks)


def stamp(dt):
    return dt.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')


def render(events, now=None):
    created = stamp(now or datetime.now(UTC))
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Calendar Hub//Classes 0.1//EN',
             'CALSCALE:GREGORIAN']
    for event in events:
        lines += ['BEGIN:VEVENT', 'UID:' + event['uid'], 'DTSTAMP:' + created,
                  'DTSTART:' + stamp(event['start']), 'DTEND:' + stamp(event['end']),
                  'SUMMARY:' + escape(event['title']), 'LOCATION:' + escape(event['location']),
                  'TRANSP:OPAQUE', 'END:VEVENT']
    lines.append('END:VCALENDAR')
    return ('\r\n'.join(fold_line(line) for line in lines) + '\r\n').encode('utf-8')


def private_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(payload)


def initialize(root=LOCAL):
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    example = dict(timezone='America/New_York', namespace='replace-with-unique-term-id', courses=[dict(
        id='example101-lecture', title='EXAMPLE101 — Replace with your course', confirmed=False,
        source='', start_date='2026-08-24', end_date='2026-12-04', days=['MO', 'WE'],
        start_time='09:00', end_time='09:50', location='', exclude_dates=[])])
    contents = {
        'classes.json': json.dumps(example, indent=2) + '\n',
        'status.md': '# Private Calendar Hub status\n\n'
                     'Setup: pending\n\n'
                     'Record accounts, timezone, devices, enrolled courses, source/destination IDs, '
                     'decisions, publication consent, verified samples, colors, scheduler status, '
                     'last source refresh, last successful check, and blockers here. '
                     'Keep private feed links in a separate local secret file if needed.\n'
    }
    for name, content in contents.items():
        try:
            private_write(root / name, content.encode())
        except FileExistsError:
            pass


def load(path):
    require(path.stat().st_size <= 1_000_000, 'Schedule file too large')
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, UnicodeError):
        raise ScheduleError('Invalid UTF-8 JSON schedule') from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init', help='Create ignored local state without replacing existing files')
    for name in ('validate', 'build-classes'):
        command = commands.add_parser(name)
        command.add_argument('--schedule', type=Path, default=LOCAL / 'classes.json')
        if name == 'build-classes':
            command.add_argument('--output', type=Path, default=LOCAL / 'classes.ics')
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            initialize()
            print('Local state ready. Fill in and verify your actual schedule before building.')
            return 0
        data = load(args.schedule)
        events = occurrences(data)
        if args.command == 'validate':
            print(f'Valid schedule: {len(data["courses"])} patterns, {len(events)} occurrences. Source truth still requires human verification.')
            return 0
        manifest_path = args.output.with_suffix('.manifest.json')
        require(args.output != manifest_path, 'Output must use a calendar filename such as classes.ics')
        require(not args.output.exists() and not manifest_path.exists(), 'Output already exists; choose a new export path and reconcile before importing')
        manifest = dict(version=1, schedule_sha256=hashlib.sha256(
            json.dumps(data, sort_keys=True).encode()).hexdigest(),
            events=[dict(uid=e['uid'], course_id=e['course_id'], date=e['date'],
                         start=stamp(e['start']), end=stamp(e['end'])) for e in events])
        private_write(args.output, render(events))
        private_write(manifest_path, (json.dumps(manifest, indent=2) + '\n').encode())
        print(f'Built {len(events)} occurrences and a reconciliation manifest locally. Review before importing once; nothing was synced.')
        return 0
    except ScheduleError as error:
        print(f'Cannot continue: {error}', file=sys.stderr)
    except OSError:
        # Do not echo a supplied path: it may contain sensitive input.
        print('Cannot access local files. Check paths, permissions, and existing outputs.', file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
