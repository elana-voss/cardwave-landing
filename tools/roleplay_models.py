"""Writes roleplay-models.html: two leaderboards on one page behind tabs. First, OpenRouter's most used models for
roleplay and fiction last week, each with its estimated tokens, its change against the week before and its OpenRouter
price. Second, LMArena's highest rated models for creative writing (arena.ai), every model with its score and,
under its name, its provider and license, behind the license switch (All, Proprietary, Open Source).

    OPENROUTER_API_KEY=... python tools/roleplay_models.py
    python tools/roleplay_models.py <rankings.json> <models.json> <arena.json>   (stored answers, no network)

The ranking is the Data API's (GET /api/v1/datasets/rankings-daily?category=roleplay&period=week; CC BY 4.0, the
page carries its source line): per week, the top 50 models by tokens, estimated from a sample; OpenRouter's terms
forbid scraping its site. Names, pages and prices are OpenRouter's own model list (GET /api/v1/models, no key),
dollars per token. Traps:
- The category data is weekly only (period=day is a 400); a row's date is its ISO week's Monday. The sample lags:
  on 2026-11-09 (end_date 11-08) the week of 11-02 held 2.8T tokens against 4.5T and 4.3T the two before, every model
  lower. So a week counts only once the week after it has ended too; the row "other" is the long tail, never shown.
- A variant the ranking names (dated id plus ":free") is priced as that variant: canonical_slug plus its suffix.
- The ranking names dated versions (deepseek/deepseek-v4.1-flash-20261017), each its own model with its own price:
  the model list's canonical_slug is that id, its id the page (deepseek/deepseek-v4.1-flash-1017). Every version is a
  row; a variant (":batch", ":free") is never the one priced.
- A failed fetch or an answer without a counted week raises before the page is written: the last page stays.
- The day the page shows is the ranking's as_of, so the daily job commits when that, a week or a price changed.
LMArena's numbers are Hugging Face's (lmarena-ai/leaderboard-dataset, CC BY 4.0, no key): the text arena with style
control, its latest public leaderboard. Traps:
- "category" values use underscores (creative_writing) and one page of the rows API holds 100 rows, so a category
  comes in pages of ranks until every license switch holds its models or the ranks run out. The datasets server
  answers 500 while its auth check is down ("try again later"); fetch() tries ten times, close together,
  and where the filter keeps failing the rows pages are scanned instead.
- A model's "rank" is its rank among every model of the category whatever the license. The license switch drives
  the columns. All: "Rank", starting at 1, the rank across all the models. Proprietary and Open Source: "Rank",
  starting at 1, the model's place in that switch; then "Overall Rank", the same rank All shows — ascending but
  with gaps, as the switch filters models out. "Proprietary" is the license "Proprietary"; every other license is
  "Open Source".
- The score is the Bradley-Terry rating as the site shows it ("1525 ±10", the ± half the confidence interval); an
  answer whose row lacks it or whose answer holds no rows raises before the page is written.
The page's own switches are semantic HTML (an ARIA tablist, a radio group) in the page's look, run by the small
vanilla script at the page's foot; every table is plain HTML first, the script only hides what is not chosen.
Standard library only. Tests: tools/tests/.
"""

import html
import json
import os
import sys
import time
from datetime import date, timedelta
from decimal import Decimal
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from build import asset  # noqa: E402  the stylesheet's address with its hash, as every page links it
PAGE = os.path.join(ROOT, "roleplay-models.html")
RANKING_URL = "https://openrouter.ai/api/v1/datasets/rankings-daily?category=roleplay&period=week&start_date={start}"
PRICES_URL = "https://openrouter.ai/api/v1/models"
ARENA_URL = ("https://datasets-server.huggingface.co/filter?dataset=lmarena-ai/leaderboard-dataset"
             "&config=text_style_control&split=latest&where={where}&length=100")
ARENA_SCAN = ("https://datasets-server.huggingface.co/rows?dataset=lmarena-ai/leaderboard-dataset"
              "&config=text_style_control&split=latest&offset={offset}&length=100")
SHOWN = 20
ARENA_SHOWN = 100  # entries per LMArena view
WEEK = timedelta(days=7)
MONTHS = "January February March April May June July August September October November December".split()


def fetch(url, key=None):
    """The answer as JSON, ten tries: the datasets server 500s while its auth check is down."""
    headers = {"User-Agent": "cardwave.cc roleplay-models"}
    if key:
        headers["Authorization"] = "Bearer " + key
    for attempt in range(10):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == 9:
                raise
        except OSError:  # URLError, timeouts and connection resets: the network's blips
            if attempt == 9:
                raise
        time.sleep(4)


def weeks(answer):
    """(as_of day, last counted week's Monday, its tokens by model, the week before's or None); ValueError without one."""
    meta = answer.get("meta") or {}
    end = date.fromisoformat(meta["end_date"])
    by_week = {}
    for row in answer.get("data") or []:
        monday = date.fromisoformat(row["date"])
        if row["model_permaslug"] != "other" and monday + timedelta(days=13) <= end:
            by_week.setdefault(monday, {})[row["model_permaslug"]] = Decimal(row["total_tokens"])
    if not by_week:
        raise ValueError("the answer has no counted week of roleplay rows")
    last = max(by_week)
    return meta["as_of"][:10], last, by_week[last], by_week.get(last - WEEK)


def rows(tokens, before, catalogue):
    """The SHOWN models with most tokens, every version its own, with their change, OpenRouter's name, page and price."""
    listed = {}
    for m in catalogue.get("data") or []:
        if ":" in m["id"]:
            listed.setdefault((m.get("canonical_slug") or m["id"].split(":")[0]) + ":" + m["id"].split(":", 1)[1], m)
        else:
            listed.setdefault(m.get("canonical_slug") or m["id"], m)
            listed.setdefault(m["id"], m)
    table = []
    for slug, count in sorted(tokens.items(), key=lambda item: -item[1])[:SHOWN]:
        entry = listed.get(slug) or {}
        pricing = entry.get("pricing") or {}
        table.append({
            "slug": entry.get("id") or slug,
            "name": (entry.get("name") or slug.split("/")[-1]).split(": ", 1)[-1],
            "tokens": count,
            "change": change(count, before.get(slug)) if before is not None else None,
            "input": per_million(pricing.get("prompt")),
            "output": per_million(pricing.get("completion")),
        })
    return table


def change(now, then):
    """The week's change as the page says it: ▲ 12%, ▼ 5%, 0%, or "new" where the week before did not list it."""
    if not then:
        return "new"
    percent = round((now / then - 1) * 100)
    return "▲ {}%".format(percent) if percent > 0 else "▼ {}%".format(-percent) if percent < 0 else "0%"


def count(value):
    """Tokens as a reader says them: 4.2B, 830M, 12K."""
    for size, unit in ((10 ** 12, "T"), (10 ** 9, "B"), (10 ** 6, "M"), (10 ** 3, "K")):
        if value >= size:
            short = value / size
            return ("{:.1f}".format(short) if short < 10 else "{:.0f}".format(short)) + unit
    return "{:.0f}".format(value)


def per_million(text):
    """OpenRouter's dollars per token (a string) as dollars per million tokens; None where none is listed."""
    if text is None or Decimal(text) < 0:
        return None
    return Decimal(text) * 1000000


def money(value):
    """Dollars as OpenRouter writes them: every digit it has, cents at least: $0.006, $0.50, $0.0434, $3.00."""
    if value is None:
        return "—"
    value = value.normalize()
    return "$" + ("{:.2f}".format(value) if value.as_tuple().exponent >= -2 else "{:f}".format(value))


def spoken_day(day):
    """A day as a reader says it: 2026-11-07 is 7 November 2026."""
    day = date.fromisoformat(day) if isinstance(day, str) else day
    return "{} {} {}".format(day.day, MONTHS[day.month - 1], day.year)


def spoken_week(monday):
    """A week as a reader says it: 2 to 8 November 2026, 27 October to 2 November 2026."""
    sunday = monday + timedelta(days=6)
    if monday.month == sunday.month:
        return "{} to {}".format(monday.day, spoken_day(sunday))
    if monday.year == sunday.year:
        return "{} {} to {}".format(monday.day, MONTHS[monday.month - 1], spoken_day(sunday))
    return "{} to {}".format(spoken_day(monday), spoken_day(sunday))


def changed(text):
    """The change's cell: the arrow at the cell's left, so it stays put whatever the number's width."""
    if not text:
        return "—"
    if text[0] in "▲▼":
        return '<span class="{}"><span class="arrow">{}</span>{}</span>'.format("up" if text[0] == "▲" else "down", text[0], text[2:])
    return text


def arena_category(where_name):
    """One category's rows of the latest LMArena text leaderboard, best rank first. The filter query is the direct
    way; where the server keeps 500ing ("try again later", its auth check is down), the rows pages are scanned
    instead, spending pages only until the category's rows run out."""
    try:
        return arena_filtered(where_name)
    except OSError:
        return arena_scanned(where_name)


def arena_filtered(where_name):
    """The category's rows as the rows API's filter answers them, in pages of 100 ranks."""
    rows = []
    for low in range(1, 3000, 100):
        where = '"category"=\'{}\' AND "rank">={} AND "rank"<={}'.format(where_name, low, low + 99)
        answer = fetch(ARENA_URL.format(where=urllib.parse.quote(where)))
        rows += [r["row"] for r in answer.get("rows") or []]
        if len(answer.get("rows") or []) < 100 or arena_filled(rows):
            break
    return sorted(rows, key=lambda r: r["rank"])


def arena_scanned(where_name):
    """The category's rows out of the rows API's pages, 100 rows at a time: the pages order the categories whole,
    ranks ascending within each, so the category's rows run out once its block is behind us."""
    rows = []
    for offset in range(0, 20000, 100):
        answer = fetch(ARENA_SCAN.format(offset=offset))
        page = [r["row"] for r in answer.get("rows") or []]
        rows += [r for r in page if r["category"] == where_name]
        if len(page) < 100 or arena_filled(rows):
            break
    return sorted(rows, key=lambda r: r["rank"])


def arena_filled(rows):
    """True once every license switch holds its ARENA_SHOWN models."""
    prop = sum(1 for r in rows if r["license"] == "Proprietary")
    return len(rows) >= ARENA_SHOWN and prop >= ARENA_SHOWN and len(rows) - prop >= ARENA_SHOWN


def arena_tables(arena_rows):
    """({"all": the top rows, "proprietary": …, "open": …}, the leaderboard's day) for the license switch; the
    "Open Source" switch is every license but "Proprietary"; ValueError where the answer holds no rows."""
    rows = sorted(arena_rows, key=lambda r: r["rank"])
    if not rows:
        raise ValueError("the answer has no rows of the LMArena leaderboard")
    prop = [r for r in rows if r["license"] == "Proprietary"]
    open_ = [r for r in rows if r["license"] != "Proprietary"]
    tables = {"all": rows[:ARENA_SHOWN], "proprietary": prop[:ARENA_SHOWN], "open": open_[:ARENA_SHOWN]}
    return tables, max(r["leaderboard_publish_date"] for r in rows)


def provider(text):
    """The organization as the site names it: google reads Google."""
    return text[:1].upper() + text[1:]


def arena_score(row):
    """The score's cell as the site shows it: 1525 ±10, the rating and half the confidence interval in grey."""
    score = "{}".format(int(round(row["rating"])))
    half = "{}".format(int(round((row["rating_upper"] - row["rating_lower"]) / 2)))
    return '{} <span class="ci">±{}</span>'.format(score, half)


def arena_body(table, filtered):
    """One LMArena table's rows: the model with its provider and license under the name and its score, behind its
    ranks. All leads with "Rank", the model's rank across all the models of the category. Proprietary and Open Source
    lead with "Rank", the model's place in that switch (starting at 1), and show the rank across all the models as
    "Overall Rank" after it — ascending, with gaps where the switch has filtered models out. All leaves the second
    cell empty, so the columns stand still when the switch changes."""
    out = []
    for place, r in enumerate(table, 1):
        lead = "<td>{}</td>".format(place if filtered else int(r["rank"]))
        lead += "<td>{}</td>".format(int(r["rank"]) if filtered else "")
        out.append(
            '      <tr>{}<td class="model-col"><span class="model">{}</span><span class="org">{} · {}</span></td>'
            '<td>{}</td></tr>'.format(
                lead, html.escape(r["model_name"]), html.escape(provider(r["organization"])),
                html.escape(r["license"]), arena_score(r)))
    return "\n".join(out)


def usage_body(table):
    """The OpenRouter table's rows: the place, the model's page, its tokens, its change and its prices."""
    return "\n".join(
        '      <tr><td>{}</td><td class="model-col"><a href="https://openrouter.ai/{}" target="_blank" '
        'rel="noopener noreferrer">{}</a></td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            i, html.escape(r["slug"]), html.escape(r["name"]), count(r["tokens"]), changed(r["change"]),
            money(r["input"]), money(r["output"]))
        for i, r in enumerate(table, 1))


def render(as_of, monday, table, arena, arena_as_of):
    return TEMPLATE.format(
        as_of=html.escape(as_of), updated=spoken_day(as_of), week=spoken_week(monday), usage_rows=usage_body(table),
        arena_as_of=html.escape(arena_as_of), arena_updated=spoken_day(arena_as_of),
        arena_all=arena_body(arena["all"], False),
        arena_proprietary=arena_body(arena["proprietary"], True),
        arena_open=arena_body(arena["open"], True),
        style=asset("style.css"), script=SCRIPT)


def write_page(path, answer, prices, arena_rows):
    """Writes the page from all three answers; raises, leaving the page as it was, when a week or the LMArena's rows are missing."""
    as_of, monday, tokens, before = weeks(answer)
    arena, arena_as_of = arena_tables(arena_rows)
    page = render(as_of, monday, rows(tokens, before, prices), arena, arena_as_of)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)


def main():
    if len(sys.argv) == 4:
        with open(sys.argv[1], encoding="utf-8") as a, open(sys.argv[2], encoding="utf-8") as p, \
                open(sys.argv[3], encoding="utf-8") as m:
            answer, prices, arena_rows = json.load(a), json.load(p), json.load(m)
    else:
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            sys.exit("OPENROUTER_API_KEY is not set")
        start = (date.today() - timedelta(days=28)).isoformat()
        answer, prices = fetch(RANKING_URL.format(start=start), key), fetch(PRICES_URL)
        totals = {}
        for row in answer.get("data") or []:
            totals[row["date"]] = totals.get(row["date"], 0) + int(Decimal(row["total_tokens"]))
        print("meta", answer.get("meta"), "tokens by week", sorted(totals.items()))  # the log's record of what came
        arena_rows = arena_category("creative_writing")
        print("arena", len(arena_rows), max(r["leaderboard_publish_date"] for r in arena_rows))
    write_page(PAGE, answer, prices, arena_rows)


SCRIPT = """  // The page's switches: the tablist of the two leaderboards above and the LMArena's license switch below.
  // The tables are all in the page already; this only hides what is not chosen and runs the tabs.
  (function () {
    var tabs = [].slice.call(document.querySelectorAll('[role="tablist"] [role="tab"]'));

    function select(tab) {
      tabs.forEach(function (other) {
        var chosen = other === tab;
        other.setAttribute('aria-selected', chosen ? 'true' : 'false');
        other.tabIndex = chosen ? 0 : -1;
        document.getElementById(other.getAttribute('aria-controls')).hidden = !chosen;
      });
    }

    tabs.forEach(function (tab, i) {
      tab.addEventListener('click', function () { select(tab); });
      tab.addEventListener('keydown', function (event) {
        var step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
        if (!step) return;
        event.preventDefault();
        var next = tabs[(i + step + tabs.length) % tabs.length];
        next.focus();
        select(next);
      });
    });
    if (tabs.length) select(tabs[0]);

    var tables = [].slice.call(document.querySelectorAll('.arena-table'));
    var switches = [].slice.call(document.querySelectorAll('.switches input'));

    function show() {
      var chosen = null;
      switches.forEach(function (input) { if (input.checked) chosen = input.value; });
      tables.forEach(function (table) {
        table.hidden = table.getAttribute('data-license') !== chosen;
      });
    }

    switches.forEach(function (input) { input.addEventListener('change', show); });
    if (tables.length) show();
  })();
"""

TEMPLATE = """<!doctype html>
<html lang="en">

<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Popular roleplay models and LMArena creative writing rankings</title>
  <meta name="description"
    content="The AI models most used for roleplay and fiction on OpenRouter last week, and LMArena's highest rated models for creative writing, with their scores." />
  <link rel="canonical" href="https://cardwave.cc/roleplay-models.html" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="Cardwave" />
  <meta property="og:url" content="https://cardwave.cc/roleplay-models.html" />
  <meta property="og:title" content="Popular roleplay models and LMArena creative writing rankings" />
  <meta property="og:description"
    content="The AI models most used for roleplay and fiction on OpenRouter last week, and LMArena's highest rated models for creative writing, with their scores." />
  <meta property="og:image" content="https://cardwave.cc/landing_desktop.jpg" />
  <meta property="og:image:width" content="1440" />
  <meta property="og:image:height" content="900" />
  <meta property="og:locale" content="en_US" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="Popular roleplay models and LMArena creative writing rankings" />
  <meta name="twitter:description"
    content="The AI models most used for roleplay and fiction on OpenRouter last week, and LMArena's highest rated models for creative writing, with their scores." />
  <meta name="twitter:image" content="https://cardwave.cc/landing_desktop.jpg" />
  <link rel="icon" href="logo_icon.png" />
  <link rel="preload" href="/fonts/geist-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin />
  <link rel="stylesheet" href="{style}" />
  <style>
    .table-wrap {{ overflow-x: auto; }}
    .ranking {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }}
    .ranking th, .ranking td {{ padding: 8px 10px; border-bottom: 1px solid #e5e5e5; text-align: right; white-space: nowrap; }}
    .ranking .model-col {{ text-align: left; white-space: normal; }}
    .ranking th {{ font-weight: 600; color: #555; font-size: 14px; white-space: normal; }}
    @media (max-width: 480px) {{ .ranking th, .ranking td {{ padding: 8px 4px; font-size: 14px; }} }}
    .ranking .arrow {{ float: left; margin-right: 6px; }}
    .ranking .up {{ color: #1a7f37; }}
    .ranking .down {{ color: #cf222e; }}
    .ranking .model, .ranking .org {{ display: block; }}
    .ranking .org {{ color: #888; font-size: 13px; }}
    .ranking .ci {{ color: #888; }}
    .arena-table .ranking {{ table-layout: fixed; }}
    .arena-table .w-rank {{ width: 64px; }}
    .arena-table .w-overall-rank {{ width: 116px; }}
    .arena-table .w-score {{ width: 112px; }}
    .source {{ color: #888; font-size: 14px; }}
    .tab-bar {{ display: flex; gap: 4px; border-bottom: 1px solid #e5e5e5; margin: 18px 0 14px; }}
    .tab-bar [role="tab"] {{ appearance: none; background: none; border: 1px solid transparent; border-bottom: none;
      border-radius: 6px 6px 0 0; margin-bottom: -1px; padding: 8px 16px; font: inherit; font-weight: 600;
      color: #666; cursor: pointer; }}
    .tab-bar [role="tab"]:hover {{ color: #111; }}
    .tab-bar [role="tab"][aria-selected="true"] {{ background: #fff; border-color: #e5e5e5; color: #111; }}
    .tab-bar [role="tab"]:focus-visible {{ outline: 2px solid #1f6feb; outline-offset: 2px; }}
    .switches {{ display: flex; flex-wrap: wrap; gap: 12px 32px; margin: 0 0 16px; }}
    .switches fieldset {{ border: 0; margin: 0; padding: 0; min-width: 0; }}
    .switches legend {{ padding: 0; margin: 0 0 4px; font-size: 13px; font-weight: 600; color: #888; }}
    .switches input {{ position: absolute; opacity: 0; }}
    .switches label {{ display: inline-block; padding: 3px 12px; margin: 0 4px 4px 0; border: 1px solid #d0d7de;
      border-radius: 999px; color: #555; font-size: 14px; cursor: pointer; }}
    .switches label:hover {{ border-color: #8c959f; color: #111; }}
    .switches input:checked + label {{ background: #1f6feb; border-color: #1f6feb; color: #fff; }}
    .switches input:focus-visible + label {{ outline: 2px solid #1f6feb; outline-offset: 2px; }}
  </style>
  <script src="https://analytics.ahrefs.com/analytics.js" data-key="Vyii1vivGp5eoVeTLVRAwA" async></script>
</head>

<body>

  <header>
    <h1><a href="index.html"><img src="logo_icon.png" alt="" /> Cardwave</a></h1>
    <span class="social">
    <a class="gh" href="https://discord.gg/C62KZVg6J" target="_blank" rel="noopener noreferrer"
      aria-label="Discord">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path
          d="M20.317 4.37a19.79 19.79 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.211.375-.445.865-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.74 19.74 0 0 0 3.677 4.37a.078.078 0 0 0-.032.028C.533 9.046-.32 13.58.099 18.058a.082.082 0 0 0 .031.056 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.873-1.295 1.226-1.994a.076.076 0 0 0-.042-.106 13.1 13.1 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.126-.094.252-.192.372-.291a.074.074 0 0 1 .078-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.009c.12.099.246.198.373.292a.077.077 0 0 1-.006.128 12.3 12.3 0 0 1-1.873.891.077.077 0 0 0-.041.107c.36.698.772 1.363 1.225 1.993a.076.076 0 0 0 .084.028 19.84 19.84 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.029ZM8.02 15.331c-1.183 0-2.157-1.086-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.095 2.157 2.42 0 1.332-.956 2.418-2.157 2.418Zm7.975 0c-1.183 0-2.157-1.086-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.095 2.157 2.42 0 1.332-.946 2.418-2.157 2.418Z" />
      </svg>
    </a>
    <a class="gh" href="https://github.com/elana-voss/cardwave" target="_blank" rel="noopener noreferrer"
      aria-label="GitHub">
      <svg width="28" height="28" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
        <path
          d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
      </svg>
    </a>
    </span>
  </header>

  <p class="page-title"><strong>Popular AI model rankings</strong></p>

  <div class="tabs">
    <div class="tab-bar" role="tablist" aria-label="Leaderboards">
      <button type="button" role="tab" id="tab-usage" aria-controls="panel-usage" aria-selected="true">Open Router</button>
      <button type="button" role="tab" id="tab-arena" aria-controls="panel-arena" aria-selected="false" tabindex="-1">LMArena</button>
    </div>

    <section id="panel-usage" role="tabpanel" aria-labelledby="tab-usage" tabindex="0">
      <p>The most used roleplay and fiction models on OpenRouter from {week}, compared with the week before.
        Last updated {updated}.</p>

      <div class="table-wrap">
        <table class="ranking">
          <thead><tr><th>#</th><th class="model-col">Model</th><th>Tokens</th><th>Change</th><th>Input per 1M</th><th>Output per 1M</th></tr></thead>
          <tbody>
{usage_rows}
          </tbody>
        </table>
      </div>

      <p class="source">Source: OpenRouter (openrouter.ai/rankings), as of {as_of}. Licensed under CC BY 4.0.</p>
    </section>

    <section id="panel-arena" role="tabpanel" aria-labelledby="tab-arena" tabindex="0">
      <p>The highest rated models for creative writing on LMArena. Last updated {arena_updated}.</p>

      <div class="switches">
        <fieldset>
          <legend>License</legend>
          <input type="radio" name="arena-license" id="arena-license-all" value="all" checked />
          <label for="arena-license-all">All</label>
          <input type="radio" name="arena-license" id="arena-license-proprietary" value="proprietary" />
          <label for="arena-license-proprietary">Proprietary</label>
          <input type="radio" name="arena-license" id="arena-license-open" value="open" />
          <label for="arena-license-open">Open Source</label>
        </fieldset>
      </div>

      <div class="table-wrap arena-table" data-license="all">
        <table class="ranking">
          <colgroup><col class="w-rank" /><col class="w-overall-rank" /><col class="w-model" /><col class="w-score" /></colgroup>
          <thead><tr><th>Rank</th><th></th><th class="model-col">Model</th><th>Score</th></tr></thead>
          <tbody>
{arena_all}
          </tbody>
        </table>
      </div>

      <div class="table-wrap arena-table" data-license="proprietary">
        <table class="ranking">
          <colgroup><col class="w-rank" /><col class="w-overall-rank" /><col class="w-model" /><col class="w-score" /></colgroup>
          <thead><tr><th>Rank</th><th>Overall Rank</th><th class="model-col">Model</th><th>Score</th></tr></thead>
          <tbody>
{arena_proprietary}
          </tbody>
        </table>
      </div>

      <div class="table-wrap arena-table" data-license="open">
        <table class="ranking">
          <colgroup><col class="w-rank" /><col class="w-overall-rank" /><col class="w-model" /><col class="w-score" /></colgroup>
          <thead><tr><th>Rank</th><th>Overall Rank</th><th class="model-col">Model</th><th>Score</th></tr></thead>
          <tbody>
{arena_open}
          </tbody>
        </table>
      </div>

      <p class="source">Source: LMArena (arena.ai/leaderboard), via Hugging Face (lmarena-ai/leaderboard-dataset),
        as of {arena_as_of}. Licensed under CC BY 4.0.</p>
    </section>
  </div>

  <hr />
  <footer>Cardwave © 2026. <a href="index.html">Home</a> · <a href="disclaimer.html">Disclaimer &amp; Terms</a></footer>

  <script>
{script}
  </script>

</body>

</html>
"""


if __name__ == "__main__":
    main()
