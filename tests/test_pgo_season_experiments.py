import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pgo_season as season


class SeasonExperimentIntegrationTests(unittest.TestCase):
    def fixture(self):
        game=dict(game_id='2026_01_NE_SEA',season=2026,week=1,game_type='REG',home='SEA',away='NE',
                  kickoff='2026-09-11T00:20:00Z',lock_at='2026-09-10T23:20:00Z',issued_at='2026-09-10T19:00:00Z',
                  inputs_as_of='2026-09-10T18:00:00Z',source_edition='test-edition',margin=4.,total=45.,
                  home_points=24.5,away_points=20.5,blocked_reason=None)
        state=dict(schema_version=1,season=2026,checked_at='2026-09-10T20:00:00Z',status='READY',
                   weeks=[dict(week=1,games=[game])],results=[],sources=[],rankings={})
        return state

    def depth(self,state):
        game=state['weeks'][0]['games'][0]
        row={k:game[k] for k in ('game_id','home','away','kickoff','lock_at')}
        row.update(captured_at=state['checked_at'],teams_with_saved_observations=[])
        return dict(identity='test-depth',status='DESCRIPTIVE / NOT IN MODEL',generated_at=state['checked_at'],
                    source_as_of='2026-09-10T19:00:00Z',teams=[],sources=[],games=[row],forecast_adjustment=None)

    def test_each_experiment_runs_and_failures_preserve_prior_pairs_without_main_mutation(self):
        self.assertTrue(hasattr(season,'refresh_experiments'),'Season experiment integration is missing')
        import pgo_penalty_monitor,pgo_totals_monitor,pgo_weights_monitor
        from research.pgo_replacement_depth_20260910 import capture
        state=self.fixture();before=copy.deepcopy(state)
        previous=dict(state,totals_shadow={'games':[{'game_id':'original'}],'status':'READY'})
        def failed_totals(detached,*args):
            detached['weeks'][0]['games'][0]['margin']=999
            raise RuntimeError('Totals source unavailable')
        with patch.object(pgo_penalty_monitor,'refresh_shadow',return_value={'games':[],'status':'READY'}) as penalty, \
             patch.object(pgo_totals_monitor,'refresh_shadow',side_effect=failed_totals) as totals, \
             patch.object(pgo_weights_monitor,'refresh_shadow',return_value={'games':[],'status':'READY'}) as weights, \
             patch.object(capture,'capture',return_value=self.depth(state)) as replacement:
            season.refresh_experiments(state,previous,Path('fixture-root'))
        self.assertEqual(state['weeks'],before['weeks'])
        self.assertEqual(state['totals_shadow']['games'],previous['totals_shadow']['games'])
        self.assertEqual(state['totals_shadow']['status'],'BLOCKED')
        self.assertIn('Totals source',state['totals_shadow']['blocked_reason'])
        self.assertEqual(state['weights_shadow']['status'],'READY')
        self.assertEqual(state['replacement_depth']['generated_at'],before['checked_at'])
        for mocked in (penalty,totals,weights,replacement):self.assertEqual(mocked.call_count,1)
        self.assertEqual(totals.call_args.args[2],state['checked_at'])
        self.assertEqual(replacement.call_args.args[1],Path('fixture-root'))

    def test_save_invokes_both_monitor_guards_before_publishing_pointer(self):
        import pgo_totals_monitor,pgo_weights_monitor
        for module,key in ((pgo_totals_monitor,'totals_shadow'),(pgo_weights_monitor,'weights_shadow')):
            state=self.fixture();state[key]={'games':[]}
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp, \
                 patch.object(season,'now',return_value='2026-09-10T23:20:00Z'), \
                 patch.object(module,'check_durable_shadow',side_effect=ValueError('Crossed experiment cutoff')) as guard:
                with self.assertRaisesRegex(ValueError,'Crossed experiment cutoff'):season.save_state(state,Path(tmp))
                self.assertFalse((Path(tmp)/'current.json').exists())
                self.assertEqual(guard.call_args.args[2],'2026-09-10T23:20:00Z')
                self.assertIsNone(guard.call_args.args[1])

    def test_replacement_snapshot_crossing_durable_cutoff_cannot_be_published(self):
        state=self.fixture();state['replacement_depth']=self.depth(state)
        with tempfile.TemporaryDirectory() as tmp,patch.object(season,'now',return_value='2026-09-10T23:20:00Z'):
            with self.assertRaisesRegex(ValueError,'Replacement.*deadline'):season.save_state(state,Path(tmp))
            self.assertFalse((Path(tmp)/'current.json').exists())

    def test_replacement_checks_metadata_future_sources_and_completed_games(self):
        self.assertTrue(hasattr(season,'check_replacement_depth'),'Replacement durable guard is missing')
        base=self.fixture();base['replacement_depth']=self.depth(base)
        mutations=[lambda s:s['replacement_depth']['games'][0].update(home='BUF'),
                   lambda s:s['replacement_depth']['games'][0].update(lock_at='2026-09-11T00:00:00Z'),
                   lambda s:s['replacement_depth']['games'][0].update(captured_at='2026-09-10T21:00:00Z'),
                   lambda s:s['replacement_depth'].update(source_as_of='2026-09-10T21:00:00Z'),
                   lambda s:s['replacement_depth']['sources'].append({'captured_at':'2026-09-10T21:00:00Z'}),
                   lambda s:s['replacement_depth']['games'].append(copy.deepcopy(s['replacement_depth']['games'][0])),
                   lambda s:s['results'].append({'game_id':'2026_01_NE_SEA'})]
        for mutate in mutations:
            state=copy.deepcopy(base);mutate(state)
            with self.subTest(mutation=mutate),self.assertRaises(ValueError):
                season.check_replacement_depth(state,None,'2026-09-10T20:30:00Z')

    def test_old_replacement_observation_survives_failure_after_lock_but_new_one_does_not(self):
        self.assertTrue(hasattr(season,'check_replacement_depth'),'Replacement durable guard is missing')
        previous=self.fixture();previous['replacement_depth']=self.depth(previous)
        current=copy.deepcopy(previous);current['checked_at']='2026-09-11T03:00:00Z'
        current['replacement_depth'].update(status='BLOCKED',blocked_reason='Source unavailable',checked_at=current['checked_at'])
        season.check_replacement_depth(current,previous,'2026-09-11T03:00:01Z')
        current['replacement_depth']['teams']=[{'team':'SEA','new_observation':True}]
        with self.assertRaises(ValueError):season.check_replacement_depth(current,previous,'2026-09-11T03:00:01Z')

    def test_successful_save_keeps_main_and_old_archive_bytes(self):
        state=self.fixture();state['replacement_depth']=self.depth(state)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(season,'now',return_value='2026-09-10T20:00:01Z'):
                original=season.save_state(state,root)
            saved_bytes=(original/'state.json.gz').read_bytes();pointer=(root/'current.json').read_bytes()
            loaded=season.load_current(root)
            later=copy.deepcopy(loaded);later['checked_at']='2026-09-11T03:00:00Z'
            with patch.object(season,'now',return_value='2026-09-11T03:00:01Z'):
                season.save_state(later,root)
            self.assertEqual((original/'state.json.gz').read_bytes(),saved_bytes)
            self.assertNotEqual((root/'current.json').read_bytes(),pointer)
            self.assertEqual(season.load_current(root)['weeks'],state['weeks'])

    def test_omitting_an_existing_shadow_cannot_remove_issued_pairs(self):
        for key in ('totals_shadow','weights_shadow'):
            current=self.fixture();previous=copy.deepcopy(current)
            previous[key]={'games':[{'game_id':'original-issued-pair'}]}
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp, \
                 patch.object(season,'now',return_value='2026-09-10T20:00:01Z'), \
                 patch.object(season,'load_current',return_value=previous):
                root=Path(tmp);(root/'current.json').write_text('{}',encoding='utf-8')
                with self.assertRaisesRegex(ValueError,'removed'):season.save_state(current,root)
                self.assertEqual((root/'current.json').read_text(encoding='utf-8'),'{}')


if __name__=='__main__':unittest.main()
