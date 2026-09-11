"""Independent source-custody and provider-final regression tests."""
import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import pgo_season as season


class SeasonSourceTests(unittest.TestCase):
    def game(self, *, away='NE', home='SEA', event_id='401872656'):
        return dict(game_id=f'2026_01_{away}_{home}',season=2026,week=1,game_type='REG',
                    home=home,away=away,kickoff='2026-09-10T00:20:00Z',espn_id=event_id)

    def scoreboard(self, games, *, completed=True):
        events=[]
        for game in games:
            status=dict(completed=completed,state='post' if completed else 'in',
                        name='STATUS_FINAL' if completed else 'STATUS_HALFTIME')
            events.append(dict(id=game['espn_id'],date=game['kickoff'],season={'year':2026,'type':2},week={'number':1},
                competitions=[dict(id=game['espn_id'],status={'type':status},competitors=[
                    dict(homeAway='home',team={'abbreviation':game['home']},score='24'),
                    dict(homeAway='away',team={'abbreviation':game['away']},score='21')])]))
        return dict(season={'year':2026,'type':2},week={'number':1},events=events)

    def final(self, game):
        return season.parse_scoreboard(self.scoreboard([game]),[game],'2026-09-10T04:00:00Z')['results'][0]

    def state(self):
        return dict(schema_version=1,season=2026,current_week=1,status='READY',
                    checked_at='2026-09-10T05:00:00Z',weeks=[],rankings={},results=[],sources=[],source_captures=[])

    def test_provider_event_and_competition_ids_are_exact_and_unique(self):
        games=[self.game(),self.game(away='NYJ',home='BUF',event_id='401872657')]
        good=self.scoreboard(games)
        self.assertEqual(len(season.parse_scoreboard(good,games,'2026-09-10T04:00:00Z')['results']),2)
        changes=[]
        duplicate=copy.deepcopy(good)
        duplicate['events'][1]['id']=duplicate['events'][0]['id']
        duplicate['events'][1]['competitions'][0]['id']=duplicate['events'][0]['id']
        changes.append(duplicate)
        mismatch=copy.deepcopy(good);mismatch['events'][0]['competitions'][0]['id']='999';changes.append(mismatch)
        wrong_schedule=copy.deepcopy(good)
        wrong_schedule['events'][0]['id']='999';wrong_schedule['events'][0]['competitions'][0]['id']='999';changes.append(wrong_schedule)
        for changed in changes:
            with self.subTest(events=changed['events']), self.assertRaises(ValueError):
                season.parse_scoreboard(changed,games,'2026-09-10T04:00:00Z')

    def test_malformed_provider_containers_raise_validation_errors(self):
        game=self.game();good=self.scoreboard([game])
        paths=[(),('season',),('week',),('events',),('events',0),
               ('events',0,'season'),('events',0,'week'),('events',0,'competitions'),
               ('events',0,'competitions',0),('events',0,'competitions',0,'competitors'),
               ('events',0,'competitions',0,'competitors',0),
               ('events',0,'competitions',0,'competitors',0,'team'),
               ('events',0,'competitions',0,'status'),('events',0,'competitions',0,'status','type')]
        for path in paths:
            for malformed in (None,42,'invalid',[],{}):
                changed=copy.deepcopy(good)
                if not path:changed=malformed
                else:
                    target=changed
                    for key in path[:-1]:target=target[key]
                    target[path[-1]]=malformed
                with self.subTest(path=path,value=malformed):
                    try:
                        season.parse_scoreboard(changed,[game],'2026-09-10T04:00:00Z')
                    except ValueError:
                        pass
                    except Exception as error:
                        self.fail(f'Malformed provider shape escaped validation: {type(error).__name__}')
                    else:
                        # An absent status object is still a pending observation.
                        self.assertIn(path[-1:] , [('status',),('type',)])
                        self.assertEqual(malformed,{})

    def test_accepted_event_identity_cannot_change_even_when_final_score_matches(self):
        final=self.final(self.game())
        later=dict(final,finalized_at='2026-09-10T05:00:00Z')
        self.assertEqual(season.merge_results([final],[later]),[final])
        with self.assertRaises(ValueError):
            season.merge_results([final],[dict(later,event_id='999')])

    def test_conflicting_event_and_competition_final_status_requires_review(self):
        game=self.game();payload=self.scoreboard([game])
        payload['events'][0]['status']={'type':{'completed':False,'state':'in','name':'STATUS_HALFTIME'}}
        with self.assertRaises(ValueError):
            season.parse_scoreboard(payload,[game],'2026-09-10T04:00:00Z')

    def test_accepted_final_returned_as_nonfinal_requires_review(self):
        game=self.game();saved=self.final(game)
        state=self.state();state.update(weeks=[{'week':1,'games':[game]}],results=[saved])
        raw=json.dumps(self.scoreboard([game],completed=False)).encode()
        meta=dict(captured_at='2026-09-10T05:00:00Z',sha256=season.sha(raw),bytes=len(raw),path='sources/scoreboard.json')
        with tempfile.TemporaryDirectory() as tmp, patch.object(season,'parse_schedule',return_value=[game]), patch.object(season,'fetch_source',side_effect=[(b'schedule',{}),(raw,meta)]):
            with self.assertRaises(ValueError):season.fetch_inputs(state,Path(tmp))
        self.assertEqual(state['results'],[saved])

    def test_source_bytes_are_checked_for_current_capture_and_accepted_result(self):
        for reference in ('source_captures','result'):
            with self.subTest(reference=reference), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'sources').mkdir()
                raw=json.dumps(self.scoreboard([self.game()])).encode()
                path='sources/'+season.sha(raw)+'.json';(root/path).write_bytes(raw)
                source=dict(url=season.SCOREBOARD.format(season=2026,week=1),path=path,
                            captured_at='2026-09-10T04:00:00Z',sha256=season.sha(raw),bytes=len(raw))
                state=self.state()
                if reference=='source_captures':state['source_captures']=[source]
                else:state['results']=[dict(self.final(self.game()),source=source)]
                season.save_state(state,root)
                self.assertEqual(season.load_current(root),state)
                (root/path).write_bytes(raw+b'tamper')
                with self.assertRaises(ValueError):season.load_current(root)

    def test_repeated_source_path_cannot_hide_conflicting_hash_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'sources').mkdir()
            raw=json.dumps(self.scoreboard([self.game()])).encode()
            path='sources/'+season.sha(raw)+'.json';(root/path).write_bytes(raw)
            source=dict(path=path,captured_at='2026-09-10T04:00:00Z',sha256=season.sha(raw),bytes=len(raw))
            state=self.state();state['source_captures']=[source]
            state['results']=[dict(self.final(self.game()),source=dict(source,sha256='0'*64))]
            season.save_state(state,root)
            with self.assertRaises(ValueError):season.load_current(root)

    def test_espn_wsh_alias_is_bound_to_washington_schedule_identity(self):
        game=self.game(away='WAS')
        payload=self.scoreboard([game])
        payload['events'][0]['competitions'][0]['competitors'][1]['team']['abbreviation']='WSH'
        result=season.parse_scoreboard(payload,[game],'2026-09-10T04:00:00Z')['results'][0]
        self.assertEqual(result['away_team'],'WAS')
        self.assertEqual(result['event_id'],game['espn_id'])

    def test_season_workflow_preserves_canonical_and_mirror_publication_boundary(self):
        root=Path(__file__).resolve().parents[1]
        workflow=(root/'.github/workflows/update-season.yml').read_text(encoding='utf-8')
        job=re.search(r'(?m)^  refresh:\s*\n((?:^(?:    .*|\s*)\n?)*)',workflow)
        self.assertIsNotNone(job)
        self.assertRegex(job[1],r'(?m)^    if:\s*(?:\$\{\{\s*)?github\.repository\s*==\s*[\'"]walshja9/Postgame_Outlet[\'"]')
        self.assertIn('cancel-in-progress: false',workflow)
        self.assertNotIn('git push --force',workflow)


if __name__=='__main__':unittest.main()
