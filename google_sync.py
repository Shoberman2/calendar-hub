#!/usr/bin/env python3
"""Authenticated, conservative class synchronization to an app-created Google calendar."""
import argparse
import base64
from contextlib import contextmanager
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
import webbrowser

import calendar_hub as hub

AUTH = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN = 'https://oauth2.googleapis.com/token'
IDENTITY = 'https://www.googleapis.com/oauth2/v2/userinfo'
API = 'https://www.googleapis.com/calendar/v3'
SCOPES = ['https://www.googleapis.com/auth/calendar.app.created',
          'https://www.googleapis.com/auth/userinfo.email']


class SyncError(ValueError):
    pass


class ApiError(SyncError):
    def __init__(self, status):
        self.status = status
        super().__init__(f'Google request failed (HTTP {status}); check authorization or retry later.')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def request(url, method='GET', body=None, token=None, etag=None, form=False):
    if urlsplit(url).hostname not in ('www.googleapis.com', 'oauth2.googleapis.com') or not url.startswith('https://'):
        raise SyncError('Unapproved API destination')
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if etag:
        headers['If-Match'] = etag
    data = None
    if body is not None:
        data = (urlencode(body) if form else json.dumps(body)).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
    try:
        with build_opener(NoRedirect).open(Request(url, data=data, headers=headers, method=method), timeout=30) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise SyncError('API response exceeds local limit')
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise SyncError('Invalid API response')
            return result
    except HTTPError as error:
        raise ApiError(error.code) from None
    except (URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError):
        raise SyncError('Network or response failure; no response details were logged') from None


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.fd = hub.private_directory(self.root)

    def close(self):
        os.close(self.fd)

    def read(self, name, default=None):
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.fd)
        except FileNotFoundError:
            return default
        try:
            info = os.fstat(fd)
            import stat
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
                raise SyncError('Private state has unsafe permissions or file type')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                raw = stream.read(1_000_001)
            if len(raw) > 1_000_000:
                raise SyncError('Private state exceeds local limit')
            return json.loads(raw)
        finally:
            os.close(fd)

    def write(self, name, data):
        try:
            hub.check_private_file(self.fd, name)
        except FileNotFoundError:
            pass
        temporary = '.write-' + secrets.token_hex(12)
        try:
            hub.private_write(self.root / temporary, (json.dumps(data, indent=2) + '\n').encode(), self.fd)
            os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=self.fd)
            except FileNotFoundError:
                pass

    @contextmanager
    def lock(self):
        fd = os.open('sync.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        try:
            hub.check_private_file(self.fd, 'sync.lock')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise SyncError('Another Calendar Hub operation is running') from None
            yield
        finally:
            os.close(fd)


def connect(store, client_path, account, browser, reauthorize=False):
    previous = store.read('connection.json')
    if previous and not reauthorize:
        raise SyncError('Already connected. Use --reauthorize to renew the same account and OAuth client.')
    if not account or '@' not in account:
        raise SyncError('Specify the Google account you intend to use')
    client = hub.load(client_path).get('installed', {})
    if not isinstance(client.get('client_id'), str) or not client['client_id'].endswith('.apps.googleusercontent.com'):
        raise SyncError('A Google Desktop app OAuth client JSON is required')
    if previous and (previous['account'].casefold() != account.casefold()
                     or previous['credentials']['client_id'] != client['client_id']):
        raise SyncError('Reauthorization must use the same account and OAuth client; preserve the existing calendar mapping')
    # Endpoints from the downloaded file are deliberately ignored.
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            parsed = urlsplit(self.path)
            values = parse_qs(parsed.query)
            valid = parsed.path == '/callback' and secrets.compare_digest(values.get('state', [''])[0], state)
            if not valid:
                self.send_response(400)
                self.end_headers()
                return
            result.update(values)
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(b'Authorization received. Return to Calendar Hub for verification.')

    class LoopbackServer(HTTPServer):
        def get_request(self):
            connection, address = super().get_request()
            connection.settimeout(5)
            return connection, address

    with LoopbackServer(('127.0.0.1', 0), Callback) as server:
        server.timeout = 1
        redirect = f'http://127.0.0.1:{server.server_port}/callback'
        params = dict(client_id=client['client_id'], redirect_uri=redirect, response_type='code',
                      scope=' '.join(SCOPES), state=state, code_challenge=challenge,
                      code_challenge_method='S256', access_type='offline', prompt='consent', login_hint=account)
        controller = webbrowser.get(browser) if browser else webbrowser
        if not controller.open(AUTH + '?' + urlencode(params)):
            raise SyncError('Could not open the selected browser')
        print('Complete Google sign-in and consent in your browser. Authorization expires locally in 5 minutes.')
        deadline = time.monotonic() + 300
        while not result and time.monotonic() < deadline:
            server.handle_request()
    if 'code' not in result:
        raise SyncError('Authorization canceled or timed out')
    credentials = dict(client_id=client['client_id'])
    if client.get('client_secret'):
        credentials['client_secret'] = client['client_secret']
    token = request(TOKEN, 'POST', {**credentials, 'code': result['code'][0],
                    'code_verifier': verifier, 'redirect_uri': redirect, 'grant_type': 'authorization_code'}, form=True)
    identity = request(IDENTITY, token=token['access_token'])
    if identity.get('verified_email') is not True or identity.get('email', '').casefold() != account.casefold():
        raise SyncError('Signed-in account differs from the requested account; credentials were not saved')
    if not token.get('refresh_token') or not set(SCOPES).issubset(set(token.get('scope', '').split())):
        raise SyncError('Google did not grant the required offline scopes; connection was not saved')
    store.write('connection.json', dict(credentials=credentials, refresh_token=token['refresh_token'], account=account))
    print('Google account verified and connected. Refresh credentials are stored only in private local state.')


def access_token(store):
    connection = store.read('connection.json')
    if not isinstance(connection, dict):
        raise SyncError('Connect your Google account first')
    response = request(TOKEN, 'POST', {**connection['credentials'], 'refresh_token': connection['refresh_token'],
                       'grant_type': 'refresh_token'}, form=True)
    return response['access_token']


def canonical(event):
    # Normalize Google dateTime formatting, which may use offsets instead of Z.
    from datetime import datetime, timezone
    fields = {'summary': event.get('summary', ''), 'location': event.get('location', '')}
    for name in ('start', 'end'):
        value = event.get(name, {}).get('dateTime')
        if not value:
            raise SyncError('Unexpected all-day or missing event time')
        fields[name] = datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc).isoformat()
    return fields


def digest(event):
    return hashlib.sha256(json.dumps(canonical(event), sort_keys=True).encode()).hexdigest()


def desired_events(schedule):
    namespace = hashlib.sha256(schedule['namespace'].encode()).hexdigest()
    events = {}
    for event in hub.occurrences(schedule):
        event_id = hashlib.sha256(event['uid'].encode()).hexdigest()
        body = dict(id=event_id, summary=event['title'], location=event['location'],
                    start={'dateTime': event['start'].isoformat()}, end={'dateTime': event['end'].isoformat()})
        body['extendedProperties'] = {'private': {'calendarHub': namespace, 'appliedDigest': digest(body)}}
        events[event_id] = body
    return namespace, events


class Google:
    def __init__(self, token):
        self.token = token

    def call(self, path, method='GET', body=None, etag=None):
        return request(API + path, method, body, self.token, etag)

    def events(self, calendar):
        result, page = [], None
        for _ in range(100):
            params = {'maxResults': 2500, 'showDeleted': 'true'}
            if page:
                params['pageToken'] = page
            response = self.call('/calendars/' + quote(calendar, safe='') + '/events?' + urlencode(params))
            result.extend(response.get('items', []))
            page = response.get('nextPageToken')
            if not page:
                return result
        raise SyncError('Calendar pagination exceeded safety limit')


def plan(desired, existing, namespace):
    current = {event['id']: event for event in existing}
    actions, conflicts = [], []
    for event_id, wanted in desired.items():
        found = current.get(event_id)
        if not found:
            actions.append(('create', wanted, None))
            continue
        markers = found.get('extendedProperties', {}).get('private', {})
        if found.get('status') == 'cancelled' or found.get('attendees') or markers.get('calendarHub') != namespace:
            conflicts.append(event_id)
            continue
        if digest(found) != markers.get('appliedDigest'):
            conflicts.append(event_id)
            continue
        if canonical(found) != canonical(wanted):
            if not found.get('etag'):
                conflicts.append(event_id)
            else:
                actions.append(('update', wanted, found['etag']))
    removed = [e['id'] for e in existing if e.get('extendedProperties', {}).get('private', {}).get('calendarHub') == namespace
               and e['id'] not in desired and e.get('status') != 'cancelled']
    return actions, conflicts, removed


def sync(store, schedule, api, apply=False):
    namespace, desired = desired_events(schedule)
    target = store.read('target.json')
    if target and target.get('namespace') != namespace:
        raise SyncError('Schedule namespace changed; a reviewed term migration is required')
    if target and target.get('pending'):
        raise SyncError('Calendar creation outcome is uncertain. Check Google for the created calendar before recovering local state; no second calendar was created.')
    if not target:
        if not apply:
            return {'create_calendar': 1, 'create': len(desired), 'update': 0, 'conflicts': 0, 'removed_needs_review': 0, 'verified': False}
        # Save intent before a non-idempotent remote creation. A crash cannot trigger a duplicate retry.
        store.write('target.json', {'namespace': namespace, 'pending': True})
        calendar = api.call('/calendars', 'POST', {'summary': 'School Classes (Calendar Hub)',
                            'timeZone': schedule['timezone'], 'description': 'Calendar Hub managed class meetings. ' + namespace})
        target = {'namespace': namespace, 'calendar': calendar['id'], 'pending': False}
        store.write('target.json', target)
    path = '/calendars/' + quote(target['calendar'], safe='') + '/events'
    actions, conflicts, removed = plan(desired, api.events(target['calendar']), namespace)
    if apply:
        # Validate the entire plan before writes; manual edits or cancellations never get overwritten.
        if conflicts or removed:
            raise SyncError('Manual edits, cancellations, or removed classes need review; no event writes were performed')
        for kind, body, etag in actions:
            endpoint = path if kind == 'create' else path + '/' + body['id']
            payload = body if kind == 'create' else {k: v for k, v in body.items() if k != 'id'}
            api.call(endpoint + '?sendUpdates=none', 'POST' if kind == 'create' else 'PATCH', payload, etag)
        remaining, conflicts, removed = plan(desired, api.events(target['calendar']), namespace)
        if remaining or conflicts or removed:
            raise SyncError('Destination verification incomplete; rerun preview before further changes')
    return {'create_calendar': 0, 'create': sum(a[0] == 'create' for a in actions),
            'update': sum(a[0] == 'update' for a in actions), 'conflicts': len(conflicts),
            'removed_needs_review': len(removed), 'verified': apply}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=hub.LOCAL)
    commands = parser.add_subparsers(dest='command', required=True)
    login = commands.add_parser('connect')
    login.add_argument('--client', type=Path, required=True)
    login.add_argument('--account', required=True)
    login.add_argument('--browser', default=None)
    login.add_argument('--reauthorize', action='store_true')
    for mode in ('preview', 'sync'):
        command = commands.add_parser(mode)
        command.add_argument('--schedule', type=Path)
        if mode == 'sync':
            command.add_argument('--apply', action='store_true', required=True)
    commands.add_parser('status')
    args = parser.parse_args(argv)
    store = None
    try:
        store = Store(args.state)
        with store.lock():
            if args.command == 'connect':
                connect(store, args.client, args.account, args.browser, args.reauthorize)
            elif args.command == 'status':
                target = store.read('target.json', {})
                print(json.dumps({'connected': bool(store.read('connection.json')),
                                  'calendar_configured': bool(target.get('calendar')) and not target.get('pending'),
                                  'calendar_creation_needs_review': bool(target.get('pending')),
                                  'last_run': store.read('last-run.json')}, indent=2))
            else:
                schedule = hub.load(args.schedule) if args.schedule else store.read('classes.json')
                hub.occurrences(schedule)  # Fail before refresh/network if schedule is unverified.
                result = sync(store, schedule, Google(access_token(store)), args.command == 'sync')
                if args.command == 'sync':
                    store.write('last-run.json', {'at': hub.stamp(hub.datetime.now(hub.UTC)), 'success': True, **result})
                print(json.dumps(result, sort_keys=True))
        return 0
    except (SyncError, hub.ScheduleError, OSError, ValueError, KeyError, TypeError, webbrowser.Error) as error:
        # Credential/remote payloads and user paths must not leak into unattended logs.
        message = str(error) if isinstance(error, (SyncError, hub.ScheduleError)) else 'Check private state permissions, verified schedule, and authorization. No error payload was logged.'
        print('Calendar Hub could not complete the operation. ' + message, file=sys.stderr)
        if store and args.command == 'sync':
            try:
                with store.lock():
                    store.write('last-run.json', {'at': hub.stamp(hub.datetime.now(hub.UTC)), 'success': False})
            except (OSError, ValueError):
                pass
        return 2
    finally:
        if store:
            store.close()


if __name__ == '__main__':
    sys.exit(main())
