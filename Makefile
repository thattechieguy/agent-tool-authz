PYTHON ?= python
VENV ?= .venv

ifeq ($(OS),Windows_NT)
VENV_BIN := $(VENV)/Scripts
else
VENV_BIN := $(VENV)/bin
endif

PIP := $(VENV_BIN)/pip
PY := $(VENV_BIN)/python
AAB := $(VENV_BIN)/aab

.PHONY: setup env-init keys lint test check apim-scaffold apim-drift up-weak up-reference down scenarios-weak scenarios-reference report demo demo-ci

setup:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -e ".[dev]"
	$(MAKE) env-init

env-init:
	$(AAB) env init --out .env

keys:
	@echo "keys generation removed; use your own identity and token setup via .env"

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

test:
	$(PY) -m pytest tests/unit

check: lint test

apim-scaffold:
	$(AAB) apim scaffold --discovery examples/apim/fixtures/discovery.sample.json --policy-out examples/apim/generated/inbound-policy.generated.xml --mapping-out examples/apim/generated/operation-mapping.generated.yaml

apim-drift:
	$(AAB) apim drift-check --discovery examples/apim/fixtures/discovery.sample.json --policy examples/apim/generated/inbound-policy.generated.xml --mapping examples/apim/generated/operation-mapping.generated.yaml

up-weak:
	@mkdir -p .run logs reports
	@$(PY) -m uvicorn agent_authz_bench.backend.app:app --host 127.0.0.1 --port 9000 > logs/backend-weak.log 2>&1 & echo $$! > .run/backend.pid
	@GATEWAY_MODE=weak BACKEND_URL=http://127.0.0.1:9000 $(PY) -m uvicorn agent_authz_bench.gateway.app:app --host 127.0.0.1 --port 8080 > logs/gateway-weak.log 2>&1 & echo $$! > .run/gateway.pid

up-reference:
	@mkdir -p .run logs reports
	@BACKEND_AUTH_MODE=service_token $(PY) -m uvicorn agent_authz_bench.backend.app:app --host 127.0.0.1 --port 9000 > logs/backend-reference.log 2>&1 & echo $$! > .run/backend.pid
	@GATEWAY_MODE=reference BACKEND_URL=http://127.0.0.1:9000 $(PY) -m uvicorn agent_authz_bench.gateway.app:app --host 127.0.0.1 --port 8080 > logs/gateway-reference.log 2>&1 & echo $$! > .run/gateway.pid

down:
	@if [ -f .run/gateway.pid ]; then kill $$(cat .run/gateway.pid) || true; rm .run/gateway.pid; fi
	@if [ -f .run/backend.pid ]; then kill $$(cat .run/backend.pid) || true; rm .run/backend.pid; fi

scenarios-weak:
	$(AAB) run --target http://127.0.0.1:8080 --backend http://127.0.0.1:9000 --admin-key test-admin-key --scenarios scenarios --label weak --out reports/weak.json

scenarios-reference:
	$(AAB) run --target http://127.0.0.1:8080 --backend http://127.0.0.1:9000 --admin-key test-admin-key --scenarios scenarios --label reference --out reports/reference.json

report:
	$(AAB) report --weak reports/weak.json --reference reports/reference.json --out reports/matrix.md

demo:
	$(MAKE) keys && $(MAKE) up-weak && $(MAKE) scenarios-weak && $(MAKE) down && $(MAKE) up-reference && $(MAKE) scenarios-reference && $(MAKE) down && $(MAKE) report && cat reports/matrix.md

demo-ci:
	$(MAKE) demo && $(PY) -c "import json;import sys;w=json.load(open('reports/weak.json'))['scenarios'];r=json.load(open('reports/reference.json'))['scenarios'];we=json.load(open('expected/weak.json'));re=json.load(open('expected/reference.json'));wo={s['id']:s['outcome'] for s in w};ro={s['id']:s['outcome'] for s in r};sys.exit(0 if wo==we and ro==re else 1)"

