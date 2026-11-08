"""Writes the site's twelve language pages and sitemap.xml from one template.

Run from this folder, after changing a text, the template or the pictures: `python build.py`; commit what it
wrote (GitHub Pages serves the files as they are). Standard library only.

- src/index.template.html: the page. `{{key}}` is a text of the language's file; `{{@name}}` is filled in here
  (the language row, the hreflang alternates, the picture box, the page's own address and language).
- src/text/<code>.txt: one language's texts, a line `key = value` each; inline HTML is allowed, and `{where}`,
  `{calculator}`, `{ccv4}`, `{disclaimer}` and `{issues}` become their links. en.txt is the golden file: every
  other language is translated from it, and the build stops when a file lacks one of its keys or has one more.
- Writes index.html (English) and <code>/index.html for every other language, each page's links absolute
  ("/style.css"), so the pages work only served from the site's root (GitHub Pages, or `python -m http.server`).
- The picture box shows a slide only where screenshots/<name>.webp exists, in SLIDES' order; the first loads
  at once, the rest lazily. A new slide needs its picture, its name in SLIDES and a caption `slide_<name>`.
- The English-only pages (ccv4, calculator, disclaimer, where to find characters) are not written here.
"""

import html
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
        imgs.append(f'        <img src="/screenshots/{name}.webp" width="1440" height="900" alt="{alt}"{lazy} />')
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
    (ROOT / "sitemap.xml").write_text(sitemap(), encoding="utf-8", newline="\n")
    print(f"wrote {len(LANGS)} pages and sitemap.xml")


if __name__ == "__main__":
    main()
