"""Capture, review, then explicitly activate official starter announcements."""
import argparse
import base64
import copy
from datetime import datetime, timedelta, timezone
from http.client import HTTPException, IncompleteRead
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pgo_expected_starters import _announcement, _primary_article, select_player
from pgo_season import DEFAULT_ROOT, IDENTITY, URLS, canonical, csv_rows, identity, load_current, require, sha, utc
from pgo_season_availability import _url
from pgo_season_rollover import source_bytes
from pgo_sources import normalize_team


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'data/pgo_starter_announcements.json'
_RECEIPT = re.compile(r'[0-9a-f]{64}\.json')


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _clock():
    return datetime.now(timezone.utc).isoformat()


def _request(url):
    """Return one response without following redirects."""
    request = Request(url, headers={'User-Agent':'Postgame-Outlet starter evidence capture'})
    try:
        response = build_opener(_NoRedirect).open(request, timeout=25)
    except HTTPError as error:
        response = error
    with response:
        try:
            body = response.read(); error = None
        except (IncompleteRead, OSError, HTTPException) as exc:
            body = exc.partial if isinstance(exc, IncompleteRead) else b''
            error = f'Incomplete starter response: {exc}'
        return dict(status=response.status, final_url=response.geturl(),
                    headers={str(k):str(v) for k,v in response.headers.items()}, body=body, error=error)


def _receipt_path(root, folder, value):
    root = Path(root); candidate = Path(value)
    name = candidate.name
    require(_RECEIPT.fullmatch(name) is not None, 'Unsafe starter receipt path')
    expected = root / folder / name
    if candidate.is_absolute():
        require(candidate.resolve() == expected.resolve(), 'Unsafe starter receipt path')
    else:
        require(candidate.as_posix() in (name, f'{folder}/{name}'), 'Unsafe starter receipt path')
    require(not root.is_symlink() and not expected.parent.is_symlink() and not expected.is_symlink(),
            'Unsafe starter receipt path')
    return expected


def _write_hashed(root, folder, value, *, exclusive=True):
    raw = canonical(value); digest = sha(raw)
    directory = Path(root) / folder
    directory.mkdir(parents=True, exist_ok=True)
    require(not Path(root).is_symlink() and not directory.is_symlink(), 'Unsafe starter receipt path')
    path = directory / f'{digest}.json'
    if path.exists() and not exclusive:
        require(not path.is_symlink() and path.read_bytes() == raw, 'Starter evidence hash collision')
    else:
        with path.open('xb') as handle:
            handle.write(raw)
    return path


def _read_receipt(root, folder, value):
    path = _receipt_path(root, folder, value)
    raw = path.read_bytes()
    require(sha(raw) == path.stem, 'Starter receipt hash differs')
    return path, raw, json.loads(raw)


def _context(root, game_id):
    """Load the verified current game and latest saved current-roster bytes."""
    root = Path(root); state = load_current(root)
    require(state is not None, 'No verified current season state')
    games = [game for game in state['schedule'] if game.get('game_id') == game_id]
    require(len(games) == 1 and games[0]['week'] == state['current_week'], 'Starter game is not uniquely current')
    refs = [ref for ref in state.get('source_captures', []) if ref.get('url') == URLS['roster']]
    require(refs, 'Current state has no saved roster source')
    roster_ref = max(refs, key=lambda ref: utc(ref['captured_at']))
    roster = csv_rows(source_bytes(root, roster_ref, state['checked_at']))
    return copy.deepcopy(games[0]), roster, copy.deepcopy(roster_ref), state['checked_at']


def _player(roster, game, team, gsis_id):
    require(team == normalize_team(team) and team in (game['home'], game['away']),
            'Starter team differs from the game')
    rows = [row for row in roster if row.get('gsis_id') == gsis_id]
    require(len(rows) == 1, 'Starter GSIS identity is missing or duplicated')
    decision = dict(game={key:game[key] for key in IDENTITY}, team=team, gsis_id=gsis_id,
                    full_name=rows[0].get('full_name'), statement='pending')
    return select_player(roster, decision, game)


def _config_snapshot(config):
    path = Path(config)
    require(path.name == 'pgo_starter_announcements.json' and not path.is_symlink()
            and not path.parent.is_symlink(), 'Unsafe starter configuration path')
    if not path.exists():
        return {'exists':False}
    raw = path.read_bytes()
    return {'exists':True, 'sha256':sha(raw), 'bytes':len(raw)}


def _fresh_roster(source, checked_at):
    age = utc(checked_at) - utc(source['captured_at'])
    require(timedelta(0) <= age <= timedelta(hours=24), 'Current roster source is future or stale')


def capture(url, game_id, team, gsis_id, statement, *, root=DEFAULT_ROOT, fetch=None, clock=None):
    """Save one exclusive capture receipt; never mutate starter configuration."""
    fetch, clock = fetch or _request, clock or _clock
    game, roster, roster_ref, state_checked_at = _context(root, game_id)
    player = _player(roster, game, team, gsis_id)
    require(isinstance(statement, str) and statement, 'Starter statement is required')
    started = clock(); response = dict(status=None, final_url=None, headers={}, body=b'')
    error = None
    try:
        require(utc(state_checked_at) <= utc(started), 'Current season state is from the future')
        _url(url, team, 'team_news')
        response = fetch(url)
        require(isinstance(response, dict) and type(response.get('status')) is int
                and isinstance(response.get('final_url'), str) and isinstance(response.get('headers'), dict)
                and isinstance(response.get('body'), bytes)
                and (response.get('error') is None or isinstance(response.get('error'), str)),
                'Invalid starter response')
        error = response.get('error')
    except (OSError, HTTPException, ValueError, KeyError, TypeError) as exc:
        error = str(exc)
    completed = clock()
    if error is None and utc(completed) < utc(started):
        error = 'Starter capture clock moved backwards'
    status, final_url = response.get('status'), response.get('final_url')
    if error is None and status != 200:
        error = f'Starter source returned HTTP {status}'
    if error is None and final_url != url:
        error = 'Starter source redirected or final URL differs'
    raw = response.get('body', b'') if isinstance(response.get('body'), bytes) else b''
    receipt = dict(schema_version=1, kind='official_starter_announcement_capture', successful=error is None,
                   url=url, final_url=final_url, status=status,
                   headers={str(k):str(v) for k,v in response.get('headers', {}).items()},
                   started_at=started, captured_at=completed, state_checked_at=state_checked_at,
                   roster_source=roster_ref, game={key:game[key] for key in IDENTITY}, team=team,
                   gsis_id=gsis_id, full_name=player['full_name'], statement=statement,
                   body_base64=base64.b64encode(raw).decode(), raw_sha256=sha(raw), raw_bytes=len(raw),
                   error=error)
    return _write_hashed(root, 'starter-drafts', receipt)


def review(draft, *, root=DEFAULT_ROOT, config=CONFIG, clock=None):
    """Validate a successful capture and save an immutable reviewed source envelope."""
    clock = clock or _clock
    draft_path, draft_raw, captured = _read_receipt(root, 'starter-drafts', draft)
    require(captured.get('schema_version') == 1 and captured.get('kind') == 'official_starter_announcement_capture'
            and captured.get('successful') is True and captured.get('status') == 200
            and captured.get('final_url') == captured.get('url'), 'Starter capture was not successful')
    reviewed_at = clock()
    game, roster, roster_ref, state_checked_at = _context(root, captured['game']['game_id'])
    require(identity(game, captured['game']), 'Current starter game differs from the capture')
    require(utc(state_checked_at) <= utc(reviewed_at), 'Current season state is from the future')
    _fresh_roster(roster_ref, reviewed_at)
    require(utc(captured['started_at']) <= utc(captured['captured_at']) <= utc(reviewed_at),
            'Starter capture or review time is from the future')
    raw = base64.b64decode(captured['body_base64'], validate=True)
    require(len(raw) == captured['raw_bytes'] and sha(raw) == captured['raw_sha256'],
            'Starter capture body differs')
    article = _primary_article(raw)
    player = _player(roster, game, captured['team'], captured['gsis_id'])
    decision = dict(game={key:game[key] for key in IDENTITY}, team=captured['team'],
                    gsis_id=captured['gsis_id'], full_name=player['full_name'], statement=captured['statement'])
    envelope = dict(schema_version=1, kind='official_starter_announcement', url=captured['url'],
                    final_url=captured['final_url'], status=captured['status'], headers=captured['headers'],
                    started_at=captured['started_at'], captured_at=captured['captured_at'],
                    reviewed_at=reviewed_at, published_at=article['datePublished'],
                    modified_at=article.get('dateModified', article['datePublished']), decision=decision,
                    body_base64=captured['body_base64'], raw_sha256=captured['raw_sha256'],
                    raw_bytes=captured['raw_bytes'])
    source_raw = canonical(envelope); source_digest = sha(source_raw)
    source = dict(path=f'source-archive/{source_digest}.json', url=envelope['url'],
                  captured_at=envelope['captured_at'], sha256=source_digest, bytes=len(source_raw))
    # Validate with the production replay path before admitting bytes to the real archive.
    with tempfile.TemporaryDirectory() as temporary:
        temporary_root = Path(temporary); path = temporary_root / source['path']
        path.parent.mkdir(parents=True); path.write_bytes(source_raw)
        admitted = _announcement(game, source, temporary_root, reviewed_at)
        select_player(roster, admitted, game)
    _write_hashed(root, 'source-archive', envelope, exclusive=False)
    admitted = _announcement(game, source, root, reviewed_at)
    select_player(roster, admitted, game)
    capture_ref = dict(path=draft_path.relative_to(root).as_posix(), sha256=sha(draft_raw), bytes=len(draft_raw))
    receipt = dict(schema_version=1, kind='official_starter_announcement_review', reviewed_at=reviewed_at,
                   capture=capture_ref, source=source, config=_config_snapshot(config))
    return _write_hashed(root, 'starter-reviews', receipt)


def activate(reviewed, *, root=DEFAULT_ROOT, config=CONFIG, clock=None):
    """Atomically append one reviewed game/team rule after current-state revalidation."""
    clock = clock or _clock
    _, _, receipt = _read_receipt(root, 'starter-reviews', reviewed)
    require(receipt.get('schema_version') == 1 and receipt.get('kind') == 'official_starter_announcement_review',
            'Invalid starter review receipt')
    _, capture_raw, captured = _read_receipt(root, 'starter-drafts', receipt['capture']['path'])
    require((sha(capture_raw), len(capture_raw)) == (receipt['capture']['sha256'], receipt['capture']['bytes'])
            and captured.get('successful') is True, 'Reviewed starter capture differs')
    activated_at = clock()
    game, roster, roster_ref, state_checked_at = _context(root, captured['game']['game_id'])
    require(identity(game, captured['game']), 'Current starter game differs from reviewed evidence')
    require(utc(state_checked_at) <= utc(activated_at), 'Current season state is from the future')
    _fresh_roster(roster_ref, activated_at)
    require(utc(activated_at) < utc(game['kickoff']) - timedelta(minutes=60),
            'Starter activation must finish before T-60')
    decision = _announcement(game, receipt['source'], root, activated_at)
    select_player(roster, decision, game)
    path = Path(config)
    _config_snapshot(path)  # Validate the operator path before creating its parent or lock.
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.parent / f'.{path.name}.activation.lock'
    acquired = False
    try:
        try:
            with lock.open('xb'):
                pass
            acquired = True
        except FileExistsError as error:
            raise ValueError('Starter configuration activation is busy') from error
        current_snapshot = _config_snapshot(path)
        require(current_snapshot == receipt['config'], 'Starter configuration drifted after review')
        if current_snapshot['exists']:
            value = json.loads(path.read_bytes())
            require(isinstance(value, dict) and type(value.get('schema_version')) is int
                    and value['schema_version'] == 1 and isinstance(value.get('announcements'), list),
                    'Invalid starter announcement configuration')
        else:
            value = {'schema_version':1, 'announcements':[]}
        for rule in value['announcements']:
            require(isinstance(rule, dict) and set(rule) == {'game_id','source'},
                    'Invalid starter announcement configuration')
            if rule['game_id'] == game['game_id']:
                existing = _announcement(game, rule['source'], root, activated_at)
                require(existing['team'] != decision['team'],
                        f"{game['game_id']} already has a starter announcement for {decision['team']}")
        rule = dict(game_id=game['game_id'], source=copy.deepcopy(receipt['source']))
        value['announcements'].append(rule)
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp')
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as handle:
                handle.write(canonical(value).decode()); handle.flush(); os.fsync(handle.fileno())
            require(_config_snapshot(path) == receipt['config'], 'Starter configuration drifted during activation')
            durable_at = clock()
            require(utc(activated_at) <= utc(durable_at), 'Starter activation clock moved backwards')
            require(utc(durable_at) < utc(game['kickoff']) - timedelta(minutes=60),
                    'Starter activation must finish before T-60')
            os.replace(temporary, path); temporary = None
        finally:
            if temporary is not None:
                try: os.unlink(temporary)
                except FileNotFoundError: pass
        return rule
    finally:
        if acquired:
            try: os.unlink(lock)
            except FileNotFoundError: pass


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    commands = parser.add_subparsers(dest='command', required=True)
    command = commands.add_parser('capture')
    for name in ('url','game-id','team','gsis-id','statement'):
        command.add_argument('--'+name, required=True)
    command = commands.add_parser('review'); command.add_argument('--draft', required=True)
    command = commands.add_parser('activate'); command.add_argument('--review', required=True)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == 'capture':
            path = capture(args.url, args.game_id, args.team, args.gsis_id, args.statement, root=args.root)
            print(path)
            return 0 if json.loads(path.read_bytes())['successful'] else 1
        if args.command == 'review':
            print(review(args.draft, root=args.root))
            return 0
        print(activate(args.review, root=args.root))
        return 0
    except (KeyError, OSError, TypeError, ValueError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
