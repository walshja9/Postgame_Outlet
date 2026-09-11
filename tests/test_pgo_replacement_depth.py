import copy
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.pgo_replacement_depth_20260910 import capture as depth


NOW = '2026-09-10T20:00:00+00:00'


def roster(pid, name, status='ACT'):
    return dict(gsis_id=pid, full_name=name, first_name=name.split()[0], last_name=name.split()[-1],
                team='NE', position='LB', status=status, season='2026', week='1')


def slot(pid, name, rank, position='LB', stamp=NOW):
    return dict(gsis_id=pid, player_name=name, team='NE', pos_grp='Base 3-4 D', pos_abb=position,
                pos_rank=str(rank), dt=stamp)


class ReplacementDepthTests(unittest.TestCase):
    def fixture(self):
        rr = [roster('00-0000001', 'Starter One'), roster('00-0000002', 'Backup Two'),
              roster('00-0000003', 'Rookie Three'), roster('00-0000004', 'Reserve Four', 'RES')]
        dd = [slot(r['gsis_id'], r['full_name'], i+1) for i,r in enumerate(rr)]
        history = {'00-0000001': dict(prior_role_share=.8, defensive_snaps=800., observed_games=16),
                   '00-0000002': dict(prior_role_share=.2, defensive_snaps=100., observed_games=8)}
        obs = {'NE': dict(report_status='VERIFIED_REPORT', final_inactives_status='UNKNOWN',
                         checked_at=NOW, observations=[dict(gsis_id='00-0000001', name='Starter One', status='OUT',
                                                           identity_status='RESOLVED', captured_at=NOW)])}
        return rr, dd, history, obs

    def test_unavailable_prior_usage_is_not_replacement_quality(self):
        args = self.fixture(); before = copy.deepcopy(args)
        team = depth.build_teams(*args, checked_at=NOW, depth_captured_at=NOW, teams={'NE'})[0]
        self.assertEqual(team['unavailable_prior_usage_subtotal'], .8)
        self.assertIsNone(team['expected_unavailable_exposure'])
        self.assertEqual(team['unavailable_unknown_prior_role'], 1)
        self.assertEqual(team['roles'][0]['remaining_experienced_backups_not_confirmed_out'], 1)
        self.assertEqual(team['roles'][0]['remaining_unknown_history_backups_not_confirmed_out'], 1)
        self.assertEqual(team['roles'][0]['position'], 'LB')
        self.assertEqual(args, before)

    def test_complete_inventory_preserves_unavailable_subset_and_existing_counts(self):
        args = self.fixture(); before = copy.deepcopy(args)
        team = depth.build_teams(*args, checked_at=NOW, depth_captured_at=NOW, teams={'NE'})[0]
        self.assertEqual(team.get('inventory_version'), 1)
        self.assertEqual(len(team['defenders']), 4)
        self.assertEqual(team['unavailable_players'], [p for p in team['defenders'] if p['confirmed_unavailable']])
        self.assertEqual([p['gsis_id'] for p in team['defenders']], [r['gsis_id'] for r in args[0]])
        self.assertEqual(team['active_defenders'], 3)
        self.assertEqual(team['reserve_defenders'], 1)
        self.assertEqual(team['unavailable_prior_usage_subtotal'], .8)
        self.assertIsNone(team['defenders'][2]['prior_role_share'])
        self.assertEqual(team['roles'][0]['remaining_experienced_backups_not_confirmed_out'], 1)
        self.assertEqual(args, before)

    def test_dnp_uncertain_missing_and_name_conflict_remain_distinct(self):
        rr, dd, hh, obs = self.fixture()
        obs['NE']['observations'][0].update(status='NO_GAME_DESIGNATION', practice_status='Did Not Participate')
        obs['NE']['observations'].append(dict(gsis_id='00-0000002', name='Backup Two', status='QUESTIONABLE',
                                             identity_status='RESOLVED', captured_at=NOW))
        dd[2]['player_name'] = 'Wrong Person'
        team = depth.build_teams(rr, dd, hh, obs, checked_at=NOW, depth_captured_at=NOW, teams={'NE'})[0]
        self.assertEqual(team['unavailable_prior_usage_subtotal'], 0.)
        self.assertEqual(team['roles'][0]['uncertain_backups'], 1)
        self.assertEqual(team['depth_identity_conflicts'], 1)
        self.assertEqual(team['unavailable_unknown_prior_role'], 1)

    def test_future_depth_is_ignored_old_depth_unknown_and_duplicate_rejected(self):
        rr, dd, hh, obs = self.fixture()
        dd += [slot('00-0000002', 'Backup Two', 1, stamp='2026-09-11T00:00:00+00:00')]
        team = depth.build_teams(rr, dd, hh, obs, checked_at=NOW, depth_captured_at=NOW, teams={'NE'})[0]
        self.assertEqual(team['listed_first'], 1)
        for row in dd: row['dt'] = '2026-09-01T00:00:00+00:00'
        team = depth.build_teams(rr, dd, hh, obs, checked_at=NOW, depth_captured_at=NOW, teams={'NE'})[0]
        self.assertEqual(team['depth_status'], 'STALE')
        self.assertEqual(team['roles'], [])
        with self.assertRaises(ValueError):
            depth.build_teams(rr+[rr[0]], dd, hh, obs, checked_at=NOW, depth_captured_at=NOW, teams={'NE'})

    def test_relative_source_hash_and_time_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); raw=gzip.compress(b'team,position\nNE,LB\n', mtime=0)
            digest=hashlib.sha256(raw).hexdigest(); rel='source-archive/'+digest+'.csv.gz'
            (root/'source-archive').mkdir(); (root/rel).write_bytes(raw)
            ref=dict(path=rel, sha256=digest, bytes=len(raw), captured_at=NOW, url=depth.ROSTER_URL)
            self.assertEqual(depth.read_source(root, ref, NOW), raw)
            for change in ({'path':'../bad.csv.gz'}, {'sha256':'0'*64}, {'captured_at':'2026-09-11T00:00:00+00:00'}):
                with self.assertRaises(ValueError): depth.read_source(root, dict(ref, **change), NOW)

    def test_saved_unknown_report_is_not_claimed_verified(self):
        game=dict(game_id='future',season=2026,week=1,home='NE',away='SEA',
                  kickoff='2026-09-11T00:00:00+00:00',lock_at='2026-09-10T23:00:00+00:00')
        saved=dict(game,checked_at=NOW,teams={'NE':dict(report_status='UNKNOWN',observations=[])})
        archive='availability-v2/20260910T195000000000Z'
        game['availability']=dict(saved,source_archive=archive)
        refs=[dict(url=url,path='source-archive/'+'a'*64+'.csv.gz',captured_at=NOW)
              for url in (depth.ROSTER_URL,depth.DEPTH_URL)]
        state=dict(source_captures=refs,weeks=[dict(games=[game])])
        before=copy.deepcopy(state)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/archive).mkdir(parents=True)
            (root/archive/'manifest.json').write_bytes(b'{}')
            with patch.object(depth,'read_source',return_value=b''), patch.object(depth,'_csv',return_value=[]), \
                 patch.object(depth,'_history',return_value=({},None)), patch.object(depth,'build_teams',return_value=[]), \
                 patch('pgo_season_availability.load_availability',return_value=dict(checked_at=NOW,games={'future':saved})):
                result=depth.capture(state,root,NOW)
        self.assertEqual(result['games'][0]['teams_with_saved_observations'],['NE'])
        self.assertNotIn('teams_with_verified_observations',result['games'][0])
        self.assertEqual(state,before)

    def test_missing_capture_is_separate_blocked_and_input_unchanged(self):
        state=dict(season=2026, current_week=1, weeks=[], source_captures=[])
        before=copy.deepcopy(state)
        with tempfile.TemporaryDirectory() as temp:
            result=depth.capture(state, Path(temp), NOW)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIsNone(result['forecast_adjustment'])
        self.assertEqual(state,before)

    def test_results_only_refresh_reuses_valid_prior_sources_until_expiry(self):
        rr, dd, history, _ = self.fixture()
        game=dict(game_id='future',home='NE',away='SEA',kickoff='2026-09-12T00:00:00+00:00',
                  lock_at='2026-09-11T23:00:00+00:00')
        with tempfile.TemporaryDirectory() as temp, patch.object(depth,'_history',return_value=(history,None)):
            root=Path(temp); (root/'source-archive').mkdir(); refs=[]
            for url, rows in ((depth.ROSTER_URL,rr),(depth.DEPTH_URL,dd)):
                text=io.StringIO(); writer=csv.DictWriter(text,fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows)
                raw=gzip.compress(text.getvalue().encode(),mtime=0); digest=hashlib.sha256(raw).hexdigest()
                relative='source-archive/'+digest+'.csv.gz'; (root/relative).write_bytes(raw)
                refs.append(dict(url=url,path=relative,sha256=digest,bytes=len(raw),captured_at=NOW))
            state=dict(source_captures=refs,weeks=[dict(games=[game])])
            previous=depth.capture(state,root,NOW)
            self.assertEqual(previous['status'],'DESCRIPTIVE / NOT IN MODEL')
            # A results-only refresh replaces the current references, retaining the last description.
            state=dict(source_captures=[],sources=[],weeks=state['weeks'],replacement_depth=previous)
            before=copy.deepcopy(state); checked='2026-09-10T21:00:00+00:00'
            result=depth.capture(state,root,checked)
            self.assertEqual(result['status'],'DESCRIPTIVE / NOT IN MODEL')
            self.assertEqual(result['teams'],previous['teams'])
            self.assertEqual(result['source_as_of'],NOW)
            self.assertEqual(result['games'][0]['captured_at'],checked)
            self.assertIsNone(result['forecast_adjustment'])
            self.assertEqual(state,before)
            expired=depth.capture(state,root,'2026-09-11T20:00:01+00:00')
            self.assertEqual(expired['status'],'BLOCKED')
            self.assertIn('older than 24 hours',expired['blocked_reason'])
            for change in ({'path':'../bad.csv.gz'},{'sha256':'0'*64},{'bytes':0},
                           {'captured_at':'2026-09-11T00:00:00+00:00'}):
                invalid=copy.deepcopy(state); invalid['replacement_depth']['sources'][0].update(change)
                with self.subTest(change=change), self.assertRaises(ValueError):
                    depth.capture(invalid,root,checked)

    def test_only_future_unlocked_games_are_eligible(self):
        games=[dict(game_id='old',kickoff='2026-09-09T23:00:00+00:00',lock_at='2026-09-09T22:00:00+00:00'),
               dict(game_id='boundary',kickoff='2026-09-10T21:00:00+00:00',lock_at=NOW),
               dict(game_id='future',kickoff='2026-09-11T00:00:00+00:00',lock_at='2026-09-10T23:00:00+00:00')]
        self.assertEqual([g['game_id'] for g in depth.eligible_games({'weeks':[{'games':games}]}, NOW)], ['future'])

    def test_actual_historical_admission_stops_fitting(self):
        result=depth.admission()
        self.assertEqual(result['status'], 'BLOCKED FOR FITTING')
        self.assertEqual(result['historical_depth_sources'], [])
        self.assertEqual(result['sources_with_publication_or_capture_clock'], 0)
        self.assertGreater(result['stable_2025_player_histories'], 1000)
        self.assertIsNone(result['forecast_adjustment'])

    def test_missing_roster_identity_stays_visible_unknown(self):
        rr, dd, hh, obs = self.fixture(); rr[2]['gsis_id']=''
        team=depth.build_teams(rr, dd, hh, obs, checked_at=NOW, depth_captured_at=NOW, teams={'NE'})[0]
        self.assertEqual(team['unresolved_roster'][0]['name'],'Rookie Three')
        self.assertEqual(team['unresolved_roster'][0]['reason'],'Missing stable GSIS identity')

    def test_official_identity_absent_from_current_roster_stays_visible(self):
        rr, dd, hh, obs = self.fixture()
        obs['NE']['observations'].append(dict(gsis_id='00-9999999',name='Departed Defender',position='LB',
                                             status='OUT',identity_status='RESOLVED',captured_at=NOW))
        team=depth.build_teams(rr, dd, hh, obs, checked_at=NOW, depth_captured_at=NOW, teams={'NE'})[0]
        self.assertIn('Departed Defender',team['unresolved_official_names'])


if __name__ == '__main__':
    unittest.main()
