import copy
import csv
import gzip
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

from pgo_season import canonical, sha, utc
from pgo_sources import CURRENT_TEAMS
from research.pgo_replacement_depth_20260910 import capture as source

NOW = '2026-09-10T20:00:00+00:00'
GAME = dict(game_id='2026_01_SF_LA', season=2026, week=1, game_type='REG', home='LAR', away='SF',
            kickoff='2026-09-11T00:35:00+00:00', lock_at='2026-09-10T23:35:00+00:00')


def fixture_rows():
    roster = [dict(gsis_id=f'00-{i:07d}', full_name=f'Player {team}', first_name='Player', last_name=team,
                   team=team, position='WR', status='ACT', season='2026', week='1', game_type='REG', pfr_id=f'Test{i:04d}')
              for i, team in enumerate(sorted(CURRENT_TEAMS), 1)]
    depth = [dict(gsis_id=r['gsis_id'], player_name=r['full_name'], team=r['team'], pos_grp='3WR 1TE',
                  pos_abb='WR', pos_rank='1', pos_slot='1', dt=NOW) for r in roster]
    return roster, depth


def sources(root, roster, depth, captured=NOW):
    refs = []
    for url, rows in ((source.ROSTER_URL, roster), (source.DEPTH_URL, depth)):
        stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
        raw = gzip.compress(stream.getvalue().encode(), mtime=0)
        relative = f'source-archive/{sha(raw)}.csv.gz'
        path = root/relative; path.parent.mkdir(exist_ok=True); path.write_bytes(raw)
        refs.append(dict(url=url, path=relative, sha256=sha(raw), bytes=len(raw), captured_at=captured))
    return refs


def archive(root, state, durable):
    relative = 'runs-v2/'+utc(state['checked_at']).strftime('%Y%m%dT%H%M%S%fZ')
    path = root/relative; path.mkdir(parents=True)
    raw = canonical(state); (path/'state.json').write_bytes(raw)
    manifest = canonical(dict(created_at=durable, files={'state.json': dict(sha256=sha(raw), bytes=len(raw))}))
    (path/'manifest.json').write_bytes(manifest)
    pointer = dict(path=relative, manifest_sha256=sha(manifest))
    (root/'current.json').write_bytes(canonical(pointer))
    return pointer


class OffensiveInventoryTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('pgo_offensive_inventory'), 'Offensive inventory API is missing')
        import pgo_offensive_inventory
        return pgo_offensive_inventory

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.roster, self.depth = fixture_rows()

    def state(self, checked=NOW):
        return dict(schema_version=1, season=2026, checked_at=checked,
                    source_captures=sources(self.root, self.roster, self.depth), weeks=[dict(games=[GAME])],
                    replacement_depth={'frozen': 'defender evidence'}, results=[])

    def test_capture_all_teams_scope_and_replay_without_mutation(self):
        api = self.api()
        for i, (position, status) in enumerate([('RB','RES'), ('FB','DEV'), ('TE','EXE'), ('OL','INA'), ('QB','ACT'), ('LS','ACT')], 100):
            self.roster.append(dict(self.roster[0], gsis_id=f'00-{i:07d}', full_name=f'Other {i}', position=position, status=status, pfr_id=f'Other{i}'))
        state = self.state(); before = copy.deepcopy(state)
        result = api.capture(state, self.root, NOW)
        self.assertEqual(result['status'], 'DESCRIPTIVE / NOT IN MODEL'); self.assertEqual(len(result['teams']), 32)
        players = [p for t in result['teams'] for p in t['players']]
        self.assertEqual(len(players), 36); self.assertFalse(any(p['confirmed_unavailable'] for p in players))
        self.assertTrue(all('prior_role_share' not in p for p in players))
        self.assertEqual(state, before)
        state['offensive_inventory'] = result
        pointer = archive(self.root, state, '2026-09-10T20:00:01+00:00')
        loaded, roster = api.load_inventory(self.root, pointer)
        self.assertEqual(loaded['teams'], result['teams']); self.assertEqual(roster, self.roster)
        self.assertEqual(loaded['completed_at'], '2026-09-10T20:00:01+00:00')

    def test_source_missing_stale_tampered_or_incomplete_blocks(self):
        api = self.api(); state = self.state()
        self.assertEqual(api.capture({}, self.root, NOW)['status'], 'BLOCKED')
        self.assertEqual(api.capture(state, self.root, '2026-09-11T20:00:01Z')['status'], 'BLOCKED')
        path = self.root/state['source_captures'][0]['path']; path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(ValueError): api.capture(state, self.root, NOW)
        self.roster.pop(); state = self.state()
        with self.assertRaises(ValueError): api.capture(state, self.root, NOW)

    def test_duplicate_identity_move_and_depth_mismatch_stay_unknown(self):
        api = self.api(); self.roster.append(dict(self.roster[0], team=self.roster[1]['team']))
        with self.assertRaises(ValueError): api.capture(self.state(), self.root, NOW)
        self.roster.pop(); self.depth[0]['player_name'] = 'Wrong Person'
        self.depth[1]['gsis_id'] = self.roster[0]['gsis_id']
        result = api.capture(self.state(), self.root, NOW)
        self.assertEqual(result['teams'][0]['players'][0]['depth_status'], 'NAME_MISMATCH')
        self.assertEqual(result['teams'][1]['players'][0]['depth_rows'], [])
        self.assertTrue(result['teams'][1]['unresolved_depth'])

    def test_conflicting_rank_for_same_provider_slot_is_rejected(self):
        api = self.api()
        self.depth.append(dict(self.depth[0], pos_rank='2'))
        with self.assertRaisesRegex(ValueError, 'Duplicate offensive depth'):
            api.capture(self.state(), self.root, NOW)
        self.depth[-1]['pos_slot'] = '2'
        result = api.capture(self.state(), self.root, NOW)
        self.assertEqual(len(result['teams'][0]['players'][0]['depth_rows']), 2)

    def test_exact_t60_does_not_capture_and_late_durable_cannot_replay_as_early(self):
        api = self.api(); state = self.state(GAME['lock_at'])
        self.assertEqual(api.capture(state, self.root, GAME['lock_at'])['games'], [])
        state = self.state(); state['offensive_inventory'] = api.capture(state, self.root, NOW)
        pointer = archive(self.root, state, GAME['lock_at'])
        result, _ = api.load_inventory(self.root, pointer)
        self.assertEqual(result['completed_at'], GAME['lock_at'])

    def test_current_official_observation_only_confirms_matching_offensive_identity(self):
        api = self.api(); row = self.roster[0]
        observation = dict(gsis_id=row['gsis_id'], name=row['full_name'], position='WR', status='OUT',
                           identity_status='RESOLVED', captured_at=NOW, published_at=None)
        context = {row['team']: dict(checked_at=NOW, report_status='VERIFIED_REPORT', observations=[observation])}
        result = api.build_teams(self.roster, self.depth, context, NOW, NOW)
        self.assertTrue(result[0]['players'][0]['confirmed_unavailable'])
        observation['name'] = 'Someone Else'
        result = api.build_teams(self.roster, self.depth, context, NOW, NOW)
        self.assertFalse(result[0]['players'][0]['confirmed_unavailable'])
        self.assertEqual(result[0]['unresolved_official_names'], ['Someone Else'])
        observation['name'] = row['full_name']
        later = '2026-09-11T20:00:01Z'
        result = api.build_teams(self.roster, self.depth, context, later, NOW)
        self.assertEqual(result[0]['availability_status'], 'STALE')
        self.assertEqual(result[0]['players'][0]['availability_statuses'], ['UNKNOWN'])
        self.assertEqual(result[0]['players'][0]['depth_status'], 'STALE')

    def test_bounded_real_archive_replay_is_read_only_and_not_historical_admission(self):
        api = self.api()
        from pgo_season_rollover import load_archive
        root = Path(__file__).resolve().parents[1]/'docs/evidence/season-2026'
        pointer = dict(path='runs-v2/20260912T185509498844Z',
                       manifest_sha256='f66d1efbf9310239b1c6c0ea1c25b89562ce6611292c706c3014a02679a454f1')
        state, _ = load_archive(root, pointer); before = canonical(state)
        result = api.capture(state, root, state['checked_at'])
        self.assertEqual(result['status'], 'DESCRIPTIVE / NOT IN MODEL')
        self.assertEqual(len(result['teams']), 32); self.assertEqual(len(result['games']), 14)
        self.assertEqual(sum(len(team['players']) for team in result['teams']), 1108)
        self.assertEqual(sum(len(team['unresolved_roster']) for team in result['teams']), 1)
        self.assertTrue(any(ref.get('kind') == 'verified_official_availability' for ref in result['sources']))
        self.assertTrue(any(player['observations'] for team in result['teams'] for player in team['players']))
        self.assertEqual(canonical(state), before)
        with self.assertRaises(ValueError): api.load_inventory(root, pointer)


if __name__ == '__main__':
    unittest.main()
