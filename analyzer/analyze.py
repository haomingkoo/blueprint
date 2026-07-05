"""Analyze a public GitHub repo (or local path) into structured JSON facts.

Issue 1: Repo, File, and language-count facts only. No dependency/manifest
parsing yet — that's Issue 2.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

IGNORED_DIRS = {
    ".git", "node_modules", "dist", "build", ".next", "venv", ".venv",
    "__pycache__", "coverage", ".pytest_cache",
}

LANGUAGE_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".go": "Go", ".rs": "Rust", ".java": "Java", ".rb": "Ruby",
    ".md": "Markdown", ".json": "JSON", ".yml": "YAML", ".yaml": "YAML",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".sh": "Shell",
}


@dataclass
class RepoInfo:
    provider: str
    owner: str
    name: str
    branch: str
    commit_sha: str
    url: str


@dataclass
class FileInfo:
    path: str
    language: str
    size: int


@dataclass
class RepoIndex:
    repo: RepoInfo
    files: list[FileInfo]
    language_counts: dict[str, int]


def parse_github_url(url: str) -> tuple[str, str]:
    owner, name = url.rstrip("/").removesuffix(".git").split("/")[-2:]
    return owner, name


def clone_repo(url: str, dest: Path) -> None:
    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)], check=True, capture_output=True
    )


def _git(repo_path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def scan_files(repo_path: Path) -> list[FileInfo]:
    files = []
    for path in sorted(repo_path.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_path)
        if any(part in IGNORED_DIRS for part in rel.parts):
            continue
        language = LANGUAGE_BY_EXT.get(path.suffix, "Other")
        files.append(FileInfo(path=str(rel), language=language, size=path.stat().st_size))
    return files


def analyze_local_repo(repo_path: Path, url: str = "") -> RepoIndex:
    owner, name = (parse_github_url(url) if url else ("", repo_path.name))
    branch, commit_sha = "", ""
    if (repo_path / ".git").exists():
        branch = _git(repo_path, "rev-parse", "--abbrev-ref", "HEAD")
        commit_sha = _git(repo_path, "rev-parse", "HEAD")

    files = scan_files(repo_path)
    language_counts: dict[str, int] = {}
    for f in files:
        language_counts[f.language] = language_counts.get(f.language, 0) + 1

    repo_info = RepoInfo(
        provider="github" if url else "local",
        owner=owner, name=name, branch=branch, commit_sha=commit_sha, url=url,
    )
    return RepoIndex(repo=repo_info, files=files, language_counts=language_counts)


def analyze_github_repo(url: str) -> RepoIndex:
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "repo"
        clone_repo(url, dest)
        return analyze_local_repo(dest, url=url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a public GitHub repo into structured JSON")
    parser.add_argument("repo_url", help="Public GitHub repo URL, e.g. https://github.com/owner/name")
    args = parser.parse_args()
    index = analyze_github_repo(args.repo_url)
    print(json.dumps(asdict(index), indent=2))


if __name__ == "__main__":
    main()
