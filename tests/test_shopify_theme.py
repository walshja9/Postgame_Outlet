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


if __name__ == "__main__":
    unittest.main()
