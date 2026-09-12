"""Notify the PGO owner through one deduplicated, bot-owned GitHub issue."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request
import uuid

from pgo_season import DEFAULT_ROOT, SEASON, availability_watch, load_current, now, utc
from pgo_sources import CURRENT_TEAMS
from pgo_workflow_status import report_health

REPOSITORY = 'walshja9/Postgame_Outlet'
ASSIGNEE = 'walshja9'
BOT = 'github-actions[bot]'
MARKER = '<!-- pgo-alerts:v1 -->'
META = re.compile(r'<!-- pgo-alert-state:(\{[^\n]*\}) -->')
RUN_URL = 'https://github.com/' + REPOSITORY + '/actions/runs/1'
STAGES = ('verify', 'refresh', 'render', 'publish', 'rollover')
FAILURE_CATEGORIES = ('ISSUE_RESPONSE', 'ISSUE_OWNERSHIP', 'ISSUE_METADATA', 'ISSUE_DUPLICATE', 'ISSUE_CONFIRMATION')
PUBLIC_POINTER = 'https://walshja9.github.io/Postgame_Outlet/evidence/season-2026/current.json'
NOT_CHECKED = object()


def assess(state, *, outcomes, run_refresh=True, checked_at=None, refresh_started_at=None, public_pointer=NOT_CHECKED):
    """Read verified saved state; never fetch sources or change predictions."""
    checked = utc(checked_at or now())
    report = dict(checked_at=checked.isoformat(), state_checked_at=None, public_checked_at=None,
                  conditions=[], can_resolve=False)
    if not run_refresh:
        return dict(report, skipped=True)

    def add(key, message, urgent=False):
        report['conditions'].append(dict(key=key, message=message, urgent=urgent))

    public_ready = False
    if public_pointer is not NOT_CHECKED:
        try:
            if (not isinstance(public_pointer, dict)
                    or not re.fullmatch(r'runs(?:-v2)?/\d{8}T\d{12}Z', public_pointer.get('path', ''))
                    or not re.fullmatch(r'[0-9a-f]{64}', public_pointer.get('manifest_sha256', ''))):
                raise ValueError('Invalid public pointer')
            stamp = utc(public_pointer['checked_at'])
            report['public_checked_at'] = stamp.isoformat()
            public_ready = 0 <= (checked - stamp).total_seconds() <= 45 * 60
            if not public_ready:
                raise ValueError('Public pointer time is unavailable or stale')
        except (ValueError, TypeError, KeyError):
            add('public-update', 'The public season update is unavailable, unverified or more than 45 minutes old. Check Pages publication.')
    failures = [stage for stage in STAGES if outcomes.get(stage) in ('failure', 'cancelled')]
    for stage in failures:
        add('failed-' + stage, 'The ' + stage + ' stage did not complete successfully. Review the linked workflow.')
    if not failures and any(outcomes.get(stage) != 'success' for stage in STAGES):
        add('pipeline-incomplete', 'The update did not complete every required stage. Review the linked workflow.')
    try:
        if not isinstance(state, dict) or state.get('schema_version') != 1 or state.get('season') != SEASON:
            raise ValueError('Invalid state')
        if state.get('status') not in ('READY', 'BLOCKED') or not state.get('weeks'):
            raise ValueError('Invalid state')
        saved = utc(state['checked_at'])
        if saved > checked:
            raise ValueError('Future state')
        games = [game for week in state['weeks'] for game in week['games']]
        if not games or len({game['game_id'] for game in games}) != len(games):
            raise ValueError('Invalid game inventory')
        for game in games:
            if game['home'] not in CURRENT_TEAMS or game['away'] not in CURRENT_TEAMS or game['home'] == game['away']:
                raise ValueError('Invalid teams')
            if not re.fullmatch(r'\d{4}_\d{2}_[A-Z]{2,3}_[A-Z]{2,3}', game['game_id']):
                raise ValueError('Invalid game id')
            utc(game['kickoff']); utc(game['lock_at'])
        # The existing health classifier owns source/next-week distinctions. Discard its
        # raw logging here: public alerts use only fixed descriptions, never error text.
        with contextlib.redirect_stdout(io.StringIO()):
            health = report_health(state)
        watch = availability_watch(state, checked.isoformat())
        report['state_checked_at'] = saved.isoformat()
        if (checked - saved).total_seconds() > 45 * 60 and not state.get('season_complete'):
            add('automation-overdue', 'No saved automation check within 45 minutes. Check the workflow schedule and latest run.')
        if health['condition'] not in ('READY', 'WAITING_FOR_NEXT_WEEK'):
            add('source-review', 'A saved source or availability update needs review. Check the linked workflow and saved health report.')
        if health['condition'] == 'WAITING_FOR_NEXT_WEEK' and _weekly_wait_overdue(state, checked):
            add('weekly-update-overdue', 'All current-week games have verified finals, but the next edition is still missing more than six hours later. Review weekly input availability.')
        if health['ats_status'] == 'BLOCKED':
            add('ats-source-review', 'The saved sportsbook-line update needs review. Existing locked lines remain unchanged.')
        for prefix, label in [('penalty', 'penalty comparison'), ('totals', 'scoring comparison'),
                              ('weights', 'model-weight comparison'), ('replacement_depth', 'defender evidence'),
                              ('injury_usage', 'postgame defender usage'),
                              ('offensive_inventory', 'offensive player inventory'),
                              ('offensive_usage', 'postgame offensive usage'),
                              ('score_range_collection', 'future score-error collection')]:
            if health[prefix + '_status'] == 'BLOCKED':
                add('monitor-' + prefix.replace('_', '-'), 'The independent ' + label
                    + ' update is blocked. Main picks and grades are checked separately.')
        if watch.get('blocked_reason'):
            add('inactive-source-review', 'The latest official inactive-list check could not be verified.',
                any(utc(game['kickoff']) > checked for game in watch['games']))
        for game in watch['games']:
            if game['status'] in ('MISSING', 'STALE'):
                reason = ('final inactive lists are missing for ' + ', '.join(game['missing_teams'])
                          if game['status'] == 'MISSING' else 'the final inactive-list check is overdue')
                add('inactive:' + game['game_id'], game['away'] + ' at ' + game['home'] + ': ' + reason
                    + '. Kickoff ' + utc(game['kickoff']).isoformat() + '.', utc(game['kickoff']) > checked)
        finals = {result['game_id'] for result in state.get('results', [])}
        for game in games:
            remaining = (utc(game['kickoff']) - checked).total_seconds()
            if game['game_id'] in finals or not 3600 < remaining <= 86400:
                continue
            observed = (game.get('availability') or {}).get('checked_at')
            if not observed or not 0 <= (checked - utc(observed)).total_seconds() <= 30 * 60:
                add('availability:' + game['game_id'], game['away'] + ' at ' + game['home']
                    + ': the pre-lock availability check is missing or more than 30 minutes old.', remaining <= 75 * 60)
        report['can_resolve'] = (public_ready and not report['conditions'] and all(outcomes.get(stage) == 'success' for stage in STAGES)
            and bool(refresh_started_at) and utc(refresh_started_at) <= saved <= checked
            and (checked - saved).total_seconds() <= 45 * 60)
    except (ValueError, TypeError, KeyError, AttributeError):
        add('state-unverified', 'The saved season state or its observation time could not be verified. Review the workflow before clearing this alert.')
        report['can_resolve'] = False
    report['conditions'].sort(key=lambda item: item['key'])
    return report


def _weekly_wait_overdue(state, checked):
    week = state['current_week']
    scheduled = [game for game in state['schedule'] if game['week'] == week]
    results = {result['game_id']: result for result in state['results']}
    if len(results) != len(state['results']) or len({game['game_id'] for game in scheduled}) != len(scheduled):
        raise ValueError('Duplicate weekly identity')
    if not scheduled or not all(game['game_id'] in results for game in scheduled):
        return False
    finished = []
    for game in scheduled:
        result = results[game['game_id']]
        if (any(result.get(key) != game.get(key) for key in ('season', 'week', 'kickoff', 'game_type'))
                or result.get('home_team') != game['home'] or result.get('away_team') != game['away']):
            raise ValueError('Final identity differs')
        stamp = utc(result['finalized_at'])
        if not utc(game['kickoff']) <= stamp <= checked:
            raise ValueError('Final time differs')
        finished.append(stamp)
    return (checked - max(finished)).total_seconds() > 6 * 3600


def fetch_public_pointer():
    """One fixed deployment-health GET; this does not collect new model inputs."""
    try:
        request = urllib.request.Request(PUBLIC_POINTER, headers={'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.geturl() != PUBLIC_POINTER:
                return None
            raw = response.read(65537)
        return json.loads(raw) if len(raw) <= 65536 else None
    except (OSError, ValueError):
        return None


def issue_body(report, run_url, pending=None):
    if not re.fullmatch(r'https://github\.com/walshja9/Postgame_Outlet/actions/runs/\d+(?:/attempts/\d+)?', run_url):
        raise ValueError('Untrusted workflow URL')
    metadata = {'conditions': {row['key']: row['urgent'] for row in report['conditions']}}
    if pending:
        metadata['pending'] = pending
    commissioning = set(metadata['conditions']) == {'commissioning'}
    intro = 'This is a notification setup check, not a model or data failure.' if commissioning else 'PGO needs an operator check.'
    lines = [MARKER, '<!-- pgo-alert-state:' + json.dumps(metadata, sort_keys=True, separators=(',', ':')) + ' -->',
             intro, '', *['- ' + row['message'] for row in report['conditions']], '',
             'Observed: ' + report['checked_at'] + '.', '[Open the workflow run](' + run_url + ').', '',
             'Saved picks and grades are not changed by this notification. This issue is assigned only to the PGO owner.',
             'GitHub delivery does not confirm that email or mobile notifications were received.']
    return '\n'.join(lines)


def github_api(method, path, payload=None):
    command = ['gh', 'api', '--method', method, '-H', 'Accept: application/vnd.github+json', path]
    if payload is not None:
        command += ['--input', '-']
    try:
        result = subprocess.run(command, input=json.dumps(payload) if payload is not None else None,
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError('GitHub request failed')
        return json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raise RuntimeError('GitHub request failed') from None


class AlertError(ValueError):
    """A fixed public-safe delivery failure category."""


def _issue_metadata(row):
    if (not isinstance(row, dict) or type(row.get('number')) is not int or row['number'] < 1
            or row.get('state') != 'open' or not isinstance(row.get('body'), str)):
        raise AlertError('ISSUE_RESPONSE')
    if ('pull_request' in row or not isinstance(row.get('user'), dict)
            or row['user'].get('login') != BOT or row['user'].get('type') != 'Bot'
            or not isinstance(row.get('assignees'), list)
            or any(not isinstance(user, dict) for user in row['assignees'])
            or [user.get('login') for user in row['assignees']] != [ASSIGNEE]):
        raise AlertError('ISSUE_OWNERSHIP')
    matches = META.findall(row['body'])
    if row['body'].count(MARKER) != 1 or len(matches) != 1:
        raise AlertError('ISSUE_METADATA')
    try:
        metadata = json.loads(matches[0])
    except ValueError:
        raise AlertError('ISSUE_METADATA') from None
    if (not isinstance(metadata, dict) or not isinstance(metadata.get('conditions'), dict)
            or not all(isinstance(key, str) and type(value) is bool for key, value in metadata['conditions'].items())
            or ('pending' in metadata and not re.fullmatch(r'[0-9a-f]{32}', str(metadata['pending'])))):
        raise AlertError('ISSUE_METADATA')
    return metadata


def _owned_issue(api):
    found = []
    page = 1
    while True:
        rows = api('GET', 'repos/' + REPOSITORY + '/issues?state=open&per_page=100&page=' + str(page))
        if not isinstance(rows, list):
            raise AlertError('ISSUE_RESPONSE')
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('body') or '', str):
                raise AlertError('ISSUE_RESPONSE')
            if MARKER not in (row.get('body') or ''):
                continue
            found.append((row, _issue_metadata(row)))
        if len(rows) < 100:
            break
        page += 1
    if len(found) > 1:
        raise AlertError('ISSUE_DUPLICATE')
    return found[0] if found else (None, {})


def deliver(report, api, run_url):
    """Requires the existing board-update concurrency lock; unchanged incidents make no writes."""
    if report.get('skipped'):
        return {'action': 'skipped'}
    body = issue_body(report, run_url)
    issue, metadata = _owned_issue(api)
    previous = metadata.get('conditions', {})
    current = {row['key']: row['urgent'] for row in report['conditions']}
    base = 'repos/' + REPOSITORY + '/issues'
    if current:
        title = '[PGO] ' + ('Notification delivery check' if set(current) == {'commissioning'} else
                           'Urgent availability check' if any(current.values()) else 'Update needs attention')
        if issue is None:
            issue = api('POST', base, dict(title=title, body=body, assignees=[ASSIGNEE]))
            metadata = _issue_metadata(issue)
            if metadata.get('conditions') != current:
                raise AlertError('ISSUE_CONFIRMATION')
            confirmed = api('GET', base + '/' + str(issue['number']))
            if _issue_metadata(confirmed) != metadata or confirmed['number'] != issue['number']:
                raise AlertError('ISSUE_CONFIRMATION')
            # GitHub has no atomic create-if-absent operation. The workflow lock is the
            # race prevention. The list may lag the confirmed direct issue read, but
            # an observed duplicate or different incident still fails visibly.
            observed, listed_metadata = _owned_issue(api)
            if observed and (observed['number'] != issue['number'] or listed_metadata != metadata):
                raise AlertError('ISSUE_CONFIRMATION')
            return dict(action='created', issue=issue['number'])
        if current == previous and not metadata.get('pending'):
            return dict(action='unchanged', issue=issue['number'])
        escalate = any(key not in previous or urgent and not previous[key] for key, urgent in current.items())
        path = base + '/' + str(issue['number'])
        pending = uuid.uuid4().hex if escalate else metadata.get('pending')
        api('PATCH', path, dict(title=title, body=issue_body(report, run_url, pending)))
        if pending:
            marker = '<!-- pgo-alert-notification:' + pending + ' -->'
            page, sent = 1, False
            while True:
                comments = api('GET', path + '/comments?per_page=100&page=' + str(page))
                if not isinstance(comments, list):
                    raise AlertError('ISSUE_RESPONSE')
                for comment in comments:
                    if not isinstance(comment, dict) or not isinstance(comment.get('body'), str):
                        raise AlertError('ISSUE_RESPONSE')
                    if marker in comment['body']:
                        if (not isinstance(comment.get('user'), dict) or comment['user'].get('login') != BOT
                                or comment['user'].get('type') != 'Bot'):
                            raise AlertError('ISSUE_OWNERSHIP')
                        sent = True
                if len(comments) < 100:
                    break
                page += 1
            if not sent:
                api('POST', path + '/comments', {'body': marker + '\nNew condition requires review.\n\n' + body})
            api('PATCH', path, dict(title=title, body=body))
        return dict(action='escalated' if pending else 'updated', issue=issue['number'])
    if issue and report['can_resolve']:
        api('PATCH', base + '/' + str(issue['number']), dict(state='closed', state_reason='completed',
            body=body.replace('PGO needs an operator check.', 'Resolved after a fresh saved refresh and publication request.')))
        return dict(action='resolved', issue=issue['number'])
    return dict(action='held' if issue else 'healthy')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--run-refresh', default='true', choices=('true', 'false', ''))
    for stage in STAGES:
        parser.add_argument('--' + stage + '-outcome', default='')
    parser.add_argument('--refresh-started-at')
    parser.add_argument('--check-public', action='store_true', help='Check the fixed public season pointer; required for resolution')
    parser.add_argument('--deliver', action='store_true', help='Send owner-only GitHub issue updates; default prints a dry run')
    args = parser.parse_args()
    state = None
    if args.run_refresh != 'false':
        try:
            state = load_current(args.root)
        except (OSError, ValueError, KeyError, TypeError, ImportError):
            pass
    report = assess(state, outcomes={stage: getattr(args, stage + '_outcome') for stage in STAGES},
                    run_refresh=args.run_refresh != 'false', refresh_started_at=args.refresh_started_at,
                    public_pointer=fetch_public_pointer() if args.check_public and args.run_refresh != 'false' else NOT_CHECKED)
    print(json.dumps(report, indent=2))
    if args.deliver:
        if os.environ.get('GITHUB_REPOSITORY') != REPOSITORY:
            raise ValueError('Notification repository is not authorized')
        run_id = os.environ.get('GITHUB_RUN_ID', '')
        attempt = os.environ.get('GITHUB_RUN_ATTEMPT', '1')
        url = 'https://github.com/' + REPOSITORY + '/actions/runs/' + run_id + '/attempts/' + attempt
        print(json.dumps(deliver(report, github_api, url), sort_keys=True))


def cli():
    try:
        main()
    except (RuntimeError, ValueError, KeyError, TypeError) as error:
        category = str(error) if isinstance(error, AlertError) and str(error) in FAILURE_CATEGORIES else 'GITHUB_API' if isinstance(error, RuntimeError) else 'INPUT_INVALID'
        print('::error::PGO alert delivery was not verified [' + category + ']. Check the alert and workflow permissions.')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(cli())
