import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicBoardWorkflowTests(unittest.TestCase):
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
