"""Three-way template upgrade planner with candidate-first verification.

The command does not modify Template or user files by default. ``--apply``
requires a clean Candidate copy, validates that Candidate, and only then
promotes safe template-owned files. It never deletes files and never performs
Git operations. Compact evidence is recorded outside ``AI/``.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from tools.core.version_contract import validate_repository_versions
    from tools.core.file_inventory import repository_files
except ModuleNotFoundError:  # Direct execution: python tools/template_upgrade.py
    from core.version_contract import validate_repository_versions
    from core.file_inventory import repository_files

VERSION = re.compile(r"^\d+\.\d+\.\d+$")
STATUS_SUCCESS = "SUCCESS"
STATUS_REVIEW_REQUIRED = "REVIEW_REQUIRED"
STATUS_BLOCKED = "BLOCKED"
STATUS_FAILED = "FAILED"
EXIT_CODES = {
    STATUS_SUCCESS: 0,
    STATUS_REVIEW_REQUIRED: 1,
    STATUS_BLOCKED: 2,
    STATUS_FAILED: 3,
}


def validate_manifest(manifest: dict) -> list[str]:
    errors: list[str] = []
    for field in ("template_id", "template_version", "schema_version", "data_format_version"):
        if not manifest.get(field):
            errors.append(f"manifest missing {field}")
    for field in ("template_version", "schema_version", "data_format_version"):
        if manifest.get(field) and not VERSION.fullmatch(str(manifest[field])):
            errors.append(f"manifest {field} must use MAJOR.MINOR.PATCH")
    contract = manifest.get("upgrade_contract")
    if not isinstance(contract, dict):
        errors.append("manifest missing upgrade_contract")
    else:
        if contract.get("baseline") != manifest.get("template_version"):
            errors.append("manifest upgrade_contract.baseline must equal template_version")
        if contract.get("comparison") != ["previous_template", "current_project", "new_template"]:
            errors.append("manifest upgrade_contract.comparison must define P/C/N order")
        if contract.get("user_data_policy") != "preserve":
            errors.append("manifest upgrade_contract.user_data_policy must be preserve")
        if contract.get("automatic_deletion") is not False:
            errors.append("manifest upgrade_contract.automatic_deletion must be false")
        if contract.get("git_operations") != "manual":
            errors.append("manifest upgrade_contract.git_operations must be manual")
        if contract.get("candidate_required") is not True:
            errors.append("manifest upgrade_contract.candidate_required must be true")
        if contract.get("legacy_bootstrap") is not True:
            errors.append("manifest upgrade_contract.legacy_bootstrap must be true")
        if contract.get("evidence_root") != "records/template-upgrades":
            errors.append("manifest upgrade_contract.evidence_root must be records/template-upgrades")
        source_policy = contract.get("source_policy")
        if not isinstance(source_policy, dict) or "stable_release" not in source_policy.get("allowed", []):
            errors.append("manifest upgrade_contract.source_policy must allow stable_release")
        status_codes = contract.get("status_codes")
        if status_codes is not None:
            for status in (STATUS_SUCCESS, STATUS_REVIEW_REQUIRED, STATUS_BLOCKED, STATUS_FAILED):
                if status not in status_codes:
                    errors.append(f"manifest upgrade_contract.status_codes missing {status}")
    ownership_values = manifest.get("ownership")
    if ownership_values is not None:
        if not isinstance(ownership_values, dict):
            errors.append("manifest ownership must be an object")
        else:
            for kind in ("template_owned", "user_owned", "generated", "reference", "master", "unknown", "review_required"):
                if kind in ownership_values and not isinstance(ownership_values[kind], list):
                    errors.append(f"manifest ownership.{kind} must be an array")
    migration_paths = manifest.get("migration_paths")
    if migration_paths is not None:
        if not isinstance(migration_paths, list):
            errors.append("manifest migration_paths must be an array")
        else:
            for index, migration in enumerate(migration_paths):
                if not isinstance(migration, dict):
                    errors.append(f"manifest migration_paths[{index}] must be an object")
                    continue
                for field in ("from", "to", "status", "strategy"):
                    if not migration.get(field):
                        errors.append(f"manifest migration_paths[{index}] missing {field}")
                for field in ("from", "to"):
                    if migration.get(field) and not VERSION.fullmatch(str(migration[field])):
                        errors.append(f"manifest migration_paths[{index}].{field} must use MAJOR.MINOR.PATCH")
                if migration.get("automatic_data_migration") is not False:
                    errors.append(f"manifest migration_paths[{index}] must explicitly disable automatic data migration")
    return errors


def files(root: Path) -> set[str]:
    return {path.relative_to(root.resolve()).as_posix() for path in repository_files(root)}


def safe_destination(root: Path, relative: str) -> Path:
    destination = (root / relative).resolve()
    root_resolved = root.resolve()
    if destination != root_resolved and root_resolved not in destination.parents:
        raise ValueError(f"unsafe destination: {relative}")
    return destination


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def same(root: Path, relative: str, other: Path) -> bool:
    left, right = root / relative, other / relative
    return left.exists() and right.exists() and left.is_file() and right.is_file() and left.read_bytes() == right.read_bytes()


def ownership(relative: str, manifest: dict) -> str:
    """Resolve ownership with explicit review and user protection first."""

    values = manifest.get("ownership", {})
    if not isinstance(values, dict):
        return "UNKNOWN"
    # Specific protection classes must win over broad patterns such as
    # config/** and records/**.
    for kind in ("review_required", "user_owned", "master", "reference", "generated", "template_owned", "unknown"):
        patterns = values.get(kind, [])
        if any(fnmatch.fnmatch(relative, pattern) for pattern in patterns):
            return kind.upper()
    return "UNKNOWN"


def plan_details(previous: Path, current: Path, new: Path, manifest: dict) -> list[dict[str, Any]]:
    previous_files, current_files, new_files = files(previous), files(current), files(new)
    all_files = previous_files | current_files | new_files
    details: list[dict[str, Any]] = []
    for relative in sorted(all_files):
        p, c, n = relative in previous_files, relative in current_files, relative in new_files
        owner = ownership(relative, manifest)
        if not c and n:
            action = "AUTO" if owner == "TEMPLATE_OWNED" else STATUS_REVIEW_REQUIRED
            classification = "TEMPLATE_ONLY" if action == "AUTO" else "UNKNOWN"
        elif c and not n:
            action, classification = STATUS_REVIEW_REQUIRED, "REMOVED_FROM_NEW_TEMPLATE"
        elif p and c and n and same(previous, relative, current) and same(previous, relative, new):
            action, classification = "UNCHANGED", "UNCHANGED"
        elif p and c and n and same(previous, relative, current) and not same(previous, relative, new):
            action = "AUTO" if owner == "TEMPLATE_OWNED" else STATUS_REVIEW_REQUIRED
            classification = "TEMPLATE_ONLY" if action == "AUTO" else "CONFLICT"
        elif p and c and n and not same(previous, relative, current) and same(previous, relative, new):
            action, classification = "PRESERVE", "USER_ONLY"
        else:
            action, classification = STATUS_REVIEW_REQUIRED, "CONFLICT"
        detail: dict[str, Any] = {
            "path": relative,
            "ownership": owner,
            "classification": classification,
            "action": action,
            "present": {"previous": p, "current": c, "new": n},
        }
        for label, root in (("previous", previous), ("current", current), ("new", new)):
            path = root / relative
            if path.is_file():
                detail.setdefault("sha256", {})[label] = sha256(path)
        details.append(detail)
    return details


def plan(previous: Path, current: Path, new: Path, manifest: dict) -> list[str]:
    """Compatibility output for existing callers and human review."""

    return [
        f"{item['action']}\t{item['path']}\t{item['ownership']}"
        for item in plan_details(previous, current, new, manifest)
    ]


def apply_safe(previous: Path, current: Path, new: Path, manifest: dict) -> list[str]:
    """Apply only provably template-owned AUTO changes; never remove files.

    This low-level helper writes to the supplied target.  The command-line
    workflow always supplies a Candidate here and promotes only after
    Candidate validation.
    """

    applied: list[str] = []
    for item in plan_details(previous, current, new, manifest):
        if item["action"] != "AUTO" or item["ownership"] != "TEMPLATE_OWNED":
            continue
        source = safe_destination(new, item["path"])
        destination = safe_destination(current, item["path"])
        if not source.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        applied.append(item["path"])
    return applied


def copy_candidate(source: Path, candidate: Path) -> None:
    source = source.resolve()
    candidate = candidate.resolve()
    if source == candidate or source in candidate.parents or candidate in source.parents:
        raise ValueError("candidate must be a separate directory")
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("candidate source contains a symbolic link")
    if candidate.exists():
        if not candidate.is_dir() or any(candidate.iterdir()):
            raise FileExistsError(f"candidate must be a new or empty directory: {candidate}")
    else:
        candidate.mkdir(parents=True)
    for source_file in repository_files(source):
        relative = source_file.relative_to(source)
        target = candidate / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target)


def validate_candidate(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    version_result = validate_repository_versions(root, strict=True)
    errors.extend(version_result["errors"])
    try:
        from tools import study_cli
        study_errors, study_warnings, _ = study_cli.validate(root)
        errors.extend(study_errors)
        warnings.extend(study_warnings)
    except (ImportError, OSError, ValueError) as exc:
        errors.append(f"candidate study validation failed to run: {exc}")
    return {"errors": errors, "warnings": warnings, "version": version_result}


def _upgrade_id(version: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_version = re.sub(r"[^0-9A-Za-z.-]", "-", version)
    return f"{stamp}_{safe_version}"


def write_evidence(root: Path, upgrade_id: str, evidence: dict[str, Any], evidence_root: str = "records/template-upgrades") -> Path:
    relative_root = Path(evidence_root)
    if relative_root.is_absolute() or ".." in relative_root.parts:
        raise ValueError("evidence root must remain inside the current project")
    directory = (root / relative_root / upgrade_id).resolve()
    if root.resolve() not in directory.parents:
        raise ValueError("evidence root escapes the current project")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "upgrade-result.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plan_data = evidence.get("plan", [])
    (directory / "migration-plan.json").write_text(json.dumps(plan_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return directory


def _input_status(previous: Path, current: Path, new: Path) -> str | None:
    for label, path in (("previous", previous), ("current", current), ("new", new)):
        if not path.is_dir():
            return f"{label} directory is missing"
    return None


def run_upgrade(
    previous: Path,
    current: Path,
    new: Path,
    manifest_path: Path,
    *,
    apply: bool = False,
    candidate_only: bool = False,
    legacy_bootstrap: bool = False,
    candidate: Path | None = None,
    expected_release: str | None = None,
    evidence_root: str = "records/template-upgrades",
) -> dict[str, Any]:
    """Plan or safely apply an upgrade and return a machine-readable result."""

    previous, current, new, manifest_path = (path.resolve() for path in (previous, current, new, manifest_path))
    manifest: dict[str, Any] = {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        status = STATUS_BLOCKED
        evidence = {"status": status, "mode": "APPLY" if apply else "DRY_RUN", "errors": ["manifest is missing or invalid"], "plan": []}
        evidence_dir = write_evidence(current, _upgrade_id("unknown"), evidence, evidence_root) if current.is_dir() else None
        if evidence_dir:
            evidence["evidence_path"] = evidence_dir.relative_to(current).as_posix()
        return evidence

    manifest_errors = validate_manifest(manifest)
    input_error = _input_status(previous, current, new)
    version_checks: dict[str, Any] = {}
    for label, path in (("previous", previous), ("current", current), ("new", new)):
        if (path / "config" / "template-manifest.json").exists():
            version_checks[label] = validate_repository_versions(
                path,
                expected_release=expected_release if label == "new" else None,
                strict=not (legacy_bootstrap and label in {"previous", "current"}),
            )
    if not version_checks.get("new") and not input_error:
        version_checks["new"] = {"errors": ["new template has no canonical version manifest"], "checked": [], "values": {}}
    details = plan_details(previous, current, new, manifest) if not input_error and not manifest_errors else []
    has_review = any(item["action"] == STATUS_REVIEW_REQUIRED for item in details)
    version_errors = [
        error
        for label, result in version_checks.items()
        for error in result.get("errors", [])
        if not (legacy_bootstrap and label in {"previous", "current"})
    ]
    legacy_warnings: list[str] = []
    if legacy_bootstrap:
        for relative in (
            "CHANGELOG.md",
            "TEMPLATE_BASE.md",
            "config/template.manifest.yaml",
        ):
            if not (current / relative).exists():
                legacy_warnings.append(f"legacy project is missing version carrier: {relative}")
    if input_error:
        status = STATUS_BLOCKED
    elif manifest_errors:
        status = STATUS_FAILED
    elif version_errors:
        status = STATUS_REVIEW_REQUIRED
    elif has_review:
        status = STATUS_REVIEW_REQUIRED
    else:
        status = STATUS_SUCCESS

    result: dict[str, Any] = {
        "status": status,
        "mode": "CANDIDATE_ONLY" if candidate_only else "APPLY" if apply else "DRY_RUN",
        "legacy_bootstrap": legacy_bootstrap,
        "template_version": manifest.get("template_version"),
        "paths": {"previous": "P", "current": "C", "new": "N"},
        "manifest_errors": manifest_errors,
        "input_error": input_error,
        "version_checks": version_checks,
        "plan": details,
        "applied": [],
        "candidate": None,
        "errors": version_errors,
        "warnings": legacy_warnings,
    }

    if candidate_only:
        if not candidate:
            result["status"] = STATUS_BLOCKED
            result["errors"].append("candidate-only mode requires --candidate")
        elif status in {STATUS_SUCCESS, STATUS_REVIEW_REQUIRED}:
            try:
                candidate_path = candidate.resolve()
                copy_candidate(current, candidate_path)
                applied = apply_safe(previous, candidate_path, new, manifest)
                candidate_result = validate_candidate(candidate_path)
                result["candidate"] = {
                    "retained": True,
                    "applied": applied,
                    "validation": candidate_result,
                }
                result["warnings"].extend(candidate_result.get("warnings", []))
                if candidate_result.get("errors"):
                    result["status"] = STATUS_BLOCKED
                    result["errors"].extend(candidate_result["errors"])
            except (OSError, ValueError, shutil.Error) as exc:
                result["status"] = STATUS_FAILED
                result["errors"].append(f"candidate operation failed: {type(exc).__name__}")
        else:
            result["errors"].append("candidate-only mode requires a non-blocked plan")
    elif apply and status == STATUS_SUCCESS:
        temporary_directory: tempfile.TemporaryDirectory[str] | None = None
        candidate_path = candidate.resolve() if candidate else None
        try:
            if candidate_path is None:
                temporary_directory = tempfile.TemporaryDirectory(prefix="hada-study-upgrade-")
                candidate_path = Path(temporary_directory.name)
            copy_candidate(current, candidate_path)
            applied = apply_safe(previous, candidate_path, new, manifest)
            candidate_result = validate_candidate(candidate_path)
            result["candidate"] = {
                "retained": candidate is not None,
                "applied": applied,
                "validation": candidate_result,
            }
            result["warnings"].extend(candidate_result.get("warnings", []))
            if candidate_result.get("errors"):
                result["status"] = STATUS_BLOCKED
                result["errors"].extend(candidate_result["errors"])
            else:
                promoted: list[str] = []
                for relative in applied:
                    source = safe_destination(candidate_path, relative)
                    destination = safe_destination(current, relative)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                    promoted.append(relative)
                result["applied"] = promoted
        except (OSError, ValueError, shutil.Error) as exc:
            result["status"] = STATUS_FAILED
            result["errors"].append(f"candidate operation failed: {type(exc).__name__}")
        finally:
            if temporary_directory is not None:
                temporary_directory.cleanup()
    elif apply:
        result["errors"].append("apply requires a clean plan with no review-required items")

    evidence_dir = write_evidence(current, _upgrade_id(str(manifest.get("template_version", "unknown"))), result, evidence_root)
    result["evidence_path"] = evidence_dir.relative_to(current).as_posix()
    (evidence_dir / "upgrade-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="verify a Candidate, then promote safe changes")
    parser.add_argument("--candidate-only", action="store_true", help="create and validate a retained Candidate without changing the current project")
    parser.add_argument("--legacy-bootstrap", action="store_true", help="allow missing old version carriers while preparing a Candidate")
    parser.add_argument("--candidate", type=Path, help="new or empty Candidate directory to retain for review")
    parser.add_argument("--release-version", help="expected stable release version, for example v1.3.0")
    parser.add_argument("--evidence-root", default="records/template-upgrades")
    args = parser.parse_args()
    result = run_upgrade(
        args.previous,
        args.current,
        args.new,
        args.manifest,
        apply=args.apply,
        candidate_only=args.candidate_only,
        legacy_bootstrap=args.legacy_bootstrap,
        candidate=args.candidate,
        expected_release=args.release_version,
        evidence_root=args.evidence_root,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return EXIT_CODES.get(result["status"], EXIT_CODES[STATUS_FAILED])


if __name__ == "__main__":
    raise SystemExit(main())


