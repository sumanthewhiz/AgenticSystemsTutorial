"""HTML templates: page shell, sidebar, table of contents, pager and the home page."""
from __future__ import annotations

import html

from .render import inline

SITE = "Agentic Systems, Hands-on"
THEME_INIT = ("<script>(function(){try{var t=localStorage.getItem('ast-theme')||(matchMedia('(prefers-color-scheme: dark)')"
              ".matches?'dark':'light');document.documentElement.setAttribute('data-theme',t);}catch(e){}})();</script>")


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def sidebar(outline: dict, current: str, prefix: str) -> str:
    parts = []
    for part in outline["parts"]:
        items = []
        has_current = any(ch["slug"] == current for ch in part["chapters"])
        for ch in part["chapters"]:
            cls = ' class="current" aria-current="page"' if ch["slug"] == current else ""
            items.append(f'<li><a href="{prefix}{ch["slug"]}.html" data-slug="{ch["slug"]}"{cls}>'
                         f'<span class="n">{esc(ch["short"])}</span><span class="t">{inline(ch["title"])}</span>'
                         f'<span class="done" aria-label="completed">&#10003;</span></a></li>')
        open_attr = " open" if (has_current or not current) else ""
        parts.append(f'<details class="part"{open_attr}><summary><span class="part-label">{esc(part["label"])}</span>'
                     f'<span class="part-name">{esc(part["name"])}</span></summary><ol>{"".join(items)}</ol></details>')
    return "".join(parts)


def toc_html(toc: list) -> str:
    if not toc:
        return ""
    items = "".join(f'<li class="{tag}"><a href="#{sid}">{title}</a></li>' for tag, sid, title in toc)
    return f'<div class="toc-title">On this page</div><ol>{items}</ol>'


def pager(prev_ch: dict | None, next_ch: dict | None, prefix: str) -> str:
    def card(ch, cls, label):
        if not ch:
            return f'<span class="{cls} empty"></span>'
        return (f'<a class="{cls}" href="{prefix}{ch["slug"]}.html" data-nav="{cls}"><span class="dir">{label}</span>'
                f'<span class="ptitle">{esc(ch["short_label"])} &middot; {inline(ch["title"])}</span></a>')
    return f'<nav class="pager" aria-label="Chapter navigation">{card(prev_ch, "prev", "&larr; Previous")}{card(next_ch, "next", "Next &rarr;")}</nav>'


def shell(*, title: str, root: str, slug: str, body: str, side: str, toc: str = "", home: bool = False) -> str:
    return f"""<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%233b5bdb'/%3E%3Cpath d='M16 7l8 4.5v9L16 25l-8-4.5v-9z' fill='none' stroke='white' stroke-width='2.4'/%3E%3C/svg%3E">
<link rel="stylesheet" href="{root}assets/style.css">
{THEME_INIT}
</head>
<body data-page="{esc(slug)}" data-root="{root}"{' class="home"' if home else ''}>
<a class="skip" href="#main">Skip to content</a>
<header class="topbar">
  <button class="menu-btn" type="button" aria-label="Toggle navigation" aria-expanded="false">&#9776;</button>
  <a class="brand" href="{root}index.html"><span class="logo" aria-hidden="true">&#11041;</span><span>{SITE}</span></a>
  <div class="search" role="search">
    <input type="search" id="search" placeholder="Search the tutorial  ( / )" aria-label="Search the tutorial" autocomplete="off">
    <div class="search-results" id="search-results" hidden></div>
  </div>
  <div class="progress-mini" title="Chapters completed"><span class="bar"><span class="fill"></span></span><span class="pct">0%</span></div>
  <button class="theme-btn" type="button" aria-label="Toggle dark mode" title="Toggle dark mode">&#9680;</button>
</header>
<div class="layout{' no-toc' if not toc else ''}">
  <nav class="sidebar" aria-label="Chapters">{side}</nav>
  <main id="main" class="content">
{body}
  </main>
  {f'<aside class="toc" aria-label="On this page">{toc}</aside>' if toc else ''}
</div>
<script src="{root}assets/search-index.js"></script>
<script src="{root}assets/app.js"></script>
</body>
</html>
"""


def chapter_body(page, prev_ch, next_ch) -> str:
    m = page.meta
    objectives = m.get("objectives") or []
    obj = ""
    if objectives:
        obj = ('<div class="objectives"><div class="obj-head">What you will learn</div><ul>'
               + "".join(f"<li>{inline(o)}</li>" for o in objectives) + "</ul></div>")
    facts = []
    if m.get("time"):
        facts.append(f'<span class="chip">&#9201; {esc(m["time"])}</span>')
    if m.get("level"):
        facts.append(f'<span class="chip">Level: {esc(m["level"])}</span>')
    if m.get("labs_count"):
        facts.append(f'<span class="chip">&#129514; {m["labs_count"]} hands-on lab{"s" if m["labs_count"] != 1 else ""}</span>')
    part = page.part or {}
    complete = "" if page.kind == "appendix" else (
        f'<div class="complete-box"><button class="complete-btn" type="button" data-slug="{page.slug}">'
        f'<span class="when-todo">Mark this chapter as complete</span><span class="when-done">&#10003; Completed &mdash; click to undo</span></button></div>')
    return f"""<article class="chapter" data-slug="{page.slug}">
<div class="crumbs"><a href="../index.html">Home</a> &rsaquo; {esc(part.get('label', ''))} &middot; {esc(part.get('name', ''))}</div>
<h1><span class="num">{esc(page.label)}</span>{inline(page.title)}</h1>
<div class="meta">{''.join(facts)}</div>
<p class="lede">{inline(m.get('summary', ''))}</p>
{obj}
{page.body}
{complete}
{pager(prev_ch, next_ch, '')}
</article>"""


def home_body(outline: dict, intro_html: str, stats: dict) -> str:
    first = outline["parts"][0]["chapters"][0]
    cards = []
    for part in outline["parts"]:
        chs = []
        for ch in part["chapters"]:
            chips = "".join(f'<span class="topic">{esc(c)}</span>' for c in (ch.get("covers") or [])[:6])
            meta = " &middot; ".join(x for x in (esc(ch.get("time", "")), esc(ch.get("level", ""))) if x)
            chs.append(f'<a class="ch-card" href="chapters/{ch["slug"]}.html" data-slug="{ch["slug"]}">'
                       f'<div class="ch-top"><span class="ch-num">{esc(ch["short_label"])}</span><span class="ch-meta">{meta}</span>'
                       f'<span class="done" aria-label="completed">&#10003;</span></div>'
                       f'<div class="ch-title">{inline(ch["title"])}</div><div class="ch-sum">{inline(ch.get("summary", ""))}</div>'
                       f'<div class="topics">{chips}</div></a>')
        cards.append(f'<section class="part-block" id="{esc(part["id"])}"><div class="part-head"><span class="part-label">{esc(part["label"])}</span>'
                     f'<h2>{esc(part["name"])}</h2><p>{inline(part.get("description", ""))}</p>'
                     f'<div class="part-progress" data-part="{esc(part["id"])}"></div></div>'
                     f'<div class="ch-grid">{"".join(chs)}</div></section>')
    path = "".join(f'<a class="path-step" href="#{esc(p["id"])}"><span class="ps-label">{esc(p["label"])}</span>'
                   f'<span class="ps-name">{esc(p["name"])}</span></a>' for p in outline["parts"])
    stat_html = "".join(f'<div class="stat"><div class="sv">{v}</div><div class="sl">{esc(k)}</div></div>' for k, v in stats.items())
    return f"""<section class="hero">
  <div class="hero-kicker">A hands-on tutorial</div>
  <h1>{inline(outline['title'])}</h1>
  <p class="hero-sub">{inline(outline['subtitle'])}</p>
  <div class="hero-cta">
    <a class="btn primary" href="chapters/{first['slug']}.html">Start with {esc(first['short_label'])}</a>
    <a class="btn continue" href="#" hidden>Continue where you left off</a>
  </div>
  <div class="stats">{stat_html}</div>
</section>
<section class="learning-path" aria-label="Learning path"><div class="path">{path}</div></section>
<section class="intro">{intro_html}</section>
{''.join(cards)}
"""


FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' "
           "rx='8' fill='%233b5bdb'/%3E%3Cpath d='M16 7l8 4.5v9L16 25l-8-4.5v-9z' fill='none' stroke='white' stroke-width='2.4'/%3E%3C/svg%3E")
NOTFOUND_LINKS = ("01-llm-to-agent", "09-triage-swarm", "15-eval-fundamentals", "19-threat-model", "cheatsheet", "glossary")
NOTFOUND_CSS = """
:root { --bg:#f6f8fb; --panel:#fff; --text:#1c2430; --muted:#5d6978; --border:#e3e8ef; --accent:#3b5bdb; --accent-2:#0ca678;
  --soft:#edf2ff; --shadow:0 10px 30px rgba(16,24,40,.10); }
[data-theme="dark"] { --bg:#0d1117; --panel:#151b23; --text:#e6edf3; --muted:#a2afbd; --border:#262f3a; --accent:#7aa2ff;
  --accent-2:#38d9a9; --soft:#1a2340; --shadow:0 12px 32px rgba(0,0,0,.5); }
* { box-sizing: border-box; }
[hidden] { display: none !important; }
html, body { margin: 0; }
body { min-height: 100vh; display: flex; flex-direction: column; color: var(--text);
  font: 16px/1.6 "Segoe UI", system-ui, -apple-system, Roboto, "Helvetica Neue", Arial, sans-serif;
  background: radial-gradient(1100px 560px at 8% -12%, color-mix(in srgb, var(--accent) 16%, transparent), transparent 62%),
              radial-gradient(900px 520px at 108% 112%, color-mix(in srgb, var(--accent-2) 16%, transparent), transparent 62%), var(--bg); }
a { color: var(--accent); text-decoration: none; }
a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 8px; }
.top { padding: 18px 24px; }
.brand { display: inline-flex; align-items: center; gap: 10px; font-weight: 700; color: var(--text); }
.logo { display: grid; place-items: center; width: 32px; height: 32px; border-radius: 9px; color: #fff; font-size: 17px;
  background: linear-gradient(135deg, var(--accent), var(--accent-2)); }
main { flex: 1; display: flex; align-items: center; justify-content: center; padding: 16px 18px 56px; }
.card { width: 100%; max-width: 660px; min-width: 0; text-align: center; background: var(--panel); border: 1px solid var(--border);
  border-radius: 18px; box-shadow: var(--shadow); padding: 40px 36px 28px; }
.code { margin: 0; font-size: clamp(4.5rem, 16vw, 7.5rem); font-weight: 800; line-height: 1; letter-spacing: -.04em;
  background: linear-gradient(120deg, var(--accent), var(--accent-2)); -webkit-background-clip: text; background-clip: text; color: transparent; }
h1 { margin: 12px 0 8px; font-size: 1.7rem; letter-spacing: -.01em; }
.msg { margin: 0 auto; max-width: 470px; color: var(--muted); }
.path { display: inline-block; max-width: 100%; margin: 12px 0 0; padding: 3px 10px; overflow-wrap: anywhere; color: var(--text);
  font: 13px "Cascadia Code", Consolas, monospace; background: var(--soft); border: 1px solid var(--border); border-radius: 8px; }
.actions { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; margin: 26px 0 28px; }
.btn { display: inline-block; padding: 11px 20px; border-radius: 10px; font-weight: 650; color: var(--text); background: var(--panel);
  border: 1px solid var(--border); }
.btn:hover { border-color: var(--accent); }
.btn.primary { color: #fff; border-color: transparent;
  background: linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent) 70%, var(--accent-2))); }
.quick { padding-top: 18px; border-top: 1px solid var(--border); }
.quick h2 { margin: 0 0 12px; font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.quick ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr)); text-align: left; }
.quick a { display: block; height: 100%; padding: 9px 12px; border-radius: 10px; color: var(--text); border: 1px solid var(--border);
  background: color-mix(in srgb, var(--soft) 45%, var(--panel)); }
.quick a:hover { border-color: var(--accent); }
.lbl { display: block; font-size: 11.5px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; color: var(--accent); }
.ttl { display: block; font-size: 14px; font-weight: 600; line-height: 1.35; }
.hint { margin: 20px 0 0; font-size: 13px; color: var(--muted); }
kbd { font: 12px Consolas, monospace; padding: 1px 6px; border-radius: 4px; border: 1px solid var(--border); border-bottom-width: 2px; background: var(--soft); }
@media (max-width: 520px) { .card { padding: 30px 18px 22px; } }
"""
# Cloudflare Pages serves 404.html for unknown URLs at any depth, so links are root-absolute there; opened from disk
# (file://) they switch to the relative data-local targets. Everything is inline so nothing can fail to load.
NOTFOUND_JS = """(function () {
  if (location.protocol === "file:") {
    document.querySelectorAll("a[data-local]").forEach(function (a) { a.setAttribute("href", a.getAttribute("data-local")); });
    return;
  }
  var p = document.getElementById("nf-path");
  if (p && !/^\\/404(\\.html)?$/.test(location.pathname)) { p.textContent = location.pathname; p.hidden = false; }
})();"""


def notfound_page(outline: dict) -> str:
    chapters = {ch["slug"]: ch for part in outline["parts"] for ch in part["chapters"]}
    first = outline["parts"][0]["chapters"][0]
    quick = "".join(f'<li><a href="/chapters/{s}.html" data-local="chapters/{s}.html"><span class="lbl">{esc(chapters[s]["short_label"])}</span>'
                    f'<span class="ttl">{esc(chapters[s]["title"])}</span></a></li>' for s in NOTFOUND_LINKS if s in chapters)
    return f"""<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Page not found · {SITE}</title>
<link rel="icon" href="{FAVICON}">
{THEME_INIT}
<style>{NOTFOUND_CSS}</style>
</head>
<body>
<header class="top"><a class="brand" href="/" data-local="index.html"><span class="logo" aria-hidden="true">&#11041;</span>{SITE}</a></header>
<main>
  <section class="card" aria-labelledby="nf-title">
    <p class="code" aria-hidden="true">404</p>
    <h1 id="nf-title">Page not found</h1>
    <p class="msg">The page you're looking for doesn't exist. It may have moved, or the link may be mistyped.</p>
    <p class="path" id="nf-path" hidden></p>
    <div class="actions">
      <a class="btn primary" href="/" data-local="index.html">Go to the home page</a>
      <a class="btn" href="/chapters/{first['slug']}.html" data-local="chapters/{first['slug']}.html">Start with {esc(first['short_label'])}</a>
    </div>
    <nav class="quick" aria-labelledby="nf-quick"><h2 id="nf-quick">Popular starting points</h2><ul>{quick}</ul></nav>
    <p class="hint">Tip: on any tutorial page, press <kbd>/</kbd> to search every chapter.</p>
  </section>
</main>
<script>{NOTFOUND_JS}</script>
</body>
</html>
"""
