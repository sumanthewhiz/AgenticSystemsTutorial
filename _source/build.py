"""Build the tutorial: _source/**/*.md -> static, offline HTML (index.html, chapters/*.html, assets/search-index.js).

Needs Python with markdown-it-py and PyYAML (SwarmPipe's .venv has both):
    python _source/build.py                        # build everything
    python _source/build.py --check                # build + validate against SwarmPipe (facts.json + source)
    python _source/build.py --check --only 06-contracts-and-quality 07-publishing-lineage
Refresh the ground truth after changing SwarmPipe:  python _source/extract_facts.py
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sitegen.render import BuildError, Page, render_md, render_page_body  # noqa: E402
from sitegen.templates import SITE, chapter_body, home_body, shell, sidebar, toc_html  # noqa: E402

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
OUT_CH = ROOT / "chapters"


def read_source(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end == -1:
            raise BuildError(f"{path.name}: front matter not closed")
        return yaml.safe_load(text[4:end]) or {}, text[end + 5:]
    return {}, text


def load_outline() -> dict:
    outline = yaml.safe_load((SRC / "outline.yaml").read_text(encoding="utf-8"))
    letter = iter("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    for part in outline["parts"]:
        for ch in part["chapters"]:
            if part.get("appendix"):
                ch["short"] = next(letter)
                ch["short_label"] = f"Appendix {ch['short']}"
                ch["kind"] = "appendix"
            else:
                ch["short"] = str(int(ch["slug"].split("-")[0]))
                ch["short_label"] = f"Chapter {ch['short']}"
                ch["kind"] = "chapter"
            ch["part"] = part
    return outline


def cheatsheet_md(facts: dict) -> str:
    groups: dict[str, list] = {}
    for c in facts["cli"]:
        if not c["group"]:
            groups.setdefault(c["path"].split()[0] if " " in c["path"] else "(top level)", []).append(c)
    md = ["## Complete command reference", "",
          "Generated from SwarmPipe's CLI itself, so it is always accurate. `sp` means `python -m swarmpipe` "
          "(see [Chapter 0](00-welcome.html#make-sp-a-shortcut)). Add `--help` to any command for details.", ""]
    for g in sorted(groups, key=lambda x: (x != "(top level)", x)):
        md += [f"### {g}", "", "| Command | Arguments and options | What it does |", "|---|---|---|"]
        for c in groups[g]:
            args = []
            for p in c["params"]:
                if p["kind"] == "argument":
                    args.append(f"`<{p['name']}>`")
                else:
                    args.append("`" + "/".join(p["opts"]) + ("" if p["flag"] else " <v>") + "`")
            md.append(f"| `sp {c['path']}` | {' '.join(args) or '&nbsp;'} | {c['help'].replace('|', '&#124;') or '&nbsp;'} |")
        md.append("")
    md += ["## Scenarios", "", "Use with `sp scenarios drop <name>` (add `--process` to run it synchronously without a server).", "",
           "| Scenario | What it simulates |", "|---|---|"]
    md += [f"| `{s['name']}` | {s['description'].replace('|', '&#124;')} |" for s in facts["scenarios"]]
    md += ["", "## Runtime flags", "", "Change them with `sp chaos set <key> <value>`; `chaos.` keys may be written without the prefix. "
           "Inspect with `sp chaos show`, reset with `sp chaos clear`.", "", "| Flag | Default |", "|---|---|"]
    defaults = facts.get("chaos_defaults", {})
    for f in facts["runtime_flags"]:
        d = defaults.get(f[6:]) if f.startswith("chaos.") else None
        md.append(f"| `{f}` | {json.dumps(d) if d is not None else '&nbsp;'} |")
    md += ["", "## Dashboard tabs", "", "| Tab | Use it for |", "|---|---|"]
    md += [f"| **{t['label']}** | see the chapter where it is introduced |" for t in facts["dashboard_tabs"]]
    return "\n".join(md) + "\n"


def minutes(s: str) -> int:
    m = re.match(r"\s*(\d+)", str(s or ""))
    return int(m.group(1)) if m else 0


def plain(html_text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", html_text))).strip()


def search_entries(page: Page) -> list:
    chunks = re.split(r'(<h2 id="[^"]+">.*?</h2>)', page.body)
    sections, cur_id, cur_h = [], "", "Introduction"
    buf = ""
    for c in chunks:
        m = re.match(r'<h2 id="([^"]+)">(.*?)</h2>', c)
        if m:
            if plain(buf):
                sections.append([cur_id, cur_h, plain(buf)[:1800]])
            cur_id, cur_h, buf = m.group(1), plain(m.group(2)), ""
        else:
            buf += c
    if plain(buf):
        sections.append([cur_id, cur_h, plain(buf)[:1800]])
    return sections


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="validate against SwarmPipe")
    ap.add_argument("--only", nargs="*", default=None, help="limit the report to these slugs")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any warning")
    args = ap.parse_args()

    outline = load_outline()
    facts_path = SRC / "facts.json"
    facts = json.loads(facts_path.read_text(encoding="utf-8")) if facts_path.exists() else None
    chapters = [ch for part in outline["parts"] for ch in part["chapters"]]
    pages: dict[str, Page] = {}
    for ch in chapters:
        page = Page(slug=ch["slug"], title=ch["title"], label=ch["short_label"], part=ch["part"], kind=ch["kind"])
        src = SRC / "chapters" / f"{ch['slug']}.md"
        fm, text = read_source(src) if src.exists() else ({}, "")
        if ch["slug"] == "cheatsheet" and facts:
            text = text + "\n\n" + cheatsheet_md(facts)
        if not text.strip():
            page.meta["placeholder"] = True
            text = ":::note This chapter is being written\nIt will cover: " + "; ".join(ch.get("covers") or []) + ".\n:::\n"
        page.meta.update({k: ch.get(k) for k in ("time", "level", "summary")})
        page.meta.update(fm)
        try:
            page.body = render_page_body(text, page)
        except BuildError as exc:
            page.warn(f"BUILD ERROR: {exc}")
            page.body = f'<div class="box danger"><div class="box-body"><p>Build error: {html.escape(str(exc))}</p></div></div>'
        page.meta["labs_count"] = page.counts.get("lab", 0)
        page.words = len(plain(page.body).split())
        pages[ch["slug"]] = page

    order = [ch for ch in chapters]
    OUT_CH.mkdir(parents=True, exist_ok=True)
    for i, ch in enumerate(order):
        page = pages[ch["slug"]]
        prev_ch = order[i - 1] if i > 0 else None
        next_ch = order[i + 1] if i + 1 < len(order) else None
        body = chapter_body(page, prev_ch, next_ch)
        out = shell(title=f"{page.label}: {plain(page.title)} · {SITE}", root="../", slug=page.slug, body=body,
                    side=sidebar(outline, page.slug, ""), toc=toc_html(page.toc))
        (OUT_CH / f"{page.slug}.html").write_text(out, encoding="utf-8")

    intro_page = Page(slug="index", title="Home")
    fm, intro_text = read_source(SRC / "home.md") if (SRC / "home.md").exists() else ({}, "")
    intro_html = render_page_body(intro_text, intro_page) if intro_text else ""
    real = [p for p in pages.values() if p.kind == "chapter"]
    total_min = sum(minutes(ch.get("time")) for ch in chapters if ch["kind"] == "chapter")
    stats = {"chapters": len(real), "hands-on labs": sum(p.counts.get("lab", 0) for p in real),
             "quiz questions": sum(p.counts.get("quiz", 0) for p in real), "hours of learning": f"~{round(total_min / 60)}"}
    home = shell(title=f"{plain(outline['title'])} · {SITE}", root="", slug="index", home=True,
                 body=home_body(outline, intro_html, stats), side=sidebar(outline, "", "chapters/"))
    (ROOT / "index.html").write_text(home, encoding="utf-8")

    # Cloudflare Pages serves the closest 404.html for unknown URLs (without one it falls back to SPA mode and
    # silently serves the home page). It can be served at any depth, so it uses root-absolute links.
    notfound = ('<article class="chapter"><div class="crumbs"><a href="/">Home</a></div>'
                '<h1><span class="num">404</span>Page not found</h1>'
                "<p class=\"lede\">That page doesn't exist. It may have moved, or the link may be mistyped.</p>"
                '<p><a class="btn primary" href="/">Go to the home page</a></p>'
                "<p>Or press <kbd>/</kbd> to search every chapter.</p></article>")
    (ROOT / "404.html").write_text(shell(title=f"Page not found · {SITE}", root="/", slug="404", body=notfound,
                                         side=sidebar(outline, "", "/chapters/")), encoding="utf-8")

    index = [{"u": f"chapters/{p.slug}.html", "t": plain(p.title), "l": p.label, "p": (p.part or {}).get("name", ""),
              "s": plain(str(p.meta.get("summary", ""))), "h": search_entries(p)} for p in pages.values()]
    (ROOT / "assets").mkdir(exist_ok=True)
    (ROOT / "assets" / "search-index.js").write_text("window.TUTORIAL_INDEX = " + json.dumps(index, ensure_ascii=False) + ";\n",
                                                     encoding="utf-8")

    if args.check:
        if not facts:
            print("facts.json missing - run extract_facts.py first")
            return 1
        from sitegen.check import Checker

        checker = Checker(facts_path)
        for p in pages.values():
            if p.meta.get("placeholder"):
                continue
            checker.check_page(p)
            if p.kind == "chapter" and p.slug != "00-welcome":
                for need, label in (("lab", "a :::lab"), ("quiz", "a :::quiz"), ("takeaways", "a :::takeaways box")):
                    if not p.counts.get(need):
                        p.warn(f"missing {label}")
                if not p.meta.get("objectives"):
                    p.warn("missing objectives in front matter")
                if p.words < 1200:
                    p.warn(f"only {p.words} words (aim for 1500-3000)")
        checker.check_links(pages)

    selected = [p for p in pages.values() if not args.only or p.slug in args.only]
    total_warn = 0
    print(f"{'page':38} {'words':>6} {'labs':>4} {'break':>5} {'quiz':>4} {'diag':>4} {'warn':>4}")
    for p in selected:
        flag = " (placeholder)" if p.meta.get("placeholder") else ""
        print(f"{p.slug:38} {p.words:>6} {p.counts.get('lab', 0):>4} {p.counts.get('breakit', 0):>5} {p.counts.get('quiz', 0):>4} "
              f"{p.counts.get('diagram', 0):>4} {len(p.warnings):>4}{flag}")
        total_warn += len(p.warnings)
    for p in selected:
        for w in p.warnings:
            print(f"  [{p.slug}] {w}")
    print(f"built {len(pages)} pages + index.html; warnings in report: {total_warn}")
    return 1 if (args.strict and total_warn) else 0


if __name__ == "__main__":
    sys.exit(main())
