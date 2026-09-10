import copy
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pgo_totals_monitor as monitor


def state():
    game=dict(game_id='2026_02_NE_SEA',season=2026,week=2,home='SEA',away='NE',game_type='REG',
              kickoff='2026-09-17T00:20:00Z',lock_at='2026-09-16T23:20:00Z',margin=2.,blocked_reason=None)
    result=dict(game_id='2026_01_NE_SEA',season=2026,week=1,home_team='SEA',away_team='NE',game_type='REG',
                kickoff='2026-09-10T00:20:00Z',finalized_at='2026-09-10T03:30:00Z',home_score=13,away_score=10,actual_margin=3)
    return dict(status='READY',season=2026,weeks=[dict(week=2,games=[game])],results=[result])


class TotalsMonitorTests(unittest.TestCase):
    def test_source_failure_preserves_pairs_and_existing_rows_are_fully_immutable(self):
        data=state()
        data['results'][0]['source']={'captured_at':'2026-09-10T03:30:00Z', 'sha256':'a'*64,
                                    'path':'source-archive/'+ 'a'*64+'.json'}
        seed={'rates':{'NE':{'pf':20.,'pa':24.},'SEA':{'pf':30.,'pa':18.}},'league_mean_total':46.}
        with patch.object(monitor,'load_seed',return_value=seed):
            first=monitor.refresh_shadow(data,None,'2026-09-10T20:00:00Z')
            previous=copy.deepcopy(dict(data,totals_shadow=first))
            self.assertEqual(first['games'][0]['history_witnesses'][0]['source'],data['results'][0]['source'])
            data['results'][0]['source']['captured_at']='2026-09-10T22:00:00Z'
            failed=monitor.refresh_shadow(data,previous,'2026-09-10T21:00:00Z')
            self.assertEqual(failed['status'],'BLOCKED')
            self.assertEqual(failed['games'],first['games'])
            changed=copy.deepcopy(first);changed['games'][0]['history_witnesses'][0]['home_score']=99
            with self.assertRaisesRegex(ValueError,'changed'):
                monitor.check_durable_shadow(dict(data,totals_shadow=changed),previous,'2026-09-10T21:00:00Z')
            with self.assertRaisesRegex(ValueError,'removed'):
                monitor.check_durable_shadow(dict(data,totals_shadow={'games':[]}),previous,'2026-09-10T21:00:00Z')

    def test_unready_or_unavailable_primary_never_issues(self):
        for update in ('state','reason','margin','locked'):
            data=state();game=data['weeks'][0]['games'][0]
            if update=='state':data['status']='BLOCKED'
            if update=='reason':game['blocked_reason']='Expected QB out'
            if update=='margin':game['margin']=None
            if update=='locked':game['forecast_status']='LOCKED'
            with self.subTest(update=update):
                self.assertEqual(monitor.refresh_shadow(data,None,'2026-09-10T20:00:00Z')['games'],[])

    def test_corrupt_results_block_and_a_failed_slate_does_not_partially_issue(self):
        for mutation in ('duplicate','score','identity'):
            data=state()
            if mutation=='duplicate':data['results'].append(copy.deepcopy(data['results'][0]))
            if mutation=='score':data['results'][0]['home_score']=True
            if mutation=='identity':data['results'][0]['home_team']='NE'
            with self.subTest(mutation=mutation):
                result=monitor.refresh_shadow(data,None,'2026-09-10T20:00:00Z')
                self.assertEqual(result['status'],'BLOCKED');self.assertEqual(result['games'],[])
        data=state();other=dict(data['weeks'][0]['games'][0],game_id='2026_02_BUF_NYJ',home='NYJ',away='BUF')
        data['weeks'][0]['games'].append(other)
        seed={'rates':{'NE':{'pf':20.,'pa':24.},'SEA':{'pf':30.,'pa':18.}},'league_mean_total':46.}
        with patch.object(monitor,'load_seed',return_value=seed):
            result=monitor.refresh_shadow(data,None,'2026-09-10T20:00:00Z')
        self.assertEqual(result['status'],'BLOCKED');self.assertEqual(result['games'],[])

    def test_seed_bytes_are_pinned(self):
        seed=monitor.load_seed()
        self.assertEqual(len(seed['rates']),32)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'scoring-rates.json';path.write_text('{}',encoding='utf-8')
            with patch.object(monitor,'SEED_PATH',path),self.assertRaisesRegex(ValueError,'hash'):
                monitor.load_seed()

    def test_historical_members_are_verified_and_seed_failure_still_grades_old_pairs(self):
        historical=monitor.load_historical()
        self.assertGreater(historical['games'],0)
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'attempt'
            shutil.copytree(monitor.HISTORICAL_DIR,target)
            (target/'public-summary.json').write_text('{}',encoding='utf-8')
            with patch.object(monitor,'HISTORICAL_DIR',target),self.assertRaisesRegex(ValueError,'hash'):
                monitor.load_historical()
        data=state()
        first=monitor.refresh_shadow(data,None,'2026-09-10T20:00:00Z')
        previous=copy.deepcopy(dict(data,totals_shadow=first))
        data['results'].append(dict(data['results'][0],game_id='2026_02_NE_SEA',week=2,
            kickoff='2026-09-17T00:20:00Z',finalized_at='2026-09-17T03:30:00Z'))
        with patch.object(monitor,'load_seed',side_effect=ValueError('Seed source unavailable')):
            graded=monitor.refresh_shadow(data,previous,'2026-09-17T04:00:00Z')
        self.assertEqual(graded['status'],'BLOCKED')
        self.assertEqual(graded['games'],first['games'])
        self.assertTrue(all(graded['metrics'][method]['games']==1 for method in monitor.METHODS))

    def test_fixed_pairs_use_prior_available_finals_and_never_revise(self):
        data=state(); before=copy.deepcopy(data)
        seed={'rates':{'NE':{'pf':20.,'pa':24.},'SEA':{'pf':30.,'pa':18.}},'league_mean_total':46.}
        with patch.object(monitor,'load_seed',return_value=seed):
            first=monitor.refresh_shadow(data,None,'2026-09-10T20:00:00Z')
            self.assertEqual(data,before)
            row=first['games'][0]
            self.assertEqual(row['totals']['pfpa_prior'],46.)
            self.assertAlmostEqual(row['totals']['shrink_4'],(4*92+46)/5/2)
            self.assertEqual(row['history_game_ids'],['2026_01_NE_SEA'])
            previous=dict(data,totals_shadow=first)
            data['results'].append(dict(data['results'][0],game_id='2026_02_NE_SEA',week=2,kickoff='2026-09-17T00:20:00Z',
                finalized_at='2026-09-17T03:30:00Z',home_score=20,away_score=20,actual_margin=0))
            final=monitor.refresh_shadow(data,previous,'2026-09-17T04:00:00Z')
            self.assertEqual(final['games'],first['games'])
            self.assertEqual(final['metrics']['pfpa_prior']['games'],1)
            self.assertEqual(final['metrics']['pfpa_prior']['mae'],6.)
            self.assertEqual(final['metrics']['pfpa_prior']['bias'],6.)
            self.assertEqual(monitor.refresh_shadow(data,None,'2026-09-17T04:00:00Z')['games'],[])
            monitor.check_durable_shadow(dict(data,totals_shadow=first),None,'2026-09-16T23:19:59Z')
            with self.assertRaisesRegex(ValueError,'lock'):
                monitor.check_durable_shadow(dict(data,totals_shadow=first),None,'2026-09-16T23:20:00Z')
            changed=copy.deepcopy(first);changed['games'][0]['totals']['shrink_4']+=1
            with self.assertRaisesRegex(ValueError,'changed'):
                monitor.check_durable_shadow(dict(data,totals_shadow=changed),previous,'2026-09-10T21:00:00Z')

    def test_same_day_missing_and_future_finals_are_not_training_history(self):
        data=state();game=data['weeks'][0]['games'][0]
        data['results'][0].update(kickoff='2026-09-16T17:00:00Z',finalized_at='2026-09-16T21:00:00Z')
        seed={'rates':{'NE':{'pf':20.,'pa':24.},'SEA':{'pf':30.,'pa':18.}},'league_mean_total':46.}
        with patch.object(monitor,'load_seed',return_value=seed):
            same=monitor.refresh_shadow(data,None,'2026-09-16T22:00:00Z')
            self.assertEqual(same['games'][0]['totals']['shrink_4'],46.)
            data['results'][0]['finalized_at']='2026-09-16T23:00:00Z'
            future=monitor.refresh_shadow(data,None,'2026-09-16T22:00:00Z')
            self.assertEqual(future['status'],'BLOCKED')
            self.assertEqual(future['games'],[])


if __name__=='__main__': unittest.main()
