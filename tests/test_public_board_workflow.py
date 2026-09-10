import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicBoardWorkflowTests(unittest.TestCase):
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
                       'test_pgo_replacement_depth','test_pgo_season_experiments','test_pgo_experiment_view'):
            self.assertIn('tests.'+module,gate)

    def test_saved_state_health_is_reported_after_publication(self):
        workflow = (ROOT / '.github/workflows/update-season.yml').read_text(encoding='utf-8')
        self.assertIn('id: refresh', workflow)
        self.assertIn("if: always() && steps.refresh.outcome == 'success'", workflow)
        self.assertGreater(workflow.index('python pgo_workflow_status.py'),
                           workflow.index('gh api --method POST'))

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
