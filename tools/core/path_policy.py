"""Repository-safe path, line-ending, and Windows path-length checks."""

from __future__ import annotations

from pathlib import Path


WINDOWS_PATH_LIMIT = 260


def repository_files(root: Path) -> list[Path]:
    """Return files below root while excluding Git metadata."""
    root = root.resolve()
    return sorted(
        path for path in root.rglob("*")
        if path.is_file()
        and ".git" not in path.relative_to(root).parts
        and "__pycache__" not in path.relative_to(root).parts
        and path.suffix not in {".pyc", ".pyo"}
    )


def audit_line_endings(root: Path) -> dict[str, object]:
    crlf: list[str] = []
    lone_cr: list[str] = []
    for path in repository_files(root):
        data = path.read_bytes()
        relative = path.relative_to(root).as_posix()
        if b"\r\n" in data:
            crlf.append(relative)
        if b"\r" in data.replace(b"\r\n", b""):
            lone_cr.append(relative)
    return {"crlf_files": crlf, "lone_cr_files": lone_cr}


def audit_path_lengths(root: Path, limit: int = WINDOWS_PATH_LIMIT) -> dict[str, object]:
    findings = []
    for path in repository_files(root):
        length = len(str(path.resolve()))
        if length > limit:
            findings.append({"path": path.relative_to(root).as_posix(), "length": length})
    return {"limit": limit, "over_limit": findings}


