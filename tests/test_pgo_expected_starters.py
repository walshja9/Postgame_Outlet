import base64
import copy
import importlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pgo_season import canonical, sha
from pgo_sources import CURRENT_TEAMS


class ExpectedStarterTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('pgo_expected_starters'),
                             'The source-bound expected-starter module must exist')
        self.api = importlib.import_module('pgo_expected_starters')
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.config = self.root/'announcements.json'
        changed = patch.object(self.api, 'CONFIG', self.config); changed.start(); self.addCleanup(changed.stop)
        self.checked = '2026-09-12T18:00:00+00:00'
        self.game = dict(game_id='2026_01_PIT_ATL', season=2026, week=1, game_type='REG',
                         home='ATL', away='PIT', kickoff='2026-09-13T17:00:00+00:00',
                         lock_at='2026-09-13T16:00:00+00:00')
        self.selected = {team: dict(team=team, gsis_id=f'00-{1000000+i}', full_name=team+' Quarterback',
                                   status='ACT', position='QB', season='2026')
                         for i, team in enumerate(sorted(CURRENT_TEAMS))}
        self.player = dict(team='ATL', gsis_id='00-0033930', full_name='Cooper Rush',
                           status='ACT', position='QB', season='2026')
        self.roster = [*copy.deepcopy(list(self.selected.values())), self.player]
        self.statement = 'Cooper Rush will make the start at quarterback.'
        self.article = {'@type':'NewsArticle', 'headline':'Falcons quarterback update before Steelers game',
                        'articleBody':self.statement+' The Falcons face the Pittsburgh Steelers on Sunday.',
                        'datePublished':'2026-09-11T18:12:22.097Z', 'dateModified':'2026-09-11T18:30:49.99Z'}
        url = 'https://www.atlantafalcons.com/news/quarterback-update'
        self.envelope = dict(schema_version=1, kind='official_starter_announcement', url=url, final_url=url,
                             status=200, started_at='2026-09-12T17:00:00+00:00', captured_at='2026-09-12T17:01:00+00:00',
                             reviewed_at='2026-09-12T17:30:00+00:00', published_at=self.article['datePublished'],
                             modified_at=self.article['dateModified'], decision=dict(
                                 game={k:self.game[k] for k in ('game_id','season','week','game_type','home','away','kickoff')},
                                 team='ATL', gsis_id=self.player['gsis_id'], full_name='Cooper Rush', statement=self.statement))
        self.body(self.envelope, self.article)

    def body(self, envelope, article, suffix=''):
        raw = ('<script type="application/ld+json">'+json.dumps(article)+'</script><article>'+suffix).encode()
        envelope.update(body_base64=base64.b64encode(raw).decode(), raw_sha256=sha(raw), raw_bytes=len(raw))

    def save(self, envelope=None):
        envelope = envelope or self.envelope; raw = canonical(envelope)
        relative = 'source-archive/'+sha(raw)+'.json'; path = self.root/relative
        path.parent.mkdir(exist_ok=True); path.write_bytes(raw)
        ref = dict(path=relative, url=envelope['url'], captured_at=envelope['captured_at'], sha256=sha(raw), bytes=len(raw))
        self.config.write_bytes(canonical(dict(schema_version=1, announcements=[dict(game_id=self.game['game_id'], source=ref)])))
        return ref

    def apply(self, checked=None):
        return self.api.apply(self.selected, self.roster, [self.game], self.root, checked or self.checked)

    def test_source_bound_override_is_copied_and_replays_without_current_config(self):
        ref = self.save(); before = copy.deepcopy((self.selected, self.roster, self.game))
        self.assertTrue(callable(getattr(self.api, 'select_player', None)), 'The roster selection guard must be reusable')
        player = self.api.select_player(self.roster, self.envelope['decision'], self.game)
        self.assertEqual(player, self.player); self.assertIsNot(player, self.player)
        chosen, annotations = self.apply()
        self.assertEqual(chosen['ATL'], self.player)
        self.assertEqual(annotations, {self.game['game_id']:[dict(team='ATL', gsis_id=self.player['gsis_id'],
                                                               full_name='Cooper Rush', source=ref)]})
        self.assertEqual((self.selected, self.roster, self.game), before)
        self.assertIsNot(chosen['ATL'], self.player)
        self.config.write_text('not valid JSON')
        game = dict(self.game, issued_at=self.checked, expected_qbs={'ATL':'Cooper Rush', 'PIT':'PIT Quarterback'},
                    availability={'teams':{'ATL':{'expected_qb_gsis_id':self.player['gsis_id']}}})
        self.api.verify(game, annotations[self.game['game_id']], self.root)

    def test_absent_or_other_game_config_does_not_require_a_full_selection(self):
        selected = {'ATL':{'gsis_id':'legacy-fixture'}}
        chosen, notes = self.api.apply(selected, [], [self.game], self.root, self.checked)
        self.assertEqual((chosen, notes), (selected, {})); self.assertIsNot(chosen['ATL'], selected['ATL'])
        self.config.write_bytes(canonical(dict(schema_version=1, announcements=[dict(game_id='2026_02_ATL_PIT', source={'invalid':True})])))
        self.assertEqual(self.api.apply(selected, [], [self.game], self.root, self.checked), (selected, {}))
        self.api.verify({}, [], self.root)

    def test_tampered_archive_body_and_reference_are_rejected(self):
        ref = self.save(); path = self.root/ref['path']; original = path.read_bytes(); path.write_bytes(original+b' ')
        with self.assertRaises(ValueError): self.apply()
        for change in (lambda e:e.update(body_base64='not valid base64!'),
                       lambda e:e.update(raw_sha256='0'*64), lambda e:e.update(raw_bytes=e['raw_bytes']+1),
                       lambda e:e.update(status=404), lambda e:e.update(schema_version=True)):
            value = copy.deepcopy(self.envelope); change(value); self.save(value)
            with self.subTest(change=change), self.assertRaises(ValueError): self.apply()
        ref = self.save(); ref['captured_at'] = '2026-09-12T17:00:00+00:00'
        self.config.write_bytes(canonical(dict(schema_version=1, announcements=[dict(game_id=self.game['game_id'], source=ref)])))
        with self.assertRaises(ValueError): self.apply()

    def test_primary_article_statement_and_official_url_are_bound(self):
        for change in (lambda e:e.update(url='https://example.com/news/update', final_url='https://example.com/news/update'),
                       lambda e:e.update(final_url='https://www.atlantafalcons.com/news/different'),
                       lambda e:e['decision'].update(statement='Cooper Rush was not named in this article.'),
                       lambda e:e['decision'].update(statement='will make the start at quarterback.'),
                       lambda e:e.update(published_at='2026-09-11T18:00:00Z')):
            value = copy.deepcopy(self.envelope); change(value); self.save(value)
            with self.subTest(change=change), self.assertRaises(ValueError): self.apply()
        for article in (dict(self.article, headline='Other game', articleBody=self.statement+' Patriots vs. Seahawks.'),
                        [self.article, self.article], dict(self.article, articleBody='Cooper Rush remains on the roster.')):
            value = copy.deepcopy(self.envelope); self.body(value, article); self.save(value)
            with self.subTest(article=article), self.assertRaises(ValueError): self.apply()
        value = copy.deepcopy(self.envelope)
        self.body(value, self.article, '<script type="application/ld+json">'+json.dumps(self.article)+'</script>')
        self.save(value); self.assertEqual(self.apply()[0]['ATL'], self.player)

    def test_wrong_game_team_and_duplicate_announcements_fail(self):
        for change in (lambda e:e['decision'].update(team='NE'),
                       lambda e:e['decision']['game'].update(week=2),
                       lambda e:e['decision']['game'].update(week=True),
                       lambda e:e['decision']['game'].update(season=2025),
                       lambda e:e['decision']['game'].update(home='NE'),
                       lambda e:e['decision']['game'].update(game_id='2026_02_PIT_ATL')):
            value = copy.deepcopy(self.envelope); change(value); self.save(value)
            with self.subTest(change=change), self.assertRaises(ValueError): self.apply()
        self.save(); config = json.loads(self.config.read_bytes()); config['announcements'] *= 2
        self.config.write_bytes(canonical(config))
        with self.assertRaises(ValueError): self.apply()

    def test_future_expired_and_at_lock_evidence_fails(self):
        for change in (lambda e:e.update(reviewed_at='2026-09-12T18:01:00+00:00'),
                       lambda e:e.update(started_at='2026-09-12T17:02:00+00:00'),
                       lambda e:e.update(reviewed_at='2026-09-12T17:00:00+00:00')):
            value = copy.deepcopy(self.envelope); change(value); self.save(value)
            with self.subTest(change=change), self.assertRaises(ValueError): self.apply()
        value = copy.deepcopy(self.envelope); article = dict(self.article, datePublished='2026-09-05T17:00:00Z')
        value['published_at'] = article['datePublished']; self.body(value, article); self.save(value)
        with self.assertRaises(ValueError): self.apply()
        self.save()
        with self.assertRaises(ValueError): self.apply(self.game['lock_at'])

    def test_roster_eligibility_and_complete_unique_selection_are_required(self):
        self.save(); original = copy.deepcopy(self.player)
        for field, value in (('status','RES'), ('position','WR'), ('season','2025'), ('team','NE'),
                             ('full_name','Different Player'), ('gsis_id','00-9999999')):
            self.player[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): self.apply()
            self.player.clear(); self.player.update(original)
        self.roster.append(copy.deepcopy(self.player))
        with self.assertRaises(ValueError): self.apply()
        self.roster.pop(); saved = self.selected.pop('NE')
        with self.assertRaises(ValueError): self.apply()
        self.selected['NE'] = saved
        self.selected['NE']['gsis_id'] = self.selected['PIT']['gsis_id']
        with self.assertRaises(ValueError): self.apply()

    def test_verify_binds_saved_selection_identity_and_issue_clock(self):
        self.save(); _, notes = self.apply(); annotations = notes[self.game['game_id']]
        original = dict(self.game, issued_at=self.checked, expected_qbs={'ATL':'Cooper Rush'})
        for change in (lambda g:g['expected_qbs'].update(ATL='Other Quarterback'),
                       lambda g:g.update(issued_at='2026-09-12T17:00:00+00:00'),
                       lambda g:g.update(availability={'teams':{'ATL':{'expected_qb_gsis_id':'00-9999999'}}}),
                       lambda g:g.update(week=2)):
            game = copy.deepcopy(original); change(game)
            with self.subTest(change=change), self.assertRaises(ValueError): self.api.verify(game, annotations, self.root)
        with self.assertRaises(ValueError): self.api.verify(original, annotations*2, self.root)
        changed = copy.deepcopy(annotations); changed[0]['gsis_id'] = '00-9999999'
        with self.assertRaises(ValueError): self.api.verify(original, changed, self.root)

    def test_explicit_malformed_empty_annotations_are_rejected(self):
        for value in (None, {}, 0, '', False, ()):
            with self.subTest(value=value), self.assertRaises(ValueError): self.api.verify({}, value, self.root)
        self.api.verify({}, [], self.root)

    def test_review_must_precede_declared_inputs_and_inputs_precede_issue(self):
        self.save(); _, notes = self.apply(); annotations = notes[self.game['game_id']]
        game = dict(self.game, issued_at=self.checked, expected_qbs={'ATL':'Cooper Rush'})
        for clock in ('2026-09-12T17:29:00+00:00', '2026-09-12T18:01:00+00:00'):
            with self.subTest(inputs_as_of=clock), self.assertRaises(ValueError):
                self.api.verify(dict(game, inputs_as_of=clock), annotations, self.root)
        self.api.verify(dict(game, inputs_as_of=self.envelope['reviewed_at']), annotations, self.root)

    def test_explicit_article_week_must_match_the_game(self):
        for article in (dict(self.article, headline='Week 2: Falcons vs. Steelers'),
                        dict(self.article, articleBody=self.article['articleBody']+' This is Week 2.')):
            value = copy.deepcopy(self.envelope); self.body(value, article); self.save(value)
            with self.subTest(article=article), self.assertRaises(ValueError): self.apply()


if __name__ == '__main__':
    unittest.main()
