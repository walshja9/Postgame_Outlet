import copy
import csv
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pgo_offensive_inventory as inventory
import pgo_injury_usage_monitor as shared
from pgo_season import canonical, sha
from tests.test_pgo_offensive_inventory import GAME, NOW, archive, fixture_rows, sources

CHECK = '2026-09-11T12:00:00+00:00'


class OffensiveUsageTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('pgo_offensive_usage_monitor'), 'Offensive usage API is missing')
        import pgo_offensive_usage_monitor as api
        self.api = api
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        self.roster, self.depth = fixture_rows()
        self.first = self.save(NOW, '2026-09-10T20:00:01Z')
        self.final = dict(GAME, home_team='LAR', away_team='SF', home_score=20, away_score=21,
                          actual_margin=-1, finalized_at='2026-09-11T03:30:00Z')
        self.state = dict(schema_version=1, season=2026, checked_at=CHECK, results=[self.final],
                          schedule=[GAME], weeks=[dict(games=[GAME])], replacement_depth={'preserve': 'defense'},
                          injury_usage={'preserve': 'defensive study'})
        player = next(row for row in self.roster if row['team'] == 'SF')
        self.row = dict(game_id=GAME['game_id'], season='2026', week='1', game_type='REG', team='SF', opponent='LA',
                        pfr_player_id=player['pfr_id'], offense_snaps='0')
        verification = patch.object(api, 'verify_finals'); verification.start(); self.addCleanup(verification.stop)

    def save(self, generated, durable, malformed=False, inventory_present=True):
        state = dict(schema_version=1, season=2026, checked_at=generated,
                      source_captures=sources(self.root, self.roster, self.depth), weeks=[dict(games=[GAME])])
        if inventory_present:
            state['offensive_inventory'] = inventory.capture(state, self.root, generated)
            if malformed == 'missing_version': state['offensive_inventory'].pop('inventory_version')
            elif malformed == 'missing_games': state['offensive_inventory'].pop('games')
            elif malformed == 'top_level': state['offensive_inventory'] = None
            elif malformed: state['offensive_inventory']['teams'][0]['players'] = [dict(gsis_id='bad')]
        return archive(self.root, state, durable)

    def response(self, rows=None):
        stream = io.StringIO(); writer = csv.DictWriter(stream, fieldnames=list(self.row))
        writer.writeheader(); writer.writerows([self.row] if rows is None else rows)
        response = MagicMock(); response.__enter__.return_value = response
        response.status = 200; response.headers = {}; response.read.return_value = stream.getvalue().encode()
        return response

    def refresh(self, old=None, checked=CHECK, rows=None):
        before = copy.deepcopy(self.state)
        with patch.object(shared, 'urlopen', return_value=self.response(rows)) as fetch, patch.object(shared, 'now', return_value=checked):
            result = self.api.refresh_shadow(self.state, {'offensive_usage': old} if old else {}, self.root, checked)
        self.assertEqual(self.state, before)
        return result, fetch

    def test_latest_durable_pre_t60_offensive_cohort_and_zero_vs_missing(self):
        selected = self.save('2026-09-10T21:00:00Z', '2026-09-10T21:00:01Z')
        self.save('2026-09-10T23:34:59Z', GAME['lock_at'])
        result, fetch = self.refresh()
        self.assertEqual(result['status'], 'READY'); fetch.assert_called_once()
        self.assertEqual(result['selected_games'], {GAME['game_id']: selected})
        self.assertEqual(result['metrics']['cohort_rows'], 2); self.assertEqual(result['metrics']['observed_zero'], 1)
        self.assertEqual(result['metrics']['missing_target'], 1); self.assertEqual(result['predictive_status'], 'UNAVAILABLE')
        report = json.loads((self.root/result['report']['path']).read_bytes())
        self.assertTrue(all('offensive_snaps' in row and 'defensive_snaps' not in row for row in report['rows']))

    def test_invalid_latest_freezes_and_blocks_without_fallback(self):
        selected = self.save('2026-09-10T22:00:00Z', '2026-09-10T22:00:01Z', malformed=True)
        result, fetch = self.refresh(); self.assertEqual(result['status'], 'BLOCKED'); fetch.assert_not_called()
        self.assertEqual(result['selected_games'], {GAME['game_id']: selected})
        again, _ = self.refresh(result); self.assertEqual(again['selected_games'], result['selected_games'])

    def test_missing_version_games_or_top_level_cannot_fallback_to_older_inventory(self):
        for minute, malformed in enumerate(('missing_version', 'missing_games', 'top_level')):
            selected = self.save(f'2026-09-10T22:0{minute}:00Z', f'2026-09-10T22:0{minute}:01Z', malformed=malformed)
            with self.subTest(malformed=malformed):
                result, fetch = self.refresh()
                self.assertEqual(result['selected_games'], {GAME['game_id']: selected})
                self.assertEqual(result['status'], 'BLOCKED'); fetch.assert_not_called()

    def test_selected_cohort_and_report_stay_fixed_and_share_target_receipt(self):
        first, _ = self.refresh()
        self.save('2026-09-10T22:00:00Z', '2026-09-10T22:00:01Z')
        self.state['injury_usage'] = dict(source=first['source'], last_attempt=first['last_attempt'])
        again, fetch = self.refresh(first, '2026-09-11T13:00:00Z')
        fetch.assert_not_called(); self.assertEqual(first['selected_games'], again['selected_games'])
        self.assertEqual(first['report'], again['report'])
        fresh, fetch = self.refresh(None, '2026-09-11T13:00:00Z')
        fetch.assert_not_called(); self.assertEqual(fresh['source'], first['source'])

    def test_missing_inventory_is_permanent_exclusion_and_pending_does_not_fetch(self):
        self.state['results'] = []
        result, fetch = self.refresh(); fetch.assert_not_called(); self.assertEqual(result['pending_games'], 1)
        self.state['results'] = [dict(self.final, game_id='2026_01_NE_SEA')]
        first, fetch = self.refresh(); fetch.assert_not_called()
        self.assertEqual(first['excluded_games'], [dict(game_id='2026_01_NE_SEA', reason='MISSING_PREGAME_INVENTORY')])
        again, fetch = self.refresh(first); fetch.assert_not_called(); self.assertEqual(again['excluded_games'], first['excluded_games'])

    def test_duplicate_malformed_missing_and_wrong_team_targets_are_unknown(self):
        for changed in (dict(offense_snaps='NaN'), dict(offense_snaps=''), dict(offense_snaps='-1')):
            result, _ = self.refresh(rows=[self.row, dict(self.row, **changed)])
            self.assertEqual(result['metrics']['joined'], 0); self.assertEqual(result['metrics']['observed_zero'], 0)
            self.assertEqual(result['metrics']['exclusions']['DUPLICATE_TARGET_IDENTITY'], 1)
        for changed in (dict(opponent='SEA'), dict(team='LAR'), dict(pfr_player_id='unknown'), dict(week='2')):
            result, _ = self.refresh(rows=[dict(self.row, **changed)])
            self.assertEqual(result['metrics']['joined'], 0)

    def test_target_at_final_is_pending_until_actual_later_capture(self):
        result, _ = self.refresh(checked=self.final['finalized_at'])
        self.assertEqual(result['metrics']['joined'], 0)
        self.assertEqual(result['metrics']['exclusions']['TARGET_BEFORE_FINAL_OBSERVATION'], 2)
        again, fetch = self.refresh(result)
        fetch.assert_called_once(); self.assertEqual(again['metrics']['joined'], 1)

    def test_preserved_report_source_and_archive_tampering_block(self):
        first, _ = self.refresh()
        for path in (self.root/first['source']['path'], self.root/first['report']['path'], self.root/self.first['path']/'state.json'):
            raw = path.read_bytes(); path.write_bytes(raw+b' ')
            try:
                result, fetch = self.refresh(first); self.assertEqual(result['status'], 'BLOCKED'); fetch.assert_not_called()
            finally: path.write_bytes(raw)

    def test_source_failure_is_retained_throttled_and_optional(self):
        from urllib.error import URLError
        with patch.object(shared, 'urlopen', side_effect=URLError('private')), patch.object(shared, 'now', return_value=CHECK):
            result = self.api.refresh_shadow(self.state, {}, self.root, CHECK)
        self.assertEqual(result['status'], 'BLOCKED'); self.assertNotIn('private', json.dumps(result))
        self.assertTrue((self.root/result['last_attempt']['path']).is_file())
        again, fetch = self.refresh(result, '2026-09-11T13:00:00Z')
        fetch.assert_not_called(); self.assertEqual(again['status'], 'BLOCKED')

    def test_pfr_name_conflict_and_extra_csv_fields_do_not_admit(self):
        self.row['player'] = 'A Different Person'
        result, _ = self.refresh()
        self.assertEqual(result['metrics']['joined'], 0)
        self.assertEqual(result['metrics']['invalid_target_rows'], 1)
        self.row.pop('player')
        response = self.response(); response.read.return_value += b'2026_01_SF_LA,2026,1,REG,SF,LA,Test0028,0,extra\n'
        with patch.object(shared, 'urlopen', return_value=response), patch.object(shared, 'now', return_value=CHECK):
            result = self.api.refresh_shadow(self.state, {}, self.root, CHECK)
        self.assertEqual(result['status'], 'BLOCKED')

    def test_delayed_final_requires_new_target_capture(self):
        first, _ = self.refresh()
        self.final['finalized_at'] = '2026-09-11T12:30:00Z'
        result, fetch = self.refresh(first, '2026-09-11T13:00:00Z')
        fetch.assert_called_once(); self.assertEqual(result['metrics']['joined'], 1)

    def test_selected_reader_tamper_never_uses_later_roster(self):
        first, _ = self.refresh()
        self.roster[0]['full_name'] = 'Later Roster'
        self.save('2026-09-10T22:00:00Z', '2026-09-10T22:00:01Z')
        first_state = json.loads((self.root/self.first['path']/'state.json').read_bytes())
        path = self.root/first_state['source_captures'][0]['path']
        path.write_bytes(path.read_bytes()+b' ')
        result, fetch = self.refresh(first)
        fetch.assert_not_called(); self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(result['selected_games'], first['selected_games'])


if __name__ == '__main__':
    unittest.main()
