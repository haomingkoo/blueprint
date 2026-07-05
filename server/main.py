"""Slice 5: FastAPI wrapper around the analyzer + report pipeline.

One endpoint, `POST /api/analyze`, calls `analyzer`'s existing
`analyze_github_repo` directly and returns `asdict(index)` as JSON — no
analysis logic is duplicated here. The static frontend (`server/static/`)
is a single page that calls this endpoint and renders the JSON.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# analyzer/ has no package __init__.py (its own modules import each other as
# bare top-level modules, e.g. report.py's `from analyze import ...`), so we
# add it to sys.path the same way pytest does for analyzer's own tests,
# rather than restructuring analyzer/ into a package for this slice.
ANALYZER_DIR = Path(__file__).resolve().parent.parent / "analyzer"
if str(ANALYZER_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYZER_DIR))

from analyze import analyze_github_repo  # noqa: E402

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
    return asdict(index)


# Mounted last and at "/" so it only catches requests that didn't match a
# route defined above (e.g. GET /api/analyze never fell through to here).
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
