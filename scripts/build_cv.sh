#!/usr/bin/env bash
# Compile a CV .tex file to PDF.
# Usage: bash scripts/build_cv.sh <company-slug>        → output/<slug>/tailored_cv.pdf
#        bash scripts/build_cv.sh --base                → cv/main.pdf (untailored, default attachment)
#        bash scripts/build_cv.sh --variant fullstack   → cv/fullstack.pdf (a CV version from cv_variants)

set -euo pipefail

SLUG="${1:-}"
if [[ -z "$SLUG" ]]; then
  echo "Usage: bash scripts/build_cv.sh <company-slug>" >&2
  echo "       bash scripts/build_cv.sh --base" >&2
  echo "       bash scripts/build_cv.sh --variant <name>" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CV_DIR="$ROOT/cv"

if [[ "$SLUG" == "--variant" ]]; then
  VARIANT="${2:-}"
  if [[ -z "$VARIANT" ]]; then
    echo "Usage: bash scripts/build_cv.sh --variant <name>   (builds cv/<name>.tex)" >&2
    exit 1
  fi
  # A variant lives next to main.tex, so it compiles like the base CV
  SLUG="--base"
  TEX_FILE="$CV_DIR/$VARIANT.tex"
  OUT_DIR="$CV_DIR"
  PDF_NAME="$VARIANT"
elif [[ "$SLUG" == "--base" ]]; then
  TEX_FILE="$CV_DIR/main.tex"
  OUT_DIR="$CV_DIR"
  PDF_NAME="main"
else
  TEX_FILE="$ROOT/output/$SLUG/tailored_cv.tex"
  OUT_DIR="$ROOT/output/$SLUG"
  PDF_NAME="tailored_cv"
fi

if [[ ! -f "$TEX_FILE" ]]; then
  echo "ERROR: $TEX_FILE not found. Tailor the CV first (Flow 1, Step 4)." >&2
  exit 1
fi

# Pages in a PDF (macOS PDFKit); empty when it can't tell
page_count() {
  osascript -l JavaScript -e "ObjC.import('PDFKit'); \$.PDFDocument.alloc.initWithURL(\$.NSURL.fileURLWithPath('$1')).pageCount" 2>/dev/null || true
}

compile_ok() {
  local pages
  pages="$(page_count "$1")"
  if [[ -n "$pages" && "$pages" -gt 1 ]]; then
    if [[ "$SLUG" == "--base" ]]; then
      echo "WARNING: $1 is $pages pages. A CV should be one page." >&2
    else
      echo "ERROR: $1 is $pages pages. It must fit on one page: cut lines (don't shrink fonts or margins) and build again." >&2
      exit 3
    fi
  fi
  echo "PDF ready: $1${pages:+ ($pages page)}"
  # The base CV isn't tied to a company, so there's no report to refresh
  if [[ "$SLUG" != "--base" ]]; then
    python3 "$ROOT/scripts/generate_report.py" "$SLUG"
  fi
  exit 0
}

# Copy custom class file alongside the .tex so both tectonic and pdflatex can find it
# (--base compiles inside cv/, where the class file already lives)
if [[ "$OUT_DIR" != "$CV_DIR" ]]; then
  cp "$CV_DIR/resume.cls" "$OUT_DIR/resume.cls"
fi

# Prefer tectonic (no install overhead, single binary)
if command -v tectonic &>/dev/null; then
  echo "Using tectonic..."
  tectonic --outdir "$OUT_DIR" "$TEX_FILE"
  [[ -f "$OUT_DIR/$PDF_NAME.pdf" ]] && compile_ok "$OUT_DIR/$PDF_NAME.pdf"
fi

# Fallback: pdflatex (requires MacTeX / BasicTeX)
if command -v pdflatex &>/dev/null; then
  echo "Using pdflatex..."
  pdflatex -interaction=nonstopmode -output-directory "$OUT_DIR" "$TEX_FILE" > /dev/null 2>&1
  PDF="$OUT_DIR/$PDF_NAME.pdf"
  if [[ -f "$PDF" ]]; then
    rm -f "$OUT_DIR/$PDF_NAME.aux" "$OUT_DIR/$PDF_NAME.log"
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
