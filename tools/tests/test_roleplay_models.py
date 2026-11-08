"""Tests of tools/roleplay_models.py against stored answers: classifications.json is OpenRouter's task ranking of
2026-11-07 cut to two entries, models.dev.json a few of models.dev's OpenRouter models (deepseek-v4-pro without its
undated entry, gemini-3-flash-preview left out). Never the live APIs.

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
        self.prices = load("models.dev.json")

    def test_roleplay_entry_read(self):
        as_of, days, models = rm.roleplay_entry(self.answer)
        self.assertEqual((as_of, days, len(models)), ("2026-11-07", 7, 10))

    def test_missing_entry_fails(self):
        self.answer["data"]["classifications"] = self.answer["data"]["classifications"][:1]
        with self.assertRaises(ValueError):
            rm.roleplay_entry(self.answer)

    def test_dated_versions_merged_ranked_and_priced(self):
        _, _, models = rm.roleplay_entry(self.answer)
        rows = rm.rows(models, self.prices)
        self.assertEqual([r["slug"] for r in rows[:2]], ["deepseek/deepseek-v4.1-flash", "deepseek/deepseek-v4-flash"])
        self.assertEqual(len(rows), 8)
        first = rows[0]
        self.assertEqual(first["name"], "DeepSeek V4.1 Flash")
        self.assertAlmostEqual(first["usage"], 0.241)
        self.assertAlmostEqual(first["tokens"], 0.218)
        self.assertEqual((first["input"], first["output"]), (0.056, 0.12))
        pro = next(r for r in rows if r["slug"] == "deepseek/deepseek-v4-pro")
        self.assertEqual((pro["input"], pro["output"]), (0.66, 1.98))
        gemini = rows[-1]
        self.assertEqual((gemini["name"], gemini["input"], gemini["output"]), ("gemini-3-flash-preview", None, None))

    def test_page(self):
        _, _, models = rm.roleplay_entry(self.answer)
        page = rm.render("2026-11-07", 7, rm.rows(models, self.prices))
        self.assertIn("Source: OpenRouter (openrouter.ai/rankings), as of 2026-11-07. Licensed under CC BY 4.0.", page)
        self.assertIn("models.dev", page)
        self.assertIn('href="https://openrouter.ai/deepseek/deepseek-v4.1-flash"', page)
        self.assertIn("24.1%", page)
        self.assertIn("$0.056", page)
        self.assertIn("<td>$0.66</td><td>$1.98</td>", page)
        self.assertEqual([rm.money(v) for v in (0.423864, 3, 0.029, 0.03, None)], ["$0.424", "$3.00", "$0.029", "$0.03", "—"])
        self.assertIn("<td>—</td>", page)

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
