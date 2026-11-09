"""Tests of tools/roleplay_models.py against stored answers: rankings.json is a made-up answer in the shape the
Data API documents (three ISO weeks, the last partial, the models the ranking of 2026-11-07 named plus twelve
"test/tail-NN", and the row "other"); models.json the models of OpenRouter's model list of 2026-11-09 the ranking
names, with their ":batch" and ":free" variants (gemini-3-flash-preview left out). Never the live APIs.

    python -m unittest discover -s tools/tests
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import roleplay_models as rm  # noqa: E402


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


class Ranking(unittest.TestCase):
    def setUp(self):
        self.answer = load("rankings.json")
        self.prices = load("models.json")

    def table(self):
        _, _, tokens, before = rm.weeks(self.answer)
        return rm.rows(tokens, before, self.prices)

    def test_last_whole_week_and_the_one_before(self):
        as_of, monday, tokens, before = rm.weeks(self.answer)
        self.assertEqual((as_of, monday, len(tokens), len(before)), ("2026-11-09", date(2026, 11, 2), 22, 21))
        self.assertNotIn("other", tokens)

    def test_no_whole_week_fails(self):
        self.answer["meta"]["end_date"] = "2026-10-31"
        with self.assertRaises(ValueError):
            rm.weeks(self.answer)

    def test_top_twenty_by_tokens_with_change(self):
        rows = self.table()
        self.assertEqual(len(rows), 20)
        self.assertEqual([r["tokens"] for r in rows], sorted((r["tokens"] for r in rows), reverse=True))
        changes = {r["slug"]: r["change"] for r in rows}
        self.assertEqual(changes["deepseek/deepseek-v4-flash-0731"], "▼ 50%")
        self.assertEqual(changes["deepseek/deepseek-v4.1-flash-1017"], "▲ 25%")
        self.assertEqual(changes["mistralai/mistral-nemo"], "new")
        self.assertEqual(changes["google/gemma-4-31b-it"], "0%")

    def test_without_the_week_before_no_change(self):
        _, _, tokens, _ = rm.weeks(self.answer)
        self.assertEqual({r["change"] for r in rm.rows(tokens, None, self.prices)}, {None})

    def test_every_version_its_own_row_and_priced(self):
        rows = self.table()
        flash = [r for r in rows if r["slug"].startswith("deepseek/deepseek-v4.1-flash")]
        self.assertEqual([(r["slug"], r["name"]) for r in flash],
                         [("deepseek/deepseek-v4.1-flash-1017", "DeepSeek V4.1 Flash 1017"), ("deepseek/deepseek-v4.1-flash", "DeepSeek V4.1 Flash")])
        self.assertEqual([rm.money(flash[0]["input"]), rm.money(flash[0]["output"])], ["$0.006", "$0.50"])
        gemini = next(r for r in rows if "gemini" in r["slug"])
        self.assertEqual((gemini["input"], gemini["output"]), (None, None))

    def test_page(self):
        as_of, monday, tokens, before = rm.weeks(self.answer)
        page = rm.render(as_of, monday, rm.rows(tokens, before, self.prices))
        self.assertIn("Source: OpenRouter (openrouter.ai/rankings), as of 2026-11-09. Licensed under CC BY 4.0.", page)
        self.assertIn("in the week of 2–8 November 2026.", page)
        self.assertIn("Updated every day; last updated 9 November 2026.", page)
        self.assertIn('href="https://openrouter.ai/deepseek/deepseek-v4.1-flash-1017"', page)
        self.assertIn("<td>2.2B</td><td>▼ 50%</td>", page)
        self.assertNotIn("tail-11", page)
        self.assertEqual([rm.count(rm.Decimal(v)) for v in (830_000_000, 12_400, 4_250_000_000, 15_000_000_000)], ["830M", "12K", "4.2B", "15B"])
        self.assertEqual(rm.spoken_week(date(2026, 10, 26)), "26 October – 1 November 2026")
        self.assertEqual([rm.money(rm.per_million(v)) for v in ("0.000003", "0.0000000434", "0")], ["$3.00", "$0.0434", "$0.00"])
        self.assertEqual(rm.money(None), "—")

    def test_failed_fetch_leaves_page(self):
        with tempfile.TemporaryDirectory() as d:
            page = os.path.join(d, "page.html")
            with open(page, "w", encoding="utf-8") as f:
                f.write("old")
            self.answer["data"] = []
            with self.assertRaises(ValueError):
                rm.write_page(page, self.answer, self.prices)
            with open(page, encoding="utf-8") as f:
                self.assertEqual(f.read(), "old")


if __name__ == "__main__":
    unittest.main()
