import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class PublicBoardWorkflowTests(unittest.TestCase):
    def test_manual_edition_uses_tested_source_before_snapshot_and_canonical_deploy(self):
        workflow=(ROOT/'.github/workflows/publish-edition.yml').read_text(encoding='utf-8')
        header,jobs=workflow.split('\njobs:',1)
        self.assertNotIn('\nconcurrency:',header)
        tests,publisher=jobs.split('\n  publish:',1)
        self.assertIn('\n  test:',tests)
        self.assertNotIn('concurrency:',tests)
        self.assertIn('contents: read',tests)
        self.assertIn('ref: ${{ github.sha }}',tests)
        self.assertIn('tested_sha: ${{ steps.tested.outputs.sha }}',tests)
        self.assertIn('python -m unittest discover -s tests',tests)
        self.assertNotIn('python snapshot.py',tests)
        self.assertNotIn('python pgo_comparison.py',tests)
        self.assertIn('needs: test',publisher)
        self.assertIn('group: board-update',publisher)
        self.assertIn('cancel-in-progress: false',publisher)
        self.assertIn('ref: main',publisher)
        self.assertIn('TESTED_SHA: ${{ needs.test.outputs.tested_sha }}',publisher)
        self.assertIn('git show "$TESTED_SHA:pgo_publication_guard.py"',publisher)
        self.assertLess(publisher.index('pgo_publication_guard.py'),publisher.index('python -m pip install'))
        self.assertLess(publisher.index('pgo_publication_guard.py'),publisher.index('python snapshot.py "$LABEL"'))
        self.assertIn('LABEL: ${{ inputs.label }}',publisher)
        self.assertIn('git add data/snapshots.json docs/index.html docs/forecast-lab.html',publisher)
        self.assertNotIn('git pull',publisher)
        self.assertIn('git push origin HEAD:main',publisher)
        self.assertIn('pages: write',workflow)
        deploy=publisher.split('- name: Request canonical Pages build',1)[1]
        self.assertIn("if: github.repository == 'walshja9/Postgame_Outlet'",deploy)
        self.assertIn('GH_TOKEN: ${{ github.token }}',deploy)
        self.assertIn('gh api --method POST repos/${{ github.repository }}/pages/builds',deploy)

    def test_full_tests_do_not_hold_the_publishing_lock(self):
        workflow = (ROOT / '.github/workflows/update-board.yml').read_text(encoding='utf-8')
        header, jobs = workflow.split('\njobs:', 1)
        self.assertNotIn('\nconcurrency:', header)
        self.assertIn('\n  test:', jobs)
        self.assertIn('\n  publish:', jobs)
        tests, publisher = jobs.split('\n  publish:', 1)
        publisher = publisher.split('\n  deploy:', 1)[0]
        self.assertNotIn('concurrency:', tests)
        self.assertIn('ref: ${{ github.sha }}', tests)
        self.assertIn('python -m unittest discover -s tests --durations 20', tests)
        self.assertIn('research.pgo_corrected_roster_candidate.test_temporal', tests)
        self.assertIn('research.pgo_defensive_depth_candidate.test_evidence', tests)
        self.assertNotIn('python pgo_comparison.py', tests)
        self.assertIn('needs: test', publisher)
        self.assertIn('group: board-update', publisher)
        self.assertIn('cancel-in-progress: false', publisher)
        self.assertIn('ref: main', publisher)
        self.assertIn('TESTED_SHA: ${{ needs.test.outputs.tested_sha }}', publisher)
        self.assertIn('git show "$TESTED_SHA:pgo_publication_guard.py"', publisher)
        self.assertLess(publisher.index('pgo_publication_guard.py'),
                        publisher.index('python -m pip install'))
        self.assertNotIn('git pull', publisher)
        self.assertIn('git push origin HEAD:main', publisher)
        self.assertIn('needs: publish', jobs.split('\n  deploy:', 1)[1])

    def test_publishing_rules_and_dependency_changes_trigger_full_tests(self):
        workflow = (ROOT / '.github/workflows/update-board.yml').read_text(encoding='utf-8')
        paths = workflow.split('  workflow_dispatch:', 1)[0]
        for path in ('.github/workflows/update-board.yml', '.github/workflows/update-season.yml',
                     'pgo_publication_guard.py', 'pgo_workflow_status.py',
                     'pgo_totals_monitor.py', 'pgo_weights_monitor.py',
                     'research/pgo_totals_candidate_20260910/**',
                     'research/pgo_weights_candidate_20260910/**',
                     'research/pgo_replacement_depth_20260910/**',
                     'tests/**', 'requirements-pgo.txt'):
            self.assertIn('"' + path + '"', paths)

    def test_season_gate_covers_new_accuracy_and_experimental_integrations(self):
        workflow = (ROOT / '.github/workflows/update-season.yml').read_text(encoding='utf-8')
        gate = workflow.split('- name: Capture verified finals',1)[0]
        for module in ('test_pgo_season_accuracy','test_pgo_totals_monitor','test_pgo_weights_monitor',
                       'test_pgo_replacement_depth','test_pgo_season_experiments','test_pgo_experiment_view',
                       'test_pgo_inactive_monitor'):
            self.assertIn('tests.'+module,gate)

    def test_inactive_schedule_keeps_the_shared_lock_and_canonical_publisher(self):
        workflow = (ROOT / '.github/workflows/update-season.yml').read_text(encoding='utf-8')
        self.assertIn('cron: "7,22,37,52 * * * *"', workflow)
        self.assertIn('cron: "2,12,17,27,32,42,47,57 * * * *"', workflow)
        self.assertIn('  workflow_dispatch:', workflow)
        self.assertIn('concurrency:\n  group: board-update\n  cancel-in-progress: false', workflow)
        self.assertIn("if: github.repository == 'walshja9/Postgame_Outlet'", workflow)
        self.assertIn('git add docs/evidence/season-2026 docs/index.html docs/forecast-lab.html', workflow)
        self.assertIn('git push origin HEAD:main', workflow)
        self.assertIn('gh api --method POST repos/${{ github.repository }}/pages/builds', workflow)

    def test_extra_ticks_only_refresh_when_the_observed_watch_window_is_open(self):
        workflow = (ROOT / '.github/workflows/update-season.yml').read_text(encoding='utf-8')
        route = workflow.split('- name: Route extra inactive checks', 1)[1].split('\n      - name:', 1)[0]
        self.assertIn('shell: python', route)
        script = textwrap.dedent(route.split('        run: |\n', 1)[1])
        extra = '2,12,17,27,32,42,47,57 * * * *'
        state, clock = object(), '2026-09-10T23:35:00Z'
        for event, schedule, watching, expected in (
                ('schedule', extra, [], False),
                ('schedule', extra, [{'game_id': 'SF-LAR', 'kickoff': '2026-09-11T00:35:00Z', 'status': 'VERIFIED'}], True),
                ('schedule', extra, [{'game_id': 'SF-LAR', 'kickoff': clock, 'status': 'VERIFIED'}], False),
                ('schedule', extra, [{'game_id': 'SF-LAR', 'kickoff': '2026-09-10T22:35:00Z', 'status': 'VERIFIED'}], False),
                ('schedule', extra, [{'game_id': 'SF-LAR', 'kickoff': '2026-09-10T22:35:00Z', 'status': 'MISSING'}], True),
                ('schedule', '7,22,37,52 * * * *', [], True),
                ('workflow_dispatch', '', [], True)):
            with self.subTest(event=event, schedule=schedule, watching=watching), tempfile.TemporaryDirectory() as folder:
                target = Path(folder) / 'output'
                season = SimpleNamespace(load_current=mock.Mock(return_value=state),
                                         now=mock.Mock(return_value=clock),
                                         utc=lambda value: datetime.fromisoformat(value.replace('Z', '+00:00')),
                                         availability_watch=mock.Mock(return_value={'games': watching}))
                env = {'PGO_EVENT': event, 'PGO_SCHEDULE': schedule, 'GITHUB_OUTPUT': str(target)}
                with mock.patch.dict(sys.modules, {'pgo_season': season}), mock.patch.dict(os.environ, env):
                    exec(script, {'__name__': '__main__'})
                self.assertEqual(target.read_text(encoding='utf-8'), f'run_refresh={str(expected).lower()}\n')
                if schedule == extra:
                    season.now.assert_called_once_with()
                    season.availability_watch.assert_called_once_with(state, clock)
                else:
                    season.load_current.assert_not_called()
                    season.availability_watch.assert_not_called()
        for name in ('Verify automatic grading', 'Capture verified finals', 'Render current board',
                     'Publish changed season'):
            step = workflow.split('- name: ' + name, 1)[1].split('\n      - name:', 1)[0]
            self.assertIn("if: steps.route.outputs.run_refresh == 'true'", step)

    def test_saved_state_health_is_reported_after_publication(self):
        workflow = (ROOT / '.github/workflows/update-season.yml').read_text(encoding='utf-8')
        self.assertIn('id: refresh', workflow)
        self.assertIn("if: always() && steps.refresh.outcome == 'success'", workflow)
        self.assertGreater(workflow.index('python pgo_workflow_status.py'),
                           workflow.index('gh api --method POST'))

    def test_route_imports_checkout_when_python_shell_uses_a_temporary_script(self):
        workflow = (ROOT / '.github/workflows/update-season.yml').read_text(encoding='utf-8')
        route = workflow.split('- name: Route extra inactive checks', 1)[1].split('\n      - name:', 1)[0]
        script = textwrap.dedent(route.split('        run: |\n', 1)[1])
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'github-output'
            command = Path(folder) / 'runner-step.py'
            command.write_text(script, encoding='utf-8')
            env = dict(os.environ, PGO_EVENT='workflow_dispatch', PGO_SCHEDULE='', GITHUB_OUTPUT=str(target))
            env.pop('PYTHONPATH', None)
            if 'PYTHONPATH: ${{ github.workspace }}' in route:
                env['PYTHONPATH'] = str(ROOT)
            result = subprocess.run([sys.executable, str(command)], cwd=ROOT, env=env,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_text(encoding='utf-8'), 'run_refresh=true\n')

    def test_board_workflows_use_the_approved_pgo_publisher(self):
        update_board = (ROOT / ".github" / "workflows" / "update-board.yml").read_text(
            encoding="utf-8"
        )
        publish_edition = (
            ROOT / ".github" / "workflows" / "publish-edition.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("python pgo_comparison.py --refresh-mccabe", update_board)
        self.assertIn("python pgo_comparison.py --refresh-mccabe", publish_edition)
        self.assertNotIn("python generate_site.py --output docs/index.html", update_board)
        self.assertNotIn(
            "python generate_site.py --output docs/index.html", publish_edition
        )

        public_board = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="panel-comparison"', public_board)
        self.assertIn('data-panel="comparison">PGO Model', public_board)

    def test_board_workflows_use_current_node_runtime_actions(self):
        for name in ("update-board.yml", "publish-edition.yml"):
            workflow = (ROOT / ".github" / "workflows" / name).read_text(
                encoding="utf-8"
            )
            with self.subTest(workflow=name):
                self.assertIn("actions/checkout@v7", workflow)
                self.assertIn("actions/setup-python@v7", workflow)


if __name__ == "__main__":
    unittest.main()
