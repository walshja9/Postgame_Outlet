"""Replay descriptive injury/usage admission from preserved bytes; never fit a model."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import re

from pgo_sources import normalize_team
from pgo_season import load_current
from research.pgo_replacement_depth_20260910 import capture as prior

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PREGAME = ROOT/'research/pgo_replacement_depth_20260910/capture03'
PREGAME_SHA = 'b934339a9a03589fb60949d9e03c3ba76336c4b7922ef1da1e0319abcef3f26a'
URL = 'https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_2026.csv'


def link(snapshot, roster, snaps, finals, target_captured_at):
    """Join exact event/team/PFR-to-GSIS identities. Missing rows are not zero snaps."""
    clock = prior._utc(target_captured_at)
    games = {g['game_id']: g for g in snapshot['games']}
    prior._require(len(games) == len(snapshot['games']), 'Duplicate pregame game')
    final_by_id = {g['game_id']: g for g in finals}
    prior._require(len(final_by_id) == len(finals), 'Duplicate final')
    identities = defaultdict(set)
    for r in roster:
        if str(r.get('season')) == '2026' and r.get('pfr_id') and re.fullmatch(r'00-\d{7}', r.get('gsis_id','')):
            identities[normalize_team(r['team']), r['pfr_id']].add(r['gsis_id'])
    target = defaultdict(list)
    identity_counts = Counter()
    excluded = []
    for number, r in enumerate(snaps, 2):
        reasons = []
        game = games.get(r.get('game_id'))
        team = normalize_team(r.get('team',''))
        if game is None:
            reasons.append('NO_PRESERVED_PREGAME_GAME')
        elif team not in (game['home'], game['away']) or normalize_team(r.get('opponent','')) != (game['away'] if team == game['home'] else game['home']):
            reasons.append('EVENT_TEAM_OPPONENT_MISMATCH')
        if r.get('season') != '2026' or r.get('game_type') != 'REG' or (game and r.get('week') != str(int(game['game_id'].split('_')[1]))):
            reasons.append('WRONG_SEASON_WEEK_OR_TYPE')
        ids = identities.get((team,r.get('pfr_player_id')),set())
        if len(ids) != 1:
            reasons.append('UNRESOLVED_STABLE_IDENTITY')
        if not reasons:
            identity_counts[r['game_id'],team,next(iter(ids))] += 1
        count = r.get('defense_snaps','')
        if not re.fullmatch(r'\d+', str(count)):
            reasons.append('INVALID_DEFENSIVE_SNAP_COUNT')
        if reasons:
            excluded.append(dict(source_row=number, source=r, exclusions=reasons))
        else:
            target[r['game_id'],team,next(iter(ids))].append((int(count), number, r['pfr_player_id']))
    rows = []
    for game in snapshot['games']:
        lock = prior._utc(game['lock_at'])
        prior._require(lock == prior._utc(game['kickoff'])-timedelta(minutes=60), 'Incorrect T-60 boundary')
        common = []
        if max(prior._utc(snapshot['generated_at']),prior._utc(snapshot['completed_at'])) >= lock:
            common.append('LATE_PREGAME_CAPTURE')
        if any(prior._utc(ref[field]) >= lock for ref in snapshot['sources'] for field in ('captured_at','published_at') if ref.get(field)):
            common.append('LATE_FEATURE_SOURCE')
        final = final_by_id.get(game['game_id'])
        if final is None:
            common.append('NO_VERIFIED_FINAL')
        elif (final.get('season') != 2026 or final.get('game_type') != 'REG' or final.get('week') != int(game['game_id'].split('_')[1]) or final.get('kickoff') != game['kickoff']
              or final.get('home_team') != game['home'] or final.get('away_team') != game['away']):
            common.append('FINAL_EVENT_MISMATCH')
        elif clock <= prior._utc(final['finalized_at']):
            common.append('TARGET_BEFORE_FINAL_OBSERVATION')
        for team in snapshot['teams']:
            if team['team'] not in (game['home'],game['away']):
                continue
            for p in team['unavailable_players']:
                reasons = list(common)
                if not team.get('depth_snapshot_at'):
                    reasons.append('UNKNOWN_DEPTH_CLOCK')
                elif prior._utc(team['depth_snapshot_at']) >= lock:
                    reasons.append('LATE_DEPTH_CLOCK')
                if any(prior._utc(o[f]) >= lock for o in p['observations'] for f in ('captured_at','published_at') if o.get(f)):
                    reasons.append('LATE_AVAILABILITY_SOURCE')
                matches = target.get((game['game_id'],team['team'],p['gsis_id']),[])
                if not matches:
                    reasons.append('NO_MATCHED_TARGET_ROW')
                if identity_counts[game['game_id'],team['team'],p['gsis_id']] > 1:
                    reasons.append('DUPLICATE_TARGET_IDENTITY')
                rows.append(dict(p, game_id=game['game_id'], team=team['team'], kickoff=game['kickoff'], lock_at=game['lock_at'],
                    pregame_generated_at=snapshot['generated_at'], pregame_completed_at=snapshot['completed_at'],
                    depth_snapshot_at=team.get('depth_snapshot_at'), final_observed_at=final.get('finalized_at') if final else None,
                    target_captured_at=target_captured_at, defensive_snaps=matches[0][0] if not reasons else None,
                    target_source_row=matches[0][1] if len(matches)==1 else None,
                    target_pfr_id=matches[0][2] if len(matches)==1 else None, exclusions=reasons))
    joined = sum(not r['exclusions'] for r in rows)
    eligible_final = sum(not any(x in r['exclusions'] for x in ('LATE_PREGAME_CAPTURE','LATE_FEATURE_SOURCE','NO_VERIFIED_FINAL','FINAL_EVENT_MISMATCH','UNKNOWN_DEPTH_CLOCK','LATE_DEPTH_CLOCK','LATE_AVAILABILITY_SOURCE','TARGET_BEFORE_FINAL_OBSERVATION')) for r in rows)
    return dict(status='DESCRIPTIVE LINKAGE / NOT IN MODEL' if joined else 'UNAVAILABLE / NO ADMITTED USAGE LINKS', forecast_adjustment=None,
        cohort='Preserved unavailable_players only; reserve context is not an injury diagnosis',
        cohort_rows=len(rows), eligible_final_rows=eligible_final, joined=joined, coverage=joined/len(rows) if rows else None,
        eligible_final_coverage=joined/eligible_final if eligible_final else None,
        missing_prior_history=sum(r.get('prior_role_share') is None for r in rows),
        unknown_availability=sum(r.get('availability_statuses') == ['UNKNOWN'] for r in rows),
        exclusions=dict(Counter(x for r in rows for x in r['exclusions'])),
        target_rows=len(snaps), target_games=sorted({r.get('game_id','') for r in snaps}),
        excluded_target_rows=excluded, rows=rows,
        excluded_final_games=[dict(game_id=g['game_id'],reason='NO_PRESERVED_PREGAME_GAME') for g in finals if g['game_id'] not in games])


def verified_inputs(source, root):
    manifest_raw = (PREGAME/'manifest.json').read_bytes()
    prior._require(prior._sha(manifest_raw)==PREGAME_SHA, 'Pregame manifest pin differs')
    for name, meta in json.loads(manifest_raw)['files'].items():
        prior._require(Path(name).name==name, 'Unsafe pregame member')
        raw = (PREGAME/name).read_bytes()
        prior._require(prior._sha(raw)==meta['sha256'] and len(raw)==meta['bytes'], 'Pregame bytes differ')
    snapshot = json.loads((PREGAME/'snapshot.json').read_bytes())
    roster = []
    for ref in snapshot['sources']:
        if ref.get('url') in (prior.ROSTER_URL,prior.DEPTH_URL):
            raw=prior.read_source(root,ref,snapshot['completed_at'])
            if ref['url']==prior.ROSTER_URL:
                roster=list(prior._csv(raw))
    prior._require(bool(roster), 'Missing preserved identity roster')
    receipt=json.loads((source/'receipt.json').read_bytes())
    raw=(source/'response.bin').read_bytes()
    prior._require(receipt['url']==URL and receipt['sha256']==prior._sha(raw) and receipt['bytes']==len(raw), 'Target source bytes or URL differ')
    prior._require(prior._utc(receipt['started_at'])<=prior._utc(receipt['captured_at'])<=datetime.now(timezone.utc), 'Invalid target capture clock')
    snaps=[]
    if receipt['http_status']==200:
        reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        prior._require({'game_id','season','week','game_type','team','opponent','pfr_player_id','defense_snaps'} <= set(reader.fieldnames or []), 'Target CSV schema differs')
        snaps=list(reader)
    return snapshot,roster,snaps,receipt


def run(source, output, root=ROOT/'docs/evidence/season-2026'):
    source, output, root = Path(source),Path(output),Path(root)
    prior._require(not output.exists() and output.resolve().parent==HERE, 'Use a new exclusive output directory inside this research folder')
    snapshot,roster,snaps,receipt=verified_inputs(source,root)
    pointer=(root/'current.json').read_bytes()
    state=load_current(root)
    report=link(snapshot,roster,snaps,state['results'],receipt['captured_at'])
    report.update(source_receipt=receipt,season_checked_at=state['checked_at'],historical_admission='BLOCKED FOR FITTING',
        target_publication_clock=receipt.get('published_at'), pregame_manifest_sha256=PREGAME_SHA,
        leakage_verdict='REVIEW REQUIRED / no predictive admission',
        limitations=['No model fitting or numerical injury adjustment.', 'Saved unavailable cohort excludes other defenders.',
                    'Missing snap rows are unknown, not zero.', 'Target publication clock is unknown; capture clock is preserved.'])
    prior._require((root/'current.json').read_bytes()==pointer,'Season pointer changed during audit')
    artifacts={'admission.json':prior._json(report),'season-pointer.json':pointer,
        'run-receipt.json':prior._json(dict(completed_at=datetime.now(timezone.utc).isoformat(),source_state_unchanged=True,
            source_receipt_sha256=prior._sha((source/'receipt.json').read_bytes()),code_sha256=prior._sha(Path(__file__).read_bytes()),
            charter_sha256=prior._sha((HERE/'charter.md').read_bytes()),test_sha256=prior._sha((ROOT/'tests/test_pgo_injury_usage.py').read_bytes())))}
    output.mkdir()
    for name,raw in artifacts.items(): (output/name).write_bytes(raw)
    (output/'manifest.json').write_bytes(prior._json(dict(files={n:dict(sha256=prior._sha(r),bytes=len(r)) for n,r in artifacts.items()})))
    return {k:v for k,v in report.items() if k not in ('rows','excluded_target_rows','source_receipt')}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=HERE/'source01')
    parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(run(**vars(parser.parse_args())),indent=2))
