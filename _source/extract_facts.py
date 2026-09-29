"""Extract ground-truth facts about SwarmPipe for the tutorial (commands, scenarios, agents, tools, ...).

Run with SwarmPipe's interpreter so its dependencies are importable:
    <your-SwarmPipe-folder>\\.venv\\Scripts\\python.exe _source\\extract_facts.py [--project <your-SwarmPipe-folder>]
The SwarmPipe folder comes from --project, else the SWARMPIPE_DIR environment variable, else a sibling SwarmPipe folder.

Uses an isolated temporary workspace, so it never touches the project's own data/ folder or a running server.
Writes _source/facts.json (used by build.py --check) and _source/facts.md (human-readable reference)."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_PROJECT = os.environ.get("SWARMPIPE_DIR") or str(HERE.parent.parent / "SwarmPipe")


def walk_cli(cmd, prefix: list[str]) -> list[dict]:
    # duck-typed: recent Typer versions ship their own Click classes, so isinstance(click.Group) is unreliable
    out = []
    if hasattr(cmd, "commands"):
        for name, sub in sorted(cmd.commands.items()):
            out += walk_cli(sub, prefix + [name])
        if prefix:
            out.append({"path": " ".join(prefix), "group": True, "help": (cmd.help or "").strip().split("\n")[0], "params": []})
        return out
    params = []
    for p in cmd.params:
        if getattr(p, "param_type_name", "") == "option":
            params.append({"kind": "option", "opts": list(p.opts) + list(p.secondary_opts), "flag": bool(p.is_flag),
                           "default": None if callable(p.default) else p.default, "help": (p.help or "").strip()})
        else:
            params.append({"kind": "argument", "name": p.name, "required": bool(p.required),
                           "default": None if callable(p.default) else p.default})
    out.append({"path": " ".join(prefix), "group": False, "help": (cmd.help or "").strip().split("\n")[0], "params": params})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=DEFAULT_PROJECT)
    args = ap.parse_args()
    project = Path(args.project).resolve()
    sys.path.insert(0, str(project))

    import typer.main
    import yaml

    from swarmpipe import scenarios
    from swarmpipe.app import Services
    from swarmpipe.cli import app as cli_app
    from swarmpipe.config import load_settings
    from swarmpipe.llm import mock

    facts: dict = {}  # no project location is stored: facts must not contain machine-local paths
    facts["cli"] = walk_cli(typer.main.get_command(cli_app), [])
    facts["scenarios"] = [{"name": s.name, "description": s.description} for s in scenarios.SCENARIOS.values()]

    tmp = Path(tempfile.mkdtemp(prefix="tutorial_facts_"))
    svc = None
    try:
        ov = {"paths": {"data_dir": str(tmp / "data"), "inbox": str(tmp / "inbox")}, "tracing": {"export_jsonl": False}}
        svc = Services(load_settings(project, ov), console_logs=False, log_level="ERROR")
        svc.bootstrap()
        agents = []
        for a in svc.agents.all():
            agents.append({"id": a.id, "name": a.name, "kind": a.kind, "role": a.role, "description": a.description,
                           "tools": list(a.tools), "scopes": sorted(a.scopes), "class": type(a).__name__,
                           "module": type(a).__module__})
        facts["agents"] = agents
        facts["tools"] = [{"name": s.name, "version": s.version, "description": s.description, "scope": s.scope,
                           "read_only": s.read_only, "destructive": s.destructive, "trust": s.trust,
                           "max_output_chars": s.max_output_chars, "args": sorted(s.input_schema().get("properties", {}))}
                          for s in svc.tools.tools.values()]
        wfs = []
        for name, wf in svc.engine.workflows.items():
            wfs.append({"name": name, "description": wf.description,
                        "steps": [{"name": st.name, "kind": getattr(st, "kind", "")} for st in wf.steps]})
        facts["workflows"] = wfs
        facts["prompts"] = [{k: getattr(p, k, None) for k in ("id", "version", "role", "description")} for p in svc.prompts.list()]
        try:
            from swarmpipe.mcp_server import McpServer

            m = McpServer(svc, "oncall")
            tl = m.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
            facts["mcp_tools"] = [{"name": t["name"], "description": t.get("description", "")[:160],
                                   "annotations": t.get("annotations", {})} for t in tl]
            rl = m.handle({"jsonrpc": "2.0", "id": 2, "method": "resources/list"}).get("result", {}).get("resources", [])
            facts["mcp_resources"] = [r.get("uri") for r in rl]
        except Exception as exc:  # noqa: BLE001
            facts["mcp_tools_error"] = repr(exc)
        try:
            from swarmpipe.web.api import create_app

            api = create_app(svc, None)
            facts["api_routes"] = sorted({(r.path, ",".join(sorted(getattr(r, "methods", []) or []))) for r in api.routes
                                          if getattr(r, "path", "").startswith(("/api", "/a2a", "/metrics", "/healthz", "/readyz", "/.well-known"))})
        except Exception as exc:  # noqa: BLE001
            facts["api_routes_error"] = repr(exc)
    finally:
        if svc is not None:
            svc.close()
        shutil.rmtree(tmp, ignore_errors=True)

    code = "\n".join(p.read_text(encoding="utf-8") for p in (project / "swarmpipe").rglob("*.py"))
    flags = set(re.findall(r'flags\.(?:get|set)\(\s*"([^"]+)"', code))
    flags |= {f"chaos.{k}" for k in mock.DEFAULTS}
    facts["runtime_flags"] = sorted(flags)
    facts["chaos_defaults"] = mock.DEFAULTS
    facts["metrics"] = sorted(set(re.findall(r'metrics\.(?:inc|gauge|observe|timing)\(\s*"([^"]+)"', code)))
    appjs = (project / "swarmpipe" / "web" / "static" / "app.js").read_text(encoding="utf-8")
    tabs_block = appjs[appjs.index("const TABS"):appjs.index("];", appjs.index("const TABS"))]
    facts["dashboard_tabs"] = [{"key": k, "label": l} for k, l in re.findall(r'\[\s*"([^"]+)"\s*,\s*"([^"]+)"', tabs_block)]
    facts["gate"] = yaml.safe_load((project / "evals" / "gate.yaml").read_text(encoding="utf-8"))
    ds = {}
    for f in sorted((project / "evals" / "datasets").glob("*.jsonl")):
        rows = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
        ds[f.name] = [{k: r.get(k) for k in ("id", "drops", "scenario", "question", "user", "approver", "flags", "expect", "phases") if k in r}
                      for r in rows]
    facts["eval_datasets"] = ds
    facts["policies"] = yaml.safe_load((project / "config" / "policies.yaml").read_text(encoding="utf-8"))
    cfg = yaml.safe_load((project / "config" / "swarmpipe.yaml").read_text(encoding="utf-8"))
    facts["config_sections"] = {k: (sorted(v.keys()) if isinstance(v, dict) else v) for k, v in cfg.items()}
    facts["config"] = cfg
    facts["files"] = sorted(str(p.relative_to(project)).replace("\\", "/") for p in project.rglob("*")
                            if p.is_file() and not any(x in p.parts for x in (".venv", "data", "__pycache__", ".git", ".pytest_cache"))
                            and "evals/reports" not in str(p.relative_to(project)).replace("\\", "/"))
    facts["files"] += sorted(str(p.relative_to(project)).replace("\\", "/") for p in (project / "swarmpipe" / "data").rglob("*.py"))

    (HERE / "facts.json").write_text(json.dumps(facts, indent=1, default=str), encoding="utf-8")
    md = ["# SwarmPipe facts (generated by extract_facts.py - do not edit)", ""]
    md.append("## CLI commands (`sp` = `python -m swarmpipe`)")
    for c in facts["cli"]:
        if c["group"]:
            continue
        opts = " ".join(("/".join(p["opts"]) + ("" if p["flag"] else " <v>")) if p["kind"] == "option" else f"<{p['name']}>" for p in c["params"])
        md.append(f"- `sp {c['path']}` {opts} - {c['help']}")
    md += ["", "## Scenarios (`sp scenarios drop <name> [--process]`)"] + [f"- `{s['name']}` - {s['description']}" for s in facts["scenarios"]]
    md += ["", "## Agents"] + [f"- `{a['id']}` {a['name']} ({a['kind']}, role={a['role']}) tools={a['tools']} - {a['description']}" for a in facts.get("agents", [])]
    md += ["", "## Tools"] + [f"- `{t['name']}` v{t['version']} scope={t['scope']} read_only={t['read_only']} args={t['args']} - {t['description']}" for t in facts.get("tools", [])]
    md += ["", "## Workflows"] + [f"- `{w['name']}`: {' -> '.join(s['name'] for s in w['steps'])} - {w['description']}" for w in facts.get("workflows", [])]
    md += ["", "## Dashboard tabs"] + [f"- {t['label']} (`{t['key']}`)" for t in facts["dashboard_tabs"]]
    md += ["", "## Runtime flags"] + [f"- `{f}`" for f in facts["runtime_flags"]]
    md += ["", "## Metrics"] + [f"- `{m}`" for m in facts["metrics"]]
    md += ["", "## API routes"] + [f"- {m} `{p}`" for p, m in facts.get("api_routes", [])]
    md += ["", "## MCP tools"] + [f"- `{t['name']}` {t['annotations']} - {t['description']}" for t in facts.get("mcp_tools", [])]
    md += ["", "## Prompts"] + [f"- `{p['id']}` {p['version']} (role {p['role']}) - {p['description']}" for p in facts.get("prompts", [])]
    md += ["", "## Eval gate", "```yaml", yaml.safe_dump(facts["gate"], sort_keys=False), "```"]
    md += ["", "## Eval datasets"]
    for name, rows in ds.items():
        md.append(f"### {name}")
        md += [f"- `{r.get('id')}` {json.dumps({k: v for k, v in r.items() if k != 'id'})[:260]}" for r in rows]
    md += ["", "## Project files"] + [f"- `{f}`" for f in facts["files"]]
    (HERE / "facts.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"facts: {len(facts['cli'])} cli entries, {len(facts['scenarios'])} scenarios, {len(facts.get('agents', []))} agents, "
          f"{len(facts.get('tools', []))} tools, {len(facts.get('workflows', []))} workflows, {len(facts['dashboard_tabs'])} tabs, "
          f"{len(facts['runtime_flags'])} flags, {len(facts['metrics'])} metrics, {len(facts.get('api_routes', []))} routes, "
          f"{len(facts.get('mcp_tools', []))} mcp tools, {len(facts['files'])} files; errors: "
          f"{[k for k in facts if k.endswith('_error')] or 'none'}")


if __name__ == "__main__":
    main()
