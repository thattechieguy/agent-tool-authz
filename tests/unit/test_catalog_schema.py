from pathlib import Path

import jsonschema
import yaml


def test_catalog_example_validates_against_schema() -> None:
    schema_path = Path("schema/catalog.schema.json")
    catalog_path = Path("catalogs/loans-servicing.catalog.yaml")
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    jsonschema.validate(catalog, schema)
