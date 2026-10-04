"""Consistency checks between code, services.yaml, strings and icons."""

from __future__ import annotations

import json
from pathlib import Path
import re

import yaml

from custom_components.hevy.binary_sensor import BINARY_SENSORS
from custom_components.hevy.sensor import EXERCISE_SENSORS, ROUTINE_SENSORS, SENSORS
from custom_components.hevy.services import ATTR_CONFIG_ENTRY_ID, SERVICES

ROOT = Path(__file__).parent.parent / "custom_components" / "hevy"


def load(name: str) -> dict:
    """Load a JSON file from the integration."""
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_services_match_schema() -> None:
    """services.yaml fields and strings match the voluptuous schemas."""
    services_yaml = yaml.safe_load((ROOT / "services.yaml").read_text())
    strings = load("strings.json")["services"]
    icons = load("icons.json")["services"]
    assert set(services_yaml) == set(SERVICES) == set(strings) == set(icons)
    for name, service in SERVICES.items():
        schema_keys = {str(k) for k in service.schema} | {ATTR_CONFIG_ENTRY_ID}
        assert set(services_yaml[name]["fields"]) == schema_keys, name
        assert set(strings[name]["fields"]) == schema_keys, name


def test_platform_translations() -> None:
    """Binary sensors and calendar have names and icons."""
    strings = load("strings.json")["entity"]
    icons = load("icons.json")["entity"]
    keys = {d.translation_key for d in BINARY_SENSORS}
    assert keys == set(strings["binary_sensor"]) == set(icons["binary_sensor"])
    assert set(strings["calendar"]) == set(icons["calendar"]) == {"workouts"}


def test_sensor_translations() -> None:
    """Every sensor has a name and icon."""
    keys = {d.translation_key for d in (*SENSORS, *EXERCISE_SENSORS, *ROUTINE_SENSORS)}
    assert keys == set(load("strings.json")["entity"]["sensor"])
    assert keys == set(load("icons.json")["entity"]["sensor"])


def test_exception_keys() -> None:
    """Every translation_key raised in code exists in strings.json."""
    exceptions = set(load("strings.json")["exceptions"])
    used: set[str] = set()
    for path in ROOT.glob("*.py"):
        used |= set(re.findall(r'translation_key="([a-z_]+)"', path.read_text()))
    used -= {
        key for platform in load("strings.json")["entity"].values() for key in platform
    }
    assert used <= exceptions, used - exceptions


def test_translations_match_strings() -> None:
    """en.json equals strings.json and nb.json has the same keys."""
    strings = load("strings.json")
    assert load("translations/en.json") == strings

    def keys(data: object, prefix: str = "") -> set[str]:
        if isinstance(data, dict):
            out: set[str] = set()
            for k, v in data.items():
                out |= keys(v, f"{prefix}.{k}")
            return out
        return {prefix}

    assert keys(load("translations/nb.json")) == keys(strings)
