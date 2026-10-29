.PHONY: all pdf docx diagrams clean reference-docx image watch

all:            ## Build PDF + DOCX into build/
	scripts/build.sh all

pdf:            ## Build build/relatorio.pdf
	scripts/build.sh pdf

docx:           ## Build build/relatorio.docx
	scripts/build.sh docx

diagrams:       ## Render diagramas/*.dot to figures/*.png (Graphviz)
	scripts/build.sh diagrams

image:          ## (Re)build the container image used when pandoc/lualatex are missing
	$$(command -v podman || command -v docker) build -t localhost/ufjf-report-builder:latest -f Containerfile .

reference-docx: ## Regenerate template/docx/reference.docx
	scripts/build.sh reference-docx

watch:          ## Rebuild the PDF whenever sources change (needs entr)
	find report.yaml content bib figures diagramas template -type f | entr -c scripts/build.sh pdf

clean:
	rm -rf build

help:
	@grep -E '^[a-z-]+:.*##' Makefile | sed 's/:.*## /\t/'
