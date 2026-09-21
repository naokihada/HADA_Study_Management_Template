"""Read-only three-way dry-run planner for template upgrades."""

from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import re
from pathlib import Path

VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def validate_manifest(manifest: dict) -> list[str]:
    errors = []
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
    return errors


def files(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file() and ".git" not in path.parts}


def safe_destination(root: Path, relative: str) -> Path:
    destination = (root / relative).resolve()
    root_resolved = root.resolve()
    if destination != root_resolved and root_resolved not in destination.parents:
        raise ValueError(f"unsafe destination: {relative}")
    return destination


def same(root: Path, relative: str, other: Path) -> bool:
    left, right = root / relative, other / relative
    return left.exists() and right.exists() and left.read_bytes() == right.read_bytes()


def ownership(relative: str, manifest: dict) -> str:
    values = manifest.get("ownership", {})
    for kind in ("template_owned", "user_owned", "generated"):
        if any(fnmatch.fnmatch(relative, pattern) for pattern in values.get(kind, [])):
            return kind.upper()
    return "UNKNOWN"


def plan(previous: Path, current: Path, new: Path, manifest: dict) -> list[str]:
    all_files = files(previous) | files(current) | files(new)
    lines = []
    for relative in sorted(all_files):
        p, c, n = relative in files(previous), relative in files(current), relative in files(new)
        if not c and n:
            action = "AUTO" if ownership(relative, manifest) == "TEMPLATE_OWNED" else "REVIEW_REQUIRED"
        elif c and not n:
            action = "REVIEW_REQUIRED"
        elif p and c and n and same(previous, relative, current) and same(previous, relative, new):
            action = "UNCHANGED"
        elif p and c and n and same(previous, relative, current) and not same(previous, relative, new):
            action = "AUTO" if ownership(relative, manifest) == "TEMPLATE_OWNED" else "REVIEW_REQUIRED"
        elif p and c and n and not same(previous, relative, current) and same(previous, relative, new):
            action = "PRESERVE"
        else:
            action = "REVIEW_REQUIRED"
        lines.append(f"{action}\t{relative}\t{ownership(relative, manifest)}")
    return lines


def apply_safe(previous: Path, current: Path, new: Path, manifest: dict) -> list[str]:
    """Apply only provably template-owned AUTO changes; never remove files."""
    applied: list[str] = []
    for item in plan(previous, current, new, manifest):
        action, relative, owner = item.split("\t", 2)
        if action != "AUTO" or owner != "TEMPLATE_OWNED":
            continue
        source = safe_destination(new, relative)
        destination = safe_destination(current, relative)
        if not source.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        applied.append(relative)
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="apply only AUTO template-owned changes; never delete files")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    errors = validate_manifest(manifest)
    if errors:
        print("STATUS: INVALID_MANIFEST")
        for error in errors:
            print("ERROR: " + error)
        return 2
    print("STATUS: DRY_RUN")
    print("P=" + str(args.previous.resolve()))
    print("C=" + str(args.current.resolve()))
    print("N=" + str(args.new.resolve()))
    planned = plan(args.previous, args.current, args.new, manifest)
    print("ACTION\tPATH\tOWNERSHIP")
    print("\n".join(planned))
    if args.apply:
        applied = apply_safe(args.previous, args.current, args.new, manifest)
        print("APPLIED: " + (", ".join(applied) if applied else "none"))
    return 0


try:
    from tools.template_upgrade_v13 import apply_safe, files, ownership, plan, plan_details, run_upgrade, validate_manifest
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools.template_upgrade_v13 import apply_safe, files, ownership, plan, plan_details, run_upgrade, validate_manifest


if __name__ == "__main__":
    try:
        from tools.template_upgrade_v13 import main as v13_main
    except ModuleNotFoundError:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tools.template_upgrade_v13 import main as v13_main
    raise SystemExit(v13_main())
