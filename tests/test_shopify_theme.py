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

    def test_homepage_preview_matches_mccabes_september_9_published_top_five(self):
        expected = [
            ("1", "Los Angeles Rams", "+7.6"),
            ("2", "Buffalo Bills", "+6.6"),
            ("3", "Baltimore Ravens", "+6.0"),
            ("4", "Seattle Seahawks", "+5.5"),
            ("5", "Cincinnati Bengals", "+5.0"),
        ]
        preview = data("templates/index.json")["sections"]["ratings_preview"]
        self.assertEqual("Sean McCabe", preview["settings"]["author"])
        self.assertEqual("September 9, 2026", preview["settings"]["published_at"])
        self.assertEqual("Week 1 2026 - Human power ratings", preview["settings"]["edition"])
        actual = [preview["blocks"][key]["settings"] for key in preview["block_order"]]
        self.assertEqual(
            expected,
            [(row["ordinal"], row["team"], row["rating"]) for row in actual],
        )
        lab = data("templates/index.json")["sections"]["accountability"]["blocks"]["pending"]["settings"]
        self.assertIn("See this week's game forecasts", lab["text"])
        self.assertEqual("See this week's forecasts", lab["link_label"])

    def test_sitewide_palette_has_readable_native_controls(self):
        def channels(value):
            return [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]

        def luminance(rgb):
            linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
            return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

        def contrast(foreground, background, opacity=1):
            bg = channels(background)
            fg = [a * opacity + b * (1 - opacity) for a, b in zip(channels(foreground), bg)]
            light, dark = sorted((luminance(fg), luminance(bg)), reverse=True)
            return (light + 0.05) / (dark + 0.05)

        schemes = data("config/settings_data.json")["current"]["color_schemes"]
        for name, scheme in schemes.items():
            settings = scheme["settings"]
            with self.subTest(scheme=name):
                self.assertIn(settings["background"], ("#0e1116", "#171c24"))
                self.assertGreaterEqual(contrast(settings["text"], settings["background"], 0.75), 4.5)
                self.assertGreaterEqual(contrast(settings["secondary_button_label"], settings["background"], 0.85), 4.5)
                self.assertGreaterEqual(contrast(settings["button_label"], settings["button"]), 4.5)
                self.assertGreaterEqual(contrast("#93a1b0", settings["background"]), 4.5)
                self.assertGreaterEqual(contrast("#93c5fd", settings["background"]), 3)
        self.assertIn("system-ui", text("assets/postgame-content.css"))

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
        self.assertEqual("https://walshja9.github.io/Postgame_Outlet/index.html?release=8305414", settings["ratings_url"])
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
        self.assertEqual("September 9, 2026", settings["published_at"])
        self.assertEqual("September 9, 2026", settings["updated_at"])
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
