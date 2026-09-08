import csv
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
        self.assertEqual("https://walshja9.github.io/Postgame_Outlet/forecast-lab.html", template["sections"]["accountability"]["settings"]["button_link"])
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

    def test_homepage_preview_matches_mccabes_current_top_five(self):
        with (ROOT / "data/ratings.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        score = lambda row: round(sum(float(row[key] or 0) for key in ("qb_value", "off_value", "def_value")), 1)
        expected = sorted(rows, key=lambda row: -score(row))[:5]
        preview = data("templates/index.json")["sections"]["ratings_preview"]
        self.assertEqual("Sean McCabe", preview["settings"]["author"])
        actual = [preview["blocks"][key]["settings"] for key in preview["block_order"]]
        self.assertEqual(
            [(str(i), row["team"], f"{score(row):+.1f}") for i, row in enumerate(expected, 1)],
            [(row["ordinal"], row["team"], row["rating"]) for row in actual],
        )

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
        self.assertRegex(css, r"\.postgame-featured-story :focus-visible\s*\{\s*outline: 0\.3rem solid var\(--postgame-highlight\);")

    def test_ratings_preview_counts_only_renderable_movers(self):
        section = text("sections/postgame-ratings-preview.liquid")
        self.assertIn("assign mover_count = 0", section)
        self.assertIn("assign mover_count = mover_count | plus: 1", section)
        self.assertNotIn("section.blocks | where: 'type', 'mover' | size", section)

    def test_power_ratings_has_native_context_before_origin_checked_embed(self):
        template = data("templates/page.power-ratings.json")
        self.assertEqual("postgame-ratings", template["sections"]["main"]["type"])
        section = text("sections/postgame-ratings.liquid")
        native = section.split("<iframe", 1)[0]
        schema = json.loads(section.split("{% schema %}", 1)[1].split("{% endschema %}", 1)[0])
        for setting_id in ("ratings_url", "methodology_link", "accountability_link", "archive_link"):
            setting = next(item for item in schema["settings"] if item["id"] == setting_id)
            self.assertNotIn("default", setting, setting_id)
        settings = template["sections"]["main"]["settings"]
        self.assertEqual("https://walshja9.github.io/Postgame_Outlet/", settings["ratings_url"])
        self.assertEqual("/pages/methodology", settings["methodology_link"])
        self.assertEqual("/pages/accountability", settings["accountability_link"])
        self.assertEqual("/blogs/poweratings", settings["archive_link"])
        self.assertLess(section.index("<h1"), section.index("<iframe"))
        for value in (
            "Sean McCabe's human-set rating",
            "quarterback, non-QB offense, and defense",
            "neutral-field points",
            "Choose PGO Model for the model’s rankings and team explanations",
            "McCabe and PGO ranks can be compared",
            "their rating numbers should not be subtracted to make a betting line",
            "McCabe ratings dated",
            "Page updated",
            "section.settings.status_label",
            "data-postgame-ratings-frame",
        ):
            self.assertIn(value, native)
        self.assertNotIn("MAE", native)
        self.assertNotIn("backtest", native)
        self.assertEqual("August 18, 2026", settings["published_at"])
        self.assertEqual("September 8, 2026", settings["updated_at"])
        self.assertIn("Accuracy is still being tested", settings["summary"])
        self.assertIn("assume the listed quarterback plays and exclude other injuries", settings["summary"])
        self.assertIn("the board shows when roster information was saved", settings["summary"])
        self.assertNotIn("July 21", settings["summary"])
        self.assertNotIn("September 6", settings["summary"])

    def test_fantasy_is_editorial_dynasty_and_dfs_without_a_tool(self):
        template = data("templates/page.fantasy.json")
        self.assertEqual(
            ["main-page", "postgame-tagged-articles", "postgame-tagged-articles"],
            [template["sections"][key]["type"] for key in template["order"]],
        )
        self.assertEqual("dynasty", template["sections"]["dynasty"]["settings"]["required_tag"])
        self.assertEqual("dfs", template["sections"]["dfs"]["settings"]["required_tag"])
        source = text("templates/page.fantasy.json").lower()
        for forbidden in ("assistant", "league sync", "projection tool", "healthy assumption"):
            self.assertNotIn(forbidden, source)

    def test_articles_expose_trust_fields_and_native_related_modules(self):
        article = text("sections/main-article.liquid")
        for field in (
            "custom.deck",
            "custom.byline",
            "custom.updated_at",
            "custom.model_version",
            "custom.key_takeaway",
            "custom.sources",
            "custom.methodology",
            "custom.correction_history",
        ):
            self.assertIn(field, article)
        template = data("templates/article.json")
        ordered_types = [template["sections"][key]["type"] for key in template["order"]]
        main_index = ordered_types.index("main-article")
        related_index = ordered_types.index("postgame-tagged-articles")
        product_index = ordered_types.index("featured-product")
        self.assertLess(main_index, related_index)
        self.assertLess(related_index, product_index)
        product_key = template["order"][product_index]
        self.assertTrue(template["sections"][product_key]["disabled"])
        self.assertIn("candidate.id == article.id", text("sections/postgame-tagged-articles.liquid"))
        blog = data("templates/blog.json")["sections"]["main"]["settings"]
        self.assertEqual("grid", blog["layout"])
        self.assertTrue(blog["show_author"])


if __name__ == "__main__":
    unittest.main()
