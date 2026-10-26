PYTHON ?= python
VENV ?= .venv
PIP := $(VENV)/Scripts/pip
PY := $(VENV)/Scripts/python
AAB := $(VENV)/Scripts/aab

.PHONY: setup keys lint test check up-weak up-reference down scenarios-weak scenarios-reference report demo demo-ci

setup:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -e ".[dev]"
	$(MAKE) keys

keys:
	$(AAB) keys generate --out .keys

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

test:
	$(PY) -m pytest tests/unit

check: lint test

up-weak:
	@echo "Phase 0 placeholder"

up-reference:
	@echo "Phase 0 placeholder"

down:
	@echo "Phase 0 placeholder"

scenarios-weak:
	@echo "Phase 0 placeholder"

scenarios-reference:
	@echo "Phase 0 placeholder"

report:
	@echo "Phase 0 placeholder"

demo:
	@echo "Phase 0 placeholder"

demo-ci:
	@echo "Phase 0 placeholder"

