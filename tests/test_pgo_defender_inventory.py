import copy
import csv
import importlib.util
import hashlib
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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

    def test_v2_ina_context_links_observed_usage_without_becoming_unavailable(self):
        api = self.api(); helper = self.fixture(); helper.snapshot['inventory_version'] = 2
        for team in helper.snapshot['teams']: team['inventory_version'] = 2
        player = helper.snapshot['teams'][0]['defenders'][1]
        player.update(roster_status='INA', roster_context=dict(season='2026', week='1', game_type='REG'))
        before = copy.deepcopy(helper.snapshot)
        out = api.link(helper.snapshot, helper.roster, [helper.snap, dict(helper.snap, pfr_player_id='BackTe00', defense_snaps='0')], [helper.final], helper.clock)
        self.assertEqual(out['inventory_version'], 2); self.assertEqual(out['joined'], 2)
        self.assertEqual(out['observed_zero'], 2)
        self.assertFalse(out['rows'][1]['confirmed_unavailable'])
        self.assertEqual(out['rows'][1]['roster_context'], player['roster_context'])
        self.assertEqual(helper.snapshot, before)

    def test_unknown_inventory_versions_are_rejected_at_reader_boundaries(self):
        api = self.api()
        for version in (None, 0, 3, True, 1.0, '1'):
            for location in ('snapshot', 'team'):
                helper = self.fixture()
                target = helper.snapshot if location == 'snapshot' else helper.snapshot['teams'][0]
                target['inventory_version'] = version
                with self.subTest(version=version, location=location), self.assertRaises(ValueError):
                    api.link(helper.snapshot, helper.roster, [helper.snap], [helper.final], helper.clock)
            state = dict(schema_version=1, season=2026, checked_at=helper.snapshot['generated_at'],
                         replacement_depth=dict(helper.snapshot, inventory_version=version))
            with patch.object(api, 'load_archive', return_value=(state, dict(created_at=helper.snapshot['completed_at']))):
                with self.subTest(load_version=version), self.assertRaises(ValueError):
                    api.load_inventory(Path('unused'), {})
            with self.subTest(capture_version=version), self.assertRaises(ValueError):
                api.capture.capture({}, Path('unused'), helper.clock, inventory_version=version)
        helper = self.fixture(); helper.snapshot['teams'][0]['inventory_version'] = 2
        with self.assertRaises(ValueError):
            api.link(helper.snapshot, helper.roster, [helper.snap], [helper.final], helper.clock)

    def test_saved_v1_and_v2_inventory_replay_their_own_roster_scope(self):
        api = self.api()
        from tests.test_pgo_replacement_depth import NOW, roster, slot
        rr = [roster('00-0000001', 'Active One'), dict(roster('00-0000002', 'Inactive Two', 'INA'), game_type='REG')]
        rr[0]['game_type'] = 'REG'
        dd = [slot(row['gsis_id'], row['full_name'], i+1) for i, row in enumerate(rr)]
        with tempfile.TemporaryDirectory() as tmp, patch.object(api.capture, '_history', return_value=({}, None)):
            root = Path(tmp); (root/'source-archive').mkdir(); refs = []
            for url, rows in ((api.capture.ROSTER_URL, rr), (api.capture.DEPTH_URL, dd)):
                text = io.StringIO(); writer = csv.DictWriter(text, fieldnames=list(rows[0]))
                writer.writeheader(); writer.writerows(rows); raw = gzip.compress(text.getvalue().encode(), mtime=0)
                digest = hashlib.sha256(raw).hexdigest(); relative = 'source-archive/' + digest + '.csv.gz'
                (root/relative).write_bytes(raw)
                refs.append(dict(url=url, path=relative, captured_at=NOW, sha256=digest, bytes=len(raw)))
            for version in (1, 2):
                state = dict(schema_version=1, season=2026, checked_at=NOW, source_captures=refs, weeks=[])
                snapshot = api.capture.capture(state, root, NOW, inventory_version=version)
                self.assertEqual(snapshot['inventory_version'], version)
                state['replacement_depth'] = snapshot
                archive = f'runs-v2/20260910T20000{version}000000Z'; directory = root/archive; directory.mkdir(parents=True)
                raw = json.dumps(state).encode(); (directory/'state.json').write_bytes(raw)
                manifest = json.dumps(dict(created_at=f'2026-09-10T20:00:0{version}+00:00',
                    files={'state.json': dict(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))})).encode()
                (directory/'manifest.json').write_bytes(manifest)
                loaded, raw_roster = api.load_inventory(root, dict(path=archive, manifest_sha256=hashlib.sha256(manifest).hexdigest()))
                self.assertEqual(loaded['teams'], snapshot['teams']); self.assertEqual(raw_roster, rr)
                ne = next(team for team in loaded['teams'] if team['team'] == 'NE')
                self.assertEqual(len(ne['defenders']), version)

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

    def test_report_receipt_pins_v2_addendum_only_for_v2_inventory(self):
        api = self.api()
        with tempfile.TemporaryDirectory(dir=api.ROOT) as tmp:
            here = Path(tmp); root = here/'season'; root.mkdir(); source = here/'source'; source.mkdir()
            (root/'current.json').write_text('{}'); selected = here/'selected.json'; selected.write_text('{}')
            (source/'receipt.json').write_text('{}'); (source/'response.bin').write_bytes(b'fixture')
            (here/'charter.md').write_bytes(b'original protocol fixture')
            addendum = here/'inventory-v2-addendum.md'
            for version in (1, 2):
                if version == 2: addendum.write_bytes(b'version two protocol fixture')
                helper = self.fixture(); helper.snapshot['inventory_version'] = version
                for team in helper.snapshot['teams']: team['inventory_version'] = version
                output = here/f'report{version}'
                with patch.object(api, 'HERE', here), \
                     patch.object(api, 'load_inventory', return_value=(helper.snapshot, helper.roster)), \
                     patch.object(api, 'load_target', return_value=([], dict(captured_at=helper.clock))), \
                     patch.object(api, 'load_current', return_value=dict(results=[], checked_at=helper.clock)), \
                     patch.object(api, 'verify_finals'):
                    source_argument = source.relative_to(Path.cwd()) if version == 2 else source
                    api.run(selected, source_argument, output, root)
                pins = json.loads((output/'receipt.json').read_bytes())['inputs']
                for path in (here/'charter.md', addendum):
                    key = path.relative_to(api.ROOT).as_posix()
                    if path == addendum and version == 1: self.assertNotIn(key, pins)
                    else: self.assertEqual(pins[key], dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size))


if __name__ == '__main__':
    unittest.main()
