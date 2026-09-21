"""Parser and consistency checks for TEMPLATE_BASE.md."""

from __future__ import annotations

import re
from pathlib import Path


FIELDS = ("Template ID", "Template Name", "Version", "Release", "Repository")


def parse(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^- ([^:]+): `?([^`]+)`?$", line)
        if match and match.group(1) in FIELDS:
            values[match.group(1)] = match.group(2).strip()
    return values


def validate(path: Path, manifest: dict) -> list[str]:
    if not path.is_file():
        return ["TEMPLATE_BASE.md is missing"]
    values = parse(path)
    errors = [f"TEMPLATE_BASE.md missing {field}" for field in FIELDS if not values.get(field)]
    if values.get("Template ID") != manifest.get("template_id"):
        errors.append("TEMPLATE_BASE.md Template ID does not match manifest")
    if values.get("Version") != manifest.get("template_version"):
        errors.append("TEMPLATE_BASE.md Version does not match manifest")
    return errors


