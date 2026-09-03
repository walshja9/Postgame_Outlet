import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "shopify-theme"
COMMERCE_MANIFEST = ROOT / "tests/fixtures/shopify-theme-commerce.sha256"


def text(relative):
    return (THEME / relative).read_text(encoding="utf-8")


def data(relative):
    source = text(relative)
    if source.lstrip().startswith("/*"):
        source = source.split("*/", 1)[1]
    return json.loads(source)


class ShopifyThemeTests(unittest.TestCase):
    def test_commerce_files_match_fresh_capture(self):
        entries = [line.split("  ", 1) for line in COMMERCE_MANIFEST.read_text(encoding="ascii").splitlines()]
        self.assertEqual(7, len(entries))
        for digest, relative in entries:
            self.assertEqual(64, len(digest), relative)
            actual = hashlib.sha256((THEME / relative).read_bytes()).hexdigest()
            self.assertEqual(digest, actual, relative)

    def test_shared_content_assets_are_loaded_once(self):
        layout = text("layout/theme.liquid")
        self.assertEqual(1, layout.count("postgame-content.css"))
        self.assertEqual(1, layout.count("postgame-content.js"))
        self.assertIn("data-postgame-content-type", layout)
        self.assertIn("data-postgame-content-id", layout)
        self.assertIn("template.suffix == 'power-ratings' or template.suffix == 'fantasy'", layout)
        css = text("assets/postgame-content.css")
        for value in ("--postgame-navy", "--postgame-orange", ":focus-visible", "max-width: 749px"):
            self.assertIn(value, css)

    def test_shared_script_has_embed_and_analytics_contracts(self):
        script = text("assets/postgame-content.js")
        for value in (
            "postgame_content_product_click",
            "content_type",
            "content_identifier",
            "product_handle",
            "npr:height",
            "npr:ready",
            "npr:viewport",
            "event.origin !== origin",
            "event.source !== frame.contentWindow",
            "Number.isFinite(height)",
        ):
            self.assertIn(value, script)

    def test_homepage_has_approved_content_order(self):
        template = data("templates/index.json")
        types = [
            template["sections"][section_id]["type"]
            for section_id in template["order"]
            if not template["sections"][section_id].get("disabled", False)
        ]
        self.assertEqual(
            [
                "postgame-featured-story",
                "postgame-ratings-preview",
                "postgame-tagged-articles",
                "postgame-tagged-articles",
                "postgame-tagged-articles",
                "multicolumn",
                "apps",
                "featured-collection",
            ],
            types,
        )
        self.assertEqual("dynasty", template["sections"]["dynasty"]["settings"]["required_tag"])
        self.assertEqual("dfs", template["sections"]["dfs"]["settings"]["required_tag"])
        self.assertEqual("/pages/accountability", template["sections"]["accountability"]["settings"]["button_link"])
        self.assertEqual(4, template["sections"]["merch"]["settings"]["products_to_show"])

    def test_featured_story_supports_reviewed_status_without_requiring_it(self):
        section = text("sections/postgame-featured-story.liquid")
        for value in ("section.settings.article", "status_label", "status_body", "postgame-model-status"):
            self.assertIn(value, section)
        self.assertIn("featured_article != blank", section)

    def test_ratings_preview_requires_reviewed_five_and_supports_movers(self):
        section = text("sections/postgame-ratings-preview.liquid")
        for value in (
            "team_count != 5",
            "block.type == 'team'",
            "block.type == 'mover'",
            "Rating points represent neutral-field strength",
            "View all 32 teams",
            "section.settings.ratings_link",
        ):
            self.assertIn(value, section)

    def test_preview_navigation_footer_and_email_are_isolated(self):
        header = data("sections/header-group.json")
        footer = data("sections/footer-group.json")
        self.assertEqual("content-first-preview", header["sections"]["header"]["settings"]["menu"])
        self.assertEqual(
            "content-footer-preview",
            footer["sections"]["footer"]["blocks"]["content_links"]["settings"]["menu"],
        )
        combined = json.dumps(data("templates/index.json")) + json.dumps(footer)
        self.assertEqual(1, combined.count("form-embed-block"))

    def test_featured_story_uses_a_high_contrast_focus_outline(self):
        css = text("assets/postgame-content.css")
        self.assertIn(".postgame-featured-story :focus-visible", css)
        self.assertIn("outline: 0.3rem solid var(--postgame-orange)", css)

    def test_ratings_preview_counts_only_renderable_movers(self):
        section = text("sections/postgame-ratings-preview.liquid")
        self.assertIn("assign mover_count = 0", section)
        self.assertIn("assign mover_count = mover_count | plus: 1", section)
        self.assertNotIn("section.blocks | where: 'type', 'mover' | size", section)


if __name__ == "__main__":
    unittest.main()
