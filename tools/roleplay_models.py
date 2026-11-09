"""Writes roleplay-models.html: OpenRouter's most used models for roleplay and fiction last week, each with its
estimated tokens, its change against the week before and its OpenRouter price.

    OPENROUTER_API_KEY=... python tools/roleplay_models.py
    python tools/roleplay_models.py <rankings.json> <models.json>   (stored answers, no network)

The ranking is the Data API's (GET /api/v1/datasets/rankings-daily?category=roleplay&period=week; CC BY 4.0, the
page carries its source line): per week, the top 50 models by tokens, estimated from a sample; OpenRouter's terms
forbid scraping its site. Names, pages and prices are OpenRouter's own model list (GET /api/v1/models, no key),
dollars per token. Traps:
- The category data is weekly only (period=day is a 400); a row's date is its ISO week's Monday, and the trailing
  week is partial, so only weeks that ended by meta.end_date count; the row "other" is the long tail, never shown.
- The ranking names dated versions (deepseek/deepseek-v4.1-flash-20261017), each its own model with its own price:
  the model list's canonical_slug is that id, its id the page (deepseek/deepseek-v4.1-flash-1017). Every version is a
  row; a variant (":batch", ":free") is never the one priced.
- A failed fetch or an answer without a whole week raises before the page is written: the last page stays.
- The day the page shows is the ranking's as_of, so the daily job commits when that, a week or a price changed.
Standard library only. Tests: tools/tests/.
"""

import html
import json
import os
from datetime import date, timedelta
from decimal import Decimal
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from build import asset  # noqa: E402  the stylesheet's address with its hash, as every page links it
PAGE = os.path.join(ROOT, "roleplay-models.html")
RANKING_URL = "https://openrouter.ai/api/v1/datasets/rankings-daily?category=roleplay&period=week&start_date={start}"
PRICES_URL = "https://openrouter.ai/api/v1/models"
SHOWN = 20
WEEK = timedelta(days=7)
MONTHS = "January February March April May June July August September October November December".split()


def fetch(url, key=None):
    headers = {"User-Agent": "cardwave.cc roleplay-models"}
    if key:
        headers["Authorization"] = "Bearer " + key
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
        return json.load(r)


def weeks(answer):
    """(as_of day, last whole week's Monday, its tokens by model, the week before's or None); ValueError without a whole week."""
    meta = answer.get("meta") or {}
    end = date.fromisoformat(meta["end_date"])
    by_week = {}
    for row in answer.get("data") or []:
        monday = date.fromisoformat(row["date"])
        if row["model_permaslug"] != "other" and monday + timedelta(days=6) <= end:
            by_week.setdefault(monday, {})[row["model_permaslug"]] = Decimal(row["total_tokens"])
    if not by_week:
        raise ValueError("the answer has no whole week of roleplay rows")
    last = max(by_week)
    return meta["as_of"][:10], last, by_week[last], by_week.get(last - WEEK)


def rows(tokens, before, catalogue):
    """The SHOWN models with most tokens, every version its own, with their change, OpenRouter's name, page and price."""
    listed = {}
    for m in catalogue.get("data") or []:
        if ":" not in m["id"]:
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
    """A week as a reader says it: 2–8 November 2026, 27 October – 2 November 2026."""
    sunday = monday + timedelta(days=6)
    if monday.month == sunday.month:
        return "{}–{}".format(monday.day, spoken_day(sunday))
    if monday.year == sunday.year:
        return "{} {} – {}".format(monday.day, MONTHS[monday.month - 1], spoken_day(sunday))
    return "{} – {}".format(spoken_day(monday), spoken_day(sunday))


def render(as_of, monday, table):
    body = "\n".join(
        "      <tr><td>{}</td><td><a href=\"https://openrouter.ai/{}\" target=\"_blank\" rel=\"noopener noreferrer\">{}</a></td>"
        "<td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            i, html.escape(r["slug"]), html.escape(r["name"]), count(r["tokens"]), r["change"] or "—",
            money(r["input"]), money(r["output"]))
        for i, r in enumerate(table, 1))
    return TEMPLATE.format(as_of=html.escape(as_of), updated=spoken_day(as_of), week=spoken_week(monday), rows=body,
                           style=asset("style.css"))


def write_page(path, answer, prices):
    """Writes the page from both answers; raises, leaving the page as it was, when no whole week is there."""
    as_of, monday, tokens, before = weeks(answer)
    page = render(as_of, monday, rows(tokens, before, prices))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)


def main():
    if len(sys.argv) == 3:
        with open(sys.argv[1], encoding="utf-8") as a, open(sys.argv[2], encoding="utf-8") as p:
            answer, prices = json.load(a), json.load(p)
    else:
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            sys.exit("OPENROUTER_API_KEY is not set")
        start = (date.today() - timedelta(days=28)).isoformat()
        answer, prices = fetch(RANKING_URL.format(start=start), key), fetch(PRICES_URL)
    write_page(PAGE, answer, prices)


TEMPLATE = """<!doctype html>
<html lang="en">

<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Popular roleplay models</title>
  <meta name="description"
    content="The AI models most used for roleplay and fiction on OpenRouter last week, with their tokens and price per million tokens." />
  <link rel="canonical" href="https://cardwave.cc/roleplay-models.html" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="Cardwave" />
  <meta property="og:url" content="https://cardwave.cc/roleplay-models.html" />
  <meta property="og:title" content="Popular roleplay models" />
  <meta property="og:description"
    content="The AI models most used for roleplay and fiction on OpenRouter last week, with their tokens and price per million tokens." />
  <meta property="og:image" content="https://cardwave.cc/landing_desktop.jpg" />
  <meta property="og:image:width" content="1440" />
  <meta property="og:image:height" content="900" />
  <meta property="og:locale" content="en_US" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="Popular roleplay models" />
  <meta name="twitter:description"
    content="The AI models most used for roleplay and fiction on OpenRouter last week, with their tokens and price per million tokens." />
  <meta name="twitter:image" content="https://cardwave.cc/landing_desktop.jpg" />
  <link rel="icon" href="logo_icon.png" />
  <link rel="preload" href="/fonts/geist-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin />
  <link rel="stylesheet" href="{style}" />
  <style>
    .table-wrap {{ overflow-x: auto; }}
    .ranking {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }}
    .ranking th, .ranking td {{ padding: 8px 10px; border-bottom: 1px solid #e5e5e5; text-align: right; white-space: nowrap; }}
    .ranking th:nth-child(2), .ranking td:nth-child(2) {{ text-align: left; white-space: normal; }}
    .ranking th {{ font-weight: 600; color: #555; font-size: 14px; }}
    @media (max-width: 480px) {{ .ranking th, .ranking td {{ padding: 8px 4px; font-size: 14px; }} }}
    .source {{ color: #888; font-size: 14px; }}
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
          d="M20.317 4.37a19.79 19.79 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.211.375-.445.865-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.74 19.74 0 0 0 3.677 4.37a.07.07 0 0 0-.032.028C.533 9.046-.32 13.58.099 18.058a.082.082 0 0 0 .031.056 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.873-1.295 1.226-1.994a.076.076 0 0 0-.042-.106 13.1 13.1 0 0 1-1.872-.892.077.077 0 0 1-.008-.128c.126-.094.252-.192.372-.291a.074.074 0 0 1 .078-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.009c.12.099.246.198.373.292a.077.077 0 0 1-.006.128 12.3 12.3 0 0 1-1.873.891.077.077 0 0 0-.041.107c.36.698.772 1.363 1.225 1.993a.076.076 0 0 0 .084.028 19.84 19.84 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.029ZM8.02 15.331c-1.183 0-2.157-1.086-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.095 2.157 2.42 0 1.332-.956 2.418-2.157 2.418Zm7.975 0c-1.183 0-2.157-1.086-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.095 2.157 2.42 0 1.332-.946 2.418-2.157 2.418Z" />
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

  <p class="page-title"><strong>Popular roleplay models</strong></p>
  <p>The models people used most for roleplay and fiction on OpenRouter in the week of {week}. Tokens are
    OpenRouter's estimates; the change is against the week before. Prices are OpenRouter's, in US dollars per million
    tokens. Updated every day; last updated {updated}.</p>

  <div class="table-wrap">
    <table class="ranking">
      <thead><tr><th>#</th><th>Model</th><th>Tokens</th><th>Change</th><th>Input</th><th>Output</th></tr></thead>
      <tbody>
{rows}
      </tbody>
    </table>
  </div>

  <p class="source">Source: OpenRouter (openrouter.ai/rankings), as of {as_of}. Licensed under CC BY 4.0.</p>

  <hr />
  <footer>Cardwave © 2026. <a href="index.html">Home</a> · <a href="disclaimer.html">Disclaimer &amp; Terms</a></footer>

</body>

</html>
"""

if __name__ == "__main__":
    main()
