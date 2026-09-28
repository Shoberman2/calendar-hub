from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import onboard
from google_sync import Store, SyncError


def profile():
    return {'version': 1, 'name': 'Synthetic Teammate', 'browser': 'Safari',
            'timezone': 'America/New_York', 'computer_use': 'when-approved',
            'daily_check_requested': True, 'destinations': ['apple-mac', 'apple-iphone', 'google-web'],
            'google_hub_source': 'work', 'sources': [
                {'id': 'work', 'provider': 'google', 'account': 'team@example.com',
                 'label': 'Work', 'category': 'work', 'color': '#34A853'},
                {'id': 'school', 'provider': 'canvas', 'account': 'student@example.edu',
                 'label': 'School', 'category': 'school', 'color': '#4285F4'},
                {'id': 'personal', 'provider': 'icloud', 'account': 'personal@example.com',
                 'label': 'Personal', 'category': 'personal', 'color': '#F09300'}]}


class OnboardingTests(unittest.TestCase):
    def test_all_routes_start_pending(self):
        result = onboard.report(profile(), {})
        self.assertEqual(len(result['connections']), 9)
        self.assertEqual(result['counts']['pending'], 9)
        self.assertFalse(result['all_connections_recorded_verified'])
        home_google = next(r for r in result['connections'] if r['id'] == 'personal:google-web')
        self.assertIn('approved', home_google['method'])

    def test_bad_profile_rejected(self):
        for edit in ({'timezone': 'Not/AZone'}, {'computer_use': 'always-bypass'},
                     {'google_hub_source': 'personal'}, {'daily_check_requested': 'yes'}):
            with self.subTest(edit=edit):
                data = profile()
                data.update(edit)
                with self.assertRaises(SyncError):
                    onboard.validate_profile(data)
        data = profile()
        data['sources'][1]['account'] = 'https://secret-feed.example/token'
        with self.assertRaises(SyncError):
            onboard.validate_profile(data)

    def test_duplicate_source_id_rejected(self):
        data = profile()
        data['sources'][1]['id'] = 'work'
        with self.assertRaises(SyncError):
            onboard.validate_profile(data)

    def test_install_both_and_repeat_preserves_other_skills(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            other = home / '.claude/skills/unrelated'
            other.mkdir(parents=True)
            (other / 'SKILL.md').write_text('unrelated')
            installed = onboard.install_agents(onboard.ROOT, home, 'both')
            self.assertEqual(installed, ['claude', 'codex'])
            self.assertEqual(onboard.install_agents(onboard.ROOT, home, 'both'), installed)
            for parent in ('.claude', '.agents'):
                link = home / parent / 'skills/calendar-hub'
                self.assertTrue(link.is_symlink())
                self.assertEqual(link.resolve(), onboard.SKILL)
                self.assertNotIn('team@example.com', (link / 'SKILL.md').read_text())
            self.assertEqual((other / 'SKILL.md').read_text(), 'unrelated')

    def test_existing_skill_collision_changes_neither_agent(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            conflict = home / '.agents/skills/calendar-hub'
            conflict.mkdir(parents=True)
            (conflict / 'SKILL.md').write_text('existing')
            with self.assertRaises(SyncError):
                onboard.install_agents(onboard.ROOT, home, 'both')
            self.assertFalse((home / '.claude/skills/calendar-hub').exists())
            self.assertEqual((conflict / 'SKILL.md').read_text(), 'existing')

    def test_fresh_wizard_install_and_resume_end_to_end(self):
        answers = ['Test Teammate', 'Europe/London', 'Safari', 'yes', 'when-approved',
                   'google', 'test@example.com', 'Company', 'work', 'yes',
                   'canvas', 'student@example.edu', 'University', 'school', 'no', 'yes', 'both']
        with tempfile.TemporaryDirectory() as temp:
            home, state = Path(temp) / 'home', Path(temp) / 'state'
            home.mkdir()
            with patch('builtins.input', side_effect=answers), patch('onboard.Path.home', return_value=home), redirect_stdout(io.StringIO()):
                self.assertEqual(onboard.main(['--state', str(state), 'start']), 0)
            saved = (state / 'profile.json').read_bytes()
            data = json.loads(saved)
            self.assertEqual(data['timezone'], 'Europe/London')
            self.assertEqual(len(data['sources']), 2)
            self.assertEqual((state / 'profile.json').stat().st_mode & 0o777, 0o600)
            with patch('builtins.input', side_effect=['both']), patch('onboard.Path.home', return_value=home), redirect_stdout(io.StringIO()):
                self.assertEqual(onboard.main(['--state', str(state), 'start']), 0)
            self.assertEqual((state / 'profile.json').read_bytes(), saved)
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(onboard.main(['--state', str(state), 'status']), 0)
            self.assertEqual(json.loads(output.getvalue())['counts']['pending'], 6)
            self.assertNotIn('test@example.com', output.getvalue())

    def test_ledger_requires_known_route_and_no_secret_urls(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / 'state')
            try:
                store.write('profile.json', profile())
                onboard.record_check(store, 'work:apple-mac', 'verified', 'Observed a matching synthetic event in both clients.')
                result = onboard.report(profile(), store.read('connections.json'))
                self.assertEqual(result['counts']['verified'], 1)
                self.assertEqual(result['counts']['pending'], 8)
                with self.assertRaises(SyncError):
                    onboard.record_check(store, 'unknown:apple-mac', 'verified', 'Unknown')
                with self.assertRaises(SyncError):
                    onboard.record_check(store, 'work:apple-mac', 'verified', 'https://secret.example/token')
            finally:
                store.close()

    def test_changed_account_invalidates_previous_observation(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp) / 'state')
            try:
                data = profile()
                store.write('profile.json', data)
                onboard.record_check(store, 'work:apple-mac', 'verified', 'Observed matching event.\n')
                ledger = store.read('connections.json')
                self.assertEqual(onboard.report(data, ledger)['counts']['verified'], 1)
                data['sources'][0]['account'] = 'different@example.com'
                self.assertEqual(onboard.report(data, ledger)['counts']['verified'], 0)
                self.assertEqual(onboard.report(data, ledger)['counts']['pending'], 9)
            finally:
                store.close()

    def test_malformed_ledger_rejected(self):
        for ledger in ([], {'work:apple-mac': None}, {'work:apple-mac': {'status': 'made-up'}}):
            with self.assertRaises(SyncError):
                onboard.report(profile(), ledger)

    def test_doctor_does_not_echo_accounts_or_token_contents(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / 'state'
            store = Store(state)
            store.write('profile.json', profile())
            store.write('connection.json', {'refresh_token': 'SYNTHETIC-SECRET'})
            store.close()
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(onboard.main(['--state', str(state), 'doctor']), 0)
            self.assertNotIn('SYNTHETIC-SECRET', output.getvalue())
            self.assertNotIn('team@example.com', output.getvalue())
            self.assertTrue(json.loads(output.getvalue())['profile_ready'])


if __name__ == '__main__':
    unittest.main()
