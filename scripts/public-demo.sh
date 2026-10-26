#!/usr/bin/env bash
set -euo pipefail

echo "[1/5] Setup environment"
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"

echo "[2/5] Run baseline weak fixture suite"
python -m pytest tests/integration/test_scenarios_weak.py -q
cp reports/weak.test.json reports/weak.json

echo "[3/5] Run reference fixture suite"
python -m pytest tests/integration/test_scenarios_reference.py -q
cp reports/reference.test.json reports/reference.json

echo "[4/5] Generate matrix"
aab report --weak reports/weak.json --reference reports/reference.json --scenarios scenarios --out reports/matrix.md

echo "[5/5] Show matrix"
cat reports/matrix.md
