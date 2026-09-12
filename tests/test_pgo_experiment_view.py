"""Presentation checks using detached, hand-readable experiment fixtures."""
import copy
from html.parser import HTMLParser
import unittest

import pgo_season_view as view


class ExperimentViewTests(unittest.TestCase):
    def test_score_collection_reports_future_evidence_without_numerical_ranges(self):
        state = dict(score_range_collection=dict(status='READY', checked_at='2026-09-12T20:00:00Z',
            forecast_adjustment=None, ranges=None, predictive_status='UNAVAILABLE', excluded=[{},{}],
            metrics=dict(selected_games=14,eligible_games=0,finalized_games=0,awaiting_durable_receipt=14,
                         complete_calibration_seasons=0,partial_calibration_seasons=1)))
        before = copy.deepcopy(state); page = view._experiments(state)
        for text in ('14 selected games','0 verified completed games','14 awaiting their archive receipt',
                     '2 completed calibration seasons','500 games','Reliable outcome ranges are not available yet'):
            self.assertIn(text, page)
        self.assertEqual(state, before)
        state['score_range_collection']['ranges'] = [3, 30]
        with self.assertRaises(ValueError): view._experiments(state)

    def test_offensive_collection_keeps_unknown_rows_distinct_and_claims_no_adjustment(self):
        state = dict(offensive_inventory=dict(status='DESCRIPTIVE / NOT IN MODEL',
            generated_at='2026-09-12T20:00:00Z', teams=[dict(team='NE', players=[{}, {}])], games=[{}]),
            offensive_usage=dict(status='WAITING', checked_at='2026-09-12T20:00:00Z',
            forecast_adjustment=None, predictive_status='UNAVAILABLE', pending_games=14,
            excluded_games=[{}, {}], metrics=dict(games=1, cohort_rows=3, joined=2,
            observed_positive=1, observed_zero=1, missing_target=1)))
        before = copy.deepcopy(state)
        page = view._experiments(state)
        self.assertIn('id="season-offensive-usage"', page)
        self.assertIn('2 offensive player records across 1 teams', page)
        self.assertIn('1 explicitly recorded zero', page)
        self.assertIn('1 have no matching row', page)
        self.assertIn('Missing playing time is unknown', page)
        self.assertEqual(state, before)
        state['offensive_usage']['forecast_adjustment'] = 1
        with self.assertRaises(ValueError): view._experiments(state)

    def fixture(self):
        arms = ('postseason', 'without_qb_passing', 'without_team_passing')
        game = dict(game_id='2026_02_A_B', away='NE', home='SEA', issued_at='2026-09-10T20:00:00Z')
        probabilities = {f'{arm}_{curve}': dict(selected_team='SEA' if curve=='scalar' else 'NE',
                            selected_probability=.6 if curve=='scalar' else .55)
                         for arm in arms for curve in ('scalar','intercept')}
        player = dict(name='Player <script>', position='LB', prior_role_share=None,
                      confirmed_unavailable=True, roster_status='RES')
        team = dict(team='NE', depth_snapshot_at='2026-09-10T12:00:00Z', report_status='UNKNOWN',
                    final_inactives_status='UNKNOWN', availability_checked_at=None,
                    depth_identity_conflicts=1, unlisted_active_defenders=2, unavailable_unknown_prior_role=1,
                    unavailable_players=[player], roles=[dict(position='LB', listed_first=1,
                    confirmed_unavailable_first=0, remaining_experienced_backups_not_confirmed_out=1,
                    remaining_unknown_history_backups_not_confirmed_out=2, uncertain_backups=1)])
        return dict(totals_shadow=dict(status='READY', games=[dict(game,totals=dict(league_prior=44.,pfpa_prior=45.,shrink_4=46.,shrink_8=45.5))],
                    metrics=dict(paired_games=0), historical={}),
                    weights_shadow=dict(status='BLOCKED',blocked_reason='Source <conflict>',
                    games=[dict(game,margins=dict(postseason=3.,without_qb_passing=-2.,without_team_passing=0.), probabilities=probabilities)],
                    metrics=dict(paired_games=0), historical={}),
                    replacement_depth=dict(status='DESCRIPTIVE / NOT IN MODEL',generated_at='2026-09-10T20:00:00Z',
                    source_as_of='2026-09-10T19:00:00Z',teams=[team],games=[game],
                    sources=[dict(href='https://example.test/source?team=NE&week=2',label='Source <name>')]))

    def test_real_contract_picks_probabilities_unknowns_and_escaping_preserve_input(self):
        state=self.fixture(); before=copy.deepcopy(state)
        page=view._experiments(state)
        self.assertEqual(state,before)
        self.assertIn('Source &lt;conflict&gt;',page)
        self.assertIn('Player &lt;script&gt;',page)
        self.assertNotIn('<script>',page)
        self.assertIn('Source &lt;name&gt;',page)
        self.assertIn('team=NE&amp;week=2',page)
        self.assertIn('SEA by 3.0',page)
        self.assertIn('NE by 2.0',page)
        self.assertIn('No projected edge',page)
        self.assertIn('same neutral midpoint: SEA 60.0%',page)
        self.assertIn('learned midpoint: NE 55.0%',page)
        self.assertIn('Prior usage unknown',page)
        self.assertIn('No numerical injury adjustment yet',page)
        self.assertIn('0 verified finals',page)
        self.assertIn('45.5',page)
        state['weights_shadow']['games'][0]['margins']['postseason']=.02
        state['replacement_depth']['teams'][0]['unresolved_official_names']=['Name <unknown>']
        page=view._experiments(state)
        self.assertIn('SEA by less than 0.1 point',page)
        self.assertIn('Name &lt;unknown&gt;',page)

    def test_all_disclosures_and_tables_have_unique_reading_keys(self):
        class Tags(HTMLParser):
            def __init__(self): super().__init__(); self.keys=[]; self.missing=[]
            def handle_starttag(self,tag,attributes):
                attr=dict(attributes)
                if 'data-view-key' in attr: self.keys.append(attr['data-view-key'])
                if (tag=='details' or 'table-shell' in attr.get('class','').split()) and not attr.get('data-view-key'):
                    self.missing.append(tag)
        parser=Tags(); parser.feed(view._experiments(self.fixture()))
        self.assertFalse(parser.missing)
        self.assertEqual(len(parser.keys),len(set(parser.keys)))
        self.assertIn('weights-game-2026_02_A_B',parser.keys)
        self.assertIn('replacement-team-NE',parser.keys)

    def test_named_inventory_is_separate_from_older_incomplete_captures(self):
        state = self.fixture()
        self.assertIn('This saved edition lacks the complete named defender inventory', view._experiments(state))
        depth = state['replacement_depth']
        depth['inventory_version'] = 1
        depth['teams'][0].update(inventory_version=1, defenders=depth['teams'][0]['unavailable_players'])
        before = copy.deepcopy(state)
        page = view._experiments(state)
        self.assertIn('1 named defender record saved', page)
        self.assertIn('Later snap reports can show who played', page)
        self.assertNotIn('This saved edition lacks', page)
        self.assertEqual(state, before)
        depth['status'] = 'BLOCKED'
        page = view._experiments(state)
        self.assertIn('earlier named inventory remains preserved', page)
        self.assertNotIn('This saved edition lacks', page)
        del depth['teams'][0]['inventory_version']
        self.assertIn('This saved edition lacks', view._experiments(state))

    def test_absent_or_blocked_optional_sources_do_not_invent_live_results(self):
        self.assertEqual(view._experiments({}),'')
        page=view._experiments(dict(replacement_depth=dict(status='BLOCKED',blocked_reason='No source <saved>',teams=[],games=[])))
        self.assertIn('No source &lt;saved&gt;',page)
        self.assertIn('0 team summaries; 0 unlocked matchups captured',page)
        state=self.fixture();state['replacement_depth']['sources'][0]['href']='javascript:alert(1)'
        with self.assertRaises(ValueError):view._experiments(state)

    def test_inactive_roster_context_is_not_a_current_game_absence(self):
        state = self.fixture(); depth = state['replacement_depth']; team = depth['teams'][0]
        inactive = dict(name='Dated <inactive>', position='LB', roster_status='INA',
                        confirmed_unavailable=False, prior_role_share=None)
        depth['inventory_version'] = 2
        team.update(inventory_version=2, defenders=[*team['unavailable_players'], inactive], inactive_roster_defenders=1)
        before = copy.deepcopy(state); page = view._experiments(state)
        self.assertIn('2 named defender records saved', page)
        self.assertIn('Roster-listed inactive defenders: Dated &lt;inactive&gt;', page)
        self.assertIn('does not establish absence for an upcoming game', page)
        self.assertNotIn('Dated &lt;inactive&gt; (LB): Confirmed unavailable', page)
        self.assertEqual(state, before)
        for version in (1, 3):
            depth['inventory_version'] = version
            page = view._experiments(state)
            self.assertIn('This saved edition lacks', page)
            self.assertNotIn('Roster-listed inactive defenders:', page)
        depth['inventory_version'] = team['inventory_version'] = 1
        team['defenders'] = team['unavailable_players']
        page = view._experiments(state)
        self.assertIn('This older inventory omitted roster-listed inactive players', page)
        self.assertNotIn('Roster-listed inactive defenders:', page)

    def test_usage_counts_do_not_claim_injury_weights_or_zero_for_missing_rows(self):
        state = self.fixture()
        state['injury_usage'] = dict(status='WAITING', forecast_adjustment=None,
            predictive_status='UNAVAILABLE', checked_at='2026-09-12T16:00:00Z',
            pending_games=14, excluded_games=[{'game_id':'old-game'}],
            metrics=dict(games=1, cohort_rows=20, joined=12, observed_positive=10,
                         observed_zero=2, missing_target=8))
        before = copy.deepcopy(state); page = view._experiments(state)
        for text in ('Eligible completed games: 1', 'Games awaiting finals: 14', '12 of 20',
                     '2 explicitly recorded zero', '8 have no matching row',
                     'collecting offensive player records', 'Not established.'):
            self.assertIn(text, page)
        self.assertEqual(state, before)
        state['injury_usage'].update(status='BLOCKED', blocked_reason='Source <failed>')
        page = view._experiments(state)
        self.assertIn('Source &lt;failed&gt;', page)
        self.assertNotIn('Matched playing-time rows:', page)
        state['injury_usage']['forecast_adjustment'] = 1
        with self.assertRaises(ValueError): view._experiments(state)


if __name__=='__main__': unittest.main()
