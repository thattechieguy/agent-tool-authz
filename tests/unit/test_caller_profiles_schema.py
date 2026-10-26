from pathlib import Path

import jsonschema
import yaml


def test_caller_profiles_validate_against_schema() -> None:
    schema = yaml.safe_load(Path("schema/caller-profiles.schema.json").read_text(encoding="utf-8"))
    data = yaml.safe_load(Path("catalogs/caller-profiles.yaml").read_text(encoding="utf-8"))
    jsonschema.validate(data, schema)
