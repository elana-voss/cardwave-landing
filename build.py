"""Writes the site's twelve language pages and sitemap.xml from one template.

Run from this folder, after changing a text, the template or the pictures: `python build.py`; commit what it
wrote (GitHub Pages serves the files as they are). Standard library only.

- src/index.template.html: the page. `{{key}}` is a text of the language's file; `{{@name}}` is filled in here
  (the language row, the hreflang alternates, the picture box, the page's own address and language).
- src/text/<code>.txt: one language's texts, a line `key = value` each; inline HTML is allowed, and `{where}`,
  `{calculator}`, `{ccv4}`, `{disclaimer}`, `{providers}` and `{issues}` become their links. en.txt is the golden file: every
  other language is translated from it, and the build stops when a file lacks one of its keys or has one more.
- Writes index.html (English) and <code>/index.html for every other language, each page's links absolute
  ("/style.css"), so the pages work only served from the site's root (GitHub Pages, or `python -m http.server`).
- The picture box shows a slide only where screenshots/<name>.webp exists, in SLIDES' order; the first loads
  at once, the rest lazily. A new slide needs its picture, its name in SLIDES and a caption `slide_<name>`.
- Writes providers.html (English only) from src/providers.json, which cardwave-next's tools/provider_page.py
  writes from the app's own provider list: the online services in columns, the local servers apart.
- The other English-only pages (ccv4, calculator, disclaimer, where to find characters) are not written here; their
  stylesheet link, and roleplay-models.html's, is renewed here (stamp_pages).
- style.css and the pictures are linked as `/<path>?v=<hash of the file>` (asset()): a browser holding an older copy
  (http.server and GitHub Pages let it keep one for hours) must not pair the old style with a new page, which
  showed every slide at once with bare buttons.
"""

import hashlib
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = "https://cardwave.cc"

# code (folder and text file), hreflang and html lang, og:locale, the language's own name; the row's order.
LANGS = [
    ("en", "en", "en_US", "English"),
    ("de", "de", "de_DE", "Deutsch"),
    ("ru", "ru", "ru_RU", "Русский"),
    ("pt-br", "pt-BR", "pt_BR", "Português (Brasil)"),
    ("es", "es", "es_ES", "Español"),
    ("ja", "ja", "ja_JP", "日本語"),
    ("zh-cn", "zh-CN", "zh_CN", "简体中文"),
    ("zh-tw", "zh-TW", "zh_TW", "繁體中文"),
    ("ko", "ko", "ko_KR", "한국어"),
    ("hi", "hi", "hi_IN", "हिन्दी"),
    ("vi", "vi", "vi_VN", "Tiếng Việt"),
    ("id", "id", "id_ID", "Bahasa Indonesia"),
]

# The English-only pages in the sitemap: page, how often it changes, priority.
OTHER_PAGES = [
    ("providers.html", "monthly", "0.7"),
    ("roleplay-models.html", "weekly", "0.7"),
    ("ccv4.html", "monthly", "0.7"),
    ("where-to-find-characters.html", "monthly", "0.7"),
    ("chat-turn-budget-calculator.html", "monthly", "0.7"),
    ("disclaimer.html", "yearly", "0.3"),
]

SLIDES = ["chat", "library", "card", "companion", "lorebook", "chat-dark"]

LINKS = {
    "where": "/where-to-find-characters.html",
    "calculator": "/chat-turn-budget-calculator.html",
    "ccv4": "/ccv4.html",
    "disclaimer": "/disclaimer.html",
    "providers": "/providers.html",
    "roleplay": "/roleplay-models.html",
    "issues": "https://github.com/elana-voss/cardwave/issues",
}

ARROW = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="{}" /></svg>'
LEFT, RIGHT = "M15 5l-7 7 7 7", "M9 5l7 7-7 7"

# The picture box's behaviour: arrows, arrow keys and dots move by one slide; a swipe scrolls (CSS snaps it);
# the dots and the caption follow the scroll. Smooth only where the reader has not asked for less motion.
SCRIPT = """  <script>
    (function () {
      var box = document.querySelector(".shots"); if (!box) return;
      var track = box.querySelector(".shots-track"), slides = track.children;
      var dots = box.querySelectorAll(".shots-dots button"), caption = box.querySelector(".shots-caption");
      var still = window.matchMedia("(prefers-reduced-motion: reduce)");
      function at() { return Math.round(track.scrollLeft / track.clientWidth); }
      function go(i) {
        i = (i + slides.length) % slides.length;
        track.scrollTo({ left: i * track.clientWidth, behavior: still.matches ? "auto" : "smooth" });
      }
      function show() {
        var i = at();
        dots.forEach(function (d, j) { d.setAttribute("aria-current", j === i ? "true" : "false"); });
        caption.textContent = slides[i].alt;
      }
      box.querySelector(".shots-prev").onclick = function () { go(at() - 1); };
      box.querySelector(".shots-next").onclick = function () { go(at() + 1); };
      dots.forEach(function (d, j) { d.onclick = function () { go(j); }; });
      track.addEventListener("keydown", function (e) {
        if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); go(at() + (e.key === "ArrowLeft" ? -1 : 1)); }
      });
      track.addEventListener("scroll", show, { passive: true });
    })();
  </script>"""


def asset(name):
    """The address of a file of the site with its content's hash, so a changed file is never taken from a cache."""
    digest = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()[:10]
    return f"/{name}?v={digest}"


STYLE_LINK = re.compile(r'<link rel="stylesheet" href="/?style\.css(\?v=\w+)?" />')
STAMPED = ["ccv4.html", "chat-turn-budget-calculator.html", "disclaimer.html", "where-to-find-characters.html",
           "roleplay-models.html"]


def stamp_pages():
    """The pages not written here link the current style.css."""
    link = f'<link rel="stylesheet" href="{asset("style.css")}" />'
    for name in STAMPED:
        path = ROOT / name
        text = path.read_text(encoding="utf-8")
        new, count = STYLE_LINK.subn(link, text)
        if count != 1:
            sys.exit(f"{name}: expected one stylesheet link, found {count}")
        if new != text:
            path.write_bytes(new.encode("utf-8"))


def read_texts(code):
    """The texts of one language, as written in its file."""
    texts = {}
    for number, line in enumerate((ROOT / "src" / "text" / f"{code}.txt").read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        key, sep, value = line.partition(" = ")
        if not sep:
            sys.exit(f"src/text/{code}.txt:{number}: not `key = value`")
        texts[key.strip()] = value.strip()
    return texts


def check_keys(all_texts):
    """Every language has exactly English's keys."""
    golden = set(all_texts["en"])
    wrong = []
    for code, texts in all_texts.items():
        missing, extra = golden - set(texts), set(texts) - golden
        if missing or extra:
            wrong.append(f"{code}: missing {sorted(missing)}, not in English {sorted(extra)}")
    if wrong:
        sys.exit("src/text: keys differ from en.txt\n" + "\n".join(wrong))


def page_url(code):
    return "/" if code == "en" else f"/{code}/"


def alternates():
    lines = [f'  <link rel="alternate" hreflang="{hl}" href="{SITE}{page_url(code)}" />' for code, hl, _, _ in LANGS]
    lines.append(f'  <link rel="alternate" hreflang="x-default" href="{SITE}/" />')
    return "\n".join(lines)


def lang_row(current):
    items = []
    for code, hl, _, name in LANGS:
        if code == current:
            items.append(f'    <span lang="{hl}" aria-current="page">{name}</span>')
        else:
            items.append(f'    <a lang="{hl}" href="{page_url(code)}">{name}</a>')
    return " ·\n".join(items)


def shots(texts):
    """The picture box, of the slides whose picture exists; empty without any."""
    names = [name for name in SLIDES if (ROOT / "screenshots" / f"{name}.webp").exists()]
    if not names:
        return ""
    key = lambda name: "slide_" + name.replace("-", "_")
    imgs = []
    for i, name in enumerate(names):
        alt = html.escape(texts[key(name)], quote=True)
        lazy = "" if i == 0 else ' loading="lazy"'
        imgs.append(f'        <img src="{asset(f"screenshots/{name}.webp")}" width="1440" height="900" alt="{alt}"{lazy} />')
    dots = []
    for i, _ in enumerate(names):
        label = html.escape(texts["shot_dot"].replace("{n}", str(i + 1)), quote=True)
        dots.append(f'      <button type="button" aria-label="{label}" aria-current="{"true" if i == 0 else "false"}"></button>')
    single = " single" if len(names) == 1 else ""
    return "\n".join([
        f'  <figure class="shots{single}" aria-label="{html.escape(texts["shots_label"], quote=True)}">',
        '    <div class="shots-box">',
        '      <div class="shots-track" tabindex="0">',
        *imgs,
        '      </div>',
        f'      <button type="button" class="shots-prev" aria-label="{html.escape(texts["shot_prev"], quote=True)}">{ARROW.format(LEFT)}</button>',
        f'      <button type="button" class="shots-next" aria-label="{html.escape(texts["shot_next"], quote=True)}">{ARROW.format(RIGHT)}</button>',
        '    </div>',
        '    <div class="shots-dots">',
        *dots,
        '    </div>',
        f'    <figcaption class="shots-caption">{html.escape(texts[key(names[0])])}</figcaption>',
        '  </figure>',
        SCRIPT,
    ])


def render(template, code, hl, locale, texts):
    own = {
        "@lang": hl, "@url": SITE + page_url(code), "@locale": locale, "@home": page_url(code),
        "@alternates": alternates(), "@langs": lang_row(code), "@shots": shots(texts),
        "@style": asset("style.css"),
    }

    def fill(match):
        key = match.group(1)
        if key in own:
            return own[key]
        if key not in texts:
            sys.exit(f"src/index.template.html: no text `{key}` in en.txt")
        return re.sub(r"\{(\w+)\}", lambda m: LINKS.get(m.group(1), m.group(0)), texts[key])

    out = re.sub(r"\{\{(@?\w+)\}\}", fill, template)
    if "{{" in out:
        sys.exit("src/index.template.html: a placeholder was left unfilled")
    return out


PROVIDERS_HEAD = """<!doctype html>
<html lang="en">

<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <meta name="description" content="{description}" />
  <link rel="canonical" href="{url}" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="Cardwave" />
  <meta property="og:url" content="{url}" />
  <meta property="og:title" content="{title}" />
  <meta property="og:description" content="{description}" />
  <meta property="og:image" content="https://cardwave.cc/landing_desktop.jpg" />
  <meta property="og:image:width" content="1440" />
  <meta property="og:image:height" content="900" />
  <meta property="og:locale" content="en_US" />
  <meta name="twitter:card" content="summary_large_image" />
  <link rel="icon" href="/logo_icon.png" />
  <link rel="preload" href="/fonts/geist-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin />
  <link rel="stylesheet" href="{style}" />
  <script src="https://analytics.ahrefs.com/analytics.js" data-key="Vyii1vivGp5eoVeTLVRAwA" async></script>
</head>

<body>

  <header>
    <h1><a href="/"><img src="/logo_icon.png" alt="" /> Cardwave</a></h1>
  </header>
"""


def providers_page():
    """providers.html: every online provider the app knows by its key, linked to its site; the local servers apart."""
    data = json.loads((ROOT / "src" / "providers.json").read_text(encoding="utf-8"))
    online = sorted((p for p in data if not p["local"]), key=lambda p: p["name"].casefold())
    local = sorted((p for p in data if p["local"]), key=lambda p: p["name"].casefold())

    def item(p):
        name = html.escape(p["name"])
        if not p["url"]:
            return f"    <li>{name}</li>"
        url = html.escape(p["url"], quote=True)
        return f'    <li><a href="{url}" target="_blank" rel="noopener noreferrer">{name}</a></li>'

    title = "AI providers Cardwave supports"
    description = f"The {len(online)} AI services Cardwave knows by their API key, and the local servers it works with."
    return "\n".join([
        PROVIDERS_HEAD.format(title=title, description=description, url=SITE + "/providers.html",
                              style=asset("style.css")),
        f'  <p class="page-title"><strong>{title}</strong></p>',
        f"  <p>Paste an API key from any of these {len(online)} services and Cardwave knows whose it is. "
        "Any other OpenAI-compatible server works too, by its address.</p>",
        '  <ul class="providers">',
        *[item(p) for p in online],
        "  </ul>",
        "",
        "  <h2>On your own computer</h2>",
        "  <p>Cardwave runs GGUF models itself, and it also works with these local servers.</p>",
        '  <ul class="providers">',
        *[item(p) for p in local],
        "  </ul>",
        "",
        "  <hr />",
        '  <footer>Cardwave © 2026. <a href="/">Home</a></footer>',
        "",
        "</body>",
        "",
        "</html>",
        "",
    ])


def sitemap():
    urls = []
    for code, _, _, _ in LANGS:
        priority = "1.0" if code == "en" else "0.8"
        urls.append(f"  <url>\n    <loc>{SITE}{page_url(code)}</loc>\n    <changefreq>monthly</changefreq>\n"
                    f"    <priority>{priority}</priority>\n  </url>")
    for page, freq, priority in OTHER_PAGES:
        urls.append(f"  <url>\n    <loc>{SITE}/{page}</loc>\n    <changefreq>{freq}</changefreq>\n"
                    f"    <priority>{priority}</priority>\n  </url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n")


def main():
    template = (ROOT / "src" / "index.template.html").read_text(encoding="utf-8")
    all_texts = {code: read_texts(code) for code, _, _, _ in LANGS}
    check_keys(all_texts)
    for code, hl, locale, _ in LANGS:
        target = ROOT / "index.html" if code == "en" else ROOT / code / "index.html"
        target.parent.mkdir(exist_ok=True)
        target.write_text(render(template, code, hl, locale, all_texts[code]), encoding="utf-8", newline="\n")
    (ROOT / "providers.html").write_text(providers_page(), encoding="utf-8", newline="\n")
    (ROOT / "sitemap.xml").write_text(sitemap(), encoding="utf-8", newline="\n")
    stamp_pages()
    print(f"wrote {len(LANGS)} pages, providers.html and sitemap.xml")


if __name__ == "__main__":
    main()
