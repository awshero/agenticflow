"""Loads rules.yml / instance_catalog.yml into plain dicts with dotted overrides."""
from __future__ import annotations

import copy
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def _load_packaged(name: str) -> Dict[str, Any]:
    text = resources.files("apc_optimizer.conf").joinpath(name).read_text()
    return yaml.safe_load(text)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class EngineConfig:
    """Thin accessor over the rules dict: ``cfg.get("photon.cpu_p95_threshold")``."""

    def __init__(self, rules: Dict[str, Any]):
        self.rules = rules

    @classmethod
    def load(
        cls,
        rules_path: Optional[str] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> "EngineConfig":
        rules = _load_packaged("rules.yml")
        if rules_path:
            rules = _deep_merge(rules, yaml.safe_load(Path(rules_path).read_text()))
        if overrides:
            rules = _deep_merge(rules, overrides)
        return cls(rules)

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.rules
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def section(self, name: str) -> Dict[str, Any]:
        return self.rules.get(name, {})

    @property
    def rule_version(self) -> str:
        return str(self.rules.get("rule_version", "0.0.0"))


def load_instance_catalog(path: Optional[str] = None) -> Dict[str, Dict[str, float]]:
    data = yaml.safe_load(Path(path).read_text()) if path else _load_packaged("instance_catalog.yml")
    return data["instances"]
