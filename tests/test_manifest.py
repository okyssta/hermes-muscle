from __future__ import annotations

from pathlib import Path

import yaml

from muscle import schemas
from muscle.settings import SCHEMA_KEYS, Settings

ROOT = Path(__file__).resolve().parents[1]


def _manifest():
    return yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))


def test_manifest_identity():
    manifest = _manifest()
    assert manifest["name"] == "muscle"
    assert manifest["version"] == "1.0.0"
    assert manifest["manifest_version"] == 2
    assert manifest["api_version"] == 1
    assert manifest["requires_hermes"] >= "0.22.0"
    assert manifest["description"].strip().endswith(".")


def test_manifest_tools_match_registrations():
    manifest = _manifest()
    assert set(manifest["provides_tools"]) == {schema["name"] for schema in schemas.ALL}
    assert len(manifest["provides_tools"]) == len(set(manifest["provides_tools"]))
    assert not manifest.get("provides_hooks")


def test_config_schema_matches_settings():
    manifest = _manifest()
    assert set(manifest["config_schema"]) == set(SCHEMA_KEYS)
    assert set(SCHEMA_KEYS) == set(Settings.__dataclass_fields__)


def test_every_schema_has_a_handler():
    from muscle import tools

    handlers = {
        "shell_recall": tools.shell_recall,
        "shell_show": tools.shell_show,
        "shell_last": tools.shell_last,
        "shell_habits": tools.shell_habits,
        "shell_index": tools.shell_index,
    }
    for schema in schemas.ALL:
        assert schema["name"] in handlers
        assert schema["description"]
        assert schema["parameters"]["type"] == "object"


def test_skill_is_bundled():
    skill = ROOT / "skills" / "muscle" / "SKILL.md"
    assert skill.is_file()
    text = skill.read_text(encoding="utf-8")
    assert "shell_recall" in text and "shell_show" in text


def test_disclosure_is_present():
    description = _manifest()["description"]
    assert "Disclosure" in description
    assert "no network" in description.lower()
