#!/usr/bin/env python3
"""
Tailor a LaTeX CV for a specific job.

Usage:
  python scripts/tailor_cv.py --company <slug> --job-title <title> --jd-snippet <text>
  python scripts/tailor_cv.py --company <slug> --job-title general

The script reads cv/main.tex, asks Claude (via a subprocess prompt) to produce
a tailored version following src/prompts/tailor_cv.md, then writes the result
to output/<slug>/tailored_cv.tex.

Since this runs inside Claude Code, the "asking Claude" step is done by printing
the prompt and letting Claude Code handle it. The script itself just does the
file I/O; Claude does the actual rewriting.
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def load_settings():
    with open(ROOT / "config" / "settings.json") as f:
        return json.load(f)


def load_file(path: Path) -> str:
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        sys.exit(1)
    return path.read_text()


def ensure_output_dir(slug: str) -> Path:
    out = ROOT / "output" / slug
    out.mkdir(parents=True, exist_ok=True)
    return out


def print_tailor_prompt(slug: str, job_title: str, jd_snippet: str, cv_tex: str, rules: str):
    """Print the prompt for Claude to act on."""
    print("=" * 60)
    print("TAILOR CV — Instructions for Claude")
    print("=" * 60)
    print(f"\nCompany slug: {slug}")
    print(f"Job title: {job_title}")
    print(f"\n--- TAILORING RULES ---\n{rules}\n")
    print(f"--- JOB DESCRIPTION SNIPPET ---\n{jd_snippet}\n")
    print(f"--- CURRENT CV (cv/main.tex) ---\n{cv_tex}\n")
    print("=" * 60)
    print(f"Write the tailored .tex content to: output/{slug}/tailored_cv.tex")
    print("Follow the rules above. Mark each changed bullet with a % TAILORED: comment.")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Tailor CV for a job")
    parser.add_argument("--company", required=True, help="Company slug (e.g. wiz-security)")
    parser.add_argument("--job-title", required=True, help="Job title or 'general'")
    parser.add_argument("--jd-snippet", default="", help="First ~200 words of the job description")
    args = parser.parse_args()

    cv_path = ROOT / "cv" / "main.tex"
    rules_path = ROOT / "src" / "prompts" / "tailor_cv.md"
    out_dir = ensure_output_dir(args.company)
    out_path = out_dir / "tailored_cv.tex"

    cv_tex = load_file(cv_path)
    rules = load_file(rules_path)

    if out_path.exists():
        print(f"NOTE: {out_path} already exists — will be overwritten by Claude's output.")

    print_tailor_prompt(args.company, args.job_title, args.jd_snippet, cv_tex, rules)

    print(f"\nWaiting for Claude to write output/{args.company}/tailored_cv.tex ...")
    print("(Claude Code will write the file — this script printed the prompt above)")


if __name__ == "__main__":
    main()
