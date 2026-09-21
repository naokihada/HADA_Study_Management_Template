"""Deterministic repository file inventories for safe framework operations."""

from __future__ import annotations

from pathlib import Path


GENERATED_DIRECTORY_NAMES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".venv",
    "venv",
    "env",
}
GENERATED_SUFFIXES = {".pyc", ".pyo"}


def is_generated(relative: Path) -> bool:
    """Return whether a path is a disposable build or interpreter artifact."""

    return bool(
        set(relative.parts) & GENERATED_DIRECTORY_NAMES
        or relative.suffix.lower() in GENERATED_SUFFIXES
    )


def repository_files(root: Path, *, include_generated: bool = False) -> list[Path]:
    """Return deterministic files while preserving declared user data.

    This intentionally does not treat every ``.gitignore`` entry as disposable:
    projects may keep user-owned data in ignored directories such as ``AI`` or
    ``tmp``. Only known interpreter/build artifacts are excluded by default.
    """

    root = root.resolve()
    result: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if ".git" in relative.parts:
            continue
        if not include_generated and is_generated(relative):
            continue
        result.append(path)
    return sorted(result)


def relative_files(root: Path, *, include_generated: bool = False) -> list[str]:
    """Return repository-relative POSIX paths."""

    return [
        path.relative_to(root.resolve()).as_posix()
        for path in repository_files(root, include_generated=include_generated)
    ]


