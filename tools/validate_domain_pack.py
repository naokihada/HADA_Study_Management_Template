"""Dependency-free validator for the domain-pack contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REQUIRED = {"domain_pack_id", "display_name", "goal_types", "assessment_types", "activity_types", "supports_artifacts"}
ALLOWED = REQUIRED | {"description", "event_types", "extensions", "metrics", "recommendation_rules", "source_requirements", "related_domains"}


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read JSON-compatible YAML: {exc}"]
    if not isinstance(value, dict):
        return ["domain pack must be an object"]
    errors.extend(f"missing required property: {key}" for key in sorted(REQUIRED - value.keys()))
    errors.extend(f"unknown property: {key}" for key in sorted(value.keys() - ALLOWED))
    if not isinstance(value.get("domain_pack_id"), str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", value.get("domain_pack_id", "")):
        errors.append("domain_pack_id must use lowercase letters, numbers, and hyphens")
    if not isinstance(value.get("display_name"), str) or not value.get("display_name", "").strip():
        errors.append("display_name must be a non-empty string")
    for key in ("goal_types", "assessment_types", "activity_types", "event_types"):
        if key in value and (not isinstance(value[key], list) or any(not isinstance(item, str) or not item for item in value[key])):
            errors.append(f"{key} must be an array of non-empty strings")
    if not isinstance(value.get("supports_artifacts"), bool):
        errors.append("supports_artifacts must be boolean")
    if "extensions" in value and not isinstance(value["extensions"], dict):
        errors.append("extensions must be an object")
    for key in ("source_requirements", "related_domains"):
        if key in value and (not isinstance(value[key], list) or any(not isinstance(item, str) or not item for item in value[key])):
            errors.append(f"{key} must be an array of non-empty strings")
    if "metrics" in value:
        if not isinstance(value["metrics"], list):
            errors.append("metrics must be an array")
        else:
            names = set()
            for metric in value["metrics"]:
                if not isinstance(metric, dict) or not isinstance(metric.get("name"), str) or not isinstance(metric.get("type"), str):
                    errors.append("each metric must have string name and type")
                elif metric["name"] in names:
                    errors.append(f"duplicate metric name {metric['name']!r}")
                else:
                    names.add(metric["name"])
    if "recommendation_rules" in value:
        if not isinstance(value["recommendation_rules"], list):
            errors.append("recommendation_rules must be an array")
        else:
            for rule in value["recommendation_rules"]:
                if not isinstance(rule, dict) or not isinstance(rule.get("id"), str) or not isinstance(rule.get("suggestion"), str):
                    errors.append("each recommendation rule must have string id and suggestion")
    if isinstance(value.get("extensions"), dict):
        for name, definition in value["extensions"].items():
            if not isinstance(name, str) or not name:
                errors.append("extension names must be non-empty strings")
            if not isinstance(definition, dict):
                errors.append(f"extension {name!r} must be an object")
                continue
            if not isinstance(definition.get("type"), str) or definition.get("type") not in {"string", "number", "integer", "boolean", "date", "datetime", "array"}:
                errors.append(f"extension {name!r} has unsupported type")
            if "required" in definition and not isinstance(definition["required"], bool):
                errors.append(f"extension {name!r}.required must be boolean")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    errors = validate(args.path)
    for error in errors:
        print("ERROR: " + error)
    print("VALIDATION: " + ("PASS" if not errors else "FAIL"))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
