"""Slice 5: FastAPI wrapper around the analyzer + report pipeline.

One endpoint, `POST /api/analyze`, calls `analyzer`'s existing
`analyze_github_repo` directly and returns `asdict(index)` as JSON — no
analysis logic is duplicated here. The static frontend (`server/static/`)
is a single page that calls this endpoint and renders the JSON.

Slice 8 adds three export endpoints (`/api/export/markdown`, `/mermaid`,
`/html`). None of them re-clone or re-analyze: the browser already holds
the full `RepoIndex` JSON from a prior `/api/analyze` call and posts it
back as-is, and each endpoint just reconstructs the dataclasses and calls
`analyzer`'s existing `render_markdown`/`mermaid.py`/`html_export.py`
directly -- purely packaging, no new analysis.
"""
from __future__ import annotations

import logging
import re
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# analyzer/ has no package __init__.py (its own modules import each other as
# bare top-level modules, e.g. report.py's `from analyze import ...`), so we
# add it to sys.path the same way pytest does for analyzer's own tests,
# rather than restructuring analyzer/ into a package for this slice.
ANALYZER_DIR = Path(__file__).resolve().parent.parent / "analyzer"
if str(ANALYZER_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYZER_DIR))

# server/ itself needs to be on sys.path too: when this module is loaded as
# the dotted path "server.main" (e.g. `uvicorn server.main:app --app-dir .`),
# only the repo root is on sys.path by default, so a bare `import
# understanding_bridge` below would otherwise only resolve under pytest
# (which auto-adds a test file's own directory).
_SERVER_DIR = Path(__file__).resolve().parent
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))

from analyze import (  # noqa: E402
    Edge, FileInfo, Finding, Flow, Manifest, Module, Node, RepoIndex, RepoInfo,
    analyze_github_repo,
)
from html_export import render_html_report  # noqa: E402
from mermaid import render_mermaid_flow, render_mermaid_graph  # noqa: E402
from report import render_markdown  # noqa: E402

from understanding_bridge import enrich_with_understanding

logger = logging.getLogger("blueprint.server")

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Blueprint")


class AnalyzeRequest(BaseModel):
    repo_url: str = Field(..., min_length=1)


class AnalyzeError(Exception):
    """A user-facing, already-safe-to-display error message."""

    def __init__(self, message: str) -> None:
        self.message = message


def _validate_repo_url(repo_url: str) -> str:
    url = repo_url.strip()
    if not url:
        raise AnalyzeError("Repository URL is required.")
    if not url.startswith(("http://", "https://")) or "github.com" not in url:
        raise AnalyzeError(
            "Only public GitHub repository URLs are supported, e.g. "
            "https://github.com/owner/name."
        )
    return url


@app.post("/api/analyze", response_model=None)
def analyze(request: AnalyzeRequest) -> JSONResponse | dict:
    """Analyze a public GitHub repo and return its `RepoIndex` as JSON.

    Cloning/analysis failures never leak a raw traceback to the client —
    they're logged server-side and translated to a generic 4xx message.
    """
    try:
        url = _validate_repo_url(request.repo_url)
        index = analyze_github_repo(url)
    except AnalyzeError as exc:
        return JSONResponse(status_code=400, content={"error": exc.message})
    except subprocess.CalledProcessError as exc:
        logger.warning("git clone failed for %r: %s", request.repo_url, exc.stderr)
        return JSONResponse(
            status_code=400,
            content={
                "error": "Could not clone this repository. Check that the "
                "URL is correct and the repo is public."
            },
        )
    except ValueError as exc:
        logger.warning("could not parse repo URL %r: %s", request.repo_url, exc)
        return JSONResponse(status_code=400, content={"error": "Invalid GitHub repository URL."})
    except Exception:
        logger.exception("unexpected error analyzing %r", request.repo_url)
        return JSONResponse(
            status_code=502,
            content={"error": "Analysis failed unexpectedly. Please try again."},
        )
    response = asdict(index)
    if index.repo.name:
        enrich_with_understanding(index.repo.name, response)
    return response


# ---------- Slice 8: export endpoints ----------
#
# All three take back the exact `RepoIndex` JSON the browser already got
# from `/api/analyze` (no re-clone, no re-analyze) and hand it to
# `analyzer`'s existing rendering functions.

_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


class ExportIndexRequest(BaseModel):
    index: dict


class ExportMermaidRequest(BaseModel):
    index: dict
    flow_index: int | None = None


class ExportError(Exception):
    """A user-facing, already-safe-to-display error for a malformed export request."""

    def __init__(self, message: str) -> None:
        self.message = message


def _repo_index_from_dict(data: dict) -> RepoIndex:
    """Reconstruct a `RepoIndex` (and its nested dataclasses) from the
    plain JSON dict a browser posts back -- the same shape `asdict(index)`
    produced in `/api/analyze`'s response."""
    try:
        return RepoIndex(
            repo=RepoInfo(**data["repo"]),
            files=[FileInfo(**f) for f in data.get("files", [])],
            language_counts=data.get("language_counts", {}),
            manifests=[Manifest(**m) for m in data.get("manifests", [])],
            findings=[Finding(**f) for f in data.get("findings", [])],
            modules=[Module(**m) for m in data.get("modules", [])],
            nodes=[Node(**n) for n in data.get("nodes", [])],
            edges=[Edge(**e) for e in data.get("edges", [])],
            flows=[_flow_from_dict(f) for f in data.get("flows", [])],
        )
    except (KeyError, TypeError) as exc:
        raise ExportError("Invalid analysis data.") from exc


def _flow_from_dict(data: dict) -> Flow:
    return Flow(
        title=data["title"],
        nodes=[Node(**n) for n in data["nodes"]],
        edges=[Edge(**e) for e in data["edges"]],
        explanation=data["explanation"],
        evidence=data["evidence"],
        confidence=data["confidence"],
    )


def _safe_filename_component(value: str) -> str:
    return _FILENAME_SAFE_RE.sub("_", value) or "repo"


@app.post("/api/export/markdown", response_model=None)
def export_markdown(request: ExportIndexRequest) -> PlainTextResponse | JSONResponse:
    """Markdown export: `render_markdown` as-is, already includes the repo
    URL + commit SHA (Slice 1)."""
    try:
        index = _repo_index_from_dict(request.index)
    except ExportError as exc:
        return JSONResponse(status_code=400, content={"error": exc.message})
    return PlainTextResponse(render_markdown(index), media_type="text/markdown; charset=utf-8")


@app.post("/api/export/mermaid", response_model=None)
def export_mermaid(request: ExportMermaidRequest) -> PlainTextResponse | JSONResponse:
    """Mermaid export for either the full architecture graph
    (`flow_index` omitted/`null`) or one selected flow."""
    try:
        index = _repo_index_from_dict(request.index)
    except ExportError as exc:
        return JSONResponse(status_code=400, content={"error": exc.message})
    if request.flow_index is None:
        mermaid = render_mermaid_graph(index)
    elif 0 <= request.flow_index < len(index.flows):
        mermaid = render_mermaid_flow(index, request.flow_index)
    else:
        return JSONResponse(status_code=400, content={"error": "Invalid flow index."})
    return PlainTextResponse(mermaid, media_type="text/plain; charset=utf-8")


@app.post("/api/export/html", response_model=None)
def export_html(request: ExportIndexRequest) -> HTMLResponse | JSONResponse:
    """Self-contained HTML report: styles inlined, system font stack, no
    external requests -- safe to open via file:// or send to someone."""
    try:
        index = _repo_index_from_dict(request.index)
    except ExportError as exc:
        return JSONResponse(status_code=400, content={"error": exc.message})
    filename = f"{_safe_filename_component(index.repo.name)}-blueprint-report.html"
    return HTMLResponse(
        content=render_html_report(index),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# Mounted last and at "/" so it only catches requests that didn't match a
# route defined above (e.g. GET /api/analyze never fell through to here).
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
