"""Writes roleplay-models.html: two leaderboards on one page behind tabs. First, OpenRouter's most used models for
roleplay and fiction last week, each with its estimated tokens, its change against the week before and its OpenRouter
price. Second, LMArena's highest rated models for creative writing (arena.ai), every model with its change in places
against the leaderboard of a week before and, under its name, its provider and license, behind the license switch
(All, Proprietary, Open Source).

    OPENROUTER_API_KEY=... python tools/roleplay_models.py
    python tools/roleplay_models.py <rankings.json> <models.json> <arena.json> [<arena_before.json>]   (no network)

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
- The change is in places against the last leaderboard published a week or more before (the "full" split holds
  every leaderboard, one every few days; kept in data/arena-history.json, name, rank and license of each day, so
  Hugging Face is asked for history only where the file has no day a week or more before): the "rank" values are
  1, 2, 3 without ties, and each switch compares the model's place in that switch then and now (▲ 2, ▼ 1, 0, "new" where that leaderboard lacks the name). The whole
  category is fetched for that day (about 420 rows), so a model that climbed from far below still shows its climb.
  The full split is too big to scan, so where its filter keeps failing the change column is left empty.
- The filter also answers 422 while the auth check is down; fetch() tries that again too.
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
from build import article, asset  # noqa: E402  the page's structured data; the stylesheet's address with its hash
PAGE = os.path.join(ROOT, "roleplay-models.html")
ARENA_CACHE = os.path.join(ROOT, "data", "arena-history.json")
CACHED = ("model_name", "rank", "license")  # the fields of a cached leaderboard row
RANKING_URL = "https://openrouter.ai/api/v1/datasets/rankings-daily?category=roleplay&period=week&start_date={start}"
PRICES_URL = "https://openrouter.ai/api/v1/models"
ARENA_URL = ("https://datasets-server.huggingface.co/filter?dataset=lmarena-ai/leaderboard-dataset"
             "&config=text_style_control&split=latest&where={where}&length=100")
ARENA_FULL = ("https://datasets-server.huggingface.co/filter?dataset=lmarena-ai/leaderboard-dataset"
              "&config=text_style_control&split=full&where={where}&offset={offset}&length=100")
ARENA_SCAN = ("https://datasets-server.huggingface.co/rows?dataset=lmarena-ai/leaderboard-dataset"
              "&config=text_style_control&split=latest&offset={offset}&length=100")
SHOWN = 20
ARENA_SHOWN = 100  # entries per LMArena view
WEEK = timedelta(days=7)
MONTHS = "January February March April May June July August September October November December".split()


def fetch(url, key=None):
    """The answer as JSON, ten tries: the datasets server 500s or 422s while its auth check is down."""
    headers = {"User-Agent": "cardwave.cc roleplay-models"}
    if key:
        headers["Authorization"] = "Bearer " + key
    for attempt in range(10):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if (e.code < 500 and e.code != 422) or attempt == 9:
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


def week_before(days, latest):
    """The day of the last leaderboard published a week or more before the latest one; None where there is none."""
    earlier = [d for d in days if d <= (date.fromisoformat(latest) - WEEK).isoformat()]
    return max(earlier) if earlier else None


def arena_full(where):
    """Every row of the full split that the filter `where` names, in pages of 100."""
    rows = []
    for offset in range(0, 20000, 100):
        answer = fetch(ARENA_FULL.format(where=urllib.parse.quote(where), offset=offset))
        rows += [r["row"] for r in answer.get("rows") or []]
        if len(answer.get("rows") or []) < 100:
            break
    return rows


def arena_history(where_name, latest):
    """The category's whole leaderboard of a week or more before `latest`; [] where none was published in the five
    weeks before it, or where it cannot be fetched."""
    start = (date.fromisoformat(latest) - 5 * WEEK).isoformat()
    try:
        tops = arena_full('"category"=\'{}\' AND "rank"=1 AND "leaderboard_publish_date">=\'{}\''.format(where_name, start))
        day = week_before([r["leaderboard_publish_date"] for r in tops], latest)
        if day is None:
            return []
        return arena_full('"category"=\'{}\' AND "leaderboard_publish_date"=\'{}\''.format(where_name, day))
    except (urllib.error.HTTPError, OSError) as error:
        print("The earlier LMArena leaderboard could not be fetched ({}); the change column is left empty.".format(error))
        return []


def arena_cached(cache, arena_rows):
    """(the leaderboard of a week before, the cache to keep): today's board joins `cache` ({day: slim rows}); the week
    before comes from it, else from arena_history() (stored too); days older than the one used are dropped."""
    latest = max(r["leaderboard_publish_date"] for r in arena_rows)
    slim = lambda rows: [{k: r[k] for k in CACHED} for r in rows]
    cache = dict(cache, **{latest: slim(arena_rows)})
    day = week_before(list(cache), latest)
    if day:
        before = [dict(r, leaderboard_publish_date=day) for r in cache[day]]
    else:
        before = arena_history("creative_writing", latest)
        if before:
            day = before[0]["leaderboard_publish_date"]
            cache[day] = slim(before)
    keep_from = day or (date.fromisoformat(latest) - 5 * WEEK).isoformat()
    return before, {d: r for d, r in cache.items() if d >= keep_from}


def arena_cache_load(path):
    """The cache file's days; {} where it is missing or unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            cache = json.load(f)
    except (OSError, ValueError):
        return {}
    return cache if isinstance(cache, dict) else {}


def arena_cache_save(path, cache):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cache, f, sort_keys=True)  # one line: a data file, not counted as code lines
        f.write("\n")


def arena_views(arena_rows):
    """Every row of each license switch, best rank first: All, "Proprietary" and "Open Source" (every other license)."""
    rows = sorted(arena_rows, key=lambda r: r["rank"])
    return {"all": rows, "proprietary": [r for r in rows if r["license"] == "Proprietary"],
            "open": [r for r in rows if r["license"] != "Proprietary"]}


def arena_tables(arena_rows):
    """({"all": the top rows, "proprietary": …, "open": …}, the leaderboard's day) for the license switch;
    ValueError where the answer holds no rows."""
    if not arena_rows:
        raise ValueError("the answer has no rows of the LMArena leaderboard")
    tables = {view: rows[:ARENA_SHOWN] for view, rows in arena_views(arena_rows).items()}
    return tables, max(r["leaderboard_publish_date"] for r in arena_rows)


def arena_places(arena_rows):
    """Each switch's place of every model, by name: {"all": {"Gemini 4 Argon (High)": 1, …}, …}."""
    return {view: {r["model_name"]: place for place, r in enumerate(rows, 1)}
            for view, rows in arena_views(arena_rows).items()}


def moved(now, then):
    """A model's change in places as the page says it: ▲ 2, ▼ 1, 0, or "new" where the week before lacks it."""
    if then is None:
        return "new"
    return "▲ {}".format(then - now) if then > now else "▼ {}".format(now - then) if then < now else "0"


def arena_body(table, filtered, then):
    """One LMArena table's rows: the model and its change against
    `then` (that switch's places a week before; None where there is no such leaderboard: "—"), behind its ranks.
    All leads with "Rank", the model's rank across all the models of the category. Proprietary and Open Source
    lead with "Rank", the model's place in that switch (starting at 1), and show the rank across all the models as
    "Overall Rank" after it — ascending, with gaps where the switch has filtered models out. All leaves the second
    cell empty, so the columns stand still when the switch changes. In All, where both kinds stand together, an open
    model's name carries the tag "Open Source"."""
    out = []
    for place, r in enumerate(table, 1):
        lead = "<td>{}</td>".format(place if filtered else int(r["rank"]))
        lead += "<td>{}</td>".format(int(r["rank"]) if filtered else "")
        name = html.escape(r["model_name"])
        if not filtered and r["license"] != "Proprietary":
            name += ' <span class="open-tag">Open Source</span>'
        out.append(
            '      <tr>{}<td class="model-col">{}</td><td class="change">{}</td></tr>'.format(
                lead, name, changed(moved(place, then.get(r["model_name"])) if then is not None else None)))
    return "\n".join(out)


def usage_body(table):
    """The OpenRouter table's rows: the place, the model's page, its tokens, its change and its prices."""
    return "\n".join(
        '      <tr><td>{}</td><td class="model-col"><a href="https://openrouter.ai/{}" target="_blank" '
        'rel="noopener noreferrer">{}</a></td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            i, html.escape(r["slug"]), html.escape(r["name"]), count(r["tokens"]), changed(r["change"]),
            money(r["input"]), money(r["output"]))
        for i, r in enumerate(table, 1))


def render(as_of, monday, table, arena, arena_as_of, then=None, then_day=None):
    """The page; `then` is arena_places() of the leaderboard of `then_day`, None where there is none."""
    then = then or {}
    compared = ", compared with its leaderboard of " + spoken_day(then_day) if then_day else ""
    return TEMPLATE.format(
        as_of=html.escape(as_of), updated=spoken_day(as_of), week=spoken_week(monday), usage_rows=usage_body(table),
        arena_as_of=html.escape(arena_as_of), arena_updated=spoken_day(arena_as_of), arena_compared=compared,
        arena_all=arena_body(arena["all"], False, then.get("all")),
        arena_proprietary=arena_body(arena["proprietary"], True, then.get("proprietary")),
        arena_open=arena_body(arena["open"], True, then.get("open")),
        title=TITLE, description=DESCRIPTION, style=asset("style.css"), script=SCRIPT,
        schema=article("roleplay-models.html", TITLE, DESCRIPTION, PUBLISHED, max(as_of, arena_as_of)))


def write_page(path, answer, prices, arena_rows, arena_before=()):
    """Writes the page from the answers; raises, leaving the page as it was, when a week or the LMArena's rows are
    missing. `arena_before` is the leaderboard of a week before; empty, the change column shows "—"."""
    as_of, monday, tokens, before = weeks(answer)
    arena, arena_as_of = arena_tables(arena_rows)
    then_day = max(r["leaderboard_publish_date"] for r in arena_before) if arena_before else None
    page = render(as_of, monday, rows(tokens, before, prices), arena, arena_as_of,
                  arena_places(arena_before) if arena_before else None, then_day)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)


def main():
    if len(sys.argv) in (4, 5):
        answers = []
        for name in sys.argv[1:]:
            with open(name, encoding="utf-8") as f:
                answers.append(json.load(f))
        answer, prices, arena_rows, arena_before = (answers + [[]])[:4]
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
        arena_before, cache = arena_cached(arena_cache_load(ARENA_CACHE), arena_rows)
        arena_cache_save(ARENA_CACHE, cache)
        print("arena", len(arena_rows), max(r["leaderboard_publish_date"] for r in arena_rows), "before",
              len(arena_before), arena_before and arena_before[0]["leaderboard_publish_date"], "cached", sorted(cache))
    write_page(PAGE, answer, prices, arena_rows, arena_before)


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

TITLE = "Popular roleplay models and LMArena creative writing rankings"
DESCRIPTION = ("The AI models most used for roleplay and fiction on OpenRouter, and LMArena's top models for "
               "creative writing, with how each moved since the week before.")
PUBLISHED = "2026-11-08"  # the page's first day on the site

TEMPLATE = """<!doctype html>
<html lang="en">

<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <meta name="description"
    content="{description}" />
  <link rel="canonical" href="https://cardwave.cc/roleplay-models.html" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="Cardwave" />
  <meta property="og:url" content="https://cardwave.cc/roleplay-models.html" />
  <meta property="og:title" content="{title}" />
  <meta property="og:description"
    content="{description}" />
  <meta property="og:image" content="https://cardwave.cc/landing_desktop.jpg" />
  <meta property="og:image:width" content="1440" />
  <meta property="og:image:height" content="900" />
  <meta property="og:locale" content="en_US" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{title}" />
  <meta name="twitter:description"
    content="{description}" />
  <meta name="twitter:image" content="https://cardwave.cc/landing_desktop.jpg" />
  <link rel="icon" href="logo_icon.png" />
  <link rel="preload" href="/fonts/geist-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin />
  <link rel="stylesheet" href="{style}" />
  <script src="https://analytics.ahrefs.com/analytics.js" data-key="Vyii1vivGp5eoVeTLVRAwA" async></script>
{schema}
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
      <button type="button" role="tab" id="tab-usage" aria-controls="panel-usage" aria-selected="true">OpenRouter</button>
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
      <p>The highest rated models for creative writing on LMArena{arena_compared}. Last updated {arena_updated}.</p>

      <fieldset class="switches">
        <legend>License</legend>
        <input type="radio" name="arena-license" id="arena-license-all" value="all" checked />
        <label for="arena-license-all">All</label>
        <input type="radio" name="arena-license" id="arena-license-proprietary" value="proprietary" />
        <label for="arena-license-proprietary">Proprietary</label>
        <input type="radio" name="arena-license" id="arena-license-open" value="open" />
        <label for="arena-license-open">Open Source</label>
      </fieldset>

      <div class="table-wrap arena-table" data-license="all">
        <table class="ranking">
          <colgroup><col class="w-rank" /><col class="w-overall-rank" /><col class="w-model" /><col class="w-change" /></colgroup>
          <thead><tr><th>Rank</th><th></th><th class="model-col">Model</th><th>Change</th></tr></thead>
          <tbody>
{arena_all}
          </tbody>
        </table>
      </div>

      <div class="table-wrap arena-table" data-license="proprietary">
        <table class="ranking">
          <colgroup><col class="w-rank" /><col class="w-overall-rank" /><col class="w-model" /><col class="w-change" /></colgroup>
          <thead><tr><th>Rank</th><th>Overall Rank</th><th class="model-col">Model</th><th>Change</th></tr></thead>
          <tbody>
{arena_proprietary}
          </tbody>
        </table>
      </div>

      <div class="table-wrap arena-table" data-license="open">
        <table class="ranking">
          <colgroup><col class="w-rank" /><col class="w-overall-rank" /><col class="w-model" /><col class="w-change" /></colgroup>
          <thead><tr><th>Rank</th><th>Overall Rank</th><th class="model-col">Model</th><th>Change</th></tr></thead>
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
