import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


class ATSTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('pgo_ats'), 'Saved-line ATS module is missing')
        import pgo_ats
        return pgo_ats

    def fixture(self, home='SEA', away='NE', margin=4., line=-3.5):
        game=dict(game_id=f'2026_01_{away}_{home}',season=2026,week=1,game_type='REG',home=home,away=away,
                  kickoff='2026-09-13T17:00:00Z',lock_at='2026-09-13T16:00:00Z',issued_at='2026-09-10T19:00:00Z',
                  inputs_as_of='2026-09-10T18:00:00Z',source_edition='pgo-original',margin=margin,blocked_reason=None,espn_id='123')
        favorite=home if line<0 else away
        odds=dict(provider={'id':'100','name':'DraftKings'},spread=line,details=f'{favorite} -{abs(line):g}' if line else 'EVEN',
                  pointSpread={side:{'close':{'line':f'{value:+g}'}} for side,value in (('home',line),('away',-line))},
                  homeTeamOdds={'team':{'id':'10','abbreviation':home},'favorite':line<0,'underdog':line>0},
                  awayTeamOdds={'team':{'id':'20','abbreviation':away},'favorite':line>0,'underdog':line<0})
        status={'type':{'completed':False,'state':'pre','name':'STATUS_SCHEDULED'}}
        comp=dict(id='123',date=game['kickoff'],status=status,odds=[odds],competitors=[
            dict(homeAway='home',team={'id':'10','abbreviation':home}),dict(homeAway='away',team={'id':'20','abbreviation':away})])
        event=dict(id='123',date=game['kickoff'],season={'year':2026,'type':2},week={'number':1},competitions=[comp])
        payload=dict(season={'year':2026,'type':2},week={'number':1},events=[event])
        state=dict(season=2026,status='READY',checked_at='2026-09-10T20:00:00Z',schedule=[copy.deepcopy(game)],
                   weeks=[{'week':1,'games':[game]}],results=[],events={game['game_id']:{'event_id':'123','status':'STATUS_SCHEDULED'}},source_captures=[])
        return state,payload

    def archive(self,root,state,payload,captured='2026-09-10T19:55:00Z'):
        raw=json.dumps(payload).encode();digest=hashlib.sha256(raw).hexdigest()
        folder=root/'source-archive';folder.mkdir(exist_ok=True);(folder/(digest+'.json')).write_bytes(raw)
        ref=dict(url='https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=2026&seasontype=2&week=1',
                 path='source-archive/'+digest+'.json',sha256=digest,bytes=len(raw),captured_at=captured)
        state['source_captures']=[ref]
        return ref

    def final(self,game,margin):
        return dict(game_id=game['game_id'],season=2026,week=1,game_type='REG',home_team=game['home'],away_team=game['away'],
                    kickoff=game['kickoff'],home_score=20+margin,away_score=20,actual_margin=margin,event_id='123',finalized_at='2026-09-13T21:00:00Z')

    def test_signed_home_and_away_favorite_lines_and_projected_model_spread(self):
        api=self.api()
        for home,away,margin,line,ats in [('SEA','NE',4.,-3.5,'SEA'),('IND','BAL',-1.,3.5,'IND')]:
            with self.subTest(home=home),tempfile.TemporaryDirectory() as tmp:
                state,payload=self.fixture(home,away,margin,line);root=Path(tmp);self.archive(root,state,payload)
                before=copy.deepcopy(state);out=api.refresh(state,None,root,state['checked_at']);self.assertEqual(state,before)
                self.assertEqual(out['status'],'READY');row=out['games'][0]
                self.assertEqual(row['home_handicap'],line);self.assertEqual(row['away_handicap'],-line)
                self.assertEqual(row['model_home_handicap'],-margin);self.assertEqual(row['home_edge'],margin+line)
                self.assertEqual(row['ats_pick'],ats);self.assertEqual(row['provider']['id'],'100')
                self.assertNotIn('cover_probability',row);self.assertNotIn('win_probability',row)
                api.check_durable(dict(state,ats=out),None,'2026-09-10T20:00:01Z')

    def test_loss_but_cover_win_but_not_cover_push_and_no_edge_are_distinct(self):
        api=self.api()
        cases=[(1,3.5,-2,'W','W'),(2,-7,3,'L','W'),(4,-3,3,'PUSH','PUSH'),(3,-3,7,'W','NOPICK'),(0,0,0,'NOPICK','NOPICK')]
        for margin,line,actual,su_grade,ats_grade in cases:
            with self.subTest(case=(margin,line,actual)),tempfile.TemporaryDirectory() as tmp:
                state,payload=self.fixture(margin=margin,line=line);root=Path(tmp);self.archive(root,state,payload)
                issued=api.refresh(state,None,root,state['checked_at'])
                state['results']=[self.final(state['weeks'][0]['games'][0],actual)]
                out=api.refresh(state,dict(ats=issued),root,'2026-09-13T22:00:00Z')
                self.assertEqual(out['games'][0]['grade']['straight_up_ats'],su_grade)
                self.assertEqual(out['games'][0]['grade']['ats'],ats_grade)
                self.assertEqual(out['games'][0]['status'],'LOCKED')
                if margin+line==0:self.assertEqual(out['metrics']['ats']['no_edge'],1)

    def test_missing_conflicting_quarter_and_future_quotes_never_become_zero_lines(self):
        api=self.api()
        mutations=[lambda p:p['events'][0]['competitions'][0].update(odds=[]),
                   lambda p:p['events'][0]['competitions'][0]['odds'][0].pop('spread'),
                   lambda p:p['events'][0]['competitions'][0]['odds'][0].update(spread=-3.25),
                   lambda p:p['events'][0]['competitions'][0]['odds'][0].update(details='NE -3.5'),
                   lambda p:p['events'][0]['competitions'][0]['odds'][0]['pointSpread']['away']['close'].update(line='+4.5'),
                   lambda p:p['events'][0]['competitions'][0]['odds'][0]['homeTeamOdds']['team'].update(id='999'),
                   lambda p:p['events'][0]['competitions'][0]['odds'][0]['provider'].update(id='2'),
                   lambda p:p['events'][0]['competitions'][0]['status']['type'].update(state='in',name='STATUS_IN_PROGRESS')]
        for mutate in mutations:
            with self.subTest(mutation=mutate),tempfile.TemporaryDirectory() as tmp:
                state,payload=self.fixture();mutate(payload);root=Path(tmp);self.archive(root,state,payload)
                out=api.refresh(state,None,root,state['checked_at'])
                self.assertEqual(out['games'],[]);self.assertTrue(out['unavailable'][0]['reason'])
        with tempfile.TemporaryDirectory() as tmp:
            state,payload=self.fixture();root=Path(tmp);self.archive(root,state,payload,'2026-09-10T21:00:00Z')
            self.assertEqual(api.refresh(state,None,root,state['checked_at'])['games'],[])

    def test_bad_source_hash_fails_closed_and_missing_new_feed_retains_stale_quote(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as tmp:
            state,payload=self.fixture();root=Path(tmp);ref=self.archive(root,state,payload)
            old=api.refresh(state,None,root,state['checked_at']);row=old['games'][0]
            payload['events'][0]['competitions'][0]['odds']=[];self.archive(root,state,payload,'2026-09-10T20:10:00Z')
            stale=api.refresh(state,dict(ats=old),root,'2026-09-10T20:11:00Z')
            self.assertEqual(stale['games'][0]['status'],'STALE')
            for key in ('home_handicap','quote_captured_at','issued_at','updated_at','ats_pick'):
                self.assertEqual(stale['games'][0][key],row[key])
            self.assertTrue(stale['games'][0]['stale_reason'])
            (root/state['source_captures'][0]['path']).write_bytes(b'tampered')
            broken=api.refresh(state,None,root,'2026-09-10T20:12:00Z')
            self.assertEqual(broken['games'],[]);self.assertEqual(broken['status'],'BLOCKED')

    def test_before_lock_revisions_are_allowed_but_locked_economics_are_immutable(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as tmp:
            state,payload=self.fixture();root=Path(tmp);self.archive(root,state,payload)
            old=api.refresh(state,None,root,state['checked_at'])
            changed,payload=self.fixture(line=-5.5);self.archive(root,changed,payload,'2026-09-10T20:10:00Z')
            new=api.refresh(changed,dict(ats=old),root,'2026-09-10T20:11:00Z')
            self.assertEqual(new['games'][0]['ats_pick'],'NE')
            self.assertNotEqual(new['games'][0]['issued_at'],old['games'][0]['issued_at'])
            api.check_durable(dict(changed,ats=new),dict(ats=old),'2026-09-10T20:11:01Z')
            locked=api.refresh(changed,dict(ats=old),root,'2026-09-13T16:00:00Z')
            self.assertEqual(locked['games'][0]['home_handicap'],-3.5)
            with self.assertRaises(ValueError):api.check_durable(dict(changed,ats=new),dict(ats=old),'2026-09-13T16:00:00Z')
            with self.assertRaises(ValueError):api.check_durable(dict(changed,ats={'games':[]}),dict(ats=old),'2026-09-13T16:00:00Z')

    def test_no_late_opener_and_main_blocked_only_grades_existing_ats(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as tmp:
            state,payload=self.fixture();root=Path(tmp);self.archive(root,state,payload)
            late=api.refresh(state,None,root,'2026-09-13T16:00:00Z')
            self.assertEqual(late['games'],[])
            self.assertEqual(late['unavailable'][0]['model_home_handicap'],-4.)
            old=api.refresh(state,None,root,state['checked_at']);state['status']='BLOCKED'
            blocked=api.refresh(state,None,root,state['checked_at']);self.assertEqual(blocked['games'],[])
            state['results']=[self.final(state['weeks'][0]['games'][0],7)]
            out=api.refresh(state,dict(ats=old),root,'2026-09-13T22:00:00Z')
            self.assertEqual(out['games'][0]['grade']['ats'],'W')
            self.assertEqual(out['status'],'BLOCKED')

    def test_changed_final_and_new_record_tampering_are_rejected(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as tmp:
            state,payload=self.fixture();root=Path(tmp);self.archive(root,state,payload)
            old=api.refresh(state,None,root,state['checked_at']);game=state['weeks'][0]['games'][0]
            state['results']=[self.final(game,7)]
            graded=api.refresh(state,dict(ats=old),root,'2026-09-13T22:00:00Z')
            state['results']=[self.final(game,1)]
            bad=api.refresh(state,dict(ats=graded),root,'2026-09-13T23:00:00Z')
            self.assertEqual(bad['status'],'BLOCKED');self.assertEqual(bad['games'][0]['result'],graded['games'][0]['result'])
            changed=copy.deepcopy(old);changed['games'][0]['home_edge']+=1
            with self.assertRaises(ValueError):api.check_durable(dict(state,ats=changed),None,'2026-09-10T20:00:01Z')

    def test_model_line_is_full_precision_and_can_grade_original_forecast_without_book(self):
        api=self.api()
        for actual,expected in ((6,'W'),(4,'L')):
            with self.subTest(actual=actual),tempfile.TemporaryDirectory() as tmp:
                state,payload=self.fixture(home='LAR',away='SF',margin=4.31,line=-3.5)
                root=Path(tmp);self.archive(root,state,payload)
                old=api.refresh(state,None,root,state['checked_at'])
                state['results']=[self.final(state['weeks'][0]['games'][0],actual)]
                out=api.refresh(state,dict(ats=old),root,'2026-09-13T22:00:00Z')
                self.assertEqual(out['games'][0]['grade']['model_line'],expected)
                self.assertEqual(out['games'][0]['grade']['straight_up_ats'],'W')
        with tempfile.TemporaryDirectory() as tmp:
            state,payload=self.fixture(margin=3.291695521475117);root=Path(tmp)
            state['weeks'][0]['games'][0]['confidence']={'added_after_lock':True}
            state['results']=[self.final(state['weeks'][0]['games'][0],3)]
            out=api.refresh(state,None,root,'2026-09-13T22:00:00Z')
            self.assertEqual(out['games'],[])
            self.assertEqual(out['unavailable'][0]['grade']['model_line'],'L')
            self.assertEqual(out['metrics']['model_line']['losses'],1)
            api.check_durable(dict(state,ats=out),None,'2026-09-13T22:00:01Z')
            state['weeks'][0]['games'][0]['issued_at']='2026-09-13T16:00:01Z'
            late=api.refresh(state,None,root,'2026-09-13T22:00:00Z')
            self.assertEqual(late['unavailable'][0]['grade']['model_line'],'UNAVAILABLE')

    def test_quote_age_rollback_stale_lock_and_tied_game_cover(self):
        api=self.api()
        with tempfile.TemporaryDirectory() as tmp:
            state,payload=self.fixture(margin=1,line=3.5);root=Path(tmp);self.archive(root,state,payload)
            old=api.refresh(state,None,root,state['checked_at'])
            aged=api.refresh(state,None,root,'2026-09-10T21:00:01Z')
            self.assertEqual(aged['games'],[])
            stale=api.refresh(state,dict(ats=old),root,'2026-09-10T21:00:01Z')
            self.assertEqual(stale['games'][0]['status'],'STALE')
            state['results']=[self.final(state['weeks'][0]['games'][0],0)]
            locked=api.refresh(state,dict(ats=stale),root,'2026-09-13T22:00:00Z')
            self.assertEqual(locked['games'][0]['status'],'LOCKED')
            self.assertTrue(locked['games'][0]['stale_reason'])
            self.assertEqual(locked['games'][0]['grade']['straight_up_ats'],'W')
            self.assertEqual(locked['games'][0]['grade']['model_line'],'L')
            state['results']=[]
            self.archive(root,state,payload,'2026-09-10T19:54:00Z')
            rollback=api.refresh(state,dict(ats=old),root,'2026-09-10T20:01:00Z')
            self.assertEqual(rollback['games'][0]['status'],'STALE')
            self.assertEqual(rollback['games'][0]['quote_captured_at'],old['games'][0]['quote_captured_at'])

    def test_stale_saved_comparison_survives_main_revision_withholding_and_lock(self):
        api=self.api()
        for withheld in (False,True):
            with self.subTest(withheld=withheld),tempfile.TemporaryDirectory() as tmp:
                state,payload=self.fixture();root=Path(tmp);self.archive(root,state,payload)
                old=api.refresh(state,None,root,state['checked_at'])
                game=state['weeks'][0]['games'][0]
                game.update(margin=6.,issued_at='2026-09-10T20:05:00Z',blocked_reason='QB withheld' if withheld else None)
                payload['events'][0]['competitions'][0]['odds']=[]
                self.archive(root,state,payload,'2026-09-10T20:10:00Z')
                stale=api.refresh(state,dict(ats=old),root,'2026-09-10T20:11:00Z')
                self.assertEqual(stale['games'][0]['status'],'STALE')
                self.assertEqual(stale['games'][0]['pgo_margin'],4.)
                api.check_durable(dict(state,ats=stale),dict(ats=old),'2026-09-10T20:11:01Z')
                state['results']=[self.final(game,5)]
                locked=api.refresh(state,dict(ats=stale),root,'2026-09-13T22:00:00Z')
                self.assertEqual(locked['status'],'READY')
                self.assertEqual(locked['games'][0]['grade']['model_line'],'W')
                self.assertEqual(locked['games'][0]['status'],'LOCKED')
                api.check_durable(dict(state,ats=locked),dict(ats=stale),'2026-09-13T22:00:01Z')


if __name__=='__main__':unittest.main()
