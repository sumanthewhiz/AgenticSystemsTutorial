# Production Agentic Systems, Hands-on

A chapter-by-chapter, hands-on tutorial on the concepts behind production-grade agentic (multi-agent) applications.
It uses the **[SwarmPipe](https://github.com/sumanthewhiz/SwarmPipe)** project as the live system you run, break and fix.

## Open it

Double-click **`index.html`**. Everything works offline in any modern browser, with no server and no internet. The same
files can be hosted as a static website (see [Host it on Cloudflare Pages](#host-it-on-cloudflare-pages)).

- The left sidebar lists every part and chapter. The right column shows the sections of the current page.
- Press <kbd>/</kbd> to search, and <kbd>&larr;</kbd> / <kbd>&rarr;</kbd> to move between chapters.
- **Mark this chapter as complete** at the end of each chapter. Progress is stored in your browser.
- The half-moon button toggles dark mode.

## What's inside

| Path | Contents |
|---|---|
| `index.html`, `chapters/`, `404.html` | the tutorial |
| `assets/` | styles, behavior and the search index |
| `_source/` | the Markdown sources, curriculum outline, SwarmPipe facts and the site generator |

## Host it on Cloudflare Pages

The site is plain static HTML that's already built, so no build step is needed. In the Cloudflare dashboard, go to
**Workers & Pages** > **Create** > **Pages** > **Connect to Git**, pick this repository, then set:

| Setting | Value |
|---|---|
| Framework preset | None |
| Build command | `exit 0` (or leave blank) |
| Build output directory | `/` (the repository root) |

Every push to the production branch redeploys the site. Pages serves `404.html` for unknown URLs and redirects
`page.html` to `/page`, which the site's relative links handle.

## Edit or extend it

Chapters are Markdown files in `_source\chapters`. See `_source\AUTHORING.md` for the format and rules. The build uses
your local SwarmPipe installation, so first tell it where that is, then rebuild from this folder:

```powershell
$env:SWARMPIPE_DIR = "<your-SwarmPipe-folder>"   # the folder where you installed SwarmPipe
& "$env:SWARMPIPE_DIR\.venv\Scripts\python.exe" _source\build.py --check
```

`--check` validates every command, option, scenario, flag, file path, API route and identifier against SwarmPipe,
plus all cross-links. If SwarmPipe itself changes, refresh the ground truth first with
`& "$env:SWARMPIPE_DIR\.venv\Scripts\python.exe" _source\extract_facts.py`. Commit the regenerated HTML along with the
sources, because the hosted site is served straight from the repository.
