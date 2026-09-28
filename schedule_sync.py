#!/usr/bin/env python3
"""Install a user-requested macOS daily class sync after a verified live run."""
import argparse
import hashlib
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys

import calendar_hub as hub
from google_sync import Store, SyncError


def job(state, script, python, at):
    if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', at):
        raise SyncError('Use HH:MM in 24-hour local time')
    hour, minute = map(int, at.split(':'))
    label = 'local.calendar-hub.classes.' + hashlib.sha256(str(state).encode()).hexdigest()[:12]
    return {'Label': label, 'ProgramArguments': [str(python), str(script), '--state', str(state), 'sync', '--apply'],
            'WorkingDirectory': str(script.parent), 'StartCalendarInterval': {'Hour': hour, 'Minute': minute},
            'StandardOutPath': str(state / 'daily.log'), 'StandardErrorPath': str(state / 'daily-error.log'),
            'Umask': 0o077, 'ProcessType': 'Background', 'RunAtLoad': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=hub.LOCAL)
    parser.add_argument('--at', default='07:00')
    parser.add_argument('--install', action='store_true', help='Actually install the daily job; otherwise only check readiness')
    args = parser.parse_args(argv)
    store = None
    try:
        if sys.platform != 'darwin':
            raise SyncError('The bundled scheduler supports macOS. Use your host scheduler on Linux.')
        state = args.state.absolute()
        store = Store(state)
        with store.lock():
            hub.occurrences(store.read('classes.json'))
            target = store.read('target.json', {})
            last = store.read('last-run.json', {})
            if not store.read('connection.json') or not target.get('calendar') or target.get('pending'):
                raise SyncError('Connect and create the managed calendar before scheduling')
            if not last.get('success') or not last.get('verified'):
                raise SyncError('A successful verified live sync is required before scheduling')
            spec = job(state, Path(__file__).absolute().with_name('google_sync.py'), Path(sys.executable).absolute(), args.at)
            if not args.install:
                print('Ready for daily class sync at ' + args.at + ' in the Mac local timezone. No job installed.')
                return 0
            destination = Path.home() / 'Library' / 'LaunchAgents' / (spec['Label'] + '.plist')
            destination.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(plistlib.dumps(spec))
            # launchctl is an OS utility, never a path supplied by schedule data.
            completed = subprocess.run(['/bin/launchctl', 'bootstrap', f'gui/{os.getuid()}', str(destination)],
                                       capture_output=True, timeout=20, check=False)
            if completed.returncode:
                raise SyncError('Job file was saved but launchd did not activate it; inspect it before retrying. No duplicate was installed.')
            verified = subprocess.run(['/bin/launchctl', 'print', f'gui/{os.getuid()}/{spec["Label"]}'],
                                      capture_output=True, timeout=20, check=False)
            if verified.returncode:
                raise SyncError('Job activation could not be verified')
            store.write('scheduler.json', {'label': spec['Label'], 'local_time': args.at, 'active_verified': True})
            print('Daily class sync installed and verified at ' + args.at + ' in the Mac local timezone. Read google_sync.py status for last run results.')
        return 0
    except (SyncError, hub.ScheduleError, OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        message = str(error) if isinstance(error, (SyncError, hub.ScheduleError)) else 'Check local permissions and whether a job file already exists; no raw error was logged.'
        print(message, file=sys.stderr)
        return 2
    finally:
        if store:
            store.close()


if __name__ == '__main__':
    sys.exit(main())
