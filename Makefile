.PHONY: install dev test lint format clean

VENV ?= .venv
PY := $(VENV)/bin/python

$(VENV):
	python3 -m venv $(VENV)

install: $(VENV)          ## Install ContextOS and dev tools into .venv
	$(PY) -m pip install -q -e ".[dev]"

dev:                      ## Run the website on http://localhost:8000
	$(VENV)/bin/contextos web

test:                     ## Run the test suite (offline, no keys needed)
	$(VENV)/bin/pytest -q

lint:                     ## Check style and common bugs
	$(VENV)/bin/ruff check src tests

format:                   ## Auto-fix lint issues and format code
	$(VENV)/bin/ruff check --fix src tests
	$(VENV)/bin/ruff format src tests

clean:                    ## Remove build and cache files
	rm -rf build dist src/*.egg-info .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
