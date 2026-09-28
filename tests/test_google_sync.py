import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr
from urllib.parse import parse_qs, urlencode, urlsplit
import base64
import hashlib

import calendar_hub as hub
import google_sync as sync
from test_calendar_hub import fixture


class FakeGoogle:
    def __init__(self):
        self.items = {}
        self.calls = []
        self.fail_create = False

    def events(self, calendar):
        return copy.deepcopy(list(self.items.values()))

    def call(self, path, method='GET', body=None, etag=None):
        self.calls.append((path, method, copy.deepcopy(body), etag))
        if path == '/calendars':
            if self.fail_create:
                raise sync.SyncError('Synthetic ambiguous network failure')
            return {'id': 'synthetic-calendar'}
        if method == 'POST':
            event = copy.deepcopy(body)
            event['etag'] = 'version-1'
            self.items[event['id']] = event
            return event
        if method == 'PATCH':
            event_id = path.split('/')[-1].split('?')[0]
            if self.items[event_id]['etag'] != etag:
                raise sync.ApiError(412)
            self.items[event_id].update(copy.deepcopy(body))
            self.items[event_id]['etag'] = 'version-2'
            return self.items[event_id]
        raise AssertionError('Unexpected API operation')


class GoogleSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = sync.Store(Path(self.temp.name) / 'state')
        self.api = FakeGoogle()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_preview_never_writes_to_google(self):
        result = sync.sync(self.store, fixture(), self.api)
        self.assertEqual(result['create'], 3)
        self.assertEqual(self.api.calls, [])
        self.assertIsNone(self.store.read('target.json'))

    def test_repeated_sync_is_idempotent_and_verifies(self):
        first = sync.sync(self.store, fixture(), self.api, True)
        self.assertTrue(first['verified'])
        self.assertEqual(first['create'], 3)
        self.api.calls.clear()
        again = sync.sync(self.store, fixture(), self.api, True)
        self.assertEqual(again['create'], 0)
        self.assertEqual(self.api.calls, [])
        self.assertEqual(len(self.api.items), 3)

    def test_verified_source_change_updates_with_etag_and_no_attendees(self):
        sync.sync(self.store, fixture(), self.api, True)
        schedule = fixture()
        schedule['courses'][0]['location'] = 'New verified room'
        self.api.calls.clear()
        result = sync.sync(self.store, schedule, self.api, True)
        self.assertEqual(result['update'], 3)
        for path, method, body, etag in self.api.calls:
            self.assertEqual(method, 'PATCH')
            self.assertEqual(etag, 'version-1')
            self.assertTrue(path.endswith('?sendUpdates=none'))
            self.assertNotIn('attendees', body)
            self.assertNotIn('id', body)

    def test_manual_edit_or_attendee_blocks_entire_apply(self):
        sync.sync(self.store, fixture(), self.api, True)
        event = next(iter(self.api.items.values()))
        event['summary'] = 'User changed this'
        self.api.calls.clear()
        with self.assertRaises(sync.SyncError):
            sync.sync(self.store, fixture(), self.api, True)
        self.assertEqual(self.api.calls, [])
        self.assertEqual(event['summary'], 'User changed this')

    def test_deleted_occurrence_is_not_recreated(self):
        sync.sync(self.store, fixture(), self.api, True)
        event = next(iter(self.api.items.values()))
        event.clear()
        event.update(id=next(iter(self.api.items)), status='cancelled')
        self.api.calls.clear()
        with self.assertRaises(sync.SyncError):
            sync.sync(self.store, fixture(), self.api, True)
        self.assertEqual(self.api.calls, [])

    def test_removal_and_namespace_change_need_review(self):
        sync.sync(self.store, fixture(), self.api, True)
        schedule = fixture()
        schedule['courses'][0]['exclude_dates'] = ['2026-11-02']
        result = sync.sync(self.store, schedule, self.api)
        self.assertEqual(result['removed_needs_review'], 1)
        self.api.calls.clear()
        with self.assertRaises(sync.SyncError):
            sync.sync(self.store, schedule, self.api, True)
        self.assertEqual(self.api.calls, [])
        schedule['namespace'] = 'other-term'
        with self.assertRaises(sync.SyncError):
            sync.sync(self.store, schedule, self.api, True)

    def test_uncertain_calendar_creation_cannot_duplicate(self):
        self.api.fail_create = True
        with self.assertRaises(sync.SyncError):
            sync.sync(self.store, fixture(), self.api, True)
        self.assertTrue(self.store.read('target.json')['pending'])
        self.api.fail_create = False
        self.api.calls.clear()
        with self.assertRaises(sync.SyncError):
            sync.sync(self.store, fixture(), self.api, True)
        self.assertEqual(self.api.calls, [])

    def test_unmanaged_collision_never_overwritten(self):
        sync.sync(self.store, fixture(), self.api, True)
        event = next(iter(self.api.items.values()))
        event.pop('extendedProperties')
        self.api.calls.clear()
        with self.assertRaises(sync.SyncError):
            sync.sync(self.store, fixture(), self.api, True)
        self.assertEqual(self.api.calls, [])

    def test_credentials_are_private_and_symlinks_rejected(self):
        self.store.write('connection.json', {'refresh_token': 'synthetic-only'})
        path = self.store.root / 'connection.json'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.store.write('connection.json', {'refresh_token': 'replacement-synthetic'})
        self.assertEqual(self.store.read('connection.json')['refresh_token'], 'replacement-synthetic')
        path.unlink()
        other = Path(self.temp.name) / 'other'
        other.write_text('{}')
        path.symlink_to(other)
        with self.assertRaises((OSError, hub.ScheduleError)):
            self.store.write('connection.json', {})
        self.assertEqual(other.read_text(), '{}')

    def test_concurrent_operation_refused(self):
        second = sync.Store(self.store.root)
        try:
            with self.store.lock():
                with self.assertRaises(sync.SyncError):
                    with second.lock():
                        self.fail('Must not acquire second lock')
        finally:
            second.close()

    def test_network_destination_and_redirects_fail_closed(self):
        with patch('google_sync.build_opener') as opener:
            with self.assertRaises(sync.SyncError):
                sync.request('https://attacker.example/token', token='synthetic')
            opener.assert_not_called()
        self.assertIsNone(sync.NoRedirect().redirect_request(None, None, None, None, None, None))

    def test_unverified_schedule_cannot_refresh_token(self):
        schedule = fixture()
        schedule['courses'][0]['confirmed'] = False
        self.store.write('classes.json', schedule)
        with patch('google_sync.access_token') as refresh, redirect_stderr(io.StringIO()):
            code = sync.main(['--state', str(self.store.root), 'sync', '--apply'])
        self.assertEqual(code, 2)
        refresh.assert_not_called()

    def test_status_does_not_print_credentials(self):
        self.store.write('connection.json', {'refresh_token': 'SECRET-SYNTHETIC', 'account': 'PRIVATE-SYNTHETIC'})
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(sync.main(['--state', str(self.store.root), 'status']), 0)
        self.assertNotIn('SECRET', output.getvalue())
        self.assertNotIn('PRIVATE', output.getvalue())

    def test_equivalent_timezone_serialization_is_not_a_manual_edit(self):
        sync.sync(self.store, fixture(), self.api, True)
        event = next(iter(self.api.items.values()))
        event['start']['dateTime'] = event['start']['dateTime'].replace('+00:00', 'Z')
        self.api.calls.clear()
        self.assertTrue(sync.sync(self.store, fixture(), self.api, True)['verified'])
        self.assertEqual(self.api.calls, [])

    def oauth_fixture(self, returned_account):
        captured = {}
        test = self

        class Browser:
            def open(self, url):
                captured['params'] = parse_qs(urlsplit(url).query)
                return True

        class Server:
            def __init__(self, address, handler):
                test.assertEqual(address, ('127.0.0.1', 0))
                self.handler = handler
                self.server_port = 12345
                self.count = 0

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def handle_request(self):
                self.count += 1
                state = 'wrong-state' if self.count == 1 else captured['params']['state'][0]
                callback = object.__new__(self.handler)
                callback.path = '/callback?' + urlencode({'code': 'synthetic-code', 'state': state})
                callback.wfile = io.BytesIO()
                callback.send_response = lambda status: captured.update(status=status)
                callback.send_header = lambda *args: None
                callback.end_headers = lambda: None
                callback.do_GET()
                if self.count == 1:
                    test.assertEqual(captured['status'], 400)
                else:
                    test.assertEqual(captured['status'], 200)

        def api(url, method='GET', body=None, **kwargs):
            if url == sync.TOKEN:
                challenge = base64.urlsafe_b64encode(hashlib.sha256(body['code_verifier'].encode()).digest()).rstrip(b'=').decode()
                test.assertEqual(challenge, captured['params']['code_challenge'][0])
                test.assertEqual(body['code'], 'synthetic-code')
                return {'access_token': 'synthetic-access', 'refresh_token': 'synthetic-refresh', 'scope': ' '.join(sync.SCOPES)}
            test.assertEqual(url, sync.IDENTITY)
            return {'email': returned_account, 'verified_email': True}

        client = Path(self.temp.name) / 'client.json'
        client.write_text(json.dumps({'installed': {'client_id': 'synthetic.apps.googleusercontent.com',
                                                   'token_uri': 'https://untrusted.example/ignored'}}))
        return client, Server, Browser(), api

    def test_oauth_verifies_state_pkce_and_account_before_saving(self):
        client, server, browser, api = self.oauth_fixture('student@example.com')
        with patch('google_sync.HTTPServer', server), patch('google_sync.webbrowser.get', return_value=browser), patch('google_sync.request', side_effect=api), redirect_stdout(io.StringIO()):
            sync.connect(self.store, client, 'student@example.com', 'safari')
        self.assertEqual(self.store.read('connection.json')['account'], 'student@example.com')

    def test_oauth_wrong_account_never_saved(self):
        client, server, browser, api = self.oauth_fixture('wrong@example.com')
        with patch('google_sync.HTTPServer', server), patch('google_sync.webbrowser.get', return_value=browser), patch('google_sync.request', side_effect=api), redirect_stdout(io.StringIO()):
            with self.assertRaises(sync.SyncError):
                sync.connect(self.store, client, 'student@example.com', 'safari')
        self.assertIsNone(self.store.read('connection.json'))


if __name__ == '__main__':
    unittest.main()
