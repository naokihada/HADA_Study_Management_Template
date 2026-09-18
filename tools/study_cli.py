"""Small, dependency-free CLI for the file-based study template."""

from __future__ import annotations

import argparse
import csv
import fnmatch
import json
import re
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

try:
    from tools.import_pipeline import ImportPipeline, run_chat_import, run_url_import
except ModuleNotFoundError:  # Direct execution: python tools/study_cli.py
    from import_pipeline import ImportPipeline, run_chat_import, run_url_import

CSV_CONTRACTS = {
    "data/master/goals.csv": ("goal_id", "title", "goal_type", "status", "priority", "start_date", "target_date"),
    "data/master/stages.csv": ("stage_id", "goal_id", "name", "start_date", "end_date", "status", "sequence"),
    "data/master/metrics.csv": ("metric_id", "name", "unit", "direction"),
    "data/master/targets.csv": ("target_id", "goal_id", "target_type", "name"),
    "data/master/subjects.csv": ("subject_id", "name", "subject_type"),
    "data/master/resources.csv": ("resource_id", "name", "resource_type"),
    "plans/default/epics.csv": ("epic_id", "goal_id", "title", "status", "priority"),
    "plans/default/sprints.csv": ("sprint_id", "name", "start_date", "end_date", "status"),
    "plans/default/issues.csv": ("issue_id", "issue_type", "title", "status", "priority", "sprint_id", "epic_id"),
    "plans/default/subtasks.csv": ("subtask_id", "issue_id", "title", "status", "priority"),
    "records/default/sessions.csv": ("session_id", "date", "duration_minutes", "activity_type", "content"),
    "records/default/assessments.csv": ("assessment_id", "target_id", "assessment_type", "assessment_date"),
    "records/default/metric_observations.csv": ("observation_id", "metric_id", "observed_at", "value"),
    "records/default/events.csv": ("event_id", "event_type", "title", "start_at", "all_day", "timezone", "importance", "status"),
}
PROJECT_CSV_CONTRACTS = {
    "epics.csv": ("epic_id", "goal_id", "title", "status", "priority"),
    "sprints.csv": ("sprint_id", "name", "start_date", "end_date", "status"),
    "issues.csv": ("issue_id", "issue_type", "title", "status", "priority", "sprint_id", "epic_id"),
    "subtasks.csv": ("subtask_id", "issue_id", "title", "status", "priority"),
    "sessions.csv": ("session_id", "date", "duration_minutes", "activity_type", "content"),
    "assessments.csv": ("assessment_id", "target_id", "assessment_type", "assessment_date"),
    "metric_observations.csv": ("observation_id", "metric_id", "observed_at", "value"),
    "events.csv": ("event_id", "event_type", "title", "start_at", "all_day", "timezone", "importance", "status"),
}
ID_COLUMNS = {
    "goal_id": "goals", "target_id": "targets", "subject_id": "subjects", "resource_id": "resources",
    "epic_id": "epics", "sprint_id": "sprints", "issue_id": "issues", "subtask_id": "subtasks",
    "session_id": "sessions", "assessment_id": "assessments", "event_id": "events",
    "stage_id": "stages", "current_stage_id": "stages", "transition_event_id": "events",
    "metric_id": "metrics", "observation_id": "metric_observations",
}
DATE_FIELDS = {"date", "start_date", "end_date", "target_date", "due_date", "assessment_date"}
PHOTO_DATE = re.compile(r"^(?P<date>\d{8})")
DOMAIN_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
VISIBILITY_VALUES = {"private", "summary", "public"}


def load_config(root: Path) -> dict:
    path = root / "config" / "template.yaml"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"timezone": "Asia/Tokyo", "photo_root": "artifacts", "allowed_photo_extensions": [".jpg", ".jpeg", ".png", ".webp"], "default_visibility": "private", "visibility_values": sorted(VISIBILITY_VALUES)}


def load_json_file(path: Path, default: dict | None = None) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else (default or {})
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return default or {}


def state_path(root: Path) -> Path:
    return root / "config" / "project-state.yaml"


def load_project_state(root: Path) -> dict:
    return load_json_file(state_path(root), {"initialization_status": "not_initialized", "domain_lock_status": "unlocked"})


def load_compatibility(root: Path) -> dict:
    return load_json_file(root / "config" / "domain-compatibility.yaml", {"families": {}, "related_upgrades": {}})


def domain_change_classification(root: Path, target: str) -> tuple[str, str]:
    state = load_project_state(root)
    current = str(state.get("domain_variant", ""))
    if not current:
        return "COMPATIBLE", "No existing domain is configured."
    if current == target:
        return "COMPATIBLE", "The requested domain is already active."
    compatibility = load_compatibility(root)
    families = compatibility.get("families", {})
    current_family = next((family for family, variants in families.items() if current in variants), None)
    target_family = next((family for family, variants in families.items() if target in variants), None)
    related = target in compatibility.get("related_upgrades", {}).get(current, [])
    if current_family and current_family == target_family:
        return ("COMPATIBLE_WITH_CONFIRMATION" if related else "COMPATIBLE"), "The domains share a configured family."
    return "INCOMPATIBLE_BUT_FORCE_ALLOWED", "The domains use different configured families; a separate project is recommended."


def domain_status(root: Path) -> str:
    state = load_project_state(root)
    return json.dumps({
        "initialization_status": state.get("initialization_status", "not_initialized"),
        "domain_lock_status": state.get("domain_lock_status", "unlocked"),
        "domain_family": state.get("domain_family"),
        "domain_variant": state.get("domain_variant"),
        "template_version": state.get("template_version"),
        "schema_version": state.get("schema_version"),
        "domain_history_entries": len(state.get("domain_history", [])) if isinstance(state.get("domain_history", []), list) else 0,
    }, ensure_ascii=False, indent=2)


def change_domain(root: Path, target: str, confirm: bool, force: bool) -> str:
    if not DOMAIN_ID.fullmatch(target):
        return "ERROR: domain variant must use lowercase letters, numbers, and hyphens"
    state = load_project_state(root)
    if state.get("initialization_status") != "initialized":
        return "ERROR: project is not initialized; configure the project before changing its domain"
    classification, reason = domain_change_classification(root, target)
    print(f"CLASSIFICATION: {classification}")
    print(f"REASON: {reason}")
    if classification == "INCOMPATIBLE_BUT_FORCE_ALLOWED" and not force:
        return "WARNING: use --force only after reviewing the incompatibility warning; a separate project is recommended"
    if not confirm:
        return "DRY-RUN: no files changed; pass --confirm to apply the domain change"
    current = state.get("domain_variant")
    state["domain_variant"] = target
    state["domain_lock_status"] = "locked"
    history = state.setdefault("domain_history", [])
    history.append({
        "from_domain": current,
        "to_domain": target,
        "change_type": "forced" if force else "confirmed_upgrade",
        "confirmation_status": "confirmed",
        "warning_acknowledged": bool(force or classification != "INCOMPATIBLE_BUT_FORCE_ALLOWED"),
        "changed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "classification": classification,
    })
    state_path(root).parent.mkdir(parents=True, exist_ok=True)
    state_path(root).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return f"APPLIED: domain changed from {current!r} to {target!r}; history preserved"


def ai_reset(root: Path, apply: bool) -> str:
    ai_root = (root / "AI").resolve()
    root_resolved = root.resolve()
    if ai_root.parent != root_resolved:
        return "ERROR: AI reset target is outside the project root"
    targets = [path for path in (ai_root / name for name in ("working", "cache", "reports")) if path.exists()]
    if not targets:
        return "AI RESET: no disposable AI directories found"
    lines = ["AI RESET PLAN:"] + [f"- {path.relative_to(root_resolved).as_posix()}" for path in targets]
    if not apply:
        lines.append("DRY-RUN: no files changed; pass --apply to remove only these directories")
        return "\n".join(lines)
    for path in targets:
        if path.is_symlink() or not path.resolve().is_relative_to(ai_root):
            return f"ERROR: unsafe AI reset target: {path}"
        shutil.rmtree(path)
    lines.append("APPLIED: disposable AI directories removed; data/ and artifacts/ were not changed")
    return "\n".join(lines)


def validate_ai_boundary(root: Path, errors: list[str], warnings: list[str]) -> None:
    ai_root = root / "AI"
    if not ai_root.exists():
        return
    allowed = {"README.md", "working", "cache", "reports", "history", "handoff"}
    for path in ai_root.iterdir():
        if path.name not in allowed:
            errors.append(f"AI boundary violation: unexpected path {path.relative_to(root).as_posix()!r}")
    for name in ("data", "plans", "records", "artifacts"):
        path = ai_root / name
        if path.exists():
            errors.append(f"AI boundary violation: user-data directory must be outside AI/{name}")


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def parse_date(value: str, label: str, errors: list[str]) -> None:
    if not value:
        return
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        errors.append(f"{label}: invalid date {value!r}; expected YYYY-MM-DD")


def parse_datetime(value: str, label: str, errors: list[str]) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{label}: invalid ISO datetime {value!r}")
        return None


def timezone_for_name(value: str):
    if value == "Asia/Tokyo":
        return timezone(timedelta(hours=9), "Asia/Tokyo")
    if value in {"UTC", "Etc/UTC", "GMT"}:
        return timezone.utc
    try:
        return ZoneInfo(value)
    except Exception:
        return None


def validate_timezone(value: str, label: str, errors: list[str]) -> None:
    if not value:
        return
    if timezone_for_name(value) is None:
        errors.append(f"{label}: unknown timezone {value!r}")


def split_ids(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[;,]", value or "") if item.strip()]


def contract_paths(root: Path) -> list[tuple[str, tuple[str, ...], Path]]:
    paths = [(relative, required, root / relative) for relative, required in CSV_CONTRACTS.items() if not relative.startswith(("plans/default/", "records/default/"))]
    project_ids = {path.name for parent in (root / "plans", root / "records") if parent.exists() for path in parent.iterdir() if path.is_dir()}
    for project_id in sorted(project_ids):
        for filename, required in PROJECT_CSV_CONTRACTS.items():
            relative = f"plans/{project_id}/{filename}" if filename in {"epics.csv", "sprints.csv", "issues.csv", "subtasks.csv"} else f"records/{project_id}/{filename}"
            paths.append((relative, required, root / relative))
    return paths


def validate_photos(root: Path, config: dict, errors: list[str], warnings: list[str]) -> int:
    photo_root = root / config.get("photo_root", "artifacts")
    if not photo_root.exists():
        return 0
    allowed = {str(ext).lower() for ext in config.get("allowed_photo_extensions", [])}
    count = 0
    for path in photo_root.rglob("*"):
        if not path.is_file() or path.name.startswith("."):
            continue
        count += 1
        extension = path.suffix.lower()
        if allowed and extension not in allowed:
            errors.append(f"photo {path.relative_to(root)}: unsupported extension {extension!r}")
        relative_parts = path.relative_to(photo_root).parts
        match = PHOTO_DATE.match(path.name)
        if len(relative_parts) >= 2 and relative_parts[0].isdigit() and len(relative_parts[0]) == 4 and match:
            if match.group("date")[:4] != relative_parts[0]:
                errors.append(f"photo {path.relative_to(root)}: year folder does not match filename date")
        elif not match:
            warnings.append(f"photo {path.relative_to(root)}: DATE_UNKNOWN/UNSORTED")
    return count


def validate(root: Path) -> tuple[list[str], list[str], dict[str, int]]:
    errors: list[str] = []
    warnings: list[str] = []
    config = load_config(root)
    validate_timezone(str(config.get("timezone", "Asia/Tokyo")), "config:timezone", errors)
    visibility_values = set(config.get("visibility_values", VISIBILITY_VALUES))
    if not visibility_values.issubset(VISIBILITY_VALUES):
        errors.append("config:visibility_values may only contain private, summary, public")
    if str(config.get("default_visibility", "private")) not in visibility_values:
        errors.append("config:default_visibility must be one of the configured visibility values")
    learner_profile = load_json_file(root / "data" / "learner" / "learner.yaml", {})
    if learner_profile:
        profile_visibility = str(learner_profile.get("visibility", "private"))
        if profile_visibility not in visibility_values:
            errors.append("data/learner/learner.yaml: visibility must be private, summary, or public")
    ids: dict[str, set[str]] = defaultdict(set)
    rows_by_path: dict[str, list[dict[str, str]]] = {}
    for relative, required, path in contract_paths(root):
        if not path.exists():
            warnings.append(f"missing optional data file: {relative}")
            continue
        try:
            headers, rows = read_csv(path)
        except (OSError, UnicodeError) as exc:
            errors.append(f"{relative}: cannot read CSV ({exc})")
            continue
        missing = [field for field in required if field not in headers]
        if missing:
            errors.append(f"{relative}: missing required columns: {', '.join(missing)}")
        rows_by_path[relative] = rows
        for index, row in enumerate(rows, 2):
            for field in required:
                if field in row and not row[field].strip():
                    errors.append(f"{relative}:{index}: required field {field!r} is empty")
            for field in DATE_FIELDS:
                if field in row:
                    parse_date(row[field].strip(), f"{relative}:{index}:{field}", errors)
            for field in headers:
                if field.endswith("_at") and row.get(field, ""):
                    parse_datetime(row[field].strip(), f"{relative}:{index}:{field}", errors)
            if "timezone" in row and row["timezone"].strip():
                validate_timezone(row["timezone"].strip(), f"{relative}:{index}:timezone", errors)
            if "visibility" in row and row["visibility"].strip() and row["visibility"].strip() not in visibility_values:
                errors.append(f"{relative}:{index}: visibility must be private, summary, or public")
            if "all_day" in row and row["all_day"].strip().lower() not in {"true", "false"}:
                errors.append(f"{relative}:{index}: all_day must be true or false")
            for field, kind in ID_COLUMNS.items():
                if field in row and row[field].strip():
                    entity_id = row[field].strip()
                    if field.endswith("_id") and field == headers[0]:
                        if entity_id in ids[kind]:
                            errors.append(f"{relative}:{index}: duplicate {field} {entity_id!r}")
                        ids[kind].add(entity_id)
            if "started_at" in row and "ended_at" in row and row["started_at"] and row["ended_at"]:
                start = parse_datetime(row["started_at"], f"{relative}:{index}:started_at", errors)
                end = parse_datetime(row["ended_at"], f"{relative}:{index}:ended_at", errors)
                if start and end and end < start:
                    errors.append(f"{relative}:{index}: ended_at is before started_at")
            if "score" in row and "max_score" in row and row["score"] and row["max_score"]:
                try:
                    if float(row["score"]) > float(row["max_score"]):
                        errors.append(f"{relative}:{index}: score exceeds max_score")
                except ValueError:
                    errors.append(f"{relative}:{index}: score and max_score must be numeric")
            if "percentage" in row and row["percentage"].strip():
                try:
                    if not 0 <= float(row["percentage"]) <= 100:
                        errors.append(f"{relative}:{index}: percentage must be between 0 and 100")
                except ValueError:
                    errors.append(f"{relative}:{index}: percentage must be numeric")
            if "value" in row and row["value"].strip():
                try:
                    float(row["value"])
                except ValueError:
                    errors.append(f"{relative}:{index}: value must be numeric")
            if "target_value" in row and row["target_value"].strip():
                try:
                    float(row["target_value"])
                except ValueError:
                    errors.append(f"{relative}:{index}: target_value must be numeric")
            if relative.endswith("/stages.csv") and row.get("sequence", "").strip():
                try:
                    int(row["sequence"])
                except ValueError:
                    errors.append(f"{relative}:{index}: sequence must be an integer")
            if relative.endswith("/stages.csv") and row.get("start_date") and row.get("end_date"):
                try:
                    if datetime.strptime(row["end_date"], "%Y-%m-%d") < datetime.strptime(row["start_date"], "%Y-%m-%d"):
                        errors.append(f"{relative}:{index}: end_date is before start_date")
                except ValueError:
                    pass
            if "status" in row and row["status"].strip():
                allowed_statuses = set(config.get("issue_statuses", [])) | {"ACTIVE", "PLANNED", "DONE", "CANCELLED", "DRAFT", "ARCHIVED"}
                if allowed_statuses and row["status"].strip() not in allowed_statuses:
                    errors.append(f"{relative}:{index}: unknown status {row['status'].strip()!r}")
    # Cross-file references are checked conservatively; empty multi-value fields are valid.
    known = {key: values for key, values in ids.items()}
    for relative, rows in rows_by_path.items():
        for index, row in enumerate(rows, 2):
            for field, kind in ID_COLUMNS.items():
                if field not in row or field == row.keys().__iter__().__next__():
                    continue
                for value in split_ids(row[field]):
                    if value not in known.get(kind, set()):
                        errors.append(f"{relative}:{index}: unknown {field} reference {value!r}")
    sprint_ranges = {}
    for relative, rows in rows_by_path.items():
        if relative.endswith("/sprints.csv"):
            for index, row in enumerate(rows, 2):
                if row.get("sprint_id") and row.get("start_date") and row.get("end_date"):
                    try:
                        sprint_ranges[row["sprint_id"]] = (datetime.strptime(row["start_date"], "%Y-%m-%d"), datetime.strptime(row["end_date"], "%Y-%m-%d"))
                    except ValueError:
                        pass
        if relative.endswith("/issues.csv"):
            for index, row in enumerate(rows, 2):
                sprint = sprint_ranges.get(row.get("sprint_id", ""))
                if sprint and row.get("due_date"):
                    try:
                        due = datetime.strptime(row["due_date"], "%Y-%m-%d")
                        if not sprint[0] <= due <= sprint[1]:
                            warnings.append(f"{relative}:{index}: due_date is outside its sprint")
                    except ValueError:
                        pass
    photo_count = validate_photos(root, config, errors, warnings)
    validate_ai_boundary(root, errors, warnings)
    counts = {key: len(value) for key, value in ids.items()}
    counts["photos"] = photo_count
    return errors, warnings, counts


def iter_events(root: Path) -> Iterable[dict[str, str]]:
    rows: list[dict[str, str]] = []
    records_root = root / "records"
    if records_root.exists():
        for path in sorted(records_root.glob("*/events.csv")):
            _, project_rows = read_csv(path)
            rows.extend(project_rows)
    return rows


def calendar(root: Path) -> str:
    config = load_config(root)
    local_zone = timezone_for_name(str(config.get("timezone", "Asia/Tokyo"))) or timezone.utc
    def event_key(row: dict[str, str]) -> datetime:
        value = parse_datetime(row.get("start_at", ""), "calendar:start_at", [])
        if value is None:
            return datetime.max.replace(tzinfo=timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=local_zone)
        return value.astimezone(timezone.utc)
    rows = sorted(iter_events(root), key=event_key)
    lines = []
    for row in rows:
        start = row.get("start_at", "")
        label = start[:10] if start else "DATE_UNKNOWN"
        if start and not row.get("all_day", "").lower() == "true":
            parsed = parse_datetime(start, "calendar:start_at", [])
            if parsed is not None:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=local_zone)
                label = parsed.astimezone(local_zone).isoformat(timespec="seconds")
        place = f" / {row['venue']}" if row.get("venue") else ""
        lines.append(f"- {label} — {row.get('title', '')} [{row.get('event_type', '')}]{place}")
    return "\n".join(lines) if lines else "(events: none)"


def photo_groups(root: Path) -> str:
    config = load_config(root)
    photo_root = root / config.get("photo_root", "artifacts")
    groups: dict[str, list[str]] = defaultdict(list)
    if photo_root.exists():
        for path in sorted(photo_root.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            match = PHOTO_DATE.match(path.name)
            key = f"{match.group('date')[:4]}-{match.group('date')[4:6]}-{match.group('date')[6:]}" if match else "DATE_UNKNOWN"
            groups[key].append(path.relative_to(root).as_posix())
    if not groups:
        return "(photos: none)"
    lines = []
    for key in sorted(groups):
        lines.append(f"{key}")
        lines.extend(f"- {item}" for item in groups[key])
    return "\n".join(lines)


def summary(root: Path) -> str:
    rows: list[dict[str, str]] = []
    plans_root = root / "plans"
    if plans_root.exists():
        for path in sorted(plans_root.glob("*/issues.csv")):
            _, project_rows = read_csv(path)
            rows.extend(project_rows)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row.get("status", "UNKNOWN") or "UNKNOWN"] += 1
    return "Issues: " + str(len(rows)) + "\n" + "\n".join(f"- {key}: {counts[key]}" for key in sorted(counts))


def init_project(root: Path) -> str:
    directories = ["config/schema", "data/learner", "data/learner/history", "data/master", "inbox", "plans/default", "records/default/reviews", "records/imports", "artifacts", "AI/working", "AI/cache", "AI/reports", "AI/history", "tools", "tests"]
    created = 0
    for directory in directories:
        path = root / directory
        if not path.exists():
            path.mkdir(parents=True)
            created += 1
    return f"created {created} directories; existing files were not overwritten"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["init", "validate", "calendar", "photos", "summary", "import-inbox", "import-url", "import-chat", "domain-status", "domain-change", "ai-reset"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--to", dest="domain_target")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-id")
    parser.add_argument("--url", nargs="+")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if args.command == "init":
        print(init_project(root))
        return 0
    if args.command == "calendar":
        print(calendar(root))
        return 0
    if args.command == "photos":
        print(photo_groups(root))
        return 0
    if args.command == "summary":
        print(summary(root))
        return 0
    if args.command == "import-inbox":
        if args.watch and args.interval < 1:
            print("ERROR: --interval must be at least 1 second")
            return 2
        try:
            while True:
                report, items = ImportPipeline(root).run_local(dry_run=args.dry_run, batch_id=args.batch_id)
                print(f"IMPORT REPORT: {report.relative_to(root).as_posix()}")
                print("IMPORT COUNTS: " + ", ".join(f"{status}={sum(item.status == status for item in items)}" for status in sorted({item.status for item in items})))
                if not args.watch:
                    return 0 if all(item.status in {"IMPORTED", "DUPLICATE", "VERIFIED", "ACCESS_DENIED", "REVIEW_REQUIRED", "UNSUPPORTED"} for item in items) else 1
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("IMPORT WATCH: stopped by user")
            return 0
    if args.command == "import-url":
        if not args.url:
            print("ERROR: --url is required")
            return 2
        report, items = run_url_import(root, args.url, dry_run=args.dry_run, batch_id=args.batch_id)
        print(f"IMPORT REPORT: {report.relative_to(root).as_posix()}")
        print("IMPORT COUNTS: " + ", ".join(f"{status}={sum(item.status == status for item in items)}" for status in sorted({item.status for item in items})))
        return 0
    if args.command == "import-chat":
        if not args.url:
            print("ERROR: --url is used for one or more chat export files or shared links")
            return 2
        report, items = run_chat_import(root, args.url, dry_run=args.dry_run, batch_id=args.batch_id)
        print(f"IMPORT REPORT: {report.relative_to(root).as_posix()}")
        print("IMPORT COUNTS: " + ", ".join(f"{status}={sum(item.status == status for item in items)}" for status in sorted({item.status for item in items})))
        return 0
    if args.command == "domain-status":
        print(domain_status(root))
        return 0
    if args.command == "domain-change":
        if not args.domain_target:
            print("ERROR: --to is required")
            return 2
        output = change_domain(root, args.domain_target, args.confirm, args.force)
        print(output)
        return 0 if output.startswith(("CLASSIFICATION:", "DRY-RUN:", "APPLIED:", "WARNING:")) else 1
    if args.command == "ai-reset":
        print(ai_reset(root, args.apply))
        return 0
    errors, warnings, counts = validate(root)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    print(f"VALIDATION: {'PASS' if not errors else 'FAIL'}")
    print("COUNTS: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
