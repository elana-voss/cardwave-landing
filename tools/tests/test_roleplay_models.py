"""Tests of tools/roleplay_models.py against stored answers: classifications.json is OpenRouter's task ranking of
2026-11-07 cut to two entries, models.json the models of OpenRouter's model list of 2026-11-09 the ranking names,
with their ":batch" and ":free" variants (gemini-3-flash-preview left out). Never the live APIs.

    python -m unittest discover -s tools/tests
"""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import roleplay_models as rm  # noqa: E402


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


class Ranking(unittest.TestCase):
    def setUp(self):
        self.answer = load("classifications.json")
        self.prices = load("models.json")

    def test_roleplay_entry_read(self):
        as_of, days, models = rm.roleplay_entry(self.answer)
        self.assertEqual((as_of, days, len(models)), ("2026-11-07", 7, 10))

    def test_missing_entry_fails(self):
        self.answer["data"]["classifications"] = self.answer["data"]["classifications"][:1]
        with self.assertRaises(ValueError):
            rm.roleplay_entry(self.answer)

    def test_every_version_its_own_row_ranked_and_priced(self):
        _, _, models = rm.roleplay_entry(self.answer)
        rows = rm.rows(models, self.prices)
        self.assertEqual(len(rows), 10)
        flash = [r for r in rows if r["slug"].startswith("deepseek/deepseek-v4.1-flash")]
        self.assertEqual([(r["slug"], r["name"]) for r in flash],
                         [("deepseek/deepseek-v4.1-flash-1017", "DeepSeek V4.1 Flash 1017"), ("deepseek/deepseek-v4.1-flash", "DeepSeek V4.1 Flash")])
        self.assertEqual([rm.money(flash[0]["input"]), rm.money(flash[0]["output"])], ["$0.006", "$0.50"])
        gemma = next(r for r in rows if r["slug"] == "google/gemma-4-31b-it")
        self.assertEqual([rm.money(gemma["input"]), rm.money(gemma["output"])], ["$0.20", "$0.40"])
        self.assertEqual([r["usage"] for r in rows], sorted((r["usage"] for r in rows), reverse=True))
        gemini = next(r for r in rows if "gemini" in r["slug"])
        self.assertEqual((gemini["input"], gemini["output"]), (None, None))

    def test_page(self):
        _, _, models = rm.roleplay_entry(self.answer)
        page = rm.render("2026-11-07", 7, rm.rows(models, self.prices))
        self.assertIn("Source: OpenRouter (openrouter.ai/rankings), as of 2026-11-07. Licensed under CC BY 4.0.", page)
        self.assertNotIn("models.dev", page)
        self.assertIn("Updated every day; last updated 7 November 2026.", page)
        self.assertIn('href="https://openrouter.ai/deepseek/deepseek-v4.1-flash-1017"', page)
        self.assertIn("<td>$0.0434</td><td>$0.30</td>", page)
        self.assertEqual([rm.money(rm.per_million(v)) for v in ("0.000003", "0.0000000434", "0")], ["$3.00", "$0.0434", "$0.00"])
        self.assertEqual(rm.money(None), "—")

    def test_failed_fetch_leaves_page(self):
        with tempfile.TemporaryDirectory() as d:
            page = os.path.join(d, "page.html")
            with open(page, "w", encoding="utf-8") as f:
                f.write("old")
            self.answer["data"]["classifications"] = []
            with self.assertRaises(ValueError):
                rm.write_page(page, self.answer, self.prices)
            with open(page, encoding="utf-8") as f:
                self.assertEqual(f.read(), "old")


if __name__ == "__main__":
    unittest.main()
