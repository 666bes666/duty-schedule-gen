from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from duty_schedule.models import Config

EXAMPLE_CONFIG = Path(__file__).resolve().parents[2] / "examples" / "config.yaml"


class TestConfigYamlContract:
    def test_example_config_loads(self):
        raw = yaml.safe_load(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
        cfg = Config.model_validate(raw)
        assert cfg.month > 0
        assert len(cfg.employees) > 0

    def test_example_config_has_required_fields(self):
        raw = yaml.safe_load(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
        assert "month" in raw
        assert "year" in raw
        assert "employees" in raw

    def test_minimal_yaml_config(self):
        yaml_str = """
month: 1
year: 2025
employees:
  - name: "М1"
    city: moscow
    schedule_type: flexible
  - name: "М2"
    city: moscow
    schedule_type: flexible
  - name: "М3"
    city: moscow
    schedule_type: flexible
  - name: "М4"
    city: moscow
    schedule_type: flexible
  - name: "Х1"
    city: khabarovsk
    schedule_type: flexible
  - name: "Х2"
    city: khabarovsk
    schedule_type: flexible
"""
        raw = yaml.safe_load(yaml_str)
        cfg = Config.model_validate(raw)
        assert cfg.month == 1
        assert cfg.seed == 42

    def test_unknown_fields_ignored(self):
        yaml_str = """
month: 1
year: 2025
unknown_field: "should be ignored"
employees:
  - name: "М1"
    city: moscow
    schedule_type: flexible
    team_lead: true
  - name: "М2"
    city: moscow
    schedule_type: flexible
  - name: "М3"
    city: moscow
    schedule_type: flexible
  - name: "М4"
    city: moscow
    schedule_type: flexible
  - name: "Х1"
    city: khabarovsk
    schedule_type: flexible
  - name: "Х2"
    city: khabarovsk
    schedule_type: flexible
"""
        raw = yaml.safe_load(yaml_str)
        cfg = Config.model_validate(raw)
        assert cfg.month == 1

    def test_missing_employees_raises(self):
        yaml_str = """
month: 1
year: 2025
"""
        raw = yaml.safe_load(yaml_str)
        with pytest.raises(ValidationError):
            Config.model_validate(raw)
