#!/usr/bin/env bash
# Compile a tailored CV .tex file to PDF.
# Usage: bash scripts/build_cv.sh <company-slug>
# Output: output/<slug>/tailored_cv.pdf

set -euo pipefail

SLUG="${1:-}"
if [[ -z "$SLUG" ]]; then
  echo "Usage: bash scripts/build_cv.sh <company-slug>" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEX_FILE="$ROOT/output/$SLUG/tailored_cv.tex"
OUT_DIR="$ROOT/output/$SLUG"

if [[ ! -f "$TEX_FILE" ]]; then
  echo "ERROR: $TEX_FILE not found. Tailor the CV first (Flow 1, Step 4)." >&2
  exit 1
fi

compile_ok() {
  echo "PDF ready: $1"
  python3 "$ROOT/scripts/generate_report.py" "$SLUG"
  exit 0
}

CV_DIR="$ROOT/cv"

# Copy custom class file alongside the .tex so both tectonic and pdflatex can find it
cp "$CV_DIR/resume.cls" "$OUT_DIR/resume.cls"

# Prefer tectonic (no install overhead, single binary)
if command -v tectonic &>/dev/null; then
  echo "Using tectonic..."
  tectonic --outdir "$OUT_DIR" "$TEX_FILE"
  [[ -f "$OUT_DIR/tailored_cv.pdf" ]] && compile_ok "$OUT_DIR/tailored_cv.pdf"
fi

# Fallback: pdflatex (requires MacTeX / BasicTeX)
if command -v pdflatex &>/dev/null; then
  echo "Using pdflatex..."
  pdflatex -interaction=nonstopmode -output-directory "$OUT_DIR" "$TEX_FILE" > /dev/null 2>&1
  PDF="$OUT_DIR/tailored_cv.pdf"
  if [[ -f "$PDF" ]]; then
    rm -f "$OUT_DIR/tailored_cv.aux" "$OUT_DIR/tailored_cv.log"
    compile_ok "$PDF"
  else
    echo "ERROR: pdflatex ran but no PDF was produced. Check LaTeX syntax." >&2
    exit 1
  fi
fi

echo "ERROR: Neither tectonic nor pdflatex found." >&2
echo "Install tectonic: brew install tectonic" >&2
echo "Or install BasicTeX: https://tug.org/mactex/morepackages.html" >&2
exit 1
