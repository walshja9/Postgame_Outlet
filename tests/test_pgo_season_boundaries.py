"""Regression checks at grading, quarterback-revision and immutable-clock boundaries."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pgo_season as api


class SeasonBoundaryTests(unittest.TestCase):
    def game(self, key='2026_01_NE_SEA', home='SEA', away='NE', kickoff='2026-09-13T17:00:00Z', points=5):
        return dict(game_id=key, season=2026, week=1, game_type='REG', home=home, away=away,
                    kickoff=kickoff, location='Home', home_rest=7, away_rest=7,
                    margin=3., total=45., home_points=24., away_points=21., pick=home,
                    issued_at='2026-09-09T18:00:00Z', inputs_as_of='2026-09-09T17:00:00Z',
                    source_edition='original-edition', lock_at=(api.utc(kickoff)-api.timedelta(minutes=60)).isoformat(),
                    blocked_reason=None, confidence=dict(points=points, win_probability=.6,
                        expected_points=points*.6, probabilities={'home':.6,'away':.396,'tie':.004}, earned_points=None),
                    expected_qbs={home:home+' old',away:away+' old'},
                    explanation=dict(neutral_margin=.5,home_adjustment=2.5,rest_adjustment=0.),
                    availability=dict(checked_at='2026-09-09T17:00:00Z',summary='Earlier report',blocked_reason=None))

    def state(self, games):
        teams=sorted({t for g in games for t in (g['home'],g['away'])})
        return dict(schema_version=1,season=2026,current_week=1,status='READY',
                    checked_at='2026-09-13T15:00:00Z',results=[],sources=[],archives=[],schedule=copy.deepcopy(games),
                    rankings=dict(completed_week=0,edition='original-edition',
                                  teams=[dict(team=t,rank=i+1,rating=0.,qb_gsis_id=t+'-old')for i,t in enumerate(teams)]),
                    weeks=[dict(week=1,source_edition='original-edition',generated_at='2026-09-09T18:00:00Z',
                                inputs_as_of='2026-09-09T17:00:00Z',games=copy.deepcopy(games))],
                    calibration={'slope':.15,'tie_probability':.004})

    def result(self, game):
        return dict(game_id=game['game_id'],season=2026,week=game['week'],game_type='REG',
                    home_team=game['home'],away_team=game['away'],kickoff=game['kickoff'],
                    home_score=24,away_score=21,actual_margin=3.,
                    finalized_at=(api.utc(game['kickoff'])+api.timedelta(hours=4)).isoformat())

    def test_bootstrap_stamps_each_games_own_edition_and_input_clock(self):
        source=Path(api.ROOT)/'docs/evidence/forecast-lab-2026/september-09-postseason/snapshot.json'
        snapshot=json.loads(source.read_bytes())
        pool=json.loads((Path(api.ROOT)/'docs/evidence/confidence-pool-2026/week1-full/picks.json').read_bytes())
        with patch.object(api,'initial_snapshot',return_value=snapshot), patch('pgo_confidence_full_slate.load_verified',return_value=pool):
            state=api.bootstrap()
        for game in state['weeks'][0]['games']:
            self.assertEqual(game['source_edition'],snapshot['edition'])
            self.assertEqual(game['inputs_as_of'],snapshot['inputs_as_of'])

    def test_changed_qb_reprices_pending_game_but_preserves_points_and_other_qb_block(self):
        first=self.game();second=self.game('2026_01_BAL_BUF','BUF','BAL',points=8)
        second.update(blocked_reason='Expected quarterback unavailable',blocked_by_availability=True,pick=None,
                      withheld_confidence=second['confidence'],confidence=None)
        state=self.state([first,second]);selected={t:dict(gsis_id=t+'-old',full_name=t+' old')for t in ('NE','SEA','BAL','BUF')}
        selected['SEA']=dict(gsis_id='SEA-new',full_name='SEA new')
        revised=[]
        for old in (first,second):
            g=self.game(old['game_id'],old['home'],old['away'],points=1)
            g.update(margin=7.,total=45.,home_points=26.,away_points=19.,issued_at='2026-09-13T15:00:00Z',
                     inputs_as_of='2026-09-13T15:00:00Z',source_edition='new-edition')
            g['confidence'].update(win_probability=.7,expected_points=.7)
            revised.append(g)
        rankings=copy.deepcopy(state['rankings']);rankings.update(edition='new-edition')
        for t in rankings['teams']:t['qb_gsis_id']=selected[t['team']]['gsis_id']
        revision=dict(week=1,source_edition='new-edition',generated_at='2026-09-13T15:00:00Z',
                      inputs_as_of='2026-09-13T15:00:00Z',games=revised)
        observations={'games':{g['game_id']:dict(checked_at='2026-09-13T15:00:00Z',summary='Unknown report',blocked_reason=None)for g in (first,second)}}
        with tempfile.TemporaryDirectory() as temporary, patch.object(api,'now',return_value='2026-09-13T15:00:00Z'), \
             patch.object(api,'fetch_source',return_value=(b'',{})), patch.object(api,'csv_rows',return_value=[]), \
             patch.object(api,'select_roster',return_value=selected), \
             patch('pgo_season_availability.capture_availability',return_value=observations), \
             patch.object(api,'build_next',return_value=(rankings,revision,[])):
            api.refresh_availability(state,Path(temporary))
        changed,unchanged=state['weeks'][0]['games']
        self.assertEqual(changed['margin'],7.)
        self.assertEqual(changed['confidence']['points'],5)
        self.assertAlmostEqual(changed['confidence']['expected_points'],3.5)
        self.assertEqual(unchanged['blocked_reason'],second['blocked_reason'])
        self.assertIsNone(unchanged['confidence'])
        self.assertEqual(unchanged['withheld_confidence']['points'],8)

    def test_crossing_cutoff_restores_entire_prior_prediction_before_final_grading(self):
        game=self.game();game['source_details']={'capture':'old'};state=self.state([game]);clock=['2026-09-13T15:59:50Z']
        def slow_update(changed,root):
            g=changed['weeks'][0]['games'][0]
            g.update(margin=-9.,home_points=18.,away_points=27.,source_edition='new-edition',
                     inputs_as_of=clock[0],expected_qbs={'SEA':'New QB'},new_source_extra='must not survive',
                     explanation={'neutral_margin':-11.5,'home_adjustment':2.5,'rest_adjustment':0.},
                     source_details={'capture':'new'})
            clock[0]='2026-09-13T16:00:01Z'
            return []
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);api.save_state(state,root)
            with patch.object(api,'now',side_effect=lambda:clock[0]), \
                 patch.object(api,'fetch_inputs',return_value=([game],[],[],{})), \
                 patch.object(api,'refresh_availability',side_effect=slow_update), \
                 patch.object(api,'legacy_models',return_value=[]):
                updated=api.refresh(root)
        restored=updated['weeks'][0]['games'][0]
        for key,value in game.items():self.assertEqual(restored[key],value,key)
        self.assertNotIn('new_source_extra',restored)
        self.assertEqual(restored['forecast_status'],'LOCKED')

    def test_starter_evidence_alone_cannot_change_at_durable_lock(self):
        state=self.state([self.game()])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with patch.object(api,'now',return_value='2026-09-13T15:59:00Z'):
                api.save_state(state,root)
            pointer=(root/'current.json').read_bytes()
            state['checked_at']='2026-09-13T16:00:00Z'
            state['weeks'][0]['games'][0]['starter_announcements']=[{'new':'evidence'}]
            with patch.object(api,'now',return_value=state['checked_at']), self.assertRaisesRegex(ValueError,'durable-write lock'):
                api.save_state(state,root)
            self.assertEqual((root/'current.json').read_bytes(),pointer)

    def test_week_rollover_requires_complete_finals_and_retains_grades_when_stats_missing(self):
        first=self.game(kickoff='2026-09-09T20:00:00Z');second=self.game('2026_01_BAL_BUF','BUF','BAL',points=8)
        future=self.game('2026_02_NE_SEA',kickoff='2026-09-20T17:00:00Z');future['week']=2
        original=self.state([first,second]);schedule=[first,second,future]
        new_rankings=dict(completed_week=1,edition='week-two',teams=original['rankings']['teams'])
        next_week=dict(week=2,source_edition='week-two',generated_at='2026-09-14T12:00:00Z',inputs_as_of='2026-09-14T12:00:00Z',games=[future])
        for case in ('incomplete','missing_stats','complete'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);api.save_state(original,root)
                results=[self.result(first)] if case=='incomplete' else [self.result(first),self.result(second)]
                with patch.object(api,'now',return_value='2026-09-14T12:00:00Z'), \
                     patch.object(api,'fetch_inputs',return_value=(schedule,results,[],{})), \
                     patch.object(api,'refresh_availability',return_value=[]),patch.object(api,'legacy_models',return_value=[]), \
                     patch.object(api,'refresh_replacement_sources'), \
                     patch.object(api,'build_next',return_value=(new_rankings,next_week,[]),
                                  side_effect=ValueError('Completed game is missing production') if case=='missing_stats' else None)as build:
                    updated=api.refresh(root)
                self.assertEqual(updated['weeks'][0]['games'][0]['grade'],'W')
                self.assertEqual(updated['weeks'][0]['games'][0]['margin'],first['margin'])
                if case=='complete':
                    build.assert_called_once();self.assertEqual(updated['current_week'],2)
                    self.assertEqual(len(updated['weeks']),2);self.assertEqual(updated['rankings']['completed_week'],1)
                else:
                    self.assertEqual(updated['current_week'],1);self.assertEqual(updated['rankings']['completed_week'],0)
                    if case=='incomplete':build.assert_not_called()
                    else:self.assertEqual(updated['status'],'BLOCKED');self.assertEqual(updated['model_records'][0]['wins'],2)

    def test_malformed_scoreboard_saves_blocked_state_without_changing_prior_forecasts(self):
        game=self.game();state=self.state([game])
        with tempfile.TemporaryDirectory() as temporary,patch.object(api,'now',return_value=state['checked_at']), \
             patch.object(api,'legacy_models',return_value=[]):
            root=Path(temporary);api.decorate(state,[])
            prior=api.save_state(state,root);prior_bytes=(prior/'state.json.gz').read_bytes()
            malformed=json.dumps({'season':None,'week':{'number':1},'events':[]}).encode()
            with patch.object(api,'now',return_value='2026-09-13T15:01:00Z'), \
                 patch.object(api,'parse_schedule',return_value=[game]), \
                 patch.object(api,'fetch_source',side_effect=[(b'schedule',{}),(malformed,{'captured_at':'2026-09-13T15:01:00Z'})]), \
                 patch.object(api,'refresh_experiments'):
                try:
                    updated=api.refresh(root)
                except Exception as error:
                    self.fail(f'Malformed provider response escaped refresh: {type(error).__name__}')
            self.assertEqual(updated['status'],'BLOCKED')
            self.assertIn('Automatic update needs review: Scoreboard',updated['blocked_reason'])
            self.assertEqual(updated['weeks'],state['weeks'])
            self.assertEqual(updated['results'],state['results'])
            self.assertEqual((prior/'state.json.gz').read_bytes(),prior_bytes)
            self.assertEqual(api.load_current(root),updated)


if __name__=='__main__':unittest.main()
