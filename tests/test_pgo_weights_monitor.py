import copy
import importlib.util
import unittest
from unittest.mock import patch


class WeightsMonitorTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('pgo_weights_monitor'), 'Fixed weights monitor is missing')
        import pgo_weights_monitor
        return pgo_weights_monitor

    def fixture(self, api):
        from research.pgo_weights_candidate_20260910.candidate import ARMS, CURVES, DROPS
        import pgo_sources
        names = sorted(set().union(*DROPS.values()) | {'pgo_v0','home_field','rest_difference'})
        def fit(drop=()):
            features = [n for n in names if n not in drop]
            return dict(preprocessor=dict(feature_names=features,medians=[0.]*len(features),
                scales=[1.]*len(features),missing_features=[]),
                coefficients=[0.]+[1. if n in ('pgo_v0','home_field') else 0. for n in features])
        fits = {arm:fit(DROPS.get(arm,())) for arm in ARMS}
        curves = {f'{arm}_{curve}':dict(slope=.1,intercept=-1. if curve=='intercept' else 0.,tie_probability=.02)
                  for arm in ARMS for curve in CURVES}
        teams = [dict(team=team,qb_name='QB '+team,qb_gsis_id='ID-'+team,
                      features={n:5. if n=='pgo_v0' and team=='SEA' else 2. if n=='pgo_v0' else 0.
                                for n in names if n not in ('home_field','rest_difference')})
                 for team in sorted(pgo_sources.CURRENT_TEAMS)]
        game = dict(game_id='2026_01_NE_SEA',season=2026,week=1,game_type='REG',home='SEA',away='NE',
                    kickoff='2026-09-11T00:20:00Z',lock_at='2026-09-10T23:20:00Z',issued_at='2026-09-10T19:00:00Z',
                    inputs_as_of='2026-09-10T18:00:00Z',source_edition='test-edition',margin=4.,total=45,
                    expected_qbs={'NE':'QB NE','SEA':'QB SEA'},home_rest=7,away_rest=7,location='Home',blocked_reason=None)
        rank = dict(teams=teams,completed_week=0,edition='test-edition',inputs_as_of=game['inputs_as_of'],
                    generated_at=game['issued_at'],history_through='2026-02-08T23:30:00Z')
        state = dict(season=2026,status='READY',rankings=rank,weeks=[dict(week=1,games=[game])],results=[])
        package = (fits,curves,dict(status='EXPERIMENTAL / HOLD',margin_arms={},probability_curves={}))
        return state,package

    def capture(self, api, state, package, previous=None, checked='2026-09-10T20:00:00Z'):
        with patch.object(api,'_package',return_value=package),patch.object(api,'_source_proof',return_value={'kind':'fixture_verified'}):
            return api.refresh_shadow(state,previous,checked)

    def test_fixed_three_arms_six_curves_and_control_replay_preserve_main(self):
        api=self.api();state,package=self.fixture(api);before=copy.deepcopy(state)
        shadow=self.capture(api,state,package)
        self.assertEqual(shadow['status'],'READY');self.assertEqual(state,before)
        row=shadow['games'][0]
        self.assertEqual(set(row['margins']),set(package[0]))
        self.assertEqual(len(row['probabilities']),6)
        self.assertEqual(row['margins']['postseason'],state['weeks'][0]['games'][0]['margin'])
        self.assertEqual(row['probabilities']['postseason_scalar']['selected_team'],'SEA')
        self.assertEqual(row['probabilities']['postseason_intercept']['selected_team'],'NE')
        self.assertNotIn('confidence_points',row)
        api.check_durable_shadow(dict(state,weights_shadow=shadow),None,'2026-09-10T20:00:01Z')

    def test_mismatched_control_qb_or_source_edition_blocks_without_issuance(self):
        api=self.api();state,package=self.fixture(api)
        for changes in ({'margin':5.},{'source_edition':'wrong'},{'expected_qbs':{'NE':'wrong','SEA':'QB SEA'}}):
            changed=copy.deepcopy(state);changed['weeks'][0]['games'][0].update(changes)
            shadow=self.capture(api,changed,package)
            self.assertEqual(shadow['status'],'BLOCKED');self.assertEqual(shadow['games'],[])
            self.assertTrue(shadow['excluded'][0]['reason'])

    def test_late_and_withheld_rows_do_not_become_experimental_picks(self):
        api=self.api();state,package=self.fixture(api)
        shadow=self.capture(api,state,package,checked='2026-09-10T23:20:00Z')
        self.assertEqual(shadow['games'],[])
        state['weeks'][0]['games'][0]['blocked_reason']='Expected QB unavailable'
        shadow=self.capture(api,state,package)
        self.assertEqual(shadow['games'],[])

    def test_existing_pairs_are_immutable_and_durable_cutoff_is_rechecked(self):
        api=self.api();state,package=self.fixture(api);shadow=self.capture(api,state,package)
        previous=dict(state,weights_shadow=shadow)
        changed=copy.deepcopy(state);changed['weeks'][0]['games'][0]['margin']=100
        again=self.capture(api,changed,package,previous)
        self.assertEqual(again['games'],shadow['games'])
        tampered=copy.deepcopy(shadow);tampered['games'][0]['margins']['without_qb_passing']+=1
        with self.assertRaises(ValueError):api.check_durable_shadow(dict(state,weights_shadow=tampered),previous,'2026-09-10T20:00:01Z')
        with self.assertRaises(ValueError):api.check_durable_shadow(dict(state,weights_shadow=shadow),None,'2026-09-10T23:20:00Z')
        with self.assertRaises(ValueError):api.check_durable_shadow(dict(state,weights_shadow=dict(shadow,games=[])),previous,'2026-09-10T20:00:01Z')

    def test_verified_finals_grade_all_curves_and_reject_corrections(self):
        api=self.api();state,package=self.fixture(api);shadow=self.capture(api,state,package)
        game=state['weeks'][0]['games'][0]
        result=dict(game_id=game['game_id'],season=2026,week=1,game_type='REG',home_team='SEA',away_team='NE',
                    kickoff=game['kickoff'],home_score=24,away_score=21,actual_margin=3,finalized_at='2026-09-11T04:00:00Z')
        state['results']=[result]
        graded=self.capture(api,state,package,dict(weights_shadow=shadow),'2026-09-11T05:00:00Z')
        self.assertEqual(graded['metrics']['paired_games'],1)
        self.assertEqual(graded['metrics']['margin_arms']['postseason']['mae'],1.)
        self.assertEqual(graded['games'][0]['grade']['probabilities']['postseason_scalar'],'W')
        self.assertEqual(graded['games'][0]['grade']['probabilities']['postseason_intercept'],'L')
        state['results']=[dict(result,home_score=21,actual_margin=0)]
        bad=self.capture(api,state,package,dict(weights_shadow=graded),'2026-09-11T06:00:00Z')
        self.assertEqual(bad['status'],'BLOCKED');self.assertEqual(bad['games'],graded['games'])
        tied=self.capture(api,state,package,dict(weights_shadow=shadow),'2026-09-11T06:00:00Z')
        self.assertEqual(tied['games'][0]['grade']['margins']['postseason'],'T')

    def test_source_failure_retains_saved_pairs_and_exposes_blocked_state(self):
        api=self.api();state,package=self.fixture(api);shadow=self.capture(api,state,package)
        with patch.object(api,'_package',side_effect=ValueError('Pinned package differs')):
            bad=api.refresh_shadow(state,dict(weights_shadow=shadow),'2026-09-10T21:00:00Z')
        self.assertEqual(bad['status'],'BLOCKED');self.assertEqual(bad['games'],shadow['games'])
        self.assertIn('Pinned package',bad['blocked_reason'])

    def test_blocked_main_update_grades_existing_pairs_but_cannot_issue_new_ones(self):
        api=self.api();state,package=self.fixture(api);shadow=self.capture(api,state,package)
        old=state['weeks'][0]['games'][0]
        next_game=dict(old,game_id='2026_01_NYJ_BUF',home='BUF',away='NYJ',margin=1.,
                       kickoff='2026-09-13T17:00:00Z',lock_at='2026-09-13T16:00:00Z',
                       expected_qbs={'BUF':'QB BUF','NYJ':'QB NYJ'})
        state['weeks'][0]['games'].append(next_game)
        state.update(status='BLOCKED',blocked_reason='Current provider statistics unavailable')
        state['results']=[dict(game_id=old['game_id'],season=2026,week=1,game_type='REG',
            home_team=old['home'],away_team=old['away'],kickoff=old['kickoff'],
            home_score=24,away_score=21,actual_margin=3,finalized_at='2026-09-11T04:00:00Z')]
        result=self.capture(api,state,package,dict(weights_shadow=shadow),'2026-09-11T05:00:00Z')
        self.assertEqual(result['status'],'BLOCKED')
        self.assertIn('not READY',result['blocked_reason'])
        self.assertEqual([g['game_id'] for g in result['games']],[old['game_id']])
        self.assertEqual(result['games'][0]['grade']['margins']['postseason'],'W')
        self.assertEqual(result['metrics']['paired_games'],1)


if __name__=='__main__':unittest.main()
