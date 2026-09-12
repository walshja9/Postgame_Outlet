"""Actual archive, source, deadline and immutable-collection regression checks."""
import copy
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pgo_season as api


class ScoreRangeCollectionTests(unittest.TestCase):
    def monitor(self):
        self.assertIsNotNone(importlib.util.find_spec('pgo_score_range_monitor'),
                             'Future score-error collection is missing')
        import pgo_score_range_monitor
        return pgo_score_range_monitor

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.clock = '2026-09-12T20:00:00Z'
        self.game = dict(game_id='2026_01_ATL_PIT',season=2026,week=1,game_type='REG',
            home='PIT',away='ATL',kickoff='2026-09-13T17:00:00Z',lock_at='2026-09-13T16:00:00Z',
            espn_id='401872689',margin=3.,total=45.,home_points=24.,away_points=21.,
            issued_at='2026-09-12T19:00:00Z',inputs_as_of='2026-09-12T19:00:00Z',
            source_edition='pgo-postseason-2026-week1-fixture',blocked_reason=None,
            expected_qbs={'ATL':'Cooper Rush','PIT':'Aaron Rodgers'})
        sources = [self.source(gzip.compress(kind.encode(),mtime=0), api.URLS[kind],
                               '2026-09-12T18:50:00Z', '.csv.gz') for kind in ('roster','depth')]
        # A compact, explicitly incomplete schedule may collect games but never
        # qualify a complete season. The full-schedule check is independently tested.
        self.state = dict(schema_version=1,season=2026,status='READY',checked_at='2026-09-12T19:01:00Z',
            weeks=[dict(week=1,games=[copy.deepcopy(self.game)])],schedule=[copy.deepcopy(self.game)],
            results=[],sources=[],source_captures=sources,
            rankings=dict(edition=self.game['source_edition'],source_captures=sources),
            edition_sources={self.game['source_edition']:sources})
        self.save(self.state, '2026-09-12T19:01:01Z')
        self.initial_pointer=(self.root/'current.json').read_bytes()

    def source(self, raw, url, captured_at, suffix='.json'):
        digest=api.sha(raw); relative='source-archive/'+digest+suffix
        path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        return dict(path=relative,sha256=digest,bytes=len(raw),captured_at=captured_at,url=url)

    def save(self, state, durable):
        with patch.object(api,'now',return_value=durable):
            api.save_state(state,self.root)

    def collect(self, *, state=None, previous=None):
        monitor=self.monitor()
        previous=api.load_current(self.root) if previous is None else previous
        state=copy.deepcopy(previous) if state is None else copy.deepcopy(state)
        state['checked_at']=self.clock
        before=copy.deepcopy(state)
        payload=monitor.refresh_shadow(state,previous,self.root,self.clock)
        self.assertEqual(state,before,'Collector changed primary forecasts')
        return state,payload

    def commit_collection(self):
        state,payload=self.collect()
        self.assertEqual(payload['status'],'READY',payload.get('blocked_reason'))
        state['score_range_collection']=payload
        self.monitor().check_durable_shadow(state,api.load_current(self.root),self.clock)
        self.save(state,self.clock)
        return payload

    def final(self, *, home_score=20):
        g=self.game
        payload=dict(season={'year':2026,'type':2},week={'number':1},events=[dict(
            id=g['espn_id'],date=g['kickoff'],season={'year':2026,'type':2},week={'number':1},
            competitions=[dict(id=g['espn_id'],status={'type':dict(completed=True,state='post',name='STATUS_FINAL')},
                competitors=[dict(homeAway='home',team={'abbreviation':'PIT'},score=str(home_score)),
                             dict(homeAway='away',team={'abbreviation':'ATL'},score='17')])])])
        ref=self.source(api.canonical(payload),api.SCOREBOARD.format(season=2026,week=1),self.clock)
        return dict(api.parse_scoreboard(payload,[g],self.clock)['results'][0],source=ref)

    def test_actual_future_collection_then_verified_final_keeps_original_forecast(self):
        first=self.commit_collection()
        self.assertEqual(len(first['observations']),1)
        self.assertEqual(first['metrics']['eligible_games'],0)
        self.assertIsNone(first['ranges']);self.assertIsNone(first['forecast_adjustment'])
        self.assertEqual(first['predictive_status'],'UNAVAILABLE')
        self.clock='2026-09-13T21:00:00Z'
        state=api.load_current(self.root);state['results']=[self.final()]
        _,after=self.collect(state=state)
        self.assertEqual(after['status'],'READY',after.get('blocked_reason'))
        self.assertEqual(after['observations'],first['observations'])
        self.assertEqual(after['metrics']['eligible_games'],1)
        self.assertEqual(after['metrics']['finalized_games'],1)
        result=after['results'][self.game['game_id']]
        self.assertEqual(result['margin_error'],0.)
        self.assertEqual(result['total_error'],8.)
        self.assertEqual(after['metrics']['complete_calibration_seasons'],0)

    def test_first_collection_at_or_after_t60_never_admits_an_old_forecast(self):
        for clock in ('2026-09-13T16:00:00Z','2026-09-13T16:30:00Z','2026-09-13T21:00:00Z'):
            self.clock=clock
            _,payload=self.collect()
            self.assertEqual(payload['observations'],[])
            self.assertEqual(payload['excluded'][0]['reason'],'FIRST_COLLECTION_AT_OR_AFTER_T60')

    def test_real_durable_boundary_rejects_crossing_but_retained_blocked_payload_is_allowed(self):
        self.clock='2026-09-13T15:59:59Z'
        state,payload=self.collect();state['score_range_collection']=payload
        previous=api.load_current(self.root);monitor=self.monitor()
        monitor.check_durable_shadow(state,previous,self.clock)
        with self.assertRaisesRegex(ValueError,'durable'):
            monitor.check_durable_shadow(state,previous,'2026-09-13T16:00:00Z')
        retained=dict(copy.deepcopy(previous),score_range_collection=dict(status='BLOCKED',observations=[],
            selections={},collection_witnesses={},results={},blocked_reason='Late optional collection'))
        monitor.check_durable_shadow(retained,previous,'2026-09-13T16:01:00Z')

    def test_real_season_save_discards_only_collection_when_actual_write_crosses_cutoff(self):
        self.clock='2026-09-13T15:59:59Z'
        state,payload=self.collect();state['score_range_collection']=payload
        forecast=copy.deepcopy(state['weeks'])
        original=api.read_json(self.root/'current.json')
        protected={p:p.read_bytes() for p in (self.root/original['path']).iterdir()}
        self.save(state,'2026-09-13T16:00:00Z')
        saved=api.load_current(self.root)
        self.assertEqual(saved['weeks'],forecast)
        self.assertEqual(saved['score_range_collection']['status'],'BLOCKED')
        self.assertEqual(saved['score_range_collection'].get('observations',[]),[])
        for path,raw in protected.items():self.assertEqual(path.read_bytes(),raw)

    def test_changed_draft_waits_for_actual_archive_then_appends_before_lock(self):
        first=self.commit_collection()
        self.clock='2026-09-12T21:00:00Z'
        state=api.load_current(self.root)
        revised=state['weeks'][0]['games'][0]
        revised.update(margin=5.,home_points=25.,away_points=20.,issued_at='2026-09-12T20:30:00Z')
        _,waiting=self.collect(state=state)
        self.assertEqual(waiting['observations'],first['observations'])
        self.assertIn('AWAITING_DURABLE_FORECAST',[r['reason'] for r in waiting['excluded']])
        state['checked_at']='2026-09-12T20:31:00Z';self.save(state,'2026-09-12T20:31:01Z')
        second=self.commit_collection()
        self.assertEqual(len(second['observations']),2)
        self.assertEqual(second['observations'][0],first['observations'][0])
        selected=second['selections'][self.game['game_id']]
        self.assertEqual(next(r for r in second['observations'] if r['id']==selected)['forecast']['margin'],5.)
        self.clock='2026-09-12T21:05:00Z'
        _,repeated=self.collect()
        self.assertEqual(repeated['observations'],second['observations'])
        self.clock='2026-09-13T16:01:00Z'
        state=api.load_current(self.root);state['weeks'][0]['games'][0]['margin']=99
        _,locked=self.collect(state=state)
        self.assertEqual(locked['selections'],second['selections'])

    def test_missing_or_future_source_clocks_and_source_tamper_fail_closed(self):
        for change in ('missing','future','bytes'):
            with self.subTest(change=change):
                (self.root/'current.json').write_bytes(self.initial_pointer)
                state=api.load_current(self.root)
                if change=='bytes':
                    (self.root/state['source_captures'][0]['path']).write_bytes(b'tamper')
                else:
                    ref=state['edition_sources'][self.game['source_edition']][0]
                    if change=='missing':ref.pop('captured_at')
                    else:ref['captured_at']='2026-09-12T19:00:01Z'
                    state['checked_at']=f'2026-09-12T19:02:0{int(change=="future")}Z'
                    self.save(state,state['checked_at'])
                _,payload=self.collect(previous=state)
                self.assertEqual(payload['status'],'BLOCKED')
                self.assertEqual(payload['observations'],[])
                if change=='bytes':break

    def test_duplicate_games_and_nonfinite_or_inconsistent_scores_do_not_collect(self):
        for change in ('duplicate','missing','nonfinite','scores'):
            state=api.load_current(self.root)
            if change=='duplicate':state['weeks'][0]['games'].append(copy.deepcopy(self.game))
            elif change=='missing':state['weeks'][0]['games'][0].pop('inputs_as_of')
            elif change=='nonfinite':state['weeks'][0]['games'][0]['margin']=float('nan')
            else:state['weeks'][0]['games'][0]['home_points']=99
            with self.subTest(change=change):
                _,payload=self.collect(state=state)
                self.assertEqual(payload['observations'],[])
                self.assertTrue(payload['status']=='BLOCKED' or payload['excluded'])

    def test_selected_archive_or_accepted_final_tamper_cannot_choose_an_alternative(self):
        first=self.commit_collection()
        self.clock='2026-09-13T21:00:00Z'
        state=api.load_current(self.root);state['results']=[self.final()]
        _,graded=self.collect(state=state)
        state.update(checked_at=self.clock,score_range_collection=graded)
        self.save(state,self.clock)
        self.clock='2026-09-13T21:05:00Z'
        changed=api.load_current(self.root);changed['results']=[self.final(home_score=21)]
        _,failed=self.collect(state=changed)
        self.assertEqual(failed['status'],'BLOCKED')
        self.assertEqual(failed['results'],graded['results'])
        archive=first['observations'][0]['forecast_archive']
        (self.root/archive['path']/'manifest.json').write_bytes(b'tamper')
        _,failed=self.collect(previous=state)
        self.assertEqual(failed['status'],'BLOCKED')
        self.assertEqual(failed['selections'],first['selections'])

    def test_provider_la_game_ids_accept_normalized_lar_on_either_side(self):
        monitor=self.monitor()
        for away,home,key in (('SF','LAR','2026_01_SF_LA'),('LAR','PIT','2026_01_LA_PIT')):
            game=dict(self.game,away=away,home=home,game_id=key)
            with self.subTest(game_id=key):
                self.assertEqual(monitor._forecast(game)['game_id'],key)
        with self.assertRaises(ValueError):
            monitor._forecast(dict(self.game,game_id='2026_01_NE_PIT'))

    def test_forecast_helper_byte_changes_split_collection_time_recipe(self):
        monitor=self.monitor()
        original=monitor._model()
        dependencies=('pgo_season_model.py','pgo_current_strength.py','pgo_forecast_corrected.py',
            'pgo_forecast_snapshot.py','pgo_sources.py','pgo_model.py',
            'research/pgo_input_audit/audit_model.py',
            'research/pgo_postseason_candidate/pinned_challenger.py')
        read=Path.read_bytes
        for relative in dependencies:
            target=(monitor.ROOT/relative).resolve()
            def changed(path):
                raw=read(path)
                return raw+b'\n# fixture-only changed forecast helper\n' if path.resolve()==target else raw
            with self.subTest(dependency=relative),patch.object(Path,'read_bytes',changed):
                candidate=monitor._model()
                self.assertNotEqual(api.sha(api.canonical(original)),api.sha(api.canonical(candidate)))
                pins={r['path']:r for r in candidate['collection_time_executable_dependencies']}
                self.assertEqual(pins[relative]['sha256'],api.sha(changed(target)))
                self.assertIn('not proof of original execution',candidate['model_code_time_basis'])
        first=self.commit_collection()
        self.clock='2026-09-12T21:00:00Z'
        with patch.object(Path,'read_bytes',changed):
            _,replayed=self.collect()
        self.assertEqual(replayed['status'],'READY',replayed.get('blocked_reason'))
        self.assertEqual(replayed['observations'],first['observations'])
        self.assertEqual(replayed['metrics']['eligible_games'],1)

    def test_unavailable_selection_remains_explicitly_excluded_after_lock(self):
        first=self.commit_collection()
        self.clock='2026-09-12T21:00:00Z'
        state=api.load_current(self.root);state['status']='BLOCKED'
        state,unavailable=self.collect(state=state)
        self.assertEqual(unavailable['status'],'READY',unavailable.get('blocked_reason'))
        self.assertIsNone(unavailable['selections'][self.game['game_id']])
        self.assertEqual(unavailable['excluded'],[dict(game_id=self.game['game_id'],reason='PRIMARY_FORECAST_UNAVAILABLE')])
        state['score_range_collection']=unavailable;self.save(state,self.clock)
        self.clock=self.game['lock_at']
        _,locked=self.collect()
        self.assertEqual(locked['status'],'READY',locked.get('blocked_reason'))
        self.assertEqual(locked['observations'],first['observations'])
        self.assertEqual(locked['selections'],unavailable['selections'])
        self.assertEqual(locked['excluded'],unavailable['excluded'])
        self.assertEqual(locked['metrics']['eligible_games'],0)

    def test_500_rows_do_not_replace_complete_seasons_or_merge_recipe_cohorts(self):
        monitor=self.monitor()
        def payload(second_n=272,other_recipe=False):
            out=dict(observations=[],selections={},collection_witnesses={},results={},schedules={})
            for year,n in ((2026,272),(2027,second_n)):
                ids=[f'{year}-game-{i}' for i in range(272)]
                out['schedules'][str(year)]=dict(season=year,games=dict.fromkeys(ids),complete_schedule=True)
                for key in ids[:n]:
                    row=dict(id=key,recipe_id=str(year) if other_recipe else 'fixed',
                             forecast=dict(game_id=key,season=year),schedule_id=str(year))
                    out['observations'].append(row);out['selections'][key]=key
                    out['collection_witnesses'][key]={'fixture':'prior durable receipt'};out['results'][key]={}
            return out
        partial=monitor._metrics(payload(second_n=250))
        self.assertEqual(partial['finalized_games'],522)
        self.assertEqual(partial['complete_calibration_seasons'],1)
        self.assertFalse(partial['calibration_minimum_met'])
        split=monitor._metrics(payload(other_recipe=True))
        self.assertEqual(split['complete_calibration_seasons'],2)
        self.assertFalse(split['calibration_minimum_met'])
        ready=monitor._metrics(payload())
        self.assertTrue(ready['calibration_minimum_met'])
        self.assertFalse(ready['eligible_for_ranges'])


if __name__=='__main__':unittest.main()
