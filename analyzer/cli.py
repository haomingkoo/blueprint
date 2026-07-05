"""Slice 1 entrypoint: repo URL -> Markdown report on stdout."""
from __future__ import annotations

import argparse

from analyze import analyze_github_repo
from report import render_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a public GitHub repo into a Markdown report")
    parser.add_argument("repo_url", help="Public GitHub repo URL, e.g. https://github.com/owner/name")
    args = parser.parse_args()
    index = analyze_github_repo(args.repo_url)
    print(render_markdown(index))


if __name__ == "__main__":
    main()
