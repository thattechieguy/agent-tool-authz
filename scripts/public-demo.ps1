$ErrorActionPreference = "Stop"

Write-Host "[1/5] Setup environment"
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-dev.lock

Write-Host "[2/5] Run baseline weak fixture suite"
.\.venv\Scripts\python -m pytest tests\integration\test_scenarios_weak.py -q
Copy-Item reports\weak.test.json reports\weak.json -Force

Write-Host "[3/5] Run reference fixture suite"
.\.venv\Scripts\python -m pytest tests\integration\test_scenarios_reference.py -q
Copy-Item reports\reference.test.json reports\reference.json -Force

Write-Host "[4/5] Generate matrix"
.\.venv\Scripts\aab report --weak reports/weak.json --reference reports/reference.json --scenarios scenarios --out reports/matrix.md

Write-Host "[5/5] Show matrix"
Get-Content reports/matrix.md
