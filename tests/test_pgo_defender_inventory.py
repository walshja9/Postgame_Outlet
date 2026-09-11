import copy
import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tests import test_pgo_injury_usage


class DefenderInventoryTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('research.pgo_defender_inventory_20260911.inventory'),
                             'The versioned defender inventory reader is missing')
        from research.pgo_defender_inventory_20260911 import inventory
        return inventory

    def fixture(self):
        helper = test_pgo_injury_usage.InjuryUsageTests(); helper.setUp()
        snapshot = helper.snapshot; snapshot['inventory_version'] = 1
        player = snapshot['teams'][0]['unavailable_players'][0]
        player['confirmed_unavailable'] = True
        backup = dict(player, gsis_id='00-0030001', name='Test Backup', confirmed_unavailable=False, roster_status='ACT',
                      depth_rows=[dict(position='LB', rank=2)])
        snapshot['teams'][0].update(inventory_version=1, defenders=[player, backup])
        snapshot['teams'].append(dict(team='LAR', inventory_version=1, defenders=[], unavailable_players=[], depth_snapshot_at=snapshot['teams'][0]['depth_snapshot_at']))
        helper.roster.append(dict(helper.roster[0], gsis_id=backup['gsis_id'], pfr_id='BackTe00'))
        helper.final.update(home_score=20, away_score=21, actual_margin=-1)
        return helper

    def test_inventory_links_backups_zero_and_missing_without_mutation(self):
        api = self.api(); helper = self.fixture(); before = copy.deepcopy(helper.snapshot)
        rows = [helper.snap, dict(helper.snap, pfr_player_id='BackTe00', defense_snaps='12')]
        out = api.link(helper.snapshot, helper.roster, rows, [helper.final], helper.clock)
        self.assertEqual(out['joined'], 2)
        self.assertEqual(out['observed_zero'], 1)
        self.assertEqual(out['observed_positive'], 1)
        self.assertEqual(out['rows'][1]['defensive_snaps'], 12)
        self.assertFalse(out['rows'][1]['confirmed_unavailable'])
        self.assertIsNone(out['rows'][1]['prior_role_share'])
        self.assertIsNone(out['forecast_adjustment'])
        missing = api.link(helper.snapshot, helper.roster, [helper.snap], [helper.final], helper.clock)
        self.assertEqual(missing['missing_target'], 1)
        self.assertEqual(missing['observed_zero'], 1)
        self.assertEqual(helper.snapshot, before)

    def test_old_or_incomplete_inventory_is_unavailable_not_reconstructed(self):
        api = self.api()
        for level in ('snapshot', 'team'):
            helper = self.fixture()
            (helper.snapshot if level == 'snapshot' else helper.snapshot['teams'][0]).pop('inventory_version')
            out = api.link(helper.snapshot, helper.roster, [helper.snap], [helper.final], helper.clock)
            self.assertEqual(out['joined'], 0)
            self.assertEqual(out['cohort_rows'], 0)
            self.assertEqual(out['unavailable_inventory_games'][0]['reason'], 'MISSING_PREGAME_INVENTORY')

    def test_duplicate_player_or_inconsistent_unavailable_subset_rejected(self):
        api = self.api()
        for mutation in ('duplicate', 'subset'):
            helper = self.fixture(); team = helper.snapshot['teams'][0]
            if mutation == 'duplicate': team['defenders'].append(copy.deepcopy(team['defenders'][0]))
            else: team['unavailable_players'] = []
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                api.link(helper.snapshot, helper.roster, [helper.snap], [helper.final], helper.clock)

    def test_pending_late_duplicate_target_and_wrong_final_never_admit(self):
        api = self.api(); helper = self.fixture()
        out = api.link(helper.snapshot, helper.roster, [helper.snap], [], helper.clock)
        self.assertEqual(out['pending'], 2)
        self.assertEqual(out['joined'], 0)
        duplicate = api.link(helper.snapshot, helper.roster, [helper.snap, dict(helper.snap, defense_snaps='NaN')], [helper.final], helper.clock)
        self.assertEqual(duplicate['joined'], 0)
        helper.snapshot['completed_at'] = helper.game['lock_at']
        late = api.link(helper.snapshot, helper.roster, [helper.snap], [helper.final], helper.clock)
        self.assertEqual(late['joined'], 0)
        self.assertEqual(late['exclusions']['LATE_PREGAME_CAPTURE'], 2)
        helper = self.fixture(); helper.final['finalized_at'] = helper.game['kickoff']
        with self.assertRaises(ValueError):
            api.link(helper.snapshot, helper.roster, [helper.snap], [helper.final], helper.clock)

    def test_archived_old_inventory_is_not_rebuilt_and_state_hash_is_required(self):
        api = self.api(); helper = self.fixture(); helper.snapshot.pop('inventory_version')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); archive = 'runs-v2/20260910T200001000000Z'; directory = root / archive
            directory.mkdir(parents=True)
            raw = json.dumps(dict(schema_version=1, season=2026, checked_at=helper.snapshot['generated_at'],
                                  replacement_depth=helper.snapshot)).encode()
            (directory / 'state.json').write_bytes(raw)
            manifest = json.dumps(dict(created_at=helper.snapshot['completed_at'],
                 files={'state.json': dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))})).encode()
            (directory / 'manifest.json').write_bytes(manifest)
            pointer = dict(path=archive, manifest_sha256=hashlib.sha256(manifest).hexdigest())
            snapshot, roster = api.load_inventory(root, pointer)
            self.assertNotIn('inventory_version', snapshot)
            self.assertEqual(roster, [])
            (directory / 'state.json').write_bytes(raw + b' ')
            with self.assertRaises(ValueError): api.load_inventory(root, pointer)

    def test_target_bytes_clock_http_status_and_schema_are_checked(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            raw = b'game_id,season,week,game_type,team,opponent,pfr_player_id,defense_snaps\n'
            receipt = dict(url=api.audit.URL, started_at='2026-09-11T00:00:00Z', captured_at='2026-09-11T00:00:01Z',
                           http_status=200, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
            (source / 'response.bin').write_bytes(raw)
            (source / 'receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
            self.assertEqual(api.load_target(source)[0], [])
            for change in ({'sha256': '0'*64}, {'captured_at': '2026-09-10T23:59:59Z'}, {'http_status': True},
                           {'published_at': '2026-09-11T00:01:00Z'}):
                (source / 'receipt.json').write_text(json.dumps(dict(receipt, **change)), encoding='utf-8')
                with self.subTest(change=change), self.assertRaises(ValueError): api.load_target(source)
            (source / 'receipt.json').write_text(json.dumps(dict(receipt, http_status=404)), encoding='utf-8')
            self.assertEqual(api.load_target(source)[0], [])


if __name__ == '__main__':
    unittest.main()
