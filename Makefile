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


.PHONY: test
test:
	@echo "Installing dev dependencies and running tests..."
	@if command -v uv >/dev/null 2>&1; then \
		uv sync && uv install -D pytest pytest-cov || true; \
	else \
		python3 -m pip install -U '.[dev]' || true; \
	fi
	@echo "Running pytest..."
	@pytest -q


.PHONY: analyse-llm
analyse-llm:
	@if [ -z "$(INPUT)" ]; then \
		echo "Error: set INPUT to a sanitized transcript (e.g. session.run3.sanitized.txt)."; \
		exit 1; \
	fi
	uv run tdpm_analyse_llm "$(INPUT)" --output "$(OUTPUT_DIR)" --chunks-per-call "$(CHUNKS_PER_CALL)"


.PHONY: analyse
analyse: 
	@if [ -z "$(INPUT)" ]; then \
		echo "Error: INPUT is required. Usage: make analyse INPUT=path/to/session.docx"; \
		exit 1; \
	fi
	# Step 1: run preprocessing to produce sanitized transcript (creates runN.sanitized.txt)
	$(MAKE) run INPUT="$(INPUT)" OUTPUT_DIR="$(OUTPUT_DIR)" CHUNKS_PER_CALL="$(CHUNKS_PER_CALL)"
	# session base name
	SESSION=$(notdir $(basename $(INPUT))); \
	# find latest sanitized run file
	SANITIZED=$$(ls -1t "$(OUTPUT_DIR)/"$$SESSION.run*.sanitized.txt 2>/dev/null | head -n1); \
	if [ -z "$$SANITIZED" ]; then \
		echo "Error: sanitized transcript not found in $(OUTPUT_DIR)"; \
		exit 1; \
	fi; \
	echo "Analysing $$SANITIZED with LLM..."; \
	uv run tdpm_analyse_llm "$$SANITIZED" --output "$(OUTPUT_DIR)" --chunks-per-call "$(CHUNKS_PER_CALL)"
