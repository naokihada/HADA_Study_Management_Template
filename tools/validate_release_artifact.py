"""Validate a public Template or Sample artifact without changing it."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
    from tools.core.version_contract import validate_repository_versions
except ModuleNotFoundError:  # Direct execution from tools/
    from core.version_contract import validate_repository_versions


SECRET_NAME = re.compile(r"(^|/)(\.env|.*\.(pem|key|p12|pfx))$", re.IGNORECASE)
DEFAULT_FORBIDDEN_FILES = {"SPEC.md", "ReSPEC.md", "ReSPEC_COMPARISON.md"}
DEFAULT_FORBIDDEN_PREFIXES = ("AI/", "records/template-upgrades/", "logs/external-ai/", "tmp/")
DEFAULT_TEMPLATE_FORBIDDEN_PREFIXES = ("data/", "plans/", "records/", "artifacts/")
BUILD_ARTIFACT_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".venv", "venv"}


def relative_files(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and not BUILD_ARTIFACT_PARTS.intersection(path.parts)
        and path.suffix.lower() != ".pyc"
    )


def load_manifest(root: Path) -> dict:
    path = root / "config" / "template-manifest.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def validate(root: Path, expected_release: str | None = None, artifact_kind: str = "template") -> dict:
    root = root.resolve()
    errors: list[str] = []
    checked: list[str] = []
    if not root.is_dir():
        return {"status": "BLOCKED", "errors": [f"artifact directory is missing: {root}"], "checked": []}

    manifest = load_manifest(root)
    contract = manifest.get("public_artifact_contract")
    if not isinstance(contract, dict):
        errors.append("public_artifact_contract is missing from canonical manifest")
        contract = {}

    required_files = {str(value) for value in contract.get("required_files", [])}
    allowed_files = {str(value) for value in contract.get("allowed_files", [])}
    forbidden_files = {
        str(value) for value in contract.get("forbidden_files", DEFAULT_FORBIDDEN_FILES)
    }
    forbidden_prefixes = tuple(
        str(value) for value in contract.get("forbidden_prefixes", DEFAULT_FORBIDDEN_PREFIXES)
    )
    template_forbidden_prefixes = tuple(
        str(value) for value in contract.get(
            "template_forbidden_prefixes", DEFAULT_TEMPLATE_FORBIDDEN_PREFIXES
        )
    )

    files = relative_files(root)
    checked.extend(files)
    for required in sorted(required_files):
        if not (root / Path(required)).is_file():
            errors.append(f"required public file is missing: {required}")

    for relative in files:
        if relative in forbidden_files:
            errors.append(f"internal file must not be published: {relative}")
        if any(relative.startswith(prefix) for prefix in forbidden_prefixes) and relative not in allowed_files:
            errors.append(f"internal path must not be published: {relative}")
        if artifact_kind == "template" and any(relative.startswith(prefix) for prefix in template_forbidden_prefixes):
            errors.append(f"user-data path must not be published in the Template artifact: {relative}")
        if SECRET_NAME.search(relative):
            errors.append(f"possible secret file must not be published: {relative}")

    version_result = None
    if (root / "config" / "template-manifest.json").exists():
        version_result = validate_repository_versions(root, expected_release=expected_release, strict=True)
        errors.extend(version_result["errors"])
    elif expected_release:
        errors.append("expected release was provided but canonical manifest is missing")

    return {
        "status": "SUCCESS" if not errors else "FAILED",
        "errors": errors,
        "checked": checked,
        "version": version_result,
        "artifact_kind": artifact_kind,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--expected-release")
    parser.add_argument("--artifact-kind", choices=("template", "sample"), default="template")
    parser.add_argument("--json", action="store_true", help="emit only machine-readable JSON")
    args = parser.parse_args()
    result = validate(args.root, args.expected_release, args.artifact_kind)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"RELEASE_ARTIFACT: {result['status']}")
        print(f"FILES_CHECKED: {len(result['checked'])}")
        for error in result["errors"]:
            print("ERROR: " + error)
    return 0 if result["status"] == "SUCCESS" else 2 if result["status"] == "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
