import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "shopify-theme"


def text(relative):
    return (THEME / relative).read_text(encoding="utf-8")


def data(relative):
    return json.loads(text(relative))


class ShopifyThemeTests(unittest.TestCase):
    def test_commerce_files_match_export(self):
        expected = {
            "templates/product.json": "3ccc3a33ef1f95be8b4b8673ea22492ead4d13df54adc3a6e69e9b7fcf4da42d",
            "templates/collection.json": "5de97ba28f7245538cca35deda4c7183329226826f7f65f2d8a4343e34bcb42a",
            "templates/cart.json": "4f75bd249c0c720acba10768f0c80c8af79d9b1903c02706e70fb5f693b70ec7",
            "sections/main-product.liquid": "b165c0b41605fbaf73ac0a0221f3963367c59b13f832e6ab971963cd7e7b217f",
            "sections/main-cart-items.liquid": "8f68b4939841f6e17a650d17af7378cf59951df78b97b7c38353f23fe9518da6",
            "sections/main-cart-footer.liquid": "172a57669d38ede33919ad7f826bd1161e5f7256e99903934d55cb3035783122",
            "snippets/cart-drawer.liquid": "1a906b54b52cc75c81580fb279a42fccfdccc46fe5edd5e90b5e615c3d9e76f5",
        }
        for relative, digest in expected.items():
            actual = hashlib.sha256((THEME / relative).read_bytes()).hexdigest()
            self.assertEqual(digest, actual, relative)

    def test_shared_content_assets_are_loaded_once(self):
        layout = text("layout/theme.liquid")
        self.assertEqual(1, layout.count("postgame-content.css"))
        self.assertEqual(1, layout.count("postgame-content.js"))
        self.assertIn("data-postgame-content-type", layout)
        self.assertIn("data-postgame-content-id", layout)

    def test_shared_script_has_embed_and_analytics_contracts(self):
        script_path = THEME / "assets/postgame-content.js"
        self.assertTrue(script_path.exists(), "shared script is missing")
        script = script_path.read_text(encoding="utf-8")
        for value in (
            "postgame_content_product_click",
            "content_type",
            "content_identifier",
            "product_handle",
            "npr:height",
            "npr:ready",
            "npr:viewport",
            "event.origin !== origin",
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
                "multicolumn",
                "postgame-tagged-articles",
                "featured-collection",
                "apps",
            ],
            types,
        )
        calls = template["sections"]["accountable_calls"]
        self.assertEqual("/pages/accountability", calls["settings"]["button_link"])

    def test_ratings_preview_requires_reviewed_five_and_supports_movers(self):
        path = THEME / "sections/postgame-ratings-preview.liquid"
        self.assertTrue(path.exists(), "ratings preview section is missing")
        section = path.read_text(encoding="utf-8")
        for value in (
            "team_count != 5",
            "block.type == 'team'",
            "block.type == 'mover'",
            "Rating points represent neutral-field strength",
            "View all 32 teams",
        ):
            self.assertIn(value, section)

    def test_power_ratings_template_has_native_context_before_embed(self):
        template_path = THEME / "templates/page.power-ratings.json"
        section_path = THEME / "sections/postgame-ratings.liquid"
        self.assertTrue(template_path.exists(), "Power Ratings template is missing")
        self.assertTrue(section_path.exists(), "Power Ratings section is missing")
        template = json.loads(template_path.read_text(encoding="utf-8"))
        self.assertEqual("postgame-ratings", template["sections"]["main"]["type"])
        section = section_path.read_text(encoding="utf-8")
        schema = json.loads(section.split("{% schema %}", 1)[1].split("{% endschema %}", 1)[0])
        ratings_url = next(setting for setting in schema["settings"] if setting["id"] == "ratings_url")
        self.assertNotIn("default", ratings_url)
        self.assertEqual(
            "https://walshja9.github.io/Postgame_Outlet/",
            template["sections"]["main"]["settings"]["ratings_url"],
        )
        self.assertLess(section.index("<h1"), section.index("<iframe"))
        for value in (
            "A Power Rating estimates",
            "/pages/methodology-preview",
            "/pages/accountability-preview",
            "data-postgame-ratings-frame",
        ):
            self.assertIn(value, section)

    def test_fantasy_template_has_dynasty_and_dfs_without_tools(self):
        path = THEME / "templates/page.fantasy.json"
        self.assertTrue(path.exists(), "Fantasy template is missing")
        template = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(
            ["main-page", "postgame-tagged-articles", "postgame-tagged-articles"],
            [template["sections"][key]["type"] for key in template["order"]],
        )
        self.assertEqual("dynasty", template["sections"]["dynasty"]["settings"]["required_tag"])
        self.assertEqual("dfs", template["sections"]["dfs"]["settings"]["required_tag"])
        self.assertNotIn("assistant", path.read_text(encoding="utf-8").lower())

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
        types = [template["sections"][key]["type"] for key in template["order"]]
        self.assertEqual(["main-article", "postgame-tagged-articles", "featured-product"], types)
        self.assertTrue(template["sections"]["related_product"]["disabled"])
        self.assertIn("candidate.id == article.id", text("sections/postgame-tagged-articles.liquid"))
        blog = data("templates/blog.json")["sections"]["main"]["settings"]
        self.assertEqual("grid", blog["layout"])
        self.assertTrue(blog["show_author"])

    def test_preview_navigation_and_footer_have_no_duplicate_form(self):
        header = data("sections/header-group.json")
        footer = data("sections/footer-group.json")
        self.assertEqual("content-first-preview", header["sections"]["header"]["settings"]["menu"])
        self.assertEqual(
            "content-footer-preview",
            footer["sections"]["footer"]["blocks"]["content_links"]["settings"]["menu"],
        )
        combined = json.dumps(data("templates/index.json")) + json.dumps(footer)
        self.assertEqual(1, combined.count("form-embed-block"))


if __name__ == "__main__":
    unittest.main()
