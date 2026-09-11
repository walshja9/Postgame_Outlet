import re
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pgo_comparison as comparison


class CurrentInjuryNotesTests(unittest.TestCase):
    source = comparison.HERE / 'research/pgo_opening_night_20260909/injuries/injury-source.json'

    def setUp(self):
        loader = patch('pgo_season.load_current', return_value=None)
        self.season_loader = loader.start()
        self.addCleanup(loader.stop)

    def test_newer_verified_season_inactives_join_exact_ids_without_changing_fantasy(self):
        saved = comparison.PUBLIC_OUTPUT.read_text(encoding='utf-8')
        targets = {}
        for match in re.finditer(r'<tr class="fantasy-row"([^>]*)>(.*?)</tr>', saved, re.S):
            for name in ('Tutu Atwell', 'Jordan James'):
                if re.search(r'class="fantasy-player"[^>]*>'+re.escape(name)+r'(?:<|$)',match[2]):
                    attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', match[1]))
                    targets[name] = attrs
        self.assertEqual(set(targets), {'Tutu Atwell', 'Jordan James'})
        captured = '2026-09-11T00:52:47Z'
        teams = {}
        for name, attrs in targets.items():
            teams.setdefault(attrs['data-team'],dict(final_inactives_status='VERIFIED_LIST',observations=[]))['observations'].append(
                dict(name=name, gsis_id=attrs['data-player-id'], identity_status='RESOLVED', status='INACTIVE',
                     source_kind='official_inactives', source_url='https://www.nfl.com/news/final-inactives',captured_at=captured))
        # A newer unresolved row and the same ID on a different team cannot overwrite the resolved inactive note.
        tutu = teams['LAR']['observations'][0]
        teams['LAR']['observations'].append(dict(tutu,status='QUESTIONABLE',identity_status='UNRESOLVED',captured_at='2026-09-11T00:53:00Z'))
        teams['BUF'] = dict(observations=[dict(tutu,status='OUT',captured_at='2026-09-11T00:53:00Z')])
        self.season_loader.return_value = dict(checked_at='2026-09-11T00:54:00Z', weeks=[],
            availability_context={'2026_01_SF_LA':dict(season=2026,week=1,home='LAR',away='SF',checked_at='2026-09-11T00:53:30Z',teams=teams)})
        page = comparison.add_current_injury_notes(saved, self.source)
        for name, attrs in targets.items():
            row = re.search(r'<tr class="fantasy-row"[^>]*data-player-id="'+attrs['data-player-id']+r'"[^>]*>(.*?)</tr>',page,re.S)[1]
            self.assertIn('Inactive',row)
            self.assertIn('datetime="'+captured+'"',row)
            self.assertIn('https://www.nfl.com/news/final-inactives',row)
            self.assertNotIn('Game designation: OUT',row)
            self.assertNotIn('Game designation: QUESTIONABLE',row)
        self.assertIn('Base injury-note snapshot:',page)
        self.assertNotIn('<strong>Current report:',page)
        self.assertNotIn('Current injury notes appear',page)
        self.assertEqual(comparison.strip_current_injury_notes(page),comparison.strip_current_injury_notes(saved))
        self.assertEqual(comparison.add_current_injury_notes(page,self.source),page)
        self.assertIsNotNone(comparison._extract_published_fantasy_panel(page))
        # A later recapture of an earlier report is not stronger than the final inactive list.
        season = self.season_loader.return_value
        season['checked_at'] = '2026-09-11T00:56:00Z'
        season['weeks'] = [dict(games=[dict(availability=dict(season=2026,week=1,home='LAR',away='SF',
            checked_at='2026-09-11T00:55:00Z',teams={'LAR':dict(observations=[dict(tutu,
                source_kind='official_report',status='QUESTIONABLE',captured_at='2026-09-11T00:55:00Z')])}))])]
        recaptured = comparison.add_current_injury_notes(saved,self.source)
        self.assertIn('Saved report: Inactive',re.search(r'<tr class="fantasy-row"[^>]*data-player-id="'+tutu['gsis_id']+r'"[^>]*>(.*?)</tr>',recaptured,re.S)[1])
        # A different week or opponent cannot supply availability for this saved Week 1 matchup.
        season['availability_context']['2026_01_SF_LA']['week'] = 2
        season['weeks'][0]['games'][0]['availability']['away'] = 'BUF'
        unrelated = comparison.add_current_injury_notes(saved,self.source)
        row = re.search(r'<tr class="fantasy-row"[^>]*data-player-id="'+tutu['gsis_id']+r'"[^>]*>(.*?)</tr>',unrelated,re.S)[1]
        self.assertNotIn('Saved report:',row)

    def test_season_emergency_qb_and_capture_clock_remain_distinct(self):
        player = dict(name='Emergency QB', gsis_id='fixture-qb', identity_status='RESOLVED',
                      status='EMERGENCY_QB', source_kind='official_inactives',
                      source_url='https://www.seahawks.com/news/inactives', captured_at='2026-09-09T22:52:00Z')
        self.season_loader.return_value = dict(checked_at='2026-09-09T22:54:00Z',weeks=[],availability_context={
            'game':dict(season=2026,week=1,home='SEA',away='NE',checked_at='2026-09-09T22:53:00Z',
                        teams={'SEA':dict(final_inactives_status='VERIFIED_LIST',observations=[player])})})
        page = ('<section id="panel-fantasy"><h2>2026 Week 1 Fantasy Rankings</h2>'
                '<tr class="fantasy-row" data-team="SEA" data-player-id="fixture-qb" data-inactive="false">'
                '<td data-sort="1">1</td><th class="fantasy-player">Emergency QB</th>'
                '<td data-sort="QB">QB</td><td data-sort="SEA">SEA</td><td data-sort="NE">NE</td>'
                '<td data-sort="1.25">1.25</td></tr></section>')
        result=comparison.add_current_injury_notes(page,self.source)
        self.assertIn('Emergency third quarterback only (Week 1: NE at SEA)',result)
        self.assertNotIn('Saved report: Inactive',result)
        self.assertEqual(comparison.strip_current_injury_notes(result),page)
        player['captured_at']='2026-09-10T22:52:00Z'
        with self.assertRaisesRegex(ValueError,'later than the injury snapshot'):
            comparison.add_current_injury_notes(page,self.source)

    def test_current_notes_preserve_every_saved_projection_byte_and_are_idempotent(self):
        saved = comparison.PUBLIC_OUTPUT.read_text(encoding='utf-8')
        page = comparison.add_current_injury_notes(saved, self.source)
        self.assertEqual(comparison.strip_current_injury_notes(page),
                         comparison.strip_current_injury_notes(saved))
        self.assertEqual(comparison.add_current_injury_notes(page, self.source), page)
        self.assertIsNotNone(comparison._extract_published_fantasy_panel(page))
        for identifier, status in [('00-0040734', 'Game designation: OUT'),
                                   ('00-0040648', 'Game designation: QUESTIONABLE'),
                                   ('00-0033288', 'no final game designation supplied')]:
            row = re.search(r'<tr class="fantasy-row"[^>]*data-player-id="' + identifier +
                            r'"[^>]*>(.*?)</tr>', page, re.S)[1]
            self.assertIn(status, row)
            self.assertIn('Official report</a>', row)
            self.assertNotIn('Final inactives pending.', row)
        self.assertIn('points and league values have not been recalculated', page)

    def test_official_inactive_news_preserves_emergency_qb_language_and_saved_values(self):
        data = json.loads(self.source.read_bytes())
        data['source_as_of'] = '2026-09-09T22:53:00Z'
        for source in data['team_sources']:
            if source['team'] in ('NE', 'SEA'):
                source.update(source_kind='official_news', captured_at='2026-09-09T22:52:00Z',
                              source_url='https://example.com/final-inactives')
        data['players'] = [p for p in data['players'] if p['team'] not in ('NE', 'SEA')]
        notes = [('NE', '00-0040734', 'TreVeyon Henderson', 'RB', 'Inactive for Week 1'),
                 ('SEA', 'emergency-qb-fixture', 'Emergency QB', 'QB',
                  'Inactive except as emergency third quarterback <not ordinary OUT>')]
        for team, identifier, name, position, text in notes:
            data['players'].append(dict(team=team, gsis_id=identifier, player=name, position=position,
                source_url='https://example.com/final-inactives', availability_text=text))
        saved = comparison.PUBLIC_OUTPUT.read_text(encoding='utf-8')
        extra = ('<tr class="fantasy-row" data-team="SEA" data-player-id="emergency-qb-fixture" '
                 'data-base-points="1.25" data-inactive="false"><th class="fantasy-player">'
                 'Emergency QB</th><td>1.25</td></tr>')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'final-inactives.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            page = comparison.add_current_injury_notes(saved, path)
            self.assertEqual(comparison.strip_current_injury_notes(page),
                             comparison.strip_current_injury_notes(saved))
            self.assertIsNotNone(comparison._extract_published_fantasy_panel(page))
            henderson = re.search(r'<tr class="fantasy-row"[^>]*data-player-id="00-0040734"[^>]*>(.*?)</tr>', page, re.S)[1]
            self.assertIn('Inactive for Week 1', henderson)
            self.assertIn('datetime="2026-09-09T22:52:00Z"', henderson)
            self.assertNotIn('Final inactives pending', page)
            qb_page = '<section id="panel-fantasy">' + extra + '</section>'
            annotated = comparison.add_current_injury_notes(qb_page, path)
            self.assertIn('emergency third quarterback &lt;not ordinary OUT&gt;', annotated)
            self.assertNotIn('Game designation: OUT', annotated)
            self.assertEqual(comparison.strip_current_injury_notes(annotated), qb_page)
            self.assertEqual(comparison.add_current_injury_notes(annotated, path), annotated)
            wrong_team = qb_page.replace('data-team="SEA"', 'data-team="NE"')
            self.assertEqual(comparison.add_current_injury_notes(wrong_team, path), wrong_team)

    def test_identity_requires_same_team_and_unknown_players_are_not_declared_healthy(self):
        row = ('<tr class="fantasy-row" data-team="BUF" data-player-id="00-0040734">'
               '<th scope="row" class="fantasy-player">Different team</th><td>11.4</td></tr>')
        page = '<section id="panel-fantasy">' + row + '</section>'
        self.assertEqual(comparison.add_current_injury_notes(page, self.source), page)

    def test_source_capture_cannot_follow_the_saved_snapshot(self):
        data = json.loads(self.source.read_bytes())
        next(row for row in data['team_sources'] if row['team'] == 'NE')['captured_at'] = '2027-01-01T00:00:00Z'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'invalid.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'later than the injury snapshot'):
                comparison.add_current_injury_notes(comparison.PUBLIC_OUTPUT.read_text(encoding='utf-8'), path)


if __name__ == '__main__':
    unittest.main()
