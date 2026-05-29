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

.PHONY: viewer run-app
viewer run-app:
	uv run python -m symptoms_analyser.app

.PHONY: tunnel
tunnel:
	ngrok http 8000 --url https://reveler-lagging-these.ngrok-free.dev --config ~/.config/ngrok/personal.yml
