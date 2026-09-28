import copy
import json
from pathlib import Path
import tempfile
import os
import unittest
from datetime import datetime, timezone

import calendar_hub as hub


def fixture():
    return {'timezone': 'America/New_York', 'namespace': 'synthetic-term', 'courses': [{
        'id': 'test-lecture', 'title': 'Test, course; α', 'confirmed': True,
        'source': 'Synthetic fixture', 'start_date': '2026-10-26', 'end_date': '2026-11-09',
        'days': ['MO'], 'start_time': '09:00', 'end_time': '09:50', 'exclude_dates': []}]}


class ScheduleTests(unittest.TestCase):
    def test_dst_preserves_wall_clock(self):
        events = hub.occurrences(fixture())
        self.assertEqual([hub.stamp(e['start']) for e in events],
                         ['20261026T130000Z', '20261102T140000Z', '20261109T140000Z'])

    def test_holidays_bounds_and_uids(self):
        original = hub.occurrences(fixture())
        changed = fixture()
        changed['courses'][0]['exclude_dates'] = ['2026-11-02']
        changed['courses'][0]['title'] = 'New title'
        changed['courses'][0]['start_time'] = '09:10'
        revised = hub.occurrences(changed)
        self.assertEqual([e['date'] for e in revised], ['2026-10-26', '2026-11-09'])
        self.assertEqual([e['uid'] for e in revised], [original[0]['uid'], original[2]['uid']])
        other = fixture()
        other['namespace'] = 'other-term'
        self.assertNotEqual(hub.occurrences(other)[0]['uid'], original[0]['uid'])

    def test_rejects_unverified_or_bad_schedules(self):
        for patch in ({'confirmed': False}, {'source': ''}, {'end_time': '08:00'},
                      {'days': ['XX']}, {'exclude_dates': ['2026-10-27']},
                      {'title': 'fake\nBEGIN:VEVENT'}, {'days': ['MO', 'MO']},
                      {'end_date': '2026-09-01'}, {'start_time': '99:30'}):
            with self.subTest(patch=patch):
                data = fixture()
                data['courses'][0].update(patch)
                with self.assertRaises(hub.ScheduleError):
                    hub.occurrences(data)

    def test_rejects_ambiguous_and_nonexistent_times(self):
        for day, start, end in [('2026-11-01', '01:15', '01:45'), ('2026-03-08', '02:15', '02:45')]:
            data = fixture()
            data['courses'][0].update(start_date=day, end_date=day, days=['SU'],
                                      start_time=start, end_time=end)
            with self.assertRaises(hub.ScheduleError):
                hub.occurrences(data)

    def test_ics_encoding_and_no_invites(self):
        data = fixture()
        data['courses'][0]['location'] = 'é' * 100
        encoded = hub.render(hub.occurrences(data), datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertTrue(encoded.endswith(b'END:VCALENDAR\r\n'))
        self.assertTrue(all(len(line) <= 75 for line in encoded.split(b'\r\n')))
        unfolded = encoded.decode().replace('\r\n ', '')
        self.assertIn('SUMMARY:Test\\, course\\; α', unfolded)
        self.assertIn('LOCATION:' + 'é' * 100, unfolded)
        self.assertNotIn('ATTENDEE', unfolded)
        self.assertNotIn('METHOD:', unfolded)
        self.assertNotIn('Synthetic fixture', unfolded)
        self.assertEqual(unfolded.count('BEGIN:VEVENT'), 3)

    def test_duplicate_pattern_id(self):
        data = fixture()
        data['courses'].append(copy.deepcopy(data['courses'][0]))
        with self.assertRaises(hub.ScheduleError):
            hub.occurrences(data)

    def test_init_preserves_state_and_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'state'
            hub.initialize(root)
            path = root / 'classes.json'
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)
            path.write_text('existing user state')
            hub.initialize(root)
            self.assertEqual(path.read_text(), 'existing user state')

    def test_cli_build_and_overwrite_refusal(self):
        with tempfile.TemporaryDirectory() as temp:
            schedule, output = Path(temp) / 'schedule.json', Path(temp) / 'out.ics'
            schedule.write_text(json.dumps(fixture()))
            args = ['build-classes', '--schedule', str(schedule), '--output', str(output)]
            self.assertEqual(hub.main(args), 0)
            before = output.read_bytes()
            self.assertEqual(hub.main(args), 2)
            self.assertEqual(before, output.read_bytes())
            manifest = json.loads(output.with_suffix('.manifest.json').read_text())
            self.assertEqual(len(manifest['events']), 3)

    def test_rejects_existing_shared_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'state'
            root.mkdir(mode=0o755)
            root.chmod(0o755)
            with self.assertRaises(hub.ScheduleError):
                hub.initialize(root)
            self.assertFalse((root / 'classes.json').exists())

    def test_rejects_existing_readable_state_without_changing_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'state'
            hub.initialize(root)
            state = root / 'status.md'
            state.write_text('synthetic private notes')
            state.chmod(0o644)
            with self.assertRaises(hub.ScheduleError):
                hub.initialize(root)
            self.assertEqual(state.read_text(), 'synthetic private notes')
            self.assertEqual(state.stat().st_mode & 0o777, 0o644)

    def test_rejects_symlinked_directory_and_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'state'
            target = Path(temp) / 'target'
            target.mkdir(mode=0o700)
            root.symlink_to(target, target_is_directory=True)
            with self.assertRaises(OSError):
                hub.initialize(root)
            self.assertEqual(list(target.iterdir()), [])
            root.unlink()
            hub.initialize(root)
            state = root / 'status.md'
            state.unlink()
            target_file = target / 'notes'
            target_file.write_text('untouched')
            state.symlink_to(target_file)
            with self.assertRaises(hub.ScheduleError):
                hub.initialize(root)
            self.assertEqual(target_file.read_text(), 'untouched')

    def test_private_write_refuses_final_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'original'
            target.write_text('unchanged')
            output = Path(temp) / 'output'
            output.symlink_to(target)
            with self.assertRaises(FileExistsError):
                hub.private_write(output, b'replacement')
            self.assertEqual(target.read_text(), 'unchanged')

    def test_directory_descriptor_keeps_write_in_checked_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root, moved = Path(temp) / 'private', Path(temp) / 'moved'
            fd = hub.private_directory(root)
            try:
                root.rename(moved)
                root.mkdir(mode=0o700)
                hub.private_write(root / 'export', b'private', fd)
                self.assertFalse((root / 'export').exists())
                self.assertEqual((moved / 'export').read_bytes(), b'private')
            finally:
                os.close(fd)


if __name__ == '__main__':
    unittest.main()
