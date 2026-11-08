"""Writes roleplay-models.html: OpenRouter's most used models for roleplay and fiction, each with its OpenRouter price.

    OPENROUTER_API_KEY=... python tools/roleplay_models.py
    python tools/roleplay_models.py <classifications.json> <models.dev api.json>   (stored answers, no network)

The ranking is the Data API's task ranking (GET /api/v1/classifications/task?window=7d, its entry roleplay_fiction,
top 10 by share of requests; CC BY 4.0, the page carries its source line); OpenRouter's terms forbid scraping its site.
Prices are models.dev's provider openrouter (MIT), dollars per million tokens. Traps:
- The ranking names dated versions (deepseek/deepseek-v4-flash-20260731); versions of one model are merged into one
  row by the id without its date, their shares summed. The price is the undated id's (what a reader picks), else the
  dated one models.dev lists as <id>-MMDD, else a dash.
- A failed fetch or an answer without the roleplay entry raises before the page is written: the last page stays.
- The page holds no time of its own, so it changes only when the ranking or a price does (the weekly job commits then).
Standard library only. Tests: tools/tests/.
"""

import html
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "roleplay-models.html")
RANKING_URL = "https://openrouter.ai/api/v1/classifications/task?window=7d"
PRICES_URL = "https://models.dev/api.json"
TAG = "roleplay_fiction"
DATED = re.compile(r"^(.*)-(\d{4})(\d{2})(\d{2})$")


def fetch(url, key=None):
    headers = {"User-Agent": "cardwave.cc roleplay-models"}
    if key:
        headers["Authorization"] = "Bearer " + key
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
        return json.load(r)


def roleplay_entry(answer):
    """(as_of, window_days, models) of the roleplay entry; ValueError when the answer lacks it."""
    data = answer.get("data") or {}
    for entry in data.get("classifications") or []:
        if entry.get("tag") == TAG and entry.get("models"):
            return data["as_of"], data["window_days"], entry["models"]
    raise ValueError("the answer has no " + TAG + " entry with models")


def rows(models, prices):
    """One row per model, dated versions merged, ranked by share of requests."""
    catalogue = (prices.get("openrouter") or {}).get("models") or {}
    merged = {}
    for m in models:
        found = DATED.match(m["id"])
        slug = found.group(1) if found else m["id"]
        row = merged.setdefault(slug, {"slug": slug, "usage": 0.0, "tokens": 0.0, "dated": []})
        row["usage"] += m.get("tag_usage_share") or 0.0
        row["tokens"] += m.get("tag_token_share") or 0.0
        if found:
            row["dated"].append(slug + "-" + found.group(3) + found.group(4))
    for row in merged.values():
        entry = next((catalogue[k] for k in [row["slug"]] + row.pop("dated") if k in catalogue), None)
        cost = (entry or {}).get("cost") or {}
        row["name"] = (entry or {}).get("name") or row["slug"].split("/")[-1]
        row["input"], row["output"] = cost.get("input"), cost.get("output")
    return sorted(merged.values(), key=lambda r: -r["usage"])


def money(value):
    return "—" if value is None else "${:g}".format(value)


def share(value):
    return "{:.1f}%".format(value * 100)


def render(as_of, days, table):
    body = "\n".join(
        "      <tr><td>{}</td><td><a href=\"https://openrouter.ai/{}\" target=\"_blank\" rel=\"noopener noreferrer\">{}</a></td>"
        "<td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            i, html.escape(r["slug"]), html.escape(r["name"]), share(r["usage"]), share(r["tokens"]),
            money(r["input"]), money(r["output"]))
        for i, r in enumerate(table, 1))
    return TEMPLATE.format(as_of=html.escape(as_of), days=days, rows=body)


def write_page(path, answer, prices):
    """Writes the page from both answers; raises, leaving the page as it was, when the ranking is missing."""
    as_of, days, models = roleplay_entry(answer)
    page = render(as_of, days, rows(models, prices))
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
        answer, prices = fetch(RANKING_URL, key), fetch(PRICES_URL)
    write_page(PAGE, answer, prices)


TEMPLATE = """<!doctype html>
<html lang="en">

<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Popular roleplay models</title>
  <meta name="description"
    content="The AI models most used for roleplay and fiction on OpenRouter this week, with their price per million tokens." />
  <link rel="canonical" href="https://cardwave.cc/roleplay-models.html" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="Cardwave" />
  <meta property="og:url" content="https://cardwave.cc/roleplay-models.html" />
  <meta property="og:title" content="Popular roleplay models" />
  <meta property="og:description"
    content="The AI models most used for roleplay and fiction on OpenRouter this week, with their price per million tokens." />
  <meta property="og:image" content="https://cardwave.cc/landing_desktop.jpg" />
  <meta property="og:image:width" content="1440" />
  <meta property="og:image:height" content="900" />
  <meta property="og:locale" content="en_US" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="Popular roleplay models" />
  <meta name="twitter:description"
    content="The AI models most used for roleplay and fiction on OpenRouter this week, with their price per million tokens." />
  <meta name="twitter:image" content="https://cardwave.cc/landing_desktop.jpg" />
  <link rel="icon" href="logo_icon.png" />
  <link rel="preload" href="/fonts/geist-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin />
  <link rel="stylesheet" href="style.css" />
  <style>
    .table-wrap {{ overflow-x: auto; }}
    .ranking {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }}
    .ranking th, .ranking td {{ padding: 8px 10px; border-bottom: 1px solid #e5e5e5; text-align: right; white-space: nowrap; }}
    .ranking th:nth-child(2), .ranking td:nth-child(2) {{ text-align: left; white-space: normal; }}
    .ranking th {{ font-weight: 600; color: #555; font-size: 14px; }}
    .source {{ color: #888; font-size: 14px; }}
  </style>
  <script src="https://analytics.ahrefs.com/analytics.js" data-key="Vyii1vivGp5eoVeTLVRAwA" async></script>
</head>

<body>

  <header>
    <h1><a href="index.html"><img src="logo_icon.png" alt="" /> Cardwave</a></h1>
    <a class="gh" href="https://github.com/elana-voss/cardwave" target="_blank" rel="noopener noreferrer"
      aria-label="GitHub">
      <svg width="28" height="28" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
        <path
          d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
      </svg>
    </a>
  </header>

  <p class="page-title"><strong>Popular roleplay models</strong></p>
  <p>The models people used most for roleplay and fiction on OpenRouter over the last {days} days, ranked by their
    share of those requests. Versions of one model count as one. Prices are OpenRouter's, in US dollars per million
    tokens; a dash means none is listed. Updated every week.</p>

  <div class="table-wrap">
    <table class="ranking">
      <thead><tr><th>#</th><th>Model</th><th>Requests</th><th>Tokens</th><th>Input</th><th>Output</th></tr></thead>
      <tbody>
{rows}
      </tbody>
    </table>
  </div>

  <p class="source">Source: OpenRouter (openrouter.ai/rankings), as of {as_of}. Licensed under CC BY 4.0.
    Prices: <a href="https://models.dev" target="_blank" rel="noopener noreferrer">models.dev</a>, MIT licence.</p>

  <hr />
  <footer>Cardwave © 2026. <a href="index.html">Home</a> · <a href="disclaimer.html">Disclaimer &amp; Terms</a></footer>

</body>

</html>
"""

if __name__ == "__main__":
    main()
