"""--check: validate every page against ground truth so the tutorial never teaches something SwarmPipe can't do.

Checks: `sp ...` / `python -m swarmpipe ...` commands and their options; scenario names, chaos flags, LLM profiles,
eval suites, tenants; project file paths; API routes; code identifiers in inline code (must appear somewhere in the
SwarmPipe source); internal links and #anchors; required chapter elements (lab, quiz, takeaways, objectives).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_CMD = re.compile(r"^(?:sp|(?:\S*python(?:\.exe)?)\s+-m\s+swarmpipe)\s+(.+)$")
_TOK = re.compile(r'"[^"]*"|\'[^\']*\'|\S+')
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*(?:\(\))?$")
TOP_DIRS = {"swarmpipe", "config", "docs", "evals", "prompts", "knowledge", "tests"}
TEXT_EXT = {".py", ".yaml", ".yml", ".md", ".json", ".jsonl", ".js", ".html", ".css", ".txt", ".toml"}
EVAL_SUITES = {"all", "triage", "redteam", "router", "analyst", "judge"}


class Checker:
    def __init__(self, facts_path: Path):
        self.facts = json.loads(facts_path.read_text(encoding="utf-8"))
        project = Path(self.facts["project"])
        # facts.json stores the project relative to the tutorial root (the folder above _source)
        self.project = project if project.is_absolute() else (facts_path.resolve().parent.parent / project).resolve()
        self.cli = {tuple(c["path"].split()): c for c in self.facts["cli"]}
        self.scenarios = {s["name"] for s in self.facts["scenarios"]}
        self.flags = set(self.facts["runtime_flags"])
        cfg = self.facts.get("config", {})
        self.profiles = set((cfg.get("llm") or {}).get("profiles", {}) or {})
        self.tenants = set(cfg.get("tenants", {}) or {}) | {"default"}
        self.actions = set((self.facts.get("policies") or {}).get("actions", {}) or {})
        self.files = set(self.facts["files"])
        self.routes = [re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(p)) + "/?$") for p, _ in self.facts.get("api_routes", [])]
        self.words: set[str] = set()
        for p in self.project.rglob("*"):
            if p.is_file() and p.suffix in TEXT_EXT and not any(x in p.parts for x in (".venv", ".git", "__pycache__", ".pytest_cache")) \
                    and not (p.parts[len(self.project.parts)] == "data" if len(p.parts) > len(self.project.parts) else False):
                try:
                    self.words.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", p.read_text(encoding="utf-8", errors="ignore")))
                except OSError:
                    pass
        self.words_lower = {w.lower() for w in self.words}

    # ---------------------------------------------------------------- commands
    def _opt(self, entry: dict, name: str) -> dict | None:
        for p in entry["params"]:
            if p["kind"] == "option" and name in p["opts"]:
                return p
        return None

    def check_command(self, page, raw: str) -> None:
        s = re.sub(r"\s+#.*$", "", raw.strip())
        m = _CMD.match(s)
        if not m:
            return
        toks = [t for t in _TOK.findall(m.group(1)) if t not in ("|", ">", ">>")]
        if toks and toks[0] in ("--help", "-h"):
            return
        path = next((tuple(toks[:n]) for n in (2, 1) if tuple(toks[:n]) in self.cli and not self.cli[tuple(toks[:n])]["group"]), None)
        if path is None:
            if toks and tuple(toks[:1]) in self.cli and ("--help" in toks or len(toks) == 1):
                return
            page.warn(f"unknown command: sp {' '.join(toks)}")
            return
        entry, rest, positional, k = self.cli[path], toks[len(path):], [], 0
        cmd = "sp " + " ".join(path)
        while k < len(rest):
            t = rest[k]
            if t.startswith("--"):
                name = t.split("=", 1)[0]
                p = self._opt(entry, name)
                if name != "--help" and p is None:
                    page.warn(f"unknown option {name} for `{cmd}`")
                elif p is not None and not p["flag"]:
                    val = t.split("=", 1)[1] if "=" in t else (rest[k + 1] if k + 1 < len(rest) else None)
                    if "=" not in t:
                        k += 1
                    self._check_value(page, path, name, (val or "").strip("\"'"))
            elif not re.match(r"^-[A-Za-z]", t):
                positional.append(t.strip("\"'"))
            k += 1
        self._check_positional(page, path, positional)

    def _placeholder(self, v: str) -> bool:
        return not v or v.startswith(("<", "$", "{")) or v in ("...", "…")

    def _check_value(self, page, path, name, val) -> None:
        if self._placeholder(val):
            return
        if path == ("evals", "run") and name == "--suite" and val not in EVAL_SUITES:
            page.warn(f"unknown eval suite '{val}' (known: {sorted(EVAL_SUITES)})")
        if name == "--profile" and self.profiles and val not in self.profiles:
            page.warn(f"unknown LLM profile '{val}' (known: {sorted(self.profiles)})")
        if name == "--tenant" and val not in self.tenants:
            page.warn(f"unknown tenant '{val}' (known: {sorted(self.tenants)})")
        if path == ("evals", "calibrate-judge") and name == "--version" and val not in ("v1", "v2"):
            page.warn(f"unknown judge version '{val}'")

    def _check_positional(self, page, path, pos) -> None:
        first = pos[0] if pos else ""
        if self._placeholder(first):
            return
        if path == ("scenarios", "drop") and first not in self.scenarios:
            page.warn(f"unknown scenario '{first}'")
        elif path == ("chaos", "set") and first not in self.flags and f"chaos.{first}" not in self.flags:
            page.warn(f"unknown runtime flag '{first}' for `sp chaos set`")
        elif path == ("llm", "use") and self.profiles and first not in self.profiles:
            page.warn(f"unknown LLM profile '{first}'")
        elif path in (("policy",), ("autonomy", "set")) and self.actions and first not in self.actions:
            page.warn(f"unknown action class '{first}' (known: {sorted(self.actions)})")

    # ---------------------------------------------------------------- inline code
    def check_inline(self, page, code: str) -> None:
        s = code.strip()
        if _CMD.match(s):
            self.check_command(page, s)
            return
        if s.startswith("/") and not s.startswith("//"):
            path = s.split("?")[0].split(" ")[0]
            if path.startswith(("/api", "/a2a", "/metrics", "/healthz", "/readyz", "/.well-known")) and "<" not in path \
                    and not any(r.match(path) for r in self.routes) and path not in ("/metrics", "/healthz", "/readyz"):
                page.warn(f"API route not found: {path}")
            return
        norm = s.replace("\\", "/")
        if "/" in norm and " " not in norm:
            p = re.sub(r"^\./", "", norm).split("#")[0]
            p = re.sub(r":\d+$", "", p)
            first = p.split("/")[0]
            if first in TOP_DIRS and "*" not in p and "<" not in p:
                if p not in self.files and not any(f.startswith(p.rstrip("/") + "/") for f in self.files):
                    page.warn(f"path not found in SwarmPipe: {s}")
            return
        if _IDENT.match(s) and len(s) > 2:
            parts = [x for x in s.rstrip("()").split(".") if x]
            missing = [x for x in parts if x not in self.words and x.lower() not in self.words_lower]
            if missing:
                page.warn(f"identifier not found in SwarmPipe source: `{s}`")

    # ---------------------------------------------------------------- page
    def check_page(self, page) -> None:
        for lang, code in page.fences:
            if lang in ("powershell", "ps", "ps1", "pwsh", "console", "bash", "sh", "text"):
                for line in code.split("\n"):
                    self.check_command(page, line)
        for c in page.inline_codes:
            self.check_inline(page, c)

    def check_links(self, pages: dict) -> None:
        for page in pages.values():
            ext = 0
            for href in page.links:
                if href.startswith(("http://", "https://")):
                    ext += 1
                    continue
                if href.startswith("mailto:"):
                    continue
                target, _, anchor = href.partition("#")
                if target == "":
                    tp = page
                else:
                    name = target.split("/")[-1]
                    slug = name[:-5] if name.endswith(".html") else None
                    if slug == "index":
                        continue
                    tp = pages.get(slug) if slug else None
                    if tp is None:
                        page.warn(f"broken link: {href}")
                        continue
                if anchor and anchor not in tp.ids:
                    page.warn(f"broken anchor: {href}")
            page.counts["external_links"] = ext
