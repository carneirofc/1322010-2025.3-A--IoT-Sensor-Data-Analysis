#!/usr/bin/env bash
# Build the report (PDF and/or DOCX) from report.yaml + content/*.md.
# Diagrams in diagramas/*.dot are rendered first (Graphviz) to figures/*.{png,pdf}.
#
#   scripts/build.sh [pdf|docx|all|diagrams|reference-docx]   (default: all)
#
# Uses a local pandoc + lualatex when both exist; otherwise runs itself inside
# the container from ./Containerfile (podman or docker). Force with
#   BUILD_MODE=native|container scripts/build.sh
# Output: build/$OUT_NAME.{pdf,docx}   (OUT_NAME defaults to "relatorio").
set -euo pipefail
cd "$(dirname "$0")/.."

TARGET="${1:-all}"
OUT_NAME="${OUT_NAME:-relatorio}"
IMAGE="${IMAGE:-localhost/ufjf-report-builder:latest}"
MODE="${BUILD_MODE:-auto}"

if [[ "$MODE" == auto ]]; then
  if command -v pandoc >/dev/null && command -v lualatex >/dev/null && command -v dot >/dev/null; then
    MODE=native
  else
    MODE=container
  fi
fi

if [[ "$MODE" == container ]]; then
  ENGINE="$(command -v podman || command -v docker || true)"
  [[ -n "$ENGINE" ]] || { echo "error: need pandoc+lualatex, or podman/docker" >&2; exit 1; }
  if ! "$ENGINE" image exists "$IMAGE" 2>/dev/null && ! "$ENGINE" image inspect "$IMAGE" >/dev/null 2>&1; then
    echo ">> building $IMAGE (first run only)"
    "$ENGINE" build -t "$IMAGE" -f Containerfile .
  fi
  # Files written in the bind mount must stay owned by the invoking user.
  if [[ "$(basename "$ENGINE")" == podman ]]; then USERFLAG=(--userns=keep-id); else USERFLAG=(--user "$(id -u):$(id -g)"); fi
  # The parent folder is mounted too, so content can include files that live
  # beside the report (e.g. a code appendix from ../analise).
  exec "$ENGINE" run --rm -v "$PWD/..:/data:Z" -w "/data/$(basename "$PWD")" "${USERFLAG[@]}" \
    -e BUILD_MODE=native -e OUT_NAME="$OUT_NAME" \
    --entrypoint bash "$IMAGE" scripts/build.sh "$TARGET"
fi

mkdir -p build
shopt -s nullglob
INPUTS=(content/*.md)
(( ${#INPUTS[@]} )) || { echo "error: no content/*.md" >&2; exit 1; }

meta() {  # meta '<pandoc template expr>' -> plain text from report.yaml
  printf '%s' "$1" > build/.meta.tpl
  pandoc /dev/null -f markdown -t plain --metadata-file=report.yaml --template=build/.meta.tpl
}

build_diagrams() {  # diagramas/NAME.dot -> figures/NAME.png (DOCX) + figures/NAME.pdf (PDF, vector)
  local f out
  for f in diagramas/*.dot; do
    out="figures/$(basename "${f%.dot}")"
    dot -Tpng -Gdpi=300 "$f" -o "$out.png"
    dot -Tpdf -Gmargin=0 "$f" -o "$out.pdf"
  done
}

build_pdf() {
  pandoc -d template/pandoc/pdf.yaml "${INPUTS[@]}" -o "build/$OUT_NAME.pdf"
  echo "ok -> build/$OUT_NAME.pdf"
}

build_docx() {
  pandoc -d template/pandoc/docx.yaml "${INPUTS[@]}" -o "build/$OUT_NAME.docx"
  python3 scripts/fix_docx.py "build/$OUT_NAME.docx" \
    --title "$(meta '$report.title$')" \
    --author "$(meta '$for(report.authors)$$report.authors$$sep$; $endfor$')"
}

case "$TARGET" in
  pdf) build_diagrams; build_pdf ;;
  docx) build_diagrams; build_docx ;;
  all) build_diagrams; build_pdf; build_docx ;;
  diagrams) build_diagrams ;;
  reference-docx) python3 scripts/make_reference_docx.py template/docx/reference.docx ;;
  *) echo "usage: $0 [pdf|docx|all|diagrams|reference-docx]" >&2; exit 2 ;;
esac
