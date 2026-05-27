.PHONY: install run clean

# Install dependencies using uv
install:
	uv sync

# Run preprocessing on a .docx file
# Usage: make preprocess INPUT=path/to/session.docx
# Optional: make preprocess INPUT=path/to/session.docx OUTPUT_DIR=path/to/output BLOCKS_PER_CALL=6
INPUT ?=
OUTPUT_DIR ?= output
BLOCKS_PER_CALL ?= 100
STYLE_REF ?= data/speaking_style_reference.txt
INJECT ?=

preprocess:
	@if [ -z "$(INPUT)" ]; then \
		echo "Error: INPUT is required. Usage: make preprocess INPUT=path/to/session.docx"; \
		exit 1; \
	fi
	uv run preprocess "$(INPUT)" --output-dir "$(OUTPUT_DIR)/preprocess" --blocks-per-call "$(BLOCKS_PER_CALL)"

# Remove all generated output files
clean:
	rm -rf output/


.PHONY: db-prune prune-db db-clean clean-db
# Prune the database and start over completely fresh (empty schema, no seeds)
db-prune prune-db db-clean clean-db:
	uv run python scripts/clean_db.py


.PHONY: test
test:
	@echo "Installing dev dependencies and running tests..."
	@if command -v uv >/dev/null 2>&1; then \
		uv sync && uv pip install pytest pytest-cov || true; \
		echo "Running pytest..."; \
		uv run pytest -q; \
	else \
		python3 -m pip install -U '.[dev]' || true; \
		echo "Running pytest..."; \
		pytest -q; \
	fi


.PHONY: analyse-llm
analyse-llm:
	@if [ -z "$(INPUT)" ]; then \
		echo "Error: set INPUT to a sanitized transcript (e.g. session.run3.sanitized.txt)."; \
		exit 1; \
	fi
	uv run tdpm_analysis "$(INPUT)" --output "$(OUTPUT_DIR)/tdpm_analysis" --blocks-per-call "$(BLOCKS_PER_CALL)"


.PHONY: analyse
analyse: 
	@if [ -z "$(INPUT)" ]; then \
		echo "Error: INPUT is required. Usage: make analyse INPUT=path/to/session.docx"; \
		exit 1; \
	fi
	# Step 1: run preprocessing to produce sanitized transcript (creates runN.sanitized.txt)
	$(MAKE) preprocess INPUT="$(INPUT)" OUTPUT_DIR="$(OUTPUT_DIR)" BLOCKS_PER_CALL="$(BLOCKS_PER_CALL)"
	# session base name
	SESSION=$(notdir $(basename $(INPUT))); \
	# find latest sanitized run file
	SANITIZED=$$(ls -1t "$(OUTPUT_DIR)/preprocess/"$$SESSION.run*.sanitized.txt 2>/dev/null | head -n1); \
	if [ -z "$$SANITIZED" ]; then \
		echo "Error: sanitized transcript not found in $(OUTPUT_DIR)/preprocess"; \
		exit 1; \
	fi; \
	echo "Analysing $$SANITIZED with LLM..."; \
	uv run tdpm_analysis "$$SANITIZED" --output "$(OUTPUT_DIR)/tdpm_analysis" --blocks-per-call "$(BLOCKS_PER_CALL)"


.PHONY: viewer
viewer:
	uv run python -m symptoms_analyser.app


.PHONY: synthetic-scratch
synthetic-scratch:
	@if [ -z "$(INJECT)" ]; then \
		echo "Error: INJECT is required. Usage: make synthetic-scratch INJECT='Paciente1:1.1,1.2'"; \
		exit 1; \
	fi
	uv run python -m symptoms_analyser.generate_from_scratch --style-ref "$(STYLE_REF)" --output-dir "$(OUTPUT_DIR)/synthetic" --inject $(INJECT) $(if $(SCENES),--scenes $(SCENES),)

