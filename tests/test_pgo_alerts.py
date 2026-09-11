import copy
import io
import json
import unittest
from unittest.mock import patch

import pgo_alerts as alerts
from tests import test_pgo_season_boundaries as fixtures


class AlertTests(unittest.TestCase):
    def test_missing_dependency_keeps_safe_failure_notification_reachable(self):
        with patch('sys.argv', ['pgo_alerts.py', '--deliver', '--verify-outcome', 'failure',
                               '--refresh-outcome', 'skipped', '--render-outcome', 'skipped',
                               '--publish-outcome', 'skipped']), \
             patch.dict(alerts.os.environ, {'GITHUB_REPOSITORY': alerts.REPOSITORY,
                 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1'}), \
             patch.object(alerts, 'load_current', side_effect=ImportError('private dependency detail')), \
             patch.object(alerts, 'deliver', return_value={'action': 'created'}) as deliver, \
             patch('builtins.print') as printed:
            alerts.main()
        report = deliver.call_args.args[0]
        self.assertFalse(report['can_resolve'])
        self.assertEqual({row['key'] for row in report['conditions']}, {'failed-verify', 'state-unverified'})
        self.assertNotIn('private dependency detail', str(printed.call_args_list))

    def state(self):
        fixture = fixtures.SeasonBoundaryTests()
        game = fixture.game()
        state = fixture.state([game])
        state['checked_at'] = '2026-09-13T15:30:00Z'
        state['weeks'][0]['games'][0]['availability']['checked_at'] = state['checked_at']
        state['ats'] = {'status': 'READY'}
        return state

    def report(self, state=None, **kwargs):
        return alerts.assess(self.state() if state is None else state,
            outcomes=dict.fromkeys(('verify', 'refresh', 'render', 'publish'), 'success'),
            checked_at='2026-09-13T15:31:00Z', refresh_started_at='2026-09-13T15:29:00Z',
            public_pointer=kwargs.pop('public_pointer', self.pointer()), **kwargs)

    def pointer(self, checked='2026-09-13T15:30:00Z'):
        return dict(checked_at=checked, path='runs-v2/20260913T153000000000Z', manifest_sha256='a' * 64)

    def test_public_pointer_is_required_for_resolution_and_bad_or_stale_is_attention(self):
        for pointer in (None, {}, self.pointer('2026-09-13T14:00:00Z'), self.pointer('2026-09-13T16:00:00Z')):
            report = self.report(public_pointer=pointer)
            self.assertFalse(report['can_resolve'])
            self.assertIn('public-update', [item['key'] for item in report['conditions']])
        self.assertTrue(self.report()['can_resolve'])
        self.assertFalse(alerts.assess(self.state(), outcomes=dict.fromkeys(alerts.STAGES, 'success'),
            checked_at='2026-09-13T15:31:00Z', refresh_started_at='2026-09-13T15:29:00Z')['can_resolve'])

    def test_public_get_is_fixed_bounded_and_does_not_expose_fetch_errors(self):
        for raw, url, expected in [(json.dumps(self.pointer()).encode(), alerts.PUBLIC_POINTER, self.pointer()),
                                   (b'bad json secret', alerts.PUBLIC_POINTER, None),
                                   (b' ' * 65537, alerts.PUBLIC_POINTER, None),
                                   (b'{}', 'https://other.example/', None)]:
            response = io.BytesIO(raw)
            response.geturl = lambda: url
            with patch.object(alerts.urllib.request, 'urlopen', return_value=response) as get:
                self.assertEqual(alerts.fetch_public_pointer(), expected)
                self.assertEqual(get.call_args.args[0].full_url, alerts.PUBLIC_POINTER)
                self.assertEqual(get.call_args.kwargs['timeout'], 20)
        with patch.object(alerts.urllib.request, 'urlopen', side_effect=OSError('secret error')):
            self.assertIsNone(alerts.fetch_public_pointer())

    def test_weekly_wait_escalates_only_after_verified_slate_and_six_hour_grace(self):
        state = self.state()
        state.update(status='BLOCKED', blocked_reason='Waiting to publish the next week: pending')
        self.assertEqual(self.report(state)['conditions'], [])
        game = state['schedule'][0]
        result = fixtures.SeasonBoundaryTests().result(game)
        state['results'] = [result]
        for checked, expected in [('2026-09-14T03:00:00Z', False), ('2026-09-14T03:00:01Z', True)]:
            state['checked_at'] = checked
            report = alerts.assess(state, outcomes=dict.fromkeys(alerts.STAGES, 'success'), checked_at=checked)
            self.assertEqual('weekly-update-overdue' in [item['key'] for item in report['conditions']], expected)
        state['results'][0]['home_team'] = 'BUF'
        report = alerts.assess(state, outcomes=dict.fromkeys(alerts.STAGES, 'success'), checked_at=state['checked_at'])
        self.assertIn('state-unverified', [item['key'] for item in report['conditions']])

    def test_watch_reused_missing_stale_urgent_and_safe_details(self):
        state = self.state()
        state['checked_at'] = '2026-09-13T15:50:00Z'
        before = copy.deepcopy(state)
        report = alerts.assess(state, outcomes={'refresh': 'success'}, checked_at=state['checked_at'])
        self.assertIn('inactive:2026_01_NE_SEA', [item['key'] for item in report['conditions']])
        self.assertTrue(any(item['urgent'] for item in report['conditions']))
        self.assertEqual(before, state)
        state['availability_context_check'] = {'status': 'BLOCKED', 'blocked_reason': 'SECRET @everyone <script>'}
        report = alerts.assess(state, outcomes={'refresh': 'success'}, checked_at=state['checked_at'])
        self.assertNotIn('SECRET', json.dumps(report))
        state['weeks'][0]['games'][0]['availability']['teams'] = {
            team: {'final_inactives_status': 'VERIFIED_LIST'} for team in ('SEA', 'NE')}
        report = alerts.assess(state, outcomes={'refresh': 'success'}, checked_at=state['checked_at'])
        self.assertIn('check is overdue', json.dumps(report))

    def test_normal_wait_and_awaiting_lists_do_not_alert(self):
        report = self.report()
        self.assertEqual(report['conditions'], [])
        self.assertTrue(report['can_resolve'])
        state = self.state()
        state.update(status='BLOCKED', blocked_reason='Waiting to publish the next week: new data pending')
        self.assertEqual(self.report(state)['conditions'], [])

    def test_stale_future_invalid_state_and_failed_pipeline_cannot_resolve(self):
        state = self.state()
        state['checked_at'] = '2026-09-13T13:00:00Z'
        report = self.report(state)
        self.assertIn('automation-overdue', [item['key'] for item in report['conditions']])
        self.assertFalse(report['can_resolve'])
        state['checked_at'] = '2026-09-13T16:00:00Z'
        self.assertIn('state-unverified', [item['key'] for item in self.report(state)['conditions']])
        self.assertFalse(self.report({})['can_resolve'])
        for stage in ('verify', 'refresh', 'render', 'publish'):
            outcomes = dict.fromkeys(('verify', 'refresh', 'render', 'publish'), 'success')
            outcomes[stage] = 'failure'
            report = alerts.assess(self.state(), outcomes=outcomes, checked_at='2026-09-13T15:31:00Z')
            self.assertIn('failed-' + stage, [item['key'] for item in report['conditions']])
            self.assertFalse(report['can_resolve'])
        self.assertFalse(alerts.assess(self.state(), outcomes=dict.fromkeys(('verify', 'refresh', 'render', 'publish'), 'success'),
            checked_at='2026-09-13T15:31:00Z', refresh_started_at='2026-09-13T15:30:01Z')['can_resolve'])

    def test_noop_never_reads_issues_or_resolves(self):
        report = alerts.assess(None, outcomes={}, run_refresh=False)
        self.assertEqual(alerts.deliver(report, lambda *args: self.fail('API called'), alerts.RUN_URL), {'action': 'skipped'})

    def issue(self, report, number=1, **kwargs):
        item = dict(number=number, state='open', user={'login': alerts.BOT, 'type': 'Bot'},
                    assignees=[{'login': alerts.ASSIGNEE}], body=alerts.issue_body(report, alerts.RUN_URL))
        item.update(kwargs)
        return item

    def incident(self):
        return alerts.assess(None, outcomes={'refresh': 'failure'}, checked_at='2026-09-13T15:31:00Z')

    def test_delivery_creates_only_assigned_bot_incident_and_unchanged_is_noop(self):
        report = self.incident()
        fake = FakeAPI([])
        self.assertEqual(alerts.deliver(report, fake, alerts.RUN_URL)['action'], 'created')
        self.assertEqual(fake.calls[1][2]['assignees'], ['walshja9'])
        fake.calls.clear()
        self.assertEqual(alerts.deliver(report, fake, alerts.RUN_URL)['action'], 'unchanged')
        self.assertEqual(len(fake.calls), 1)

    def test_new_urgent_condition_comments_once_and_fresh_health_closes(self):
        prior = self.incident()
        fake = FakeAPI([self.issue(prior)])
        changed = copy.deepcopy(prior)
        changed['conditions'].append({'key': 'inactive:2026_01_NE_SEA', 'message': 'Missing final lists.', 'urgent': True})
        self.assertEqual(alerts.deliver(changed, fake, alerts.RUN_URL)['action'], 'escalated')
        self.assertEqual(sum(path.endswith('/comments') for _, path, _ in fake.calls), 1)
        fake.calls.clear()
        self.assertEqual(alerts.deliver(changed, fake, alerts.RUN_URL)['action'], 'unchanged')
        self.assertEqual(alerts.deliver(self.report(), fake, alerts.RUN_URL)['action'], 'resolved')
        self.assertEqual(fake.issues[0]['state'], 'closed')

    def test_ambiguous_ownership_duplicate_incidents_or_metadata_prevent_mutation(self):
        report = self.incident()
        for items in ([self.issue(report, user={'login': 'walshja9', 'type': 'User'})],
                      [self.issue(report, assignees=[{'login': 'someone-else'}])],
                      [self.issue(report), self.issue(report, 2)],
                      [self.issue(report, body=alerts.MARKER)]):
            fake = FakeAPI(items)
            with self.assertRaises(ValueError):
                alerts.deliver(report, fake, alerts.RUN_URL)
            self.assertTrue(all(method == 'GET' for method, _, _ in fake.calls))

    def test_failed_escalation_is_retried_without_duplicate_comments(self):
        prior = self.incident()
        fake = FakeAPI([self.issue(prior)])
        changed = copy.deepcopy(prior)
        changed['conditions'].append({'key': 'inactive:2026_01_NE_SEA', 'message': 'Missing final lists.', 'urgent': True})
        failed = False
        def flaky(method, path, payload=None):
            nonlocal failed
            if method == 'POST' and path.endswith('/comments') and not failed:
                failed = True
                raise RuntimeError('API unavailable')
            return fake(method, path, payload)
        with self.assertRaises(RuntimeError):
            alerts.deliver(changed, flaky, alerts.RUN_URL)
        self.assertEqual(alerts.deliver(changed, fake, alerts.RUN_URL)['action'], 'escalated')
        self.assertEqual(len(fake.comments), 1)
        self.assertEqual(alerts.deliver(changed, fake, alerts.RUN_URL)['action'], 'unchanged')
        self.assertEqual(len(fake.comments), 1)
        # Successful POST with a lost response must not send a second comment.
        fake = FakeAPI([self.issue(prior)])
        failed = False
        def lost_response(method, path, payload=None):
            nonlocal failed
            result = fake(method, path, payload)
            if method == 'POST' and path.endswith('/comments') and not failed:
                failed = True
                raise RuntimeError('response lost')
            return result
        with self.assertRaises(RuntimeError):
            alerts.deliver(changed, lost_response, alerts.RUN_URL)
        self.assertEqual(alerts.deliver(changed, fake, alerts.RUN_URL)['action'], 'escalated')
        self.assertEqual(len(fake.comments), 1)

    def test_pagination_finds_incident_after_first_page_and_api_error_is_not_success(self):
        report = self.incident()
        fake = FakeAPI([{'number': i + 10, 'body': '', 'state': 'open'} for i in range(100)] + [self.issue(report)])
        self.assertEqual(alerts.deliver(report, fake, alerts.RUN_URL)['action'], 'unchanged')
        self.assertIn('page=2', fake.calls[1][1])
        with self.assertRaises(RuntimeError):
            alerts.deliver(report, lambda *args: (_ for _ in ()).throw(RuntimeError('API failed')), alerts.RUN_URL)

    def test_public_url_and_recipient_are_fixed(self):
        with self.assertRaises(ValueError):
            alerts.issue_body(self.incident(), 'https://evil.example/?secret=token')
        with patch.object(alerts.subprocess, 'run') as run:
            run.return_value.returncode = 1
            run.return_value.stderr = 'raw secret'
            with self.assertRaisesRegex(RuntimeError, '^GitHub request failed$'):
                alerts.github_api('GET', 'repos/walshja9/Postgame_Outlet/issues')

    def test_commissioning_does_not_claim_an_operational_failure(self):
        report = self.report()
        report['conditions'] = [dict(key='commissioning', message='Notification setup check only.', urgent=False)]
        fake = FakeAPI([])
        alerts.deliver(report, fake, alerts.RUN_URL)
        self.assertEqual(fake.issues[0]['title'], '[PGO] Notification delivery check')
        self.assertIn('This is a notification setup check, not a model or data failure.', fake.issues[0]['body'])


class FakeAPI:
    def __init__(self, issues):
        self.issues = copy.deepcopy(issues)
        self.calls = []
        self.comments = []

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == 'GET' and '/comments?' in path:
            return self.comments
        if method == 'POST' and path.endswith('/comments'):
            item = dict(payload, user={'login': alerts.BOT, 'type': 'Bot'})
            self.comments.append(item)
            return item
        if method == 'GET':
            page = int(path.rsplit('page=', 1)[1])
            return [i for i in self.issues if i['state'] == 'open'][(page - 1) * 100:page * 100]
        if method == 'POST' and path.endswith('/issues'):
            item = dict(number=1, state='open', user={'login': alerts.BOT, 'type': 'Bot'},
                        assignees=[{'login': alerts.ASSIGNEE}], **{k:v for k,v in payload.items() if k != 'assignees'})
            self.issues.append(item)
            return item
        if method == 'PATCH':
            self.issues[0].update(payload)
            return self.issues[0]
        return {'id': 1}


if __name__ == '__main__':
    unittest.main()
