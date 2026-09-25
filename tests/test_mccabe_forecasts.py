import copy
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pgo_season as season
import spreads


class McCabeForecastTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'season'
        self.root.mkdir()
        self.data = Path(self.temp.name) / 'data'
        self.data.mkdir()
        self.clock = '2026-09-25T12:00:00Z'
        self.edition = 'Week 3 2026'
        self.rows = [dict(team=name, conf='AFC', division='East', qb_name=code + ' QB',
                          qb_value=2 if code == 'SEA' else 1 if code == 'NE' else 0,
                          off_value=0, def_value=0, needs_review='N')
                     for name, code in spreads.ABBR.items()]
        self.write_inputs()
        self.game = dict(game_id='2026_03_NE_SEA', season=2026, week=3, game_type='REG',
                         home='SEA', away='NE', kickoff='2026-09-27T17:00:00Z',
                         lock_at='2026-09-27T16:00:00Z', location='Home', espn_id='123')
        self.state = dict(schema_version=1, season=2026, current_week=3, checked_at=self.clock,
                          status='READY', schedule=[copy.deepcopy(self.game)], results=[],
                          weeks=[dict(week=3, games=[copy.deepcopy(self.game)])],
                          sources=[], source_captures=[], rankings={})

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('mccabe_forecasts'),
                             'Future McCabe capture module is missing')
        import mccabe_forecasts
        return mccabe_forecasts

    def write_csv(self, name, rows):
        with (self.data / name).open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def write_inputs(self, published='2026-09-24T12:00:00Z'):
        self.write_csv('ratings.csv', self.rows)
        self.write_csv('config.csv', [dict(key='season', value=2026),
                                      dict(key='edition', value=self.edition)])
        self.write_csv('hfa.csv', [dict(team='DEFAULT', home_field=1.5),
                                   dict(team='Seattle Seahawks', home_field=2)])
        frozen = [dict(team=r['team'], conf=r['conf'], div=r['division'], qb_name=r['qb_name'],
                       qb=r['qb_value'], off=r['off_value'], **{'def': r['def_value']},
                       rating=round(sum(r[k] for k in ('qb_value', 'off_value', 'def_value')), 1))
                  for r in self.rows]
        (self.data / 'snapshots.json').write_text(json.dumps({self.edition: dict(
            published_at=published, rows=frozen, corrections=[])}), encoding='utf-8')

    def collect(self, state=None, previous=None):
        state = copy.deepcopy(self.state if state is None else state)
        out = self.api().refresh(state, previous, self.root, state['checked_at'], data_dir=self.data)
        return dict(state, mccabe_forecasts=out)

    def save(self, state, durable=None):
        with patch.object(season, 'now', return_value=durable or state['checked_at']):
            return season.save_state(state, self.root)

    def test_capture_replays_exact_inputs_and_roundtrips_without_current_files(self):
        before = copy.deepcopy(self.state)
        state = self.collect()
        payload = state['mccabe_forecasts']
        self.assertEqual(payload['status'], 'READY', payload.get('blocked_reason'))
        row, = payload['games']
        self.assertEqual((row['margin'], row['spread'], row['hfa']), (3, -3, 2))
        self.assertEqual(row['teams']['home']['qb_name'], 'SEA QB')
        self.assertEqual(row['edition'], self.edition)
        self.assertEqual(row['market']['status'], 'UNAVAILABLE')
        files = payload['inputs'][row['input_id']]
        for name, source in files.items():
            self.assertEqual(source['sha256'], season.sha((self.data / name).read_bytes()))
        self.api().validate(state, self.root)
        directory = self.save(state)
        archived = (directory / 'state.json.gz').read_bytes()
        for path in self.data.iterdir():
            path.unlink()
        self.assertEqual(season.load_current(self.root), state)
        self.assertEqual((directory / 'state.json.gz').read_bytes(), archived)
        self.assertEqual(self.state, before)

    def test_repeated_refresh_and_changed_inputs_do_not_replace_first_game(self):
        first = self.collect()
        self.rows[0]['qb_value'] = 9
        self.write_inputs()
        self.state['checked_at'] = '2026-09-25T13:00:00Z'
        again = self.collect(previous=first)
        self.assertEqual(again['mccabe_forecasts']['games'], first['mccabe_forecasts']['games'])
        self.assertEqual(again['mccabe_forecasts']['inputs'], first['mccabe_forecasts']['inputs'])
        self.api().check_durable(again, first, self.state['checked_at'], self.root)

    def test_only_current_edition_week_and_pregame_records_are_eligible(self):
        for change in ('old', 'future_week', 'different_edition', 'cutoff', 'after', 'final'):
            state = copy.deepcopy(self.state)
            if change in ('old', 'future_week'):
                week = 2 if change == 'old' else 4
                state['schedule'][0].update(week=week, game_id=f'2026_0{week}_NE_SEA')
            elif change == 'different_edition':
                state['current_week'] = 4
            elif change in ('cutoff', 'after'):
                state['checked_at'] = '2026-09-27T16:00:00Z' if change == 'cutoff' else '2026-09-27T19:00:00Z'
            else:
                state['results'] = [{'game_id': self.game['game_id']}]
            with self.subTest(change=change):
                out = self.collect(state)['mccabe_forecasts']
                self.assertEqual(out['games'], [])

    def test_legacy_primetime_neutral_and_half_point_convention_is_preserved(self):
        state = copy.deepcopy(self.state)
        state['schedule'][0].update(kickoff='2026-09-28T00:20:00Z',
                                    lock_at='2026-09-27T23:20:00Z', location='Neutral')
        self.rows[0]['off_value'] = 0.1
        self.write_inputs()
        out = self.collect(state)['mccabe_forecasts']
        row, = out['games']
        self.assertEqual((row['hfa'], row['margin'], row['spread']), (2.5, 3.5, -3.5))
        self.assertIn('neutral', row['method'])

    def test_primetime_uses_utc_hour_for_an_equivalent_offset_kickoff(self):
        state = copy.deepcopy(self.state)
        state['schedule'][0].update(kickoff='2026-09-27T20:20:00-04:00',
                                    lock_at='2026-09-27T19:20:00-04:00')
        row, = self.collect(state)['mccabe_forecasts']['games']
        self.assertEqual(row['hfa'], 2.5)

    def test_existing_multigame_market_capture_is_replayed_without_new_fetch(self):
        from tests.test_pgo_ats import ATSTests
        fixture = ATSTests()
        _, provider = fixture.fixture()
        event = provider['events'][0]
        provider['week']['number'] = event['week']['number'] = 3
        event['date'] = event['competitions'][0]['date'] = self.game['kickoff']
        other = copy.deepcopy(event)
        other['id'] = other['competitions'][0]['id'] = '456'
        for side in other['competitions'][0]['competitors']:
            side['team']['abbreviation'] = 'BUF' if side['homeAway'] == 'home' else 'MIA'
        provider['events'].append(other)
        state = copy.deepcopy(self.state)
        state['schedule'].append(dict(self.game, game_id='2026_03_MIA_BUF', home='BUF', away='MIA', espn_id='456'))
        raw = json.dumps(provider).encode(); digest = season.sha(raw)
        source = dict(path=f'source-archive/{digest}.json', bytes=len(raw), sha256=digest,
                      captured_at='2026-09-25T11:55:00Z',
                      url=season.SCOREBOARD.format(season=2026, week=3))
        path = self.root / source['path']; path.parent.mkdir(); path.write_bytes(raw)
        state['source_captures'] = [source]
        out = self.collect(state)
        self.assertEqual(out['mccabe_forecasts']['status'], 'READY', out['mccabe_forecasts']['blocked_reason'])
        row = next(r for r in out['mccabe_forecasts']['games'] if r['home'] == 'SEA')
        self.assertEqual(row['market']['status'], 'AVAILABLE')
        self.assertEqual(row['market']['home_handicap'], -3.5)
        self.assertEqual(row['market']['captured_at'], source['captured_at'])
        self.assertIsNone(row['market']['provider_published_at'])
        self.save(out)
        self.assertEqual(season.load_current(self.root), out)
        path.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'hash|length'):
            season.load_current(self.root)

    def test_invalid_review_numbers_inventory_snapshot_and_clocks_fail_closed(self):
        for change in ('review', 'blank', 'nan', 'missing_team', 'duplicate', 'qb_mismatch',
                       'component_mismatch', 'future_snapshot', 'missing_file', 'bad_hfa'):
            self.write_inputs()
            if change in ('review', 'blank', 'nan', 'missing_team', 'duplicate'):
                rows = copy.deepcopy(self.rows)
                if change == 'review': rows[0]['needs_review'] = 'Y'
                elif change == 'blank': rows[0]['qb_value'] = ''
                elif change == 'nan': rows[0]['qb_value'] = 'nan'
                elif change == 'missing_team': rows.pop()
                else: rows[-1] = copy.deepcopy(rows[0])
                self.write_csv('ratings.csv', rows)
            elif change in ('qb_mismatch', 'component_mismatch', 'future_snapshot'):
                path = self.data / 'snapshots.json'; doc = json.loads(path.read_text())
                entry = doc[self.edition]
                if change == 'qb_mismatch': entry['rows'][0]['qb_name'] = 'Other QB'
                elif change == 'component_mismatch':
                    entry['rows'][0]['qb'] += 1; entry['rows'][0]['off'] -= 1
                else: entry['published_at'] = '2026-09-26T12:00:00Z'
                path.write_text(json.dumps(doc), encoding='utf-8')
            elif change == 'missing_file': (self.data / 'hfa.csv').unlink()
            else: self.write_csv('hfa.csv', [dict(team='DEFAULT', home_field='inf')])
            with self.subTest(change=change):
                out = self.collect()['mccabe_forecasts']
                self.assertEqual(out['status'], 'BLOCKED')
                self.assertEqual(out['games'], [])

    def test_bad_schedule_identity_duplicate_or_naive_clock_does_not_capture(self):
        for change in ('identity', 'duplicate', 'naive', 'lock', 'same_team'):
            state = copy.deepcopy(self.state)
            if change == 'identity': state['schedule'][0]['home'] = 'BUF'
            elif change == 'duplicate': state['schedule'].append(copy.deepcopy(self.game))
            elif change == 'naive': state['schedule'][0]['kickoff'] = '2026-09-27T17:00:00'
            elif change == 'lock': state['schedule'][0]['lock_at'] = '2026-09-27T15:00:00Z'
            else: state['schedule'][0]['away'] = 'SEA'
            with self.subTest(change=change):
                out = self.collect(state)['mccabe_forecasts']
                self.assertEqual(out['status'], 'BLOCKED')
                self.assertEqual(out['games'], [])

    def test_input_failure_retains_previous_games_and_primary_state(self):
        first = self.collect(); before = copy.deepcopy(self.state)
        (self.data / 'ratings.csv').unlink()
        out = self.collect(previous=first)
        self.assertEqual(out['mccabe_forecasts']['games'], first['mccabe_forecasts']['games'])
        self.assertEqual(self.state, before)
        self.assertEqual(out['status'], 'READY')

    def test_durable_crossing_discards_new_capture_and_keeps_primary_and_prior(self):
        initial = copy.deepcopy(self.state)
        self.save(initial)
        self.state['checked_at'] = '2026-09-27T15:59:59Z'
        new = self.collect(previous=initial)
        self.assertEqual(len(new['mccabe_forecasts']['games']), 1)
        self.save(new, '2026-09-27T16:00:00Z')
        loaded = season.load_current(self.root)
        self.assertEqual(loaded['status'], 'READY')
        self.assertEqual(loaded['weeks'], self.state['weeks'])
        self.assertEqual(loaded['mccabe_forecasts']['status'], 'BLOCKED')
        self.assertEqual(loaded['mccabe_forecasts']['games'], [])

    def test_late_new_game_discards_only_new_records_and_preserves_old_evidence(self):
        first = self.collect(); self.save(first)
        state = copy.deepcopy(self.state)
        state['checked_at'] = '2026-09-27T15:59:59Z'
        state['schedule'].append(dict(self.game, game_id='2026_03_MIA_BUF', home='BUF', away='MIA', espn_id='456'))
        new = self.collect(state, first)
        self.assertEqual(len(new['mccabe_forecasts']['games']), 2)
        self.save(new, '2026-09-27T16:00:00Z')
        saved = season.load_current(self.root)
        self.assertEqual(saved['mccabe_forecasts']['games'], first['mccabe_forecasts']['games'])
        self.assertEqual(saved['mccabe_forecasts']['inputs'], first['mccabe_forecasts']['inputs'])

    def test_other_optional_rewrite_rechecks_mccabe_at_its_new_durable_clock(self):
        from types import SimpleNamespace
        first = self.collect(); self.save(first)
        state = copy.deepcopy(self.state)
        state['checked_at'] = '2026-09-27T15:59:58Z'
        state['schedule'].append(dict(self.game, game_id='2026_03_MIA_BUF', home='BUF', away='MIA', espn_id='456'))
        new = self.collect(state, first)
        new['score_range_collection'] = dict(status='READY', observations=[{'game_id': 'new-score'}])
        clocks = []
        def score_guard(saved, previous, durable):
            clocks.append(durable)
            if saved['score_range_collection'].get('observations'):
                raise ValueError('Optional score observation requires fallback')
        times = ['2026-09-27T15:59:59Z', '2026-09-27T16:00:00Z', '2026-09-27T16:00:01Z']
        with patch.dict('sys.modules', {'pgo_score_range_monitor': SimpleNamespace(check_durable_shadow=score_guard)}), \
             patch.object(season, 'now', side_effect=times):
            season.save_state(new, self.root)
        saved = season.load_current(self.root)
        self.assertEqual(clocks, times)
        self.assertEqual(saved['mccabe_forecasts']['games'], first['mccabe_forecasts']['games'])
        self.assertEqual(saved['mccabe_forecasts']['inputs'], first['mccabe_forecasts']['inputs'])
        self.assertEqual(saved['mccabe_forecasts']['status'], 'BLOCKED')
        self.assertEqual(saved['score_range_collection']['status'], 'BLOCKED')
        self.assertEqual(saved['weeks'], first['weeks'])
        self.assertEqual(saved['status'], 'READY')

    def test_new_capture_cannot_claim_an_earlier_issue_time_than_collection(self):
        state = self.collect()
        row = state['mccabe_forecasts']['games'][0]
        row['issued_at'] = '2026-09-25T11:59:59Z'
        with self.assertRaisesRegex(ValueError, 'issue|clock'):
            self.api().check_durable(state, None, self.clock, self.root)

    def test_writer_rejects_new_capture_with_blocked_schedule_or_accepted_final(self):
        for change in ('blocked', 'final'):
            state = self.collect()
            if change == 'blocked':
                state['status'] = 'BLOCKED'
            else:
                state['results'] = [{'game_id': self.game['game_id']}]
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'schedule|final'):
                self.api().check_durable(state, None, self.clock, self.root)

    def test_saved_records_cannot_be_removed_changed_or_replayed_with_tampered_inputs(self):
        first = self.collect(); self.save(first)
        pointer = (self.root / 'current.json').read_bytes()
        for index, change in enumerate(('remove', 'margin', 'input_hash', 'input_bytes', 'market', 'omit')):
            state = copy.deepcopy(first)
            state['checked_at'] = f'2026-09-25T13:00:0{index}Z'
            payload = state['mccabe_forecasts']; row = payload['games'][0]
            if change == 'remove': payload['games'] = []
            elif change == 'margin': row['margin'] += 1
            elif change == 'input_hash': payload['inputs'][row['input_id']]['ratings.csv']['sha256'] = '0' * 64
            elif change == 'input_bytes': payload['inputs'][row['input_id']]['ratings.csv']['text'] += '\n'
            elif change == 'market': row['market'] = {'status': 'AVAILABLE', 'home_handicap': -3}
            else: state.pop('mccabe_forecasts')
            with self.subTest(change=change), self.assertRaises((ValueError, KeyError)):
                self.save(state)
            self.assertEqual((self.root / 'current.json').read_bytes(), pointer)

    def test_read_validation_rejects_rehashed_but_unreplayable_record(self):
        state = self.collect(); directory = self.save(state)
        state['mccabe_forecasts']['games'][0]['spread'] = 99
        import gzip
        raw = gzip.compress(season.canonical(state), mtime=0)
        (directory / 'state.json.gz').write_bytes(raw)
        manifest = json.loads((directory / 'manifest.json').read_bytes())
        manifest['files']['state.json.gz'] = dict(sha256=season.sha(raw), bytes=len(raw))
        raw = season.canonical(manifest); (directory / 'manifest.json').write_bytes(raw)
        pointer = json.loads((self.root / 'current.json').read_bytes())
        pointer['manifest_sha256'] = season.sha(raw)
        (self.root / 'current.json').write_bytes(season.canonical(pointer))
        with self.assertRaisesRegex(ValueError, 'replay|arithmetic'):
            season.load_current(self.root)

    def test_optional_collector_is_integrated_and_failure_is_isolated(self):
        api = self.api()
        before = copy.deepcopy(self.state)
        with patch.object(api, 'refresh', side_effect=RuntimeError('McCabe unavailable')) as collector:
            season.refresh_experiments(self.state, None, self.root)
        self.assertEqual(collector.call_count, 1)
        self.assertEqual(self.state['weeks'], before['weeks'])
        self.assertEqual(self.state['status'], 'READY')
        self.assertEqual(self.state['mccabe_forecasts']['status'], 'BLOCKED')


if __name__ == '__main__':
    unittest.main()
