"""Canonical template version checks.

The repository keeps a small number of human-readable compatibility carriers.
They are mirrors of the canonical JSON manifest, not independent sources of
truth.  This module intentionally performs read-only checks and never invokes
Git or a network client.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def normalize_version(value: Any) -> str | None:
    """Return a normalized semantic version, accepting an optional ``v``."""

    text = str(value or "").strip()
    if text.startswith(("v", "V")):
        text = text[1:]
    return text if VERSION.fullmatch(text) else None


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def changelog_version(path: Path) -> str | None:
    """Read the first release heading from CHANGELOG.md."""

    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^##\s+\[?v?(\d+\.\d+\.\d+)\]?", line.strip())
            if match:
                return match.group(1)
    except (FileNotFoundError, OSError, UnicodeError):
        return None
    return None


def _add_match(errors: list[str], label: str, value: Any, expected: str) -> None:
    normalized = normalize_version(value)
    if normalized is None:
        errors.append(f"{label} must use MAJOR.MINOR.PATCH")
    elif normalized != expected:
        errors.append(f"{label} {normalized} does not match canonical version {expected}")


def validate_repository_versions(
    root: Path,
    *,
    expected_release: str | None = None,
    strict: bool = True,
) -> dict[str, Any]:
    """Validate version carriers under ``root``.

    ``strict=False`` is useful for a Candidate that intentionally does not
    contain the full repository metadata.  The normal repository and release
    paths use strict mode.
    """

    root = root.resolve()
    errors: list[str] = []
    checked: list[str] = []
    values: dict[str, Any] = {}

    manifest_path = root / "config" / "template-manifest.json"
    manifest = load_json(manifest_path)
    if not manifest:
        if strict:
            errors.append("config/template-manifest.json is missing or invalid")
        return {"errors": errors, "checked": checked, "values": values}
    checked.append("config/template-manifest.json")

    template_id = str(manifest.get("template_id", ""))
    canonical = normalize_version(manifest.get("template_version"))
    schema_version = normalize_version(manifest.get("schema_version"))
    data_version = normalize_version(manifest.get("data_format_version"))
    if not template_id:
        errors.append("canonical manifest is missing template_id")
    if canonical is None:
        errors.append("canonical manifest template_version must use MAJOR.MINOR.PATCH")
    if schema_version is None:
        errors.append("canonical manifest schema_version must use MAJOR.MINOR.PATCH")
    if data_version is None:
        errors.append("canonical manifest data_format_version must use MAJOR.MINOR.PATCH")
    if canonical is None:
        return {"errors": errors, "checked": checked, "values": values}

    values.update({
        "template_id": template_id,
        "template_version": canonical,
        "schema_version": schema_version,
        "data_format_version": data_version,
    })

    carriers = [
        ("config/template.yaml", load_json(root / "config" / "template.yaml")),
        ("config/template.manifest.yaml", load_json(root / "config" / "template.manifest.yaml")),
    ]
    for relative, carrier in carriers:
        path = root / relative
        if not carrier:
            if strict:
                errors.append(f"{relative} is missing or invalid")
            continue
        checked.append(relative)
        if relative.endswith("template.manifest.yaml"):
            template = carrier.get("template", {})
            compatibility = carrier.get("compatibility", {})
            _add_match(errors, f"{relative}:template.version", template.get("version"), canonical)
            if template.get("id") != template_id:
                errors.append(f"{relative}:template.id does not match canonical template_id")
            _add_match(errors, f"{relative}:compatibility.schema_version", compatibility.get("schema_version"), schema_version or "")
            _add_match(errors, f"{relative}:compatibility.data_format_version", compatibility.get("data_format_version"), data_version or "")
        else:
            if carrier.get("template_id") != template_id:
                errors.append(f"{relative}:template_id does not match canonical template_id")
            _add_match(errors, f"{relative}:template_version", carrier.get("template_version"), canonical)
            _add_match(errors, f"{relative}:schema_version", carrier.get("schema_version"), schema_version or "")
            _add_match(errors, f"{relative}:data_format_version", carrier.get("data_format_version"), data_version or "")

    base_path = root / "TEMPLATE_BASE.md"
    try:
        base_lines = base_path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError, UnicodeError):
        base_lines = []
    if base_lines:
        checked.append("TEMPLATE_BASE.md")
        base_values: dict[str, str] = {}
        for line in base_lines:
            match = re.match(r"^- ([^:]+): `?([^`]+)`?$", line)
            if match:
                base_values[match.group(1)] = match.group(2).strip()
        if base_values.get("Template ID") != template_id:
            errors.append("TEMPLATE_BASE.md Template ID does not match canonical template_id")
        _add_match(errors, "TEMPLATE_BASE.md Version", base_values.get("Version"), canonical)
        _add_match(errors, "TEMPLATE_BASE.md Release", base_values.get("Release"), canonical)
    elif strict:
        errors.append("TEMPLATE_BASE.md is missing or unreadable")

    changelog = changelog_version(root / "CHANGELOG.md")
    if changelog is not None:
        checked.append("CHANGELOG.md")
        _add_match(errors, "CHANGELOG.md first release", changelog, canonical)
    elif strict:
        errors.append("CHANGELOG.md has no release heading")

    project_state = load_json(root / "config" / "project-state.yaml")
    if project_state:
        checked.append("config/project-state.yaml")
        state_version = project_state.get("template_version")
        if state_version is not None:
            _add_match(errors, "config/project-state.yaml:template_version", state_version, canonical)

    if expected_release is not None:
        release = normalize_version(expected_release)
        if release is None:
            errors.append("expected release must use MAJOR.MINOR.PATCH or vMAJOR.MINOR.PATCH")
        elif release != canonical:
            errors.append(f"release {release} does not match canonical version {canonical}")

    values["checked_release"] = expected_release
    return {"errors": errors, "checked": checked, "values": values}



