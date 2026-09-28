import io
from contextlib import redirect_stderr
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from google_sync import Store, SyncError
import schedule_sync as scheduler
from test_calendar_hub import fixture


class SchedulerTests(unittest.TestCase):
    def test_arguments_remain_literal_and_time_is_validated(self):
        state = Path('/private/path with spaces; literal')
        spec = scheduler.job(state, Path('/app/google_sync.py'), Path('/usr/bin/python3'), '07:30')
        self.assertEqual(spec['ProgramArguments'][3], str(state))
        self.assertEqual(spec['StartCalendarInterval'], {'Hour': 7, 'Minute': 30})
        self.assertFalse(spec['RunAtLoad'])
        self.assertEqual(spec['Umask'], 0o077)
        with self.assertRaises(SyncError):
            scheduler.job(state, Path('/app/google_sync.py'), Path('/usr/bin/python3'), '24:00')

    def test_unverified_connection_cannot_install_job(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'state'
            store = Store(root)
            store.write('classes.json', fixture())
            store.close()
            with patch('schedule_sync.sys.platform', 'darwin'), patch('schedule_sync.subprocess.run') as run, redirect_stderr(io.StringIO()):
                self.assertEqual(scheduler.main(['--state', str(root), '--install']), 2)
                run.assert_not_called()
