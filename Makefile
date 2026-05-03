.PHONY: install run clean

# Install dependencies using uv
install:
	uv sync

# Run preprocessing on a .docx file
# Usage: make run INPUT=path/to/session.docx
# Optional: make run INPUT=path/to/session.docx OUTPUT_DIR=path/to/output CHUNKS_PER_CALL=6
INPUT ?=
OUTPUT_DIR ?= output
CHUNKS_PER_CALL ?= 6

run:
	@if [ -z "$(INPUT)" ]; then \
		echo "Error: INPUT is required. Usage: make run INPUT=path/to/session.docx"; \
		exit 1; \
	fi
	uv run preprocess "$(INPUT)" --output-dir "$(OUTPUT_DIR)" --chunks-per-call "$(CHUNKS_PER_CALL)"

# Remove all generated output files
clean:
	rm -rf output/
