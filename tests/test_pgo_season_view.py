import copy
from html.parser import HTMLParser
import unittest
from unittest.mock import patch

import generate_site
import pgo_season_view as view


def state():
    codes = sorted(row[0] for row in generate_site.TEAM.values())
    teams = [dict(team=team, rank=i + 1, rating=15.5 - i, prior_rank=32-i,
                  qb_name='QB <source>', features={'pgo_v0': 15.5-i},
                  contributions={'pgo_v0': 15.5-i}) for i, team in enumerate(codes)]
    def game(key, week, grade, result, **changes):
        row = dict(game_id=key, season=2026, week=week, home='SEA', away='NE',
                   kickoff='2026-09-16T23:00:00Z', lock_at='2026-09-16T22:00:00Z',
                   margin=.2, total=50.2, home_points=25.2, away_points=25.0,
                   pick='SEA', grade=grade, result=result, forecast_status='LOCKED',
                   blocked_reason=None, availability={'checked_at':'2026-09-16T21:00:00Z',
                   'summary':'Expected QB verified; other injuries are context', 'blocked_reason':None},
                   confidence={'points':1, 'win_probability':.51, 'expected_points':.51,
                               'earned_points':None, 'added_after_lock':False})
        row.update(changes)
        return row
    old = game('old', 1, 'W', {'home_score':24, 'away_score':20}, forecast_status='FINAL',
               confidence={'points':1,'win_probability':.6,'expected_points':.6,
                           'earned_points':1,'added_after_lock':True})
    return dict(schema_version=1, season=2026, current_week=2, checked_at='2026-09-16T22:30:00Z',
                status='READY', blocked_reason=None, freshness='Sources checked; no new final results',
                rankings=dict(edition='pgo-2026-week2', generated_at='2026-09-16T21:00:00Z',
                              inputs_as_of='2026-09-16T21:00:00Z',history_through='2026-09-15T23:00:00Z',teams=teams),
                model_records=[dict(name='Weekly model',edition='pgo-weekly',wins=1,losses=0,ties=0,no_pick=0,pending=1)],
                sources=[dict(label='Saved <source>',href='evidence/season-2026/week2.json')],
                weeks=[dict(week=1,status='COMPLETE',source_edition='old',generated_at='2026-09-09T21:00:00Z',
                            inputs_as_of='2026-09-09T21:00:00Z',games=[old]),
                       dict(week=2,status='UPCOMING',source_edition='pgo-2026-week2',generated_at='2026-09-16T21:00:00Z',
                            inputs_as_of='2026-09-16T21:00:00Z',games=[game('current',2,'PENDING',None)])])


class SeasonViewTests(unittest.TestCase):
    def test_final_inactive_watch_and_late_context_do_not_rewrite_saved_forecast(self):
        data = state()
        game = data['weeks'][1]['games'][0]
        original = copy.deepcopy(game)
        base_row = view._game(game,data['weeks'][1]).split('id="season-game-current"')[1].split('</tr>')[0]
        context = dict(checked_at='2026-09-16T22:20:00Z', summary='Latest <official> list',
                       teams={'NE': {'final_inactives_status':'VERIFIED_LIST', 'observations':[
                           dict(name='New <inactive>', position='LB', status='INACTIVE',
                                source_url='https://example.com/inactives')]},
                              'SEA': {'final_inactives_status':'UNKNOWN', 'observations':[]}})
        data['availability_context'] = {'current':context}
        watch = dict(status='ATTENTION', checked_at=data['checked_at'], games=[
            dict(game_id='current', home='SEA', away='NE', kickoff=game['kickoff'], lock_at=game['lock_at'],
                 checked_at=context['checked_at'], missing_teams=['SEA'], status='MISSING', after_lock=True)])
        before = copy.deepcopy(data)
        with patch('pgo_season.availability_watch', return_value=watch, create=True):
            page = view.render_season(data)
        self.assertEqual(data, before)
        self.assertEqual(game, original)
        self.assertEqual(page.split('id="season-game-current"')[1].split('</tr>')[0], base_row)
        self.assertIn('id="season-inactive-watch"', page)
        banner = page.split('id="season-inactive-watch"')[1].split('</aside>')[0]
        self.assertIn('Final inactive lists missing: SEA', banner)
        self.assertNotIn('<details', banner)
        self.assertIn('data-freshness-minutes="10"', banner)
        self.assertIn('data-freshness-until="2026-09-16T23:00:00Z"', banner)
        self.assertIn('data-freshness-ended-label="Kickoff reached; final list status shown above"', banner)
        card = next(part.split('</article>')[0] for part in page.split('class="game-day-card"')[1:]
                    if 'data-view-key="game-day-availability-current"' in part.split('</article>')[0])
        self.assertIn('Latest availability update', card)
        self.assertIn('This update was observed after prediction lock', card)
        self.assertIn('Saved forecast availability', card)
        self.assertNotIn('Latest &lt;official&gt; list', card)
        self.assertNotIn('VERIFIED_LIST', card)
        self.assertIn('New &lt;inactive&gt;', card)
        self.assertIn('https://example.com/inactives', card)
        self.assertNotIn('This update was observed after kickoff', card)
        context['teams']['NE']['observations'].append(dict(name='Earlier uncertain player', position='LB',
                                                         status='QUESTIONABLE', gsis_id='00-0000002'))
        with patch('pgo_season.availability_watch', return_value=watch, create=True):
            current = view.render_season(data)
        self.assertIn('Earlier report: Questionable; not on final inactive list', current)
        context['checked_at'] = '2026-09-16T23:10:00Z'
        data['checked_at'] = '2026-09-16T23:15:00Z'
        with patch('pgo_season.availability_watch', return_value=watch, create=True):
            page = view.render_season(data)
        self.assertIn('This update was observed after kickoff', page)

    def test_inline_grades_keep_winner_and_saved_spread_outcomes_separate(self):
        from tests.test_pgo_ats_view import fixture
        data=state(); game=data['weeks'][0]['games'][0]
        game.update(margin=3.3,total=45,home_points=24.15,away_points=20.85,
                    result={'home_score':13,'away_score':10},source_edition='old',
                    issued_at='2026-09-09T21:00:00Z')
        data['ats']=fixture(); comparison=data['ats']['games'][0]
        comparison.update(game_id='old',home='SEA',away='NE',su_pick='SEA',ats_pick='NE',
                          pgo_margin=3.3,model_home_handicap=-3.3,home_handicap=-7,away_handicap=7,
                          home_edge=-3.7,source_edition='old',pgo_issued_at=game['issued_at'],
                          grade=dict(model_line='L',straight_up_ats='L',ats='W'))
        before=copy.deepcopy(data); page=view.render_season(data)
        row=page.split('id="season-game-old"')[1].split('</tr>')[0]
        for text in ('Predicted: NE 21, SEA 24','Final: NE 10, SEA 13','Winner:</strong> W',
                     'PGO line (SEA -3.3): Below projection',
                     'Winner vs sportsbook (SEA -7): Not covered',
                     'ATS pick (NE +7): Covered','data-grade="W"'):
            self.assertIn(text,row)
        self.assertNotIn('Earlier saved comparison',row)
        self.assertEqual(data,before)
        comparison.update(source_edition='older',pgo_margin=-1,model_home_handicap=1,
                          su_pick='NE',grade=dict(model_line='PUSH',straight_up_ats='PUSH',ats='NOPICK'),
                          ats_pick=None,home_edge=0)
        row=view.render_season(data).split('id="season-game-old"')[1].split('</tr>')[0]
        for text in ('Earlier saved comparison','NE','Matched projection','Push','No edge','Winner:</strong> W'):
            self.assertIn(text,row)
        data['ats']['games']=[]; data['ats']['unavailable']=[dict(comparison,reason='No pre-lock quote',
                                                               grade=dict(model_line='L'))]
        row=view.render_season(data).split('id="season-game-old"')[1].split('</tr>')[0]
        self.assertIn('Below projection',row)
        self.assertIn('Winner vs sportsbook: Unavailable',row)
        self.assertIn('ATS pick: Unavailable',row)
        data.pop('ats')
        row=view.render_season(data).split('id="season-game-old"')[1].split('</tr>')[0]
        self.assertNotIn('Below projection',row)
        self.assertIn('Winner:</strong> W',row)

    def test_game_day_and_freshness_use_saved_eastern_clocks(self):
        data=state(); data['checked_at']='2026-09-17T00:30:00Z'
        data['source_captures']=[{'url':'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?week=2',
                                  'captured_at':'2026-09-17T00:20:00Z'}]
        game=data['weeks'][1]['games'][0]
        game.update(kickoff='2026-09-17T01:00:00Z', lock_at='2026-09-17T00:00:00Z')
        game['availability']['teams']={'NE':{'final_inactives_status':'UNKNOWN','observations':[
            {'name':'Player <name>','position':'LB','status':'OUT','gsis_id':'00-0000001'}]}}
        for team in data['rankings']['teams']: team.pop('prior_rank')
        before=copy.deepcopy(data); page=view.render_season(data)
        self.assertEqual(data,before)
        self.assertIn('Game day &middot; September 16',page)
        self.assertLess(page.index('id="season-game-day"'),page.index('id="season-rankings"'))
        self.assertIn('51.0% win chance',page)
        self.assertIn('Player &lt;name&gt; (LB): Out',page)
        self.assertIn('Final inactive lists are not fully verified',page)
        self.assertIn('Ranking inputs captured',page)
        self.assertIn('First saved ranking edition',page)
        self.assertNotIn('Performance history through',page)
        self.assertIn('Results checked',page)
        self.assertIn('2026-09-17T00:20:00Z',page)
        self.assertIn('data-freshness-minutes="45"',page)
        game['confidence']['added_after_lock']=True
        game['blocked_reason']='Awaiting QB'; game['pick']=None
        card=view.render_season(data).split('class="game-day-card"')[-1].split('</article>')[0]
        self.assertNotIn('51.0% win chance',card)
        self.assertIn('Pick withheld',card)
        data['checked_at']='2026-09-15T20:00:00Z'
        self.assertIn('No games on this date',view.render_season(data))

    def test_availability_freshness_uses_the_actual_refresh_window(self):
        data=state();data['checked_at']='2026-09-16T21:30:00Z'
        game=data['weeks'][1]['games'][0];game['availability']['checked_at']='2026-09-16T21:25:00Z'
        later=copy.deepcopy(game);later.update(game_id='later',kickoff='2026-09-20T17:00:00Z',lock_at='2026-09-20T16:00:00Z')
        later['availability']['checked_at']='2026-09-09T21:00:00Z'
        data['weeks'][1]['games'].append(later)
        data['weeks']=data['weeks'][1:]
        freshness=view._freshness(data)
        self.assertIn('2026-09-16T21:25:00Z',freshness)
        self.assertNotIn('2026-09-09T21:00:00Z',freshness)
        self.assertNotIn('Update overdue',freshness)
        data['checked_at']='2026-09-17T12:00:00Z'
        self.assertIn('No unlocked games within the next 24 hours',view._freshness(data))

    def test_reading_keys_and_navigation_survive_rank_and_week_changes(self):
        class Tags(HTMLParser):
            def __init__(self, text):
                super().__init__(); self.items=[]; self.feed(text)
            def handle_starttag(self, tag, attrs):
                self.items.append((tag,dict(attrs)))
        data=state()
        data['penalty_shadow']={'games':[], 'metrics':{}, 'excluded':[{'game_id':'closed','reason':'Already locked'}]}
        before=copy.deepcopy(data)
        def inspect(data):
            tags=Tags(view.render_season(data)).items
            controls=[a for tag,a in tags if tag=='details' or (tag=='input' and a.get('type')=='checkbox') or 'table-shell' in a.get('class','').split()]
            self.assertTrue(all(a.get('data-view-key') for a in controls), 'Every reading control needs a stable key')
            keys=[a['data-view-key'] for _,a in tags if 'data-view-key' in a]
            self.assertEqual(len(keys),len(set(keys)))
            ids=[a['id'] for _,a in tags if 'id' in a]
            self.assertEqual(len(ids),len(set(ids)))
            for tag,a in tags:
                if tag=='a' and a.get('href','').startswith('#'):
                    self.assertIn(a['href'][1:],ids)
            self.assertIn(('nav',{'class':'season-nav','aria-label':'PGO sections'}),tags)
            return {a['data-view-key'] for a in controls}
        first=inspect(data)
        self.assertEqual(data,before)
        empty=copy.deepcopy(data); empty['weeks']=[]; empty['rankings']=None
        inspect(empty)
        for team in data['rankings']['teams']:
            team['rank']=33-team['rank']; team['rating']=-team['rating']
            team['features']['pgo_v0']=team['rating']; team['contributions']['pgo_v0']=team['rating']
        week=copy.deepcopy(data['weeks'][-1]); week['week']=3
        week['games'][0].update(game_id='next',week=3)
        data['weeks'].append(week); data['current_week']=3
        self.assertTrue(first <= inspect(data), 'Existing reading keys must survive a new weekly edition')

    def test_current_rankings_week_and_archived_grades_preserve_input(self):
        data = state(); before = copy.deepcopy(data)
        page = view.render_season(data)
        self.assertEqual(data,before)
        self.assertEqual(page.count('data-season-team='),32)
        self.assertEqual(page.count('data-season-game-id='),2)
        self.assertLess(page.index('data-season-game-id="current"'),page.index('data-season-game-id="old"'))
        self.assertIn('Week 2',page)
        self.assertIn('Any victory by the selected team earns a W, regardless of the winning margin.',page)
        self.assertIn('Week 1',page)
        self.assertIn('Model records',page)
        self.assertIn('data-season-checked-at="2026-09-16T22:30:00Z"',page)
        self.assertIn('About 25 points each',page)
        self.assertIn('SEA by 0.2 points',page)
        self.assertIn('SEA 25.2',page)
        self.assertIn('Fixed confidence points',page)
        self.assertIn('Added after lock',page)
        self.assertIn('QB &lt;source&gt;',page)
        self.assertIn('Saved &lt;source&gt;',page)
        self.assertIn('What lifts this rating',page)
        self.assertIn('What holds this rating back',page)
        self.assertNotIn('<section',page)
        self.assertNotIn('<style',page)
        self.assertNotIn('data-weekly-game-id=',page)

    def test_blocked_and_unknown_values_are_not_invented(self):
        data = state(); data.update(status='BLOCKED',blocked_reason='QB identity <missing>')
        game = data['weeks'][1]['games'][0]
        for status in ('DRAFT','LOCKED'):
            game['forecast_status']=status
            self.assertIn('data-weekly-cutoff="2026-09-16T22:00:00Z"',view.render_season(data))
        game.update(forecast_status='BLOCKED',blocked_reason='Awaiting official source',pick=None,
                    margin=None,total=None,home_points=None,away_points=None,confidence=None)
        page = view.render_season(data)
        self.assertIn('QB identity &lt;missing&gt;',page)
        self.assertIn('Awaiting official source',page)
        self.assertIn('Forecast unavailable',page)
        self.assertIn('Confidence unavailable',page)
        self.assertIn('2026-09-16T22:00:00Z',page)
        self.assertNotIn('data-weekly-cutoff=',page)
        game.update(margin=.2,total=50.2,home_points=25.2,away_points=25.0)
        before=copy.deepcopy(data)
        page=view.render_season(data)
        self.assertIn('Saved conditional estimate',page)
        self.assertIn('This estimate is withheld as a pick until the blocking issue is resolved.',page)
        self.assertEqual(data,before)

    def test_grades_ties_no_pick_and_zero_earned_remain_distinct(self):
        data = state(); game=data['weeks'][1]['games'][0]
        game.update(grade='T',result={'home_score':20,'away_score':20},forecast_status='FINAL')
        game['confidence']['earned_points']=0
        page=view.render_season(data)
        self.assertIn('data-grade="T"><strong>Winner:</strong> T',page)
        self.assertIn('SEA 20',page)
        self.assertIn('Earned pool points: 0',page)
        self.assertIn('Expected pool points: 0.51',page)
        game.update(pick=None,grade='NO_PICK',blocked_reason='No eligible pick')
        page=view.render_season(data)
        self.assertIn('No pick',page)
        self.assertNotIn('data-grade="W"',page.split('data-season-game-id="current"')[1].split('</tr>')[0])

    def test_optional_matchup_chain_reconciles_and_units_stay_distinct(self):
        data=state(); game=data['weeks'][1]['games'][0]
        game['explanation']={'neutral_margin':-.3,'home_adjustment':.5,'rest_adjustment':0}
        game['explanation'].update(home_rating=1.2,away_rating=1.5,rating_inputs_as_of='2026-09-16T20:00:00Z')
        game.update(issued_at='2026-09-16T21:00:00Z',inputs_as_of='2026-09-16T20:00:00Z',
                    expected_qbs={'SEA':'Saved <QB>', 'NE':'Other QB'},source_edition='saved-game-edition')
        page=view.render_season(data)
        self.assertIn('Neutral matchup: -0.30 points',page)
        self.assertIn('Home/venue adjustment: +0.50 points',page)
        self.assertIn('Win probability is a percentage',page)
        self.assertIn('pool points, not NFL scoreboard points',page)
        self.assertIn('Ratings saved for this forecast: SEA +1.200; NE +1.500',page)
        self.assertIn('Saved &lt;QB&gt;',page)
        self.assertIn('Edition: saved-game-edition',page)
        self.assertIn('Issued <time datetime="2026-09-16T21:00:00Z"',page)
        game['explanation']['home_rating']=1.3
        with self.assertRaisesRegex(ValueError,'rating inputs'): view.render_season(data)
        game['explanation']['home_rating']=1.2
        game['explanation']['home_adjustment']=.6
        with self.assertRaisesRegex(ValueError,'matchup explanation'): view.render_season(data)

    def test_invalid_identity_numbers_status_and_sources_raise(self):
        cases = []
        data=state(); data['rankings']['teams'][0]['rating']=float('nan'); cases.append(data)
        data=state(); data['rankings']['teams']=data['rankings']['teams'][:-1]; cases.append(data)
        data=state(); data['weeks'][1]['games'][0]['grade']='WIN'; cases.append(data)
        data=state(); data['weeks'][1]['games'][0]['forecast_status']='ASSUMED'; cases.append(data)
        data=state(); data['weeks'][1]['games'][0]['confidence']['win_probability']=1.1; cases.append(data)
        for href in ('javascript:alert(1)','//example.com','../secret','https://example.com/\\x'):
            data=state(); data['sources'][0]['href']=href; cases.append(data)
        for data in cases:
            with self.subTest(data=data['sources']), self.assertRaises(ValueError): view.render_season(data)


if __name__ == '__main__': unittest.main()
