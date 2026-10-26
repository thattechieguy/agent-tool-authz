from pathlib import Path

import jsonschema
import yaml


def test_all_scenarios_validate_against_schema() -> None:
    schema = yaml.safe_load(Path("schema/scenario.schema.json").read_text(encoding="utf-8"))
    for scenario_file in sorted(Path("scenarios").glob("S*.yaml")):
        scenario = yaml.safe_load(scenario_file.read_text(encoding="utf-8"))
        jsonschema.validate(scenario, schema)
