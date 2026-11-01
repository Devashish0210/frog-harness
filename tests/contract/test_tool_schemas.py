"""Contract test verifying Tool Gateway schemas match contracts/tools.json."""

import json
from pathlib import Path
import pytest
from frognano_harness.tool_gateway import ToolRegistry


def test_tool_registry_schemas_match_contract() -> None:
    schema_file = (
        Path(__file__).resolve().parent.parent.parent
        / "specs"
        / "002-local-execution-harness"
        / "contracts"
        / "tools.json"
    )
    assert schema_file.exists(), f"Missing schema contract: {schema_file}"

    with open(schema_file, "r", encoding="utf-8") as f:
        contract = json.load(f)

    registry = ToolRegistry()
    registered_tools = registry.get_all_tool_schemas()
    contract_tools = contract["tools"]

    assert len(registered_tools) == len(contract_tools)
    registered_names = {t["name"] for t in registered_tools}
    contract_names = {t["name"] for t in contract_tools}
    assert registered_names == contract_names

    for ct in contract_tools:
        rt = registry.get_tool_schema(ct["name"])
        assert rt is not None
        assert rt["parameters"]["type"] == ct["parameters"]["type"]
        assert set(rt["parameters"].get("required", [])) == set(ct["parameters"].get("required", []))
