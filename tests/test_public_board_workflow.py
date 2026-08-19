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


if __name__ == "__main__":
    unittest.main()
