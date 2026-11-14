"""Tests of tools/roleplay_models.py against stored answers: rankings.json is a made-up answer in the shape the
Data API documents (three ISO weeks, the last too recent to count, the models the ranking of 2026-11-07 named plus twelve
"test/tail-NN", and the row "other"); models.json the models of OpenRouter's model list of 2026-11-09 the ranking
names, with their ":batch" and ":free" variants (gemini-3-flash-preview left out); arena.json twenty-five LMArena
rows of creative writing in the shape the datasets server answers, the first fifteen proprietary, the licensing
of the others the site's open ones. Never the live APIs.

    python -m unittest discover -s tools/tests
"""

import json
import os
import sys
import tempfile
import unittest
import urllib.error
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
        self.arena = load("arena.json")

    def table(self):
        _, _, tokens, before = rm.weeks(self.answer)
        return rm.rows(tokens, before, self.prices)

    def test_last_whole_week_and_the_one_before(self):
        as_of, monday, tokens, before = rm.weeks(self.answer)
        self.assertEqual((as_of, monday, len(tokens), len(before)), ("2026-11-16", date(2026, 11, 2), 22, 21))
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

    def test_free_variant_priced_as_itself(self):
        row = rm.rows({"google/gemma-4-31b-it-20260402:free": rm.Decimal(5)}, {}, self.prices)[0]
        self.assertEqual((row["slug"], rm.money(row["input"])), ("google/gemma-4-31b-it:free", "$0.00"))

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
        arena, arena_as_of = rm.arena_tables(self.arena)
        page = rm.render(as_of, monday, rm.rows(tokens, before, self.prices), arena, arena_as_of)
        self.assertIn("Source: OpenRouter (openrouter.ai/rankings), as of 2026-11-16. Licensed under CC BY 4.0.", page)
        self.assertIn("on OpenRouter from 2 to 8 November 2026, compared with the week before.", page)
        self.assertIn("Last updated 16 November 2026.", page)
        self.assertIn('href="https://openrouter.ai/deepseek/deepseek-v4.1-flash-1017"', page)
        self.assertIn('<td>2.2B</td><td><span class="down"><span class="arrow">▼</span>50%</span></td>', page)
        self.assertNotIn("tail-11", page)
        self.assertEqual([rm.count(rm.Decimal(v)) for v in (830_000_000, 12_400, 4_250_000_000, 15_000_000_000)], ["830M", "12K", "4.2B", "15B"])
        self.assertEqual(rm.spoken_week(date(2026, 10, 26)), "26 October to 1 November 2026")
        self.assertEqual([rm.money(rm.per_million(v)) for v in ("0.000003", "0.0000000434", "0")], ["$3.00", "$0.0434", "$0.00"])
        self.assertEqual(rm.money(None), "—")

    def test_failed_fetch_leaves_page(self):
        with tempfile.TemporaryDirectory() as d:
            page = os.path.join(d, "page.html")
            with open(page, "w", encoding="utf-8") as f:
                f.write("old")
            self.answer["data"] = []
            with self.assertRaises(ValueError):
                rm.write_page(page, self.answer, self.prices, self.arena)
            with open(page, encoding="utf-8") as f:
                self.assertEqual(f.read(), "old")


class Arena(unittest.TestCase):
    def setUp(self):
        self.arena = load("arena.json")

    def test_buckets_are_the_license_switches(self):
        tables, as_of = rm.arena_tables(self.arena)
        self.assertEqual(as_of, "2026-11-09")
        self.assertEqual(len(tables["all"]), 25)  # the fixture's 25 rows; the 100 cap is tested below
        self.assertEqual(len(tables["proprietary"]), 15)
        self.assertEqual(len(tables["open"]), 10)
        self.assertTrue(all(r["license"] == "Proprietary" for r in tables["proprietary"]))
        self.assertTrue(all(r["license"] != "Proprietary" for r in tables["open"]))

    def test_rank_and_overall_rank(self):
        tables, _ = rm.arena_tables(self.arena)
        body = rm.arena_body(tables["open"], True, None)
        self.assertTrue(body.startswith('      <tr><td>1</td><td>16</td><td class="model-col">'))
        self.assertIn("DeepSeek V4.1 (Thinking)", body)  # the first open model is the category's 16th
        self.assertTrue(rm.arena_body(tables["all"], False, None).startswith('      <tr><td>1</td><td></td><td class="model-col">'))

    def test_open_models_tagged_in_the_all_view_only(self):
        tables, _ = rm.arena_tables(self.arena)
        tag = '<span class="open-tag">Open Source</span>'
        self.assertEqual(rm.arena_body(tables["all"], False, None).count(tag), 10)
        self.assertIn('Qwen 4 Max ' + tag + '</td>',rm.arena_body(tables["all"], False, None))
        self.assertNotIn(tag, rm.arena_body(tables["open"], True, None))

    def test_shows_a_hundred_entries(self):
        rows = [{"rank": i, "license": "Proprietary" if i % 2 else "Apache 2.0",
                 "leaderboard_publish_date": "2026-11-09"} for i in range(1, 151)]
        tables, _ = rm.arena_tables(rows)
        self.assertEqual([len(tables[k]) for k in ("all", "proprietary", "open")], [100, 75, 75])

    def before(self):
        """The leaderboard of a week earlier: the first and third swapped, the first open model not yet listed."""
        rows = [dict(r, leaderboard_publish_date="2026-11-02") for r in self.arena if r["rank"] != 16]
        rows[0]["rank"], rows[2]["rank"] = 3, 1
        return rows

    def test_change_against_the_week_before_in_each_switch(self):
        tables, _ = rm.arena_tables(self.arena)
        then = rm.arena_places(self.before())
        cells = lambda view: [c.split("</td>")[0] for c in rm.arena_body(tables[view], view != "all", then[view])
                              .split('<td class="change">')[1:]]
        self.assertEqual(cells("all")[:3], ['<span class="up"><span class="arrow">▲</span>2</span>', "0",
                                            '<span class="down"><span class="arrow">▼</span>2</span>'])
        self.assertEqual(cells("open")[:2], ["new", '<span class="down"><span class="arrow">▼</span>1</span>'])
        self.assertEqual(set(cells("proprietary")[3:]), {"0"})
        self.assertEqual(set(c.split("</td>")[0] for c in rm.arena_body(tables["all"], False, None)
                             .split('<td class="change">')[1:]), {"—"})

    def test_compared_with_the_last_leaderboard_a_week_or_more_before(self):
        days = ["2026-10-28", "2026-11-03", "2026-11-02", "2026-11-06", "2026-11-09"]
        self.assertEqual(rm.week_before(days, "2026-11-09"), "2026-11-02")
        self.assertIsNone(rm.week_before(["2026-11-06"], "2026-11-09"))

    def test_page(self):
        tables, arena_as_of = rm.arena_tables(self.arena)
        _, monday, tokens, before = rm.weeks(load("rankings.json"))
        page = rm.render("2026-11-16", monday, rm.rows(tokens, before, load("models.json")), tables, arena_as_of,
                         rm.arena_places(self.before()), "2026-11-02")
        self.assertIn('<td class="model-col">Gemini 4 Argon (High)</td>'
                      '<td class="change"><span class="up"><span class="arrow">▲</span>2</span></td>', page)
        self.assertNotIn("Google · Proprietary", page)  # no maker and license under the name
        self.assertNotIn("Score", page)
        self.assertIn("Source: LMArena (arena.ai/leaderboard), via Hugging Face (lmarena-ai/leaderboard-dataset),", page)
        self.assertIn("as of 2026-11-09. Licensed under CC BY 4.0.", page)
        self.assertIn("Last updated 9 November 2026.", page)
        self.assertEqual(page.count("<th>Overall Rank</th>"), 2)  # only the license switches show it
        self.assertIn('<thead><tr><th>Rank</th><th></th><th class="model-col">Model</th><th>Change</th></tr></thead>', page)
        self.assertEqual(page.count('<colgroup><col class="w-rank" /><col class="w-overall-rank" />'
                                    '<col class="w-model" /><col class="w-change" /></colgroup>'), 3)
        self.assertIn('data-license="open"', page)
        self.assertNotIn("data-category", page)  # creative writing only
        self.assertNotIn("Overall</label>", page)
        self.assertIn('role="tablist"', page)
        self.assertIn('aria-controls="panel-arena"', page)
        self.assertIn('id="arena-license-all" value="all" checked', page)
        self.assertIn("The highest rated models for creative writing on LMArena, compared with its leaderboard of"
                      " 2 November 2026. Last updated 9 November 2026.", page)
        self.assertNotIn("where people choose between two", page)  # the old long intro
        self.assertIn(">OpenRouter</button>", page)
        self.assertIn('"@type": "Article", "headline": "Popular roleplay models and LMArena creative writing rankings"', page)
        self.assertIn('"datePublished": "2026-11-08", "dateModified": "2026-11-16"', page)

    def test_where_the_filter_fails_the_rows_pages_are_scanned(self):
        calls = []

        def broken(url, key=None):
            calls.append(url)
            if "filter?" in url:
                raise urllib.error.HTTPError(url, 500, "down", None, None)
            return {"rows": [{"row": r} for r in self.arena]}

        original = rm.fetch
        rm.fetch = broken
        try:
            rows = rm.arena_category("creative_writing")
        finally:
            rm.fetch = original
        self.assertEqual([r["rank"] for r in rows], list(range(1, 26)))
        self.assertIn("filter?", calls[0])
        self.assertIn("rows?", calls[1])

    def test_where_the_history_cannot_be_fetched_it_is_empty(self):
        def broken(url, key=None):
            raise urllib.error.HTTPError(url, 500, "down", None, None)

        original = rm.fetch
        rm.fetch = broken
        try:
            self.assertEqual(rm.arena_history("creative_writing", "2026-11-09"), [])
        finally:
            rm.fetch = original

    def test_the_week_before_comes_from_the_cache_not_from_hugging_face(self):
        old = [{"model_name": r["model_name"], "rank": r["rank"], "license": r["license"]} for r in self.arena[:5]]
        cache = {"2026-11-02": old, "2026-10-20": old}

        def forbidden(url, key=None):
            self.fail("Hugging Face was asked")

        original = rm.fetch
        rm.fetch = forbidden
        try:
            before, cache = rm.arena_cached(cache, self.arena)
        finally:
            rm.fetch = original
        self.assertEqual(len(before), 5)
        self.assertEqual({r["leaderboard_publish_date"] for r in before}, {"2026-11-02"})
        self.assertEqual(before[0]["model_name"], self.arena[0]["model_name"])
        self.assertEqual(sorted(cache), ["2026-11-02", "2026-11-09"])
        self.assertEqual(set(cache["2026-11-09"][0]), {"model_name", "rank", "license"})

    def test_no_rows_fails(self):
        with self.assertRaises(ValueError):
            rm.arena_tables([])


if __name__ == "__main__":
    unittest.main()
