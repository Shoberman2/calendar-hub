#!/usr/bin/env python3
"""Local onboarding and agent discovery. Never logs in or changes a provider."""
import argparse
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import re
import shutil
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import calendar_hub as hub
from google_sync import Store, SyncError

ROOT = Path(__file__).resolve().parent
SKILL = ROOT / '.claude' / 'skills' / 'calendar-hub'
PROVIDERS = ('google', 'icloud', 'microsoft365', 'canvas', 'ics', 'other')
CLIENTS = ('apple-mac', 'apple-iphone', 'google-web')
STATUSES = ('pending', 'attempted', 'verified', 'blocked', 'skipped')


def clean(value, name, maximum=200):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise SyncError(name + ' must be a nonempty single line')
    if '://' in value:
        raise SyncError('Keep URLs and credentials out of the account inventory; record them separately in private state only when needed')
    return value.strip()


def validate_profile(profile):
    if not isinstance(profile, dict) or profile.get('version') != 1:
        raise SyncError('Unsupported profile format')
    clean(profile.get('name'), 'Name')
    clean(profile.get('browser'), 'Browser')
    try:
        ZoneInfo(profile.get('timezone', ''))
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise SyncError('Use an IANA timezone such as America/New_York') from None
    destinations = profile.get('destinations')
    if not isinstance(destinations, list) or not destinations or any(x not in CLIENTS for x in destinations):
        raise SyncError('Choose supported destination clients')
    if profile.get('computer_use') not in ('when-approved', 'manual-only'):
        raise SyncError('Choose when-approved or manual-only for computer use')
    if type(profile.get('daily_check_requested')) is not bool:
        raise SyncError('Daily-check preference must be true or false')
    sources = profile.get('sources')
    if not isinstance(sources, list) or not 1 <= len(sources) <= 50:
        raise SyncError('List 1–50 source accounts')
    seen = set()
    for source in sources:
        if not isinstance(source, dict):
            raise SyncError('Each source must be an object')
        identifier = source.get('id')
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,49}', identifier) or identifier in seen:
            raise SyncError('Source IDs must be unique lowercase identifiers')
        seen.add(identifier)
        if source.get('provider') not in PROVIDERS:
            raise SyncError('Unsupported provider; choose other for manual assessment')
        clean(source.get('account'), 'Account')
        clean(source.get('label'), 'Calendar label')
        clean(source.get('category'), 'Category')
        if not isinstance(source.get('color'), str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', source['color']):
            raise SyncError('Colors must use #RRGGBB')
    google_id = profile.get('google_hub_source')
    if 'google-web' in destinations and not any(s['id'] == google_id and s['provider'] == 'google' for s in sources):
        raise SyncError('Select a Google source account for the Google hub')
    return profile


def routes(profile):
    """Enumerate expected connections without pretending they exist."""
    validate_profile(profile)
    rows = []
    for source in profile['sources']:
        for destination in profile['destinations']:
            provider = source['provider']
            if destination.startswith('apple'):
                method = {'google': 'native Google account', 'icloud': 'native iCloud account',
                          'microsoft365': 'native Exchange account', 'canvas': 'LMS ICS subscription',
                          'ics': 'ICS subscription', 'other': 'provider assessment required'}[provider]
            else:
                method = {'google': 'native hub' if source['id'] == profile['google_hub_source'] else 'account-specific sharing assessment',
                          'icloud': 'optional approved read-only public subscription',
                          'microsoft365': 'optional approved published ICS subscription',
                          'canvas': 'LMS ICS subscription', 'ics': 'ICS subscription',
                          'other': 'provider assessment required'}[provider]
            rows.append({'id': source['id'] + ':' + destination, 'source': source['id'],
                         'destination': destination, 'method': method})
    return rows


def install_agents(repo, home, agent):
    source = (repo / '.claude' / 'skills' / 'calendar-hub').resolve(strict=True)
    if not (source / 'SKILL.md').is_file():
        raise SyncError('The download is missing the Calendar Hub skill')
    targets = []
    for name in (('claude', 'codex') if agent == 'both' else (agent,)):
        if name not in ('claude', 'codex'):
            raise SyncError('Unknown assistant')
        parent = home / ('.claude' if name == 'claude' else '.agents') / 'skills'
        target = parent / 'calendar-hub'
        if target.exists() or target.is_symlink():
            if not target.is_symlink() or target.resolve() != source:
                raise SyncError('An unrelated Calendar Hub skill already exists; inspect it before installing. Nothing was replaced.')
        targets.append((name, target))
    # Check every collision first, so a conflict for the second agent cannot
    # silently leave only the first configured.
    for _, target in targets:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not target.is_symlink():
            target.symlink_to(source, target_is_directory=True)
    return [name for name, _ in targets]


def prompt(default=''):
    return input('> ').strip() or default


def choose(question, options, default):
    while True:
        print(question + ' [' + '/'.join(options) + '] (' + default + ')')
        answer = prompt(default)
        if answer in options:
            return answer
        print('Choose one of the listed options.')


def ask(question, default=''):
    print(question + (f' ({default})' if default else ''))
    return prompt(default)


def wizard(store):
    existing = store.read('profile.json')
    if existing:
        validate_profile(existing)
        print('Your profile already exists; it was preserved. Ask your assistant to read and update the private profile only where your preferences changed.')
        return existing
    print('Calendar Hub setup. No passwords, tokens, or feed links are requested here.')
    name = ask('What name should your assistant use?')
    zone = ask('Your IANA timezone', 'America/New_York')
    browser = ask('Preferred signed-in browser', 'Safari')
    phone = choose('Include Apple Calendar on iPhone?', ('yes', 'no'), 'yes')
    computer = choose('Use available computer tools when allowed, or manual steps only?', ('when-approved', 'manual-only'), 'when-approved')
    sources = []
    palette = {'school': '#4285F4', 'work': '#34A853', 'personal': '#F09300', 'second-work': '#8E24AA'}
    while True:
        provider = choose('Add an account provider', PROVIDERS, 'google')
        account = ask('Account email or a descriptive account identifier (no URLs)')
        label = ask('Display label', provider.title())
        category = choose('Category', tuple(palette), 'school' if provider == 'canvas' else 'work')
        sources.append({'id': 'source-' + str(len(sources) + 1), 'provider': provider, 'account': account,
                        'label': label, 'category': category, 'color': palette[category]})
        if choose('Add another account or school feed source?', ('yes', 'no'), 'no') == 'no':
            break
    google = [s for s in sources if s['provider'] == 'google']
    if not google:
        raise SyncError('A Google account is needed for the requested Google hub. Rerun setup and include it; no profile was saved.')
    selected = google[0]['id']
    if len(google) > 1:
        for source in google:
            print(source['id'] + ': ' + source['label'])
        selected = choose('Which Google account is the hub?', tuple(s['id'] for s in google), selected)
    daily = choose('Ask your assistant to set up a daily reconciliation check?', ('yes', 'no'), 'yes')
    profile = {'version': 1, 'name': name, 'timezone': zone, 'browser': browser,
               'destinations': ['apple-mac', 'google-web'] + (['apple-iphone'] if phone == 'yes' else []),
               'computer_use': computer, 'daily_check_requested': daily == 'yes',
               'google_hub_source': selected, 'sources': sources}
    validate_profile(profile)
    store.write('profile.json', profile)
    return profile


def profile_digest(profile):
    return hashlib.sha256(json.dumps(validate_profile(profile), sort_keys=True).encode()).hexdigest()


def validate_ledger(ledger):
    if not isinstance(ledger, dict) or any(
        not isinstance(value, dict) or value.get('status') not in STATUSES
        for value in ledger.values()
    ):
        raise SyncError('Invalid connection records; inspect the private ledger before continuing')
    return ledger


def report(profile, ledger):
    validate_ledger(ledger)
    digest = profile_digest(profile)
    rows = routes(profile)
    for row in rows:
        saved = ledger.get(row['id'], {})
        if saved.get('profile_digest') != digest:
            saved = {}
        row.update(status=saved.get('status', 'pending'), checked_at=saved.get('checked_at'))
    counts = {status: sum(r['status'] == status for r in rows) for status in STATUSES}
    return {'connections': rows, 'counts': counts,
            'all_connections_recorded_verified': bool(rows) and counts['verified'] == len(rows),
            'note': 'Verification entries are observations recorded by your assistant or you, not independent live provider probes.'}


def record_check(store, route_id, status, evidence):
    profile = store.read('profile.json')
    expected = {r['id'] for r in routes(profile)}
    if route_id not in expected or status not in STATUSES:
        raise SyncError('Unknown connection or status')
    evidence = clean(evidence.strip(), 'Evidence', maximum=2000)
    ledger = validate_ledger(store.read('connections.json', {}))
    ledger[route_id] = {'status': status, 'evidence': evidence,
                        'checked_at': datetime.now(timezone.utc).isoformat(),
                        'profile_digest': profile_digest(profile)}
    store.write('connections.json', ledger)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=ROOT / '.calendar-hub')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('start', help='Interactive local account inventory and assistant installation')
    install = commands.add_parser('install', help='Install discoverable local assistant skills, without provider access')
    install.add_argument('--agent', choices=('claude', 'codex', 'both'), default='both')
    commands.add_parser('doctor', help='Check local readiness; does not access provider accounts')
    commands.add_parser('status', help='Summarize recorded per-destination verification')
    check = commands.add_parser('record', help='Record observed connection evidence, without performing provider actions')
    check.add_argument('--route', required=True)
    check.add_argument('--status', choices=STATUSES, required=True)
    check.add_argument('--evidence-file', type=Path, required=True, help='Local note without URLs; never put private evidence in shell arguments')
    args = parser.parse_args(argv)
    store = None
    try:
        if args.command == 'install':
            print('Installed for: ' + ', '.join(install_agents(ROOT, Path.home(), args.agent)))
            print('Keep this folder in place. Restart your assistant if the skill is not listed.')
            return 0
        if args.command == 'start':
            hub.initialize(args.state)
        store = Store(args.state)
        with store.lock():
            if args.command == 'start':
                wizard(store)
                assistant = choose('Install Calendar Hub instructions for', ('claude', 'codex', 'both', 'none'), 'both')
                if assistant != 'none':
                    install_agents(ROOT, Path.home(), assistant)
                print('\nLocal setup saved. Provider connections are still pending verification.')
                print('In Claude Code: /calendar-hub Set up and verify my calendars using my private profile.')
                print('In Codex: $calendar-hub Set up and verify my calendars using my private profile.')
                print('Use a local session with access to this folder. You handle passwords/MFA; the assistant must check tool permissions before computer use.')
            elif args.command == 'record':
                record_check(store, args.route, args.status, args.evidence_file.read_text())
                print('Observation recorded. This command did not test or change the provider.')
            elif args.command == 'status':
                print(json.dumps(report(store.read('profile.json'), store.read('connections.json', {})), indent=2))
            else:
                profile = store.read('profile.json')
                if profile:
                    validate_profile(profile)
                installed = {}
                for agent, parent in (('claude', '.claude'), ('codex', '.agents')):
                    link = Path.home() / parent / 'skills' / 'calendar-hub'
                    installed[agent] = link.is_symlink() and link.resolve() == SKILL.resolve()
                print(json.dumps({'python_supported': sys.version_info >= (3, 10),
                                  'profile_ready': bool(profile), 'agent_skills_installed': installed,
                                  'cli_detected': {x: bool(shutil.which(x)) for x in ('claude', 'codex')},
                                  'computer_use': 'must be checked in the assistant session',
                                  'provider_sync': 'not tested by doctor',
                                  'google_class_connector_configured': bool(store.read('connection.json'))}, indent=2))
        return 0
    except (SyncError, hub.ScheduleError, OSError, ValueError, TypeError, EOFError, KeyboardInterrupt) as error:
        detail = str(error) if isinstance(error, (SyncError, hub.ScheduleError)) else 'Setup stopped. Check local permissions and input; no raw private data was logged.'
        print(detail, file=sys.stderr)
        return 2
    finally:
        if store:
            store.close()


if __name__ == '__main__':
    sys.exit(main())
