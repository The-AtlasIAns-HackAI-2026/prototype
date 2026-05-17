#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIAGRAM_DIR="$ROOT_DIR/docs/diagrams"

compiler=""
for candidate in xelatex lualatex pdflatex; do
  if command -v "$candidate" >/dev/null 2>&1; then
    compiler="$candidate"
    break
  fi
done

if [[ -z "$compiler" ]]; then
  echo "No TeX compiler found. Install texlive-latex-extra or a similar TikZ-capable distribution." >&2
  exit 1
fi

for tex in "$DIAGRAM_DIR"/*.tex; do
  name="$(basename "$tex" .tex)"
  "$compiler" -halt-on-error -interaction=nonstopmode -output-directory "$DIAGRAM_DIR" "$tex"
  if command -v pdftoppm >/dev/null 2>&1; then
    pdftoppm -png -singlefile -r 180 "$DIAGRAM_DIR/$name.pdf" "$DIAGRAM_DIR/$name"
  fi
done
