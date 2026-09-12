"""Offline official-starter revisions through the real saved PGO model and archives."""
import copy
from contextlib import ExitStack
import csv
import gzip
import io
from itertools import count
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pgo_season as api
import pgo_season_availability as availability
from pgo_season_rollover import load_archive


GAME = '2026_01_ATL_PIT'
RUSH = '00-0033662'
ROSTER = '49de6434fb4ec3d13abb7de9906bf931fb35ea4fcb2e7ac357ca8e1d3e3d6e92'
DEPTH = 'ec813944a0d2c60ba9362bd066fc56ce135de0c2df793b170c5f22ea241bd744'
ANNOUNCEMENT = '08e9cb25040d8852f92854213db350cfef036763f4beaa2c3967bc4287367976'


class StarterRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.opening = api.bootstrap()
        cls.inputs = {}
        for kind, digest in (('roster', ROSTER), ('depth', DEPTH)):
            path = f'source-archive/{digest}.csv.gz'
            raw = (api.DEFAULT_ROOT / path).read_bytes()
            if api.sha(raw) != digest:
                raise AssertionError('Pinned test source changed: ' + path)
            cls.inputs[kind] = (raw, dict(url=api.URLS[kind], path=path,
                                         sha256=digest, bytes=len(raw)))
        cls.announcement_path = f'source-archive/{ANNOUNCEMENT}.json'
        cls.announcement = (api.DEFAULT_ROOT / cls.announcement_path).read_bytes()
        if api.sha(cls.announcement) != ANNOUNCEMENT:
            raise AssertionError('Pinned starter announcement changed')

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.inputs = dict(type(self).inputs)
        self.clock = '2026-09-12T18:00:00Z'
        self.rush_out = False
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(api, 'now', side_effect=lambda: self.clock))
        stack.enter_context(patch.object(availability, '_clock', side_effect=lambda now=None: api.utc(now or self.clock)))
        stack.enter_context(patch.object(api, 'fetch_source', side_effect=self.fetch_source))
        stack.enter_context(patch.object(availability, '_fetch', side_effect=self.fetch_availability))
        # Any accidental bypass of the two public-source seams must fail locally.
        stack.enter_context(patch('urllib.request.urlopen', side_effect=AssertionError('Unexpected live network call')))
        stack.enter_context(patch.object(availability, 'urlopen', side_effect=AssertionError('Unexpected live availability call')))
        for raw, ref in self.inputs.values():
            path = self.root / ref['path']; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        (self.root / self.announcement_path).write_bytes(self.announcement)
        self.state = copy.deepcopy(self.opening)
        self.state.update(checked_at='2026-09-12T17:59:00Z', source_captures=[])
        self.state['schedule'] = copy.deepcopy(self.state['weeks'][0]['games'])
        for game in self.games(self.state).values():
            game.get('availability', {}).pop('source_archive', None)
        game = self.games(self.state)[GAME]
        self.assertEqual(game['confidence']['points'], 4)
        game.update(blocked_reason='Expected QB unavailable: ATL: Tua Tagovailoa is OUT',
                    blocked_by_availability=True, pick=None,
                    withheld_confidence=game['confidence'], confidence=None)
        api.decorate(self.state, [])
        self.original = copy.deepcopy(self.state)
        directory = api.save_state(self.state, self.root)
        self.original_pointer = api.read_json(self.root / 'current.json')
        self.protected = {p: p.read_bytes() for p in directory.iterdir()}
        self.protected.update({self.root / ref['path']: raw for raw, ref in self.inputs.values()})
        self.protected[self.root / self.announcement_path] = self.announcement

    @staticmethod
    def games(state):
        return {g['game_id']: g for week in state['weeks'] for g in week['games']}

    def fetch_source(self, url, root):
        self.assertEqual(Path(root), self.root)
        kind = next((k for k in self.inputs if api.URLS[k] == url), None)
        self.assertIsNotNone(kind, 'Week 1 QB revision must not fetch model performance')
        raw, ref = self.inputs[kind]
        return raw, dict(ref, captured_at=self.clock)

    def fetch_availability(self, url):
        body = '<html><body>No official list in this fixture.</body></html>'
        if url == availability.REPORT_URL and self.rush_out:
            body = ('<title>NFL Injury Report - Week 1 of the 2026 Season</title>'
                    '<h2 class="d3-o-section-sub-title"><span>Falcons</span></h2><table>'
                    '<tr><th>Player</th><th>Position</th><th>Injuries</th><th>Practice Status</th><th>Game Status</th></tr>'
                    '<tr><td>Cooper Rush</td><td>QB</td><td>Knee</td>'
                    '<td>Did Not Participate</td><td>Out</td></tr></table>')
        return dict(body=body.encode(), status=200, final_url=url)

    def revise(self):
        refs = api.refresh_forecast_availability(self.state, self.root)
        self.state.update(checked_at=self.clock, source_captures=[r for r in refs if 'path' in r])
        api.decorate(self.state, self.state['results'])
        api.save_state(self.state, self.root)
        self.state = api.load_current(self.root)
        pointer = api.read_json(self.root / 'current.json')
        self.assertEqual(load_archive(self.root, pointer)[0], self.state)
        return self.games(self.state)[GAME]

    def assert_protected(self):
        for path, raw in self.protected.items():
            self.assertEqual(path.read_bytes(), raw, str(path))
        old, _ = load_archive(self.root, self.original_pointer)
        self.assertEqual(old, self.original)

    def later_depth_fixture(self, *, dated=None):
        """Derived test feed: swap only the latest DAL QB ranks; retain all 32 teams."""
        rows = api.csv_rows(self.inputs['depth'][0])
        latest = max(r['dt'] for r in rows if r.get('pos_abb') == 'QB')
        rows = [r for r in rows if r.get('pos_abb') == 'QB' and r['dt'] == latest]
        for row in rows:
            if row['team'] == 'DAL':
                self.assertIn(row['gsis_id'], ('00-0033077', '00-0037077'))
                row['pos_rank'] = '1' if row['gsis_id'] == '00-0037077' else '2'
            if dated:
                row['dt'] = dated
        text = io.StringIO(newline='')
        writer = csv.DictWriter(text, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
        raw = gzip.compress(text.getvalue().encode(), mtime=0)
        digest = api.sha(raw)
        ref = dict(url=api.URLS['depth'], path=f'source-archive/{digest}.csv.gz', sha256=digest, bytes=len(raw))
        (self.root / ref['path']).write_bytes(raw)
        self.inputs['depth'] = raw, ref

    def test_real_model_revision_restores_four_points_and_survives_same_depth_replay(self):
        before = self.games(self.original)
        selected = api.select_roster(api.csv_rows(self.inputs['roster'][0]),
                                     api.csv_rows(self.inputs['depth'][0]), self.clock)
        self.assertEqual(selected['ATL']['full_name'], 'Tua Tagovailoa')
        # The existing QB history decays with calendar time. Isolate the starter
        # change against the same clock/roster/fit, not the older September 9 edition.
        control_rankings, control_week, _ = api.build_next(
            self.state, self.state['schedule'], [], self.root, completed=0, selected=selected,
            roster_sources=[dict(ref, captured_at=self.clock) for _, ref in self.inputs.values()])
        control = self.games({'weeks': [control_week]})
        game = self.revise()
        self.assertEqual(game['expected_qbs']['ATL'], 'Cooper Rush')
        team = next(r for r in self.state['rankings']['teams'] if r['team'] == 'ATL')
        self.assertEqual((team['qb_gsis_id'], team['qb_name']), (RUSH, 'Cooper Rush'))
        self.assertEqual(game['availability']['teams']['ATL']['expected_qb_gsis_id'], RUSH)
        capture = self.root / game['availability']['source_archive']
        saved_inputs = json.loads(gzip.decompress((capture / 'inputs.json.gz').read_bytes()))
        self.assertEqual(saved_inputs['expected_qbs']['ATL'], RUSH)
        self.assertEqual(game['starter_announcements'][0]['gsis_id'], RUSH)
        self.assertEqual(game['starter_announcements'][0]['source']['sha256'], ANNOUNCEMENT)
        self.assertIsNone(game['blocked_reason'])
        self.assertIsNotNone(game['pick'])
        self.assertEqual(game['confidence']['points'], 4)
        self.assertAlmostEqual(game['confidence']['expected_points'],
                               4 * game['confidence']['win_probability'], places=12)
        self.assertGreater(abs(game['margin'] - control[GAME]['margin']), 1e-5)
        self.assertAlmostEqual(game['total'], before[GAME]['total'], places=12)
        controls = {r['team']: r for r in control_rankings['teams']}
        for row in self.state['rankings']['teams']:
            if row['team'] != 'ATL':
                self.assertEqual(row['features'], controls[row['team']]['features'], row['team'])
        unaffected_values = []
        for key, old in before.items():
            new = self.games(self.state)[key]
            if api.utc(old['lock_at']) <= api.utc(self.clock):
                self.assertEqual(new, old, key)
            elif key != GAME:
                for field in ('margin', 'total', 'home_points', 'away_points'):
                    unaffected_values.append((key, field, new[field], control[key][field]))
                self.assertEqual(new['confidence']['points'], old['confidence']['points'], key)
        drift = [(abs(control[key]['margin'] - old['margin']), key)
                 for key, old in before.items() if key != GAME and api.utc(old['lock_at']) > api.utc(self.clock)]
        maximum, maximum_game = max(drift)
        fields = ('margin', 'total', 'home_points', 'away_points', 'pick')
        self.diagnostic = dict(
            kind='OFFLINE FIXTURE DIAGNOSTIC; NOT AN ISSUED FORECAST', evaluated_at=self.clock,
            control=dict(**{k:control[GAME][k] for k in fields},
                         win_probability=control[GAME]['confidence']['win_probability']),
            rush=dict(**{k:game[k] for k in fields}, confidence=copy.deepcopy(game['confidence'])),
            maximum_non_ATL_margin_change_since_September9=dict(game_id=maximum_game, absolute_change=maximum,
                original=before[maximum_game]['margin'], same_clock_control=control[maximum_game]['margin']),
            maximum_non_ATL_change_due_to_starter=max(abs(a-b) for _, _, a, b in unaffected_values),
            cause='Existing calendar QB-history decay, pgo_current_strength._advance_qb_clock; 365.25-day half-life')
        first = copy.deepcopy(game)
        self.clock = '2026-09-12T18:05:00Z'
        second = self.revise()
        for field in ('margin', 'total', 'home_points', 'away_points', 'expected_qbs', 'confidence', 'starter_announcements'):
            self.assertEqual(second[field], first[field], field)
        locked = copy.deepcopy(second)
        self.clock = '2026-09-13T16:01:00Z'
        # The combined call creates distinct forecast and context captures.
        ticks = count()
        with patch.object(api, 'now', side_effect=lambda: (
                api.utc(self.clock) + api.timedelta(microseconds=next(ticks))).isoformat()):
            api.refresh_availability(self.state, self.root)
        self.assertIn('availability_context', self.state, self.state.get('availability_context_check'))
        self.assertEqual(self.state['availability_context'][GAME]['teams']['ATL']['expected_qb_gsis_id'], RUSH)
        self.assertEqual(self.games(self.state)[GAME], locked)
        self.assert_protected()
        for key, field, actual, original in unaffected_values:
            self.assertAlmostEqual(actual, original, places=11, msg=f'{key}: {field}')

    def test_real_official_report_for_rush_out_keeps_the_four_point_allocation_held(self):
        self.rush_out = True
        game = self.revise()
        self.assertEqual(game['expected_qbs']['ATL'], 'Cooper Rush')
        self.assertEqual(game['availability']['teams']['ATL']['expected_qb_status'], 'OUT')
        self.assertIsNone(game['pick'])
        self.assertIsNone(game['confidence'])
        self.assertEqual(game['withheld_confidence']['points'], 4)
        self.assertIn('Cooper Rush is OUT', game['blocked_reason'])
        self.assert_protected()

    def test_current_and_archived_replay_reject_changed_starter_source(self):
        self.revise()
        pointer = api.read_json(self.root / 'current.json')
        path = self.root / self.announcement_path
        path.write_bytes(path.read_bytes() + b' ')
        for loader in (lambda: api.load_current(self.root), lambda: load_archive(self.root, pointer)):
            with self.subTest(loader=loader), self.assertRaises(ValueError):
                loader()

    def test_later_qb_revision_retains_locked_same_week_starter_but_not_next_week(self):
        self.revise()
        self.clock = '2026-09-13T16:04:00Z'
        # Persist the normal display transition before testing a later QB edit.
        self.state['checked_at'] = self.clock
        api.decorate(self.state, self.state['results'])
        api.save_state(self.state, self.root)
        locked = copy.deepcopy(self.games(self.state)[GAME])
        self.clock = '2026-09-13T16:05:00Z'
        self.later_depth_fixture()
        self.revise()
        teams = {r['team']: r for r in self.state['rankings']['teams']}
        self.assertEqual(teams['DAL']['qb_name'], 'Sam Howell')
        self.assertEqual((teams['ATL']['qb_name'], teams['ATL']['qb_gsis_id']), ('Cooper Rush', RUSH))
        self.assertEqual(self.games(self.state)[GAME], locked)
        for refs in (self.state['rankings']['source_captures'],
                     self.state['edition_sources'][self.state['rankings']['edition']]):
            self.assertIn(ANNOUNCEMENT, [r['sha256'] for r in refs])
        self.assert_protected()

        # Week 2 lacks final/stat fixtures. Stop at the numerical boundary after
        # exercising actual roster selection, announcement retention and capture.
        self.clock = '2026-09-19T18:00:00Z'
        self.later_depth_fixture(dated='2026-09-19T11:36:06Z')
        next_game = copy.deepcopy(locked)
        next_game.update(game_id='2026_02_ATL_PIT', week=2,
                         kickoff='2026-09-20T17:00:00Z', lock_at='2026-09-20T16:00:00Z', availability={})
        next_game.pop('starter_announcements')
        self.state['rankings']['completed_week'] = 1
        self.state['current_week'] = 2
        self.state['weeks'].append(dict(week=2, games=[next_game]))
        self.state['schedule'].append(copy.deepcopy(next_game))

        class SelectionBoundaryReached(Exception):
            pass

        with patch.object(api, 'build_next', side_effect=SelectionBoundaryReached) as build:
            with self.assertRaises(SelectionBoundaryReached):
                api.refresh_forecast_availability(self.state, self.root)
        kwargs = build.call_args.kwargs
        self.assertEqual(kwargs['selected']['ATL']['full_name'], 'Tua Tagovailoa')
        self.assertNotIn(ANNOUNCEMENT, [r['sha256'] for r in kwargs['roster_sources']])
        self.assertEqual(self.games(self.state)[GAME], locked)


if __name__ == '__main__':
    unittest.main()
