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
