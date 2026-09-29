"""Markdown + teaching components -> HTML.

Components (fenced with ::: lines, not nestable; code fences inside are fine):
  :::concept Term        :::analogy [Title]     :::note [Title]      :::tip [Title]
  :::warning [Title]     :::danger [Title]      :::swarmpipe [Title] :::lab Title
  :::breakit Title       :::deepdive Title      :::takeaways         :::quiz
  :::flow [Caption]      :::flow-v [Caption]    :::loop [Caption]    :::layers [Caption]   :::cards [Caption]
Diagram/card items are one per line: "Title | subtitle" (inline Markdown allowed).
Quiz: "Q: question", options "- [ ] wrong" / "- [x] right", explanation lines starting with ">".
Code fences: ```powershell (copy button) | ```output (expected output) | ```python | ```yaml | ```json | ```sql | ```text
"""
from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import dataclass, field

from markdown_it import MarkdownIt

BOXES = {
    "concept": ("Concept", "📘"), "analogy": ("Analogy", "💭"), "note": ("Note", "ℹ️"), "tip": ("Tip", "💡"),
    "warning": ("Production gotcha", "⚠️"), "danger": ("Danger", "🛑"), "swarmpipe": ("In SwarmPipe", "🐝"),
    "lab": ("Hands-on lab", "🧪"), "breakit": ("Break it", "💥"), "deepdive": ("Deep dive", "🔍"),
    "takeaways": ("Key takeaways", "✅"),
}
DIAGRAMS = {"flow", "flow-v", "loop", "layers", "cards"}
KINDS = set(BOXES) | DIAGRAMS | {"quiz"}
LANG_LABEL = {"powershell": "PowerShell", "python": "Python", "yaml": "YAML", "json": "JSON", "sql": "SQL",
              "text": "Text", "output": "Expected output", "bash": "Shell", "http": "HTTP", "html": "HTML"}
_OPEN = re.compile(r"^:::([a-z][a-z-]*)\s*(.*)$")
_FENCE = re.compile(r"^\s*(```|~~~)")


class BuildError(Exception):
    pass


@dataclass
class Page:
    slug: str
    title: str
    label: str = ""
    part: dict | None = None
    meta: dict = field(default_factory=dict)
    kind: str = "chapter"
    body: str = ""
    toc: list = field(default_factory=list)
    ids: set = field(default_factory=set)
    inline_codes: list = field(default_factory=list)
    links: list = field(default_factory=list)
    fences: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)
    words: int = 0

    def unique_id(self, base: str) -> str:
        sid, n = base, 2
        while sid in self.ids:
            sid, n = f"{base}-{n}", n + 1
        self.ids.add(sid)
        return sid

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def slugify(text: str) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", "", text)).lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    return re.sub(r"[\s-]+", "-", s).strip("-") or "section"


def _highlight(lang: str, code: str) -> str:
    out = []
    for line in code.split("\n"):
        esc = html.escape(line)
        if lang in ("powershell", "python", "yaml", "bash"):
            m = re.search(r"(^|\s)(#.*)$", line)
            if m:
                cut = m.start(2)
                esc = html.escape(line[:cut]) + f'<span class="c">{html.escape(line[cut:])}</span>'
        out.append(esc)
    return "\n".join(out)


def render_code(lang: str, code: str) -> str:
    lang = {"ps": "powershell", "ps1": "powershell", "pwsh": "powershell", "console": "powershell", "sh": "bash",
            "yml": "yaml"}.get(lang, lang or "text")
    code = code.rstrip("\n")
    label = LANG_LABEL.get(lang, lang)
    copy = "" if lang == "output" else '<button class="copy" type="button" aria-label="Copy code">Copy</button>'
    cls = "code output" if lang == "output" else "code"
    return (f'<div class="{cls}" data-lang="{lang}"><div class="code-head"><span>{label}</span>{copy}</div>'
            f'<pre><code>{_highlight(lang, code)}</code></pre></div>\n')


def _make_md() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": True, "typographer": False}).enable("table")

    def fence(self, tokens, idx, options, env):
        tok = tokens[idx]
        info = (tok.info or "").strip()
        lang = info.split()[0].lower() if info else "text"
        page = env.get("page")
        if page is not None:
            page.fences.append((lang, tok.content))
        return render_code(lang, tok.content)

    md.add_render_rule("fence", fence)
    return md


MD = _make_md()


def inline(text: str) -> str:
    return MD.renderInline(text or "")


def render_md(text: str, page: Page, toc: bool = True) -> str:
    env = {"page": page}
    tokens = MD.parse(text, env)
    for i, t in enumerate(tokens):
        if t.type == "heading_open" and t.tag == "h1":
            page.warn("a top-level '# ' heading duplicates the page title; use '##' for sections")
        if t.type == "heading_open" and t.tag in ("h2", "h3", "h4"):
            content = tokens[i + 1].content
            sid = page.unique_id(slugify(content))
            t.attrSet("id", sid)
            if toc and t.tag in ("h2", "h3"):
                page.toc.append((t.tag, sid, inline(content)))
        if t.type == "inline":
            for c in t.children or []:
                if c.type == "code_inline":
                    page.inline_codes.append(c.content)
                elif c.type == "link_open":
                    page.links.append(c.attrGet("href") or "")
    return MD.renderer.render(tokens, MD.options, env)


def split_blocks(text: str) -> list[tuple]:
    lines, out, buf, i, fence = text.split("\n"), [], [], 0, None
    while i < len(lines):
        line = lines[i]
        m = _OPEN.match(line) if fence is None else None
        if m and m.group(1) in KINDS:
            if buf:
                out.append(("md", "\n".join(buf)))
                buf = []
            inner, j, f2 = [], i + 1, None
            while j < len(lines):
                fm = _FENCE.match(lines[j])
                if fm:
                    f2 = fm.group(1) if f2 is None else (None if lines[j].strip().startswith(f2) else f2)
                if f2 is None and lines[j].strip() == ":::":
                    break
                inner.append(lines[j])
                j += 1
            else:
                raise BuildError(f"unclosed :::{m.group(1)} opened at line {i + 1}")
            out.append((m.group(1), m.group(2).strip(), "\n".join(inner)))
            i = j + 1
            continue
        if m is not None or (fence is None and line.startswith(":::")):
            raise BuildError(f"unknown or stray component '{line.strip()}' at line {i + 1} (known: {', '.join(sorted(KINDS))})")
        fm = _FENCE.match(line)
        if fm:
            fence = fm.group(1) if fence is None else (None if line.strip().startswith(fence) else fence)
        buf.append(line)
        i += 1
    if buf:
        out.append(("md", "\n".join(buf)))
    return out


def _items(inner: str) -> list[tuple[str, str]]:
    items = []
    for line in inner.split("\n"):
        s = re.sub(r"^[-*]\s+", "", line.strip())
        if s:
            t, _, sub = s.partition("|")
            items.append((t.strip(), sub.strip()))
    return items


def _figure(cls: str, body: str, caption: str, extra: str = "") -> str:
    cap = f"<figcaption>{inline(caption)}</figcaption>" if caption else ""
    return f'<figure class="diagram"><div class="{cls}">{body}</div>{extra}{cap}</figure>\n'


def render_diagram(kind: str, title: str, inner: str, page: Page) -> str:
    items = _items(inner)
    if not items:
        page.warn(f":::{kind} has no items")
    page.counts["diagram"] += 1
    if kind == "layers":
        rows = "".join(f'<div class="layer"><div class="layer-t">{inline(t)}</div><div class="layer-s">{inline(s)}</div></div>'
                       for t, s in items)
        return _figure("layers", rows, title)
    if kind == "cards":
        cards = "".join(f'<div class="card"><div class="card-t">{inline(t)}</div><div class="card-s">{inline(s)}</div></div>'
                        for t, s in items)
        return _figure("cards", cards, title)
    nodes = [f'<div class="node"><div class="node-t">{inline(t)}</div>' + (f'<div class="node-s">{inline(s)}</div>' if s else "") + "</div>"
             for t, s in items]
    body = '<div class="arrow" aria-hidden="true"></div>'.join(nodes)
    cls = {"flow": "flow", "flow-v": "flow vertical", "loop": "flow loop"}[kind]
    back = '<div class="loop-back" aria-hidden="true">&#8634; repeat until the goal is met or a budget runs out</div>' if kind == "loop" else ""
    return _figure(cls, body, title, back)


def render_quiz(inner: str, page: Page) -> str:
    qs, cur = [], None
    for raw in inner.split("\n"):
        s = raw.strip()
        if not s:
            continue
        if s.startswith("Q:"):
            cur = {"q": s[2:].strip(), "opts": [], "exp": []}
            qs.append(cur)
        elif cur is None:
            continue
        elif re.match(r"^- \[( |x|X)\] ", s):
            cur["opts"].append([s[3] in "xX", s[6:].strip()])
        elif s.startswith(">"):
            cur["exp"].append(s[1:].strip())
        elif cur["exp"]:
            cur["exp"].append(s)
        elif cur["opts"]:
            cur["opts"][-1][1] += " " + s
        else:
            cur["q"] += " " + s
    parts = []
    for n, q in enumerate(qs, 1):
        if len(q["opts"]) < 2 or sum(1 for c, _ in q["opts"] if c) != 1 or not q["exp"]:
            page.warn(f"quiz question {n} needs 2+ options, exactly one [x] and an explanation: {q['q'][:70]}")
        opts = "".join(f'<li><button type="button" class="opt" data-correct="{"true" if c else "false"}">{inline(t)}</button></li>'
                       for c, t in q["opts"])
        parts.append(f'<div class="q"><div class="q-text"><span class="q-num">{n}</span><div>{inline(q["q"])}</div></div>'
                     f'<ul class="opts">{opts}</ul><div class="q-explain" hidden>{inline(" ".join(q["exp"]))}</div></div>')
    page.counts["quiz"] += len(qs)
    return ('<div class="box quiz"><div class="box-head"><span class="ico">❓</span><span class="kind">Check your understanding</span>'
            f'</div><div class="box-body">{"".join(parts)}</div></div>\n')


def render_box(kind: str, title: str, inner: str, page: Page) -> str:
    label, icon = BOXES[kind]
    page.counts[kind] += 1
    body = render_md(inner, page, toc=False)
    head_title = f'<span class="title">{inline(title)}</span>' if title else ""
    if kind == "deepdive":
        return (f'<details class="box deepdive"><summary><span class="ico">{icon}</span><span class="kind">{label}</span>'
                f'{head_title}</summary><div class="box-body">{body}</div></details>\n')
    return (f'<div class="box {kind}"><div class="box-head"><span class="ico">{icon}</span><span class="kind">{label}</span>'
            f'{head_title}</div><div class="box-body">{body}</div></div>\n')


def render_page_body(text: str, page: Page) -> str:
    out = []
    for block in split_blocks(text):
        if block[0] == "md":
            out.append(render_md(block[1], page))
        else:
            kind, title, inner = block
            if kind == "quiz":
                out.append(render_quiz(inner, page))
            elif kind in DIAGRAMS:
                out.append(render_diagram(kind, title, inner, page))
            else:
                out.append(render_box(kind, title, inner, page))
    return "".join(out)
