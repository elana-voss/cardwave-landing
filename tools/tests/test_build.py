"""Tests of build.py: the language pages it writes, their structured data and the sitemap.

    python -m unittest discover -s tools/tests
"""

import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import build  # noqa: E402


def page(code):
    template = (build.ROOT / "src" / "index.template.html").read_text(encoding="utf-8")
    hl, locale = next((hl, locale) for c, hl, locale, _ in build.LANGS if c == code)
    return build.render(template, code, hl, locale, build.read_texts(code))


def structured(text):
    return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S)]


class Build(unittest.TestCase):
    def test_a_section_without_heading_and_text_is_left_out(self):
        self.assertNotIn("<h2></h2>", page("en"))
        self.assertIn('<a href="/providers.html">', page("de").split("<h2>Unterstützte Anbieter</h2>")[1])

    def test_home_pages_name_the_organization_and_the_site(self):
        [data] = structured(page("ja"))
        types = {item["@type"]: item for item in data["@graph"]}
        self.assertEqual(types["Organization"]["logo"], "https://cardwave.cc/logo_icon.png")
        self.assertEqual(types["WebSite"]["name"], "Cardwave")

    def test_articles_carry_their_headline_and_publisher(self):
        [data] = structured(build.article_schema("ccv4.html"))
        self.assertEqual(data["@type"], "Article")
        self.assertEqual(data["headline"], "CCV4, a new character card format — Cardwave")
        self.assertEqual(data["publisher"]["name"], "Cardwave")

    def test_every_page_in_the_sitemap_has_its_day(self):
        original = build.lastmod
        build.lastmod = lambda name: "2026-11-13"
        try:
            sitemap = build.sitemap()
        finally:
            build.lastmod = original
        self.assertEqual(sitemap.count("<lastmod>2026-11-13</lastmod>"), sitemap.count("<url>"))


if __name__ == "__main__":
    unittest.main()
