import copy
from html.parser import HTMLParser
import unittest

import pgo_season_view as view
from tests.test_pgo_season_view import state


def projection_fixture():
    data = state()
    original = data['weeks'][1]['games'][0]
    original.update(home='DAL', away='TB', issued_at='2026-09-16T21:00:00Z',
                    source_edition='locked-week-2', expected_qbs={'TB':'Baker Mayfield','DAL':'Dak Prescott'},
                    forecast_status='BLOCKED', blocked_reason='Expected QB inactive', pick=None, grade='NO_PICK')
    current = copy.deepcopy(original)
    current.update(issued_at='2026-09-16T22:30:00Z', inputs_as_of='2026-09-16T22:30:00Z',
                   source_edition='current-week-2', expected_qbs={'TB':'Jalon Daniels','DAL':'Dak Prescott'},
                   margin=10., total=44.4, home_points=27.2, away_points=17.2, pick='DAL',
                   forecast_status='CURRENT', blocked_reason=None, grade='NOT_ELIGIBLE', confidence=None,
                   eligible_for_locked_record=False, after_lock=True, after_kickoff=False,
                   starter_announcements=[dict(team='TB',full_name='Jalon Daniels',source=dict(
                       captured_at='2026-09-16T22:15:00Z',url='https://www.buccaneers.com/news/starter',
                       path='source-archive/'+'a'*64+'.json'))])
    data['current_projections'] = {'current':current}
    return data, original, current


class CurrentProjectionViewTests(unittest.TestCase):
    def test_current_forecast_is_primary_and_original_locked_record_is_preserved(self):
        data, original, current = projection_fixture()
        before = copy.deepcopy(data)
        page = view.render_season(data)
        row = page.split('id="season-game-current"',1)[1].split('</tr>',1)[0]
        for text in ('Current projection','Jalon Daniels','DAL 27','TB 17','DAL by 10.0 points',
                     '2026-09-16T22:30:00Z','After T-60 lock','Excluded from locked records'):
            self.assertIn(text,row)
        for text in ('Baker Mayfield','Saved conditional estimate','win chance','allocated pool points',
                     'data-grade=', 'ATS pick'):
            self.assertNotIn(text,row)
        self.assertIn('Original locked forecast',page)
        original_row = page.split('id="season-original-game-current"',1)[1].split('</tr>',1)[0]
        self.assertIn('Saved conditional estimate',original_row)
        self.assertIn('2026-09-16T22:00:00Z',original_row)
        self.assertIn('Baker Mayfield',page)
        self.assertIn('2026-09-16T21:00:00Z',page)
        self.assertIn('2026-09-16T22:15:00Z',page)
        self.assertEqual(data,before)

    def test_game_day_current_forecast_does_not_inherit_original_line_or_chance(self):
        data, original, current = projection_fixture()
        data['ats'] = {'games':[dict(game_id='current',home_handicap=-7,status='STALE')]}
        before = copy.deepcopy(data)
        card = view._game_day(data).split('class="game-day-card"',1)[1].split('</article>',1)[0]
        for text in ('Current projection','PGO current winner selection: DAL','Jalon Daniels',
                     'TB 17, DAL 27','2026-09-16T22:30:00Z','2026-09-16T22:15:00Z',
                     'After T-60 lock','Original locked forecast'):
            self.assertIn(text,card)
        for text in ('Saved sportsbook line','DAL -7','51.0% win chance','Pick withheld'):
            self.assertNotIn(text,card)
        self.assertEqual(data,before)

    def test_after_kickoff_timing_is_explicit_and_new_anchors_are_unique(self):
        data, original, current = projection_fixture()
        current.update(issued_at='2026-09-16T23:05:00Z',after_kickoff=True)
        data['checked_at']='2026-09-16T23:10:00Z'
        page = view.render_season(data)
        self.assertIn('After kickoff',page)
        class Tags(HTMLParser):
            def __init__(self,text):
                super().__init__(); self.items=[]; self.feed(text)
            def handle_starttag(self,tag,attrs):
                self.items.append((tag,dict(attrs)))
        tags=Tags(page).items
        for attribute in ('id','data-view-key'):
            values=[attrs[attribute] for _,attrs in tags if attribute in attrs]
            self.assertEqual(len(values),len(set(values)),attribute)
        ids={attrs['id'] for _,attrs in tags if 'id' in attrs}
        for tag,attrs in tags:
            if tag=='a' and attrs.get('href','').startswith('#'):
                self.assertIn(attrs['href'][1:],ids)
        self.assertEqual(page.count('data-season-game-id="current"'),1)

    def test_pre_kickoff_calculation_saved_after_kickoff_is_labeled_as_late_save(self):
        data, original, current=projection_fixture()
        current.update(issued_at='2026-09-16T22:59:50Z',durable_at='2026-09-16T23:00:20Z',
                       durable_after_lock=True,durable_after_kickoff=True)
        data['checked_at']='2026-09-16T23:00:30Z'
        before=copy.deepcopy(data)
        page=view.render_season(data)
        row=page.split('id="season-game-current"',1)[1].split('</tr>',1)[0]
        self.assertIn('Saved after kickoff',row)
        self.assertIn('2026-09-16T23:00:20Z',row)
        self.assertIn('2026-09-16T22:59:50Z',row)
        self.assertIn('Issue timing:',row)
        self.assertIn('before kickoff',row)
        self.assertIn('data-current-projection-durable-at="2026-09-16T23:00:20Z"',row)
        card=view._game_day(data).split('class="game-day-card"',1)[1].split('</article>',1)[0]
        self.assertIn('Saved after kickoff',card)
        self.assertIn('2026-09-16T23:00:20Z',card)
        original_row=page.split('id="season-original-game-current"',1)[1].split('</tr>',1)[0]
        self.assertNotIn('2026-09-16T23:00:20Z',original_row)
        self.assertEqual(data,before)

    def test_durable_timing_cannot_precede_issue_or_contradict_its_saved_flags(self):
        for changes in (dict(durable_at='2026-09-16T22:20:00Z',durable_after_lock=True,durable_after_kickoff=False),
                        dict(durable_at='2026-09-16T23:00:20Z',durable_after_lock=True,durable_after_kickoff=False),
                        dict(durable_at='2026-09-16T22:40:00Z',durable_after_lock=False,durable_after_kickoff=False)):
            data, original, current=projection_fixture(); current.update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                view.render_season(data)

    def test_invalid_current_identity_timing_scores_or_eligibility_fail_closed(self):
        cases=(lambda c:c.update(home='SEA'),lambda c:c.update(pick='SEA'),
               lambda c:c.update(issued_at='2026-09-16T21:30:00Z'),
               lambda c:c.update(after_kickoff=True),lambda c:c.update(after_lock=False),
               lambda c:c.update(home_points=99.),lambda c:c.update(eligible_for_locked_record=True),
               lambda c:c.update(expected_qbs={'TB':'','DAL':'Dak Prescott'}))
        for change in cases:
            data, original, current=projection_fixture(); change(current)
            with self.subTest(change=change),self.assertRaises(ValueError):
                view.render_season(data)

    def test_blocked_current_replacement_shows_no_current_pick_or_score(self):
        data, original, current=projection_fixture()
        current.update(blocked_reason='Verified replacement starter inactive',pick=None,
                       margin=None,total=None,home_points=None,away_points=None,
                       probabilities=None,win_probability=None)
        before=copy.deepcopy(data)
        try:
            page=view.render_season(data)
        except ValueError as error:
            self.fail('Valid blocked current projection must remain renderable: '+str(error))
        row=page.split('id="season-game-current"',1)[1].split('</tr>',1)[0]
        for text in ('Current projection unavailable','Verified replacement starter inactive',
                     'Jalon Daniels','2026-09-16T22:30:00Z','Excluded from locked records'):
            self.assertIn(text,row)
        for text in ('Predicted:','DAL by','Model averages','data-grade='):
            self.assertNotIn(text,row)
        card=view._game_day(data).split('class="game-day-card"',1)[1].split('</article>',1)[0]
        self.assertIn('Current projection unavailable',card)
        self.assertIn('Verified replacement starter inactive',card)
        self.assertNotIn('Predicted:',card)
        self.assertNotIn('PGO current winner selection: DAL',card)
        self.assertIn('Original locked forecast',page)
        self.assertIn('Saved conditional estimate',page)
        self.assertEqual(data,before)

    def test_failed_current_refresh_is_visible_while_prior_projection_is_retained(self):
        data, original, current=projection_fixture()
        data['checked_at']='2026-09-16T22:40:00Z'
        data['current_projection_check']=dict(status='BLOCKED',checked_at=data['checked_at'],
                                             blocked_reason='Current QB source <missing>')
        before=copy.deepcopy(data)
        page=view.render_season(data)
        self.assertIn('Current forecast update needs review',page)
        self.assertIn('Current QB source &lt;missing&gt;',page)
        self.assertIn('Earlier current forecast is retained with its original issue time',page)
        self.assertIn('2026-09-16T22:40:00Z',page)
        self.assertIn('href="#season-current-projection-check"',page)
        row=page.split('id="season-game-current"',1)[1].split('</tr>',1)[0]
        self.assertIn('2026-09-16T22:30:00Z',row)
        self.assertEqual(data,before)

    def test_missing_current_projection_keeps_standard_frozen_display(self):
        data, original, current=projection_fixture()
        data.pop('current_projections')
        page=view.render_season(data)
        self.assertNotIn('Current projection',page)
        self.assertNotIn('season-original-game-',page)
        self.assertIn('Saved conditional estimate',page)


if __name__ == '__main__':
    unittest.main()
