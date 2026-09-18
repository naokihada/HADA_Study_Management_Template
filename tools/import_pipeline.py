"""Safe, file-based external import pipeline for the study template."""

from __future__ import annotations

import hashlib
import html
import json
import mimetypes
import re
import shutil
import subprocess
import unicodedata
import urllib.parse
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

DATE_RE = re.compile(r"^(?P<date>\d{8})(?:_|-|\s|$)")
DATE_ANY_RE = re.compile(r"(?<!\d)(?P<date>20\d{2}[-/]?\d{2}[-/]?\d{2})(?!\d)")
SAFE_SLUG_RE = re.compile(r"[^a-zA-Z0-9_-]+")
STATUS_IMPORTED = "IMPORTED"
STATUS_DUPLICATE = "DUPLICATE"
STATUS_REVIEW = "REVIEW_REQUIRED"
STATUS_DATE_UNKNOWN = "DATE_UNKNOWN"
SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".pdf", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


@dataclass
class ImportItem:
    source: Path
    relative_source: str
    size_bytes: int
    sha256: str
    detected_date: str | None
    date_basis: str
    mime_type: str
    status: str = "DISCOVERED"
    destination: str = ""
    original_name: str = ""
    renamed_from: str = ""
    error: str = ""
    analysis_path: str = ""
    extraction_status: str = "NOT_RUN"
    extraction_error: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.relative_source,
            "original_name": self.original_name,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "detected_date": self.detected_date,
            "date_basis": self.date_basis,
            "mime_type": self.mime_type,
            "status": self.status,
            "destination": self.destination,
            "renamed_from": self.renamed_from,
            "analysis_path": self.analysis_path,
            "extraction_status": self.extraction_status,
            "extraction_error": self.extraction_error,
            "error": self.error,
        }


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def valid_date(value: str) -> str | None:
    try:
        return datetime.strptime(value, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def detect_date(name: str, content: bytes | None = None) -> tuple[str | None, str]:
    match = DATE_RE.match(name)
    if match:
        value = valid_date(match.group("date"))
        if value:
            return value, "filename"
    if content is not None and len(content) <= 2_000_000:
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception:
            text = ""
        match = DATE_ANY_RE.search(text)
        if match:
            value = match.group("date").replace("/", "").replace("-", "")
            parsed = valid_date(value)
            if parsed:
                return parsed, "content"
    return None, "DATE_UNKNOWN"


def ascii_slug(name: str) -> str:
    stem = Path(name).stem
    normalized = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    slug = SAFE_SLUG_RE.sub("_", normalized).strip("_-").lower()
    return slug or "imported-file"


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def format_date(value: str | None) -> str:
    return value.replace("-", "") if value else "unknown"


def extension_for(path: Path, mime_type: str = "") -> str:
    if path.suffix:
        return path.suffix.lower()
    guessed = mimetypes.guess_extension(mime_type.split(";")[0].strip()) if mime_type else None
    return guessed or ".bin"


class ImportPipeline:
    """Phase 1 local importer; later phases reuse its safe storage/reporting rules."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.inbox = self.root / "inbox"
        self.artifacts = self.root / "artifacts"
        self.records = self.root / "records" / "imports"

    def batch_dir(self, batch_id: str) -> Path:
        return self.records / batch_id

    def discover(self) -> list[Path]:
        if not self.inbox.exists():
            return []
        found: list[Path] = []
        for path in sorted(self.inbox.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            if not is_within(path, self.inbox):
                continue
            if any(part in {".git", "AI", "__pycache__"} for part in path.relative_to(self.inbox).parts):
                continue
            found.append(path)
        return found

    def existing_hashes(self) -> dict[str, Path]:
        result: dict[str, Path] = {}
        if not self.artifacts.exists():
            return result
        for path in self.artifacts.rglob("*"):
            if path.is_file() and not path.is_symlink():
                try:
                    result.setdefault(sha256_file(path), path)
                except OSError:
                    continue
        return result

    def available_name(self, directory: Path, base_name: str, digest: str) -> tuple[Path, str]:
        candidate = directory / base_name
        if not candidate.exists():
            return candidate, ""
        if candidate.is_file():
            try:
                if sha256_file(candidate) == digest:
                    return candidate, "DUPLICATE"
            except OSError:
                pass
        suffix = candidate.suffix
        stem = candidate.stem
        index = 0
        while True:
            candidate = directory / f"{stem}_{index:03d}{suffix}"
            if not candidate.exists():
                return candidate, f"{stem}{suffix}"
            index += 1
            if index > 999_999:
                raise RuntimeError("unable to resolve destination filename collision")

    def inventory(self, paths: Iterable[Path]) -> list[ImportItem]:
        items: list[ImportItem] = []
        for path in paths:
            try:
                data = path.read_bytes()
                stat = path.stat()
                detected, basis = detect_date(path.name, data if path.suffix.lower() in {".txt", ".md", ".csv", ".json", ".yaml", ".yml"} else None)
                items.append(ImportItem(
                    source=path,
                    relative_source=path.relative_to(self.root).as_posix(),
                    size_bytes=stat.st_size,
                    sha256=hashlib.sha256(data).hexdigest(),
                    detected_date=detected,
                    date_basis=basis,
                    mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                    original_name=path.name,
                    status="FINGERPRINTED",
                ))
            except (OSError, UnicodeError) as exc:
                items.append(ImportItem(path, path.relative_to(self.root).as_posix(), 0, "", None, "DATE_UNKNOWN", "", status="ACCESS_DENIED", original_name=path.name, error=str(exc)))
        return items

    def destination_for(self, item: ImportItem) -> Path:
        year = item.detected_date[:4] if item.detected_date else "unknown"
        directory = self.artifacts / year
        directory.mkdir(parents=True, exist_ok=True)
        date_part = format_date(item.detected_date)
        slug = ascii_slug(item.original_name)
        extension = extension_for(Path(item.original_name), item.mime_type)
        return directory / f"{date_part}_{slug}_{item.sha256[:8]}{extension}"

    def extract_markdown(self, item: ImportItem, readable_path: Path, batch: Path) -> None:
        """Create a transparent extraction artifact without promoting it to a study record."""
        extension = readable_path.suffix.lower()
        facts: list[str] = []
        inferences: list[str] = []
        extracted_text = ""
        try:
            if extension in {".txt", ".md", ".csv", ".json", ".yaml", ".yml"}:
                extracted_text = readable_path.read_text(encoding="utf-8", errors="replace")
                facts.append(f"Text extracted as UTF-8 with replacement for undecodable bytes: {len(extracted_text)} characters.")
            elif extension == ".pdf":
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(str(readable_path))
                    pages: list[str] = []
                    for page in reader.pages:
                        pages.append(page.extract_text() or "")
                    extracted_text = "\n\n".join(pages)
                    facts.append(f"PDF pages: {len(reader.pages)}.")
                    facts.append(f"Extracted text characters: {len(extracted_text)}.")
                except ImportError:
                    item.extraction_status = "EXTRACTION_FAILED"
                    item.extraction_error = "pypdf is not available"
            elif extension in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
                try:
                    from PIL import Image
                    with Image.open(readable_path) as image:
                        facts.append(f"Image format: {image.format or extension.lstrip('.')}.")
                        facts.append(f"Image size: {image.width} x {image.height} pixels.")
                        facts.append(f"Color mode: {image.mode}.")
                except ImportError:
                    item.extraction_status = "EXTRACTION_FAILED"
                    item.extraction_error = "Pillow is not available"
                except OSError as exc:
                    item.extraction_status = "EXTRACTION_FAILED"
                    item.extraction_error = f"image read failed: {exc}"
                tesseract = shutil.which("tesseract")
                if tesseract:
                    try:
                        result = subprocess.run([tesseract, str(readable_path), "stdout"], capture_output=True, text=True, timeout=60, check=False)
                        if result.returncode == 0 and result.stdout.strip():
                            extracted_text = result.stdout.strip()
                            facts.append(f"OCR text characters: {len(extracted_text)}.")
                        else:
                            item.extraction_error = item.extraction_error or "OCR returned no text"
                    except (OSError, subprocess.SubprocessError) as exc:
                        item.extraction_error = f"OCR failed: {exc}"
                else:
                    item.extraction_error = item.extraction_error or "OCR engine is not installed"
            else:
                item.extraction_status = "UNSUPPORTED"
                item.extraction_error = f"unsupported extension: {extension or '<none>'}"
            if extracted_text:
                facts.append("Extracted content is preserved below; it is not an assertion that the source is correct.")
            if extension in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
                inferences.append("Semantic image interpretation was not performed by the deterministic importer.")
            if item.detected_date and item.date_basis != "filename":
                inferences.append(f"The date {item.detected_date} was inferred from {item.date_basis}; user confirmation may be appropriate.")
            if item.extraction_status == "NOT_RUN":
                item.extraction_status = "EXTRACTED"
        except (OSError, UnicodeError) as exc:
            item.extraction_status = "EXTRACTION_FAILED"
            item.extraction_error = str(exc)
        analysis_name = f"{ascii_slug(item.original_name)}_{item.sha256[:8]}.md"
        analysis = batch / "analysis" / analysis_name
        analysis.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# Extraction — {item.original_name}", "", "## Facts", ""]
        lines.extend(f"- {fact}" for fact in facts)
        lines.extend(["", "## Inferences and limitations", ""])
        lines.extend(f"- {inference}" for inference in inferences)
        if item.extraction_error:
            lines.append(f"- Extraction issue: {item.extraction_error}")
        if extracted_text:
            lines.extend(["", "## Extracted text", "", "```text", extracted_text, "```"])
        analysis.write_text("\n".join(lines) + "\n", encoding="utf-8")
        item.analysis_path = analysis.relative_to(self.root).as_posix()

    def _write_reports(self, batch_id: str, items: list[ImportItem], dry_run: bool) -> Path:
        batch = self.batch_dir(batch_id)
        batch.mkdir(parents=True, exist_ok=True)
        manifest = {
            "batch_id": batch_id,
            "mode": "local-inbox",
            "root": "inbox",
            "dry_run": dry_run,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "items": [item.as_dict() for item in items],
            "summary": {status: sum(item.status == status for item in items) for status in sorted({item.status for item in items})},
        }
        (batch / "import-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lines = [f"# Import Report — {batch_id}", "", f"- Mode: local-inbox", f"- Dry run: {str(dry_run).lower()}", "", "| Source | Status | Destination | Date | Error |", "|---|---|---|---|---|"]
        for item in items:
            lines.append(f"| `{item.relative_source}` | `{item.status}` | `{item.destination}` | `{item.detected_date or 'DATE_UNKNOWN'}` | {item.error.replace('|', '/') if item.error else ''} |")
        (batch / "import-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return batch

    def run_local(self, dry_run: bool = False, batch_id: str | None = None) -> tuple[Path, list[ImportItem]]:
        batch_id = batch_id or datetime.now().strftime("%Y%m%d-%H%M%S")
        paths = self.discover()
        items = self.inventory(paths)
        hashes = self.existing_hashes()
        seen_batch: set[str] = set()
        for item in items:
            if item.status == "ACCESS_DENIED":
                continue
            if Path(item.original_name).suffix.lower() not in SUPPORTED_EXTENSIONS:
                item.status = "UNSUPPORTED"
                item.error = "unsupported file type"
                continue
            item.status = "ANALYZED"
            if item.sha256 in hashes or item.sha256 in seen_batch:
                item.status = STATUS_DUPLICATE
                continue
            seen_batch.add(item.sha256)
            try:
                destination = self.destination_for(item)
                chosen, collision = self.available_name(destination.parent, destination.name, item.sha256)
                if collision == "DUPLICATE":
                    item.status = STATUS_DUPLICATE
                    item.destination = chosen.relative_to(self.root).as_posix()
                    continue
                item.destination = chosen.relative_to(self.root).as_posix()
                if collision:
                    item.renamed_from = collision
                if dry_run:
                    item.status = "VERIFIED"
                    self.extract_markdown(item, item.source, self.batch_dir(batch_id))
                    continue
                if not is_within(chosen, self.artifacts):
                    raise RuntimeError("destination escaped artifacts root")
                shutil.copy2(item.source, chosen)
                if sha256_file(chosen) != item.sha256 or chosen.stat().st_size != item.size_bytes:
                    chosen.unlink(missing_ok=True)
                    raise RuntimeError("destination verification failed")
                item.status = STATUS_IMPORTED
                item.source.unlink()
                hashes[item.sha256] = chosen
                self.extract_markdown(item, chosen, self.batch_dir(batch_id))
            except (OSError, RuntimeError) as exc:
                item.status = STATUS_REVIEW
                item.error = str(exc)
        return self._write_reports(batch_id, items, dry_run), items


def html_to_text(value: str) -> str:
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def canonical_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    path = parsed.path or "/"
    return urllib.parse.urlunsplit((scheme, host, path, parsed.query, ""))


def html_metadata(value: str, base_url: str) -> tuple[str, str | None, str]:
    canonical = ""
    canonical_match = re.search(r"(?is)<link[^>]+rel=[\"']canonical[\"'][^>]+href=[\"']([^\"']+)", value)
    if canonical_match:
        canonical = canonical_url(urllib.parse.urljoin(base_url, html.unescape(canonical_match.group(1))))
    date_value: str | None = None
    date_basis = "DATE_UNKNOWN"
    patterns = [
        (r"(?is)<time[^>]+datetime=[\"']([^\"']+)", "published_at"),
        (r"(?is)<meta[^>]+(?:property|name)=[\"'](?:article:published_time|datePublished|pubdate)[\"'][^>]+content=[\"']([^\"']+)", "published_at"),
    ]
    for pattern, basis in patterns:
        match = re.search(pattern, value)
        if match:
            candidate = match.group(1)[:10].replace("/", "-")
            try:
                date_value = datetime.strptime(candidate, "%Y-%m-%d").strftime("%Y-%m-%d")
                date_basis = basis
                break
            except ValueError:
                continue
    return canonical, date_value, date_basis


class UrlImportError(RuntimeError):
    pass


def fetch_url(url: str, timeout: int = 30) -> tuple[bytes, str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "HADA-Study-Management-Template/1.2"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(), response.headers.get_content_type(), response.geturl()


def run_url_import(root: Path, urls: list[str], dry_run: bool = False, batch_id: str | None = None) -> tuple[Path, list[ImportItem]]:
    pipeline = ImportPipeline(root)
    batch_id = batch_id or datetime.now().strftime("%Y%m%d-%H%M%S-url")
    batch = pipeline.batch_dir(batch_id)
    batch.mkdir(parents=True, exist_ok=True)
    items: list[ImportItem] = []
    existing = pipeline.existing_hashes()
    for original_url in urls:
        url = canonical_url(original_url)
        try:
            payload, mime_type, final_url = fetch_url(url)
            digest = hashlib.sha256(payload).hexdigest()
            parsed = urllib.parse.urlsplit(final_url)
            name = Path(parsed.path).name or "index"
            extension = extension_for(Path(name), mime_type)
            detected_date: str | None = None
            date_basis = "DATE_UNKNOWN"
            canonical = url
            if mime_type == "text/html":
                text = payload.decode("utf-8", errors="replace")
                canonical, detected_date, date_basis = html_metadata(text, final_url)
                if not canonical:
                    canonical = canonical_url(final_url)
                title = re.search(r"(?is)<title[^>]*>(.*?)</title>", text)
                report_name = f"url_{digest[:8]}.md"
                report_path = batch / "sources" / report_name
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(
                    f"# URL Import\n\n- Source URL: {url}\n- Final URL: {canonical_url(final_url)}\n- Canonical URL: {canonical}\n- Retrieved at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n- Title: {html_to_text(title.group(1)) if title else ''}\n- Published date: {detected_date or 'DATE_UNKNOWN'}\n- Deletion capability: DELETE_UNKNOWN\n\n## Extracted text\n\n{html_to_text(text)}\n",
                    encoding="utf-8",
                )
                item = ImportItem(Path(url), url, len(payload), digest, detected_date, date_basis, mime_type, original_name=name + ".html", analysis_path=report_path.relative_to(root).as_posix(), extraction_status="EXTRACTED")
            else:
                item = ImportItem(Path(url), url, len(payload), digest, None, "DATE_UNKNOWN", mime_type, original_name=name or "download", extraction_status="NOT_RUN")
                item.detected_date, item.date_basis = detect_date(item.original_name)
                if digest in existing:
                    item.status = STATUS_DUPLICATE
                    item.destination = existing[digest].relative_to(root).as_posix()
                    items.append(item)
                    continue
                year = item.detected_date[:4] if item.detected_date else "unknown"
                destination_dir = pipeline.artifacts / year
                destination_dir.mkdir(parents=True, exist_ok=True)
                base = f"{format_date(item.detected_date)}_{ascii_slug(item.original_name)}_{digest[:8]}{extension}"
                destination, collision = pipeline.available_name(destination_dir, base, digest)
                item.destination = destination.relative_to(root).as_posix()
                if collision:
                    item.renamed_from = collision
                if not dry_run:
                    destination.write_bytes(payload)
                    if sha256_file(destination) != digest:
                        destination.unlink(missing_ok=True)
                        raise UrlImportError("download verification failed")
                    existing[digest] = destination
                    item.status = STATUS_IMPORTED
                    pipeline.extract_markdown(item, destination, batch)
                else:
                    item.status = "VERIFIED"
            if item.status == "DISCOVERED":
                item.status = "VERIFIED" if dry_run else STATUS_IMPORTED
            item.error = f"source_url={url}; canonical_url={canonical}; deletion_capability=DELETE_UNKNOWN"
            items.append(item)
        except Exception as exc:
            items.append(ImportItem(Path(url), url, 0, "", None, "DATE_UNKNOWN", "", status="ACCESS_DENIED", original_name=Path(urllib.parse.urlsplit(url).path).name or "url", error=f"URL retrieval failed: {exc}"))
    report = pipeline._write_reports(batch_id, items, dry_run)
    return report, items


def message_date(value: object) -> str | None:
    if value is None:
        return None
    try:
        try:
            local_zone = ZoneInfo("Asia/Tokyo")
        except Exception:
            local_zone = timezone.utc
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), timezone.utc).astimezone(local_zone).strftime("%Y-%m-%d")
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=local_zone)
        return parsed.astimezone(local_zone).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return None


def flatten_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(flatten_content(item) for item in content)
    if isinstance(content, dict):
        for key in ("parts", "text", "content"):
            if key in content:
                return flatten_content(content[key])
    return ""


def parse_chat_export(payload: bytes, source_name: str) -> list[dict[str, object]]:
    try:
        value = json.loads(payload.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        text = payload.decode("utf-8", errors="replace")
        return [{"date": None, "role": "unknown", "text": text, "attachments": []}]
    raw_messages: list[object] = []
    if isinstance(value, dict) and isinstance(value.get("mapping"), dict):
        raw_messages = list(value["mapping"].values())
    elif isinstance(value, dict) and isinstance(value.get("messages"), list):
        raw_messages = value["messages"]
    elif isinstance(value, list):
        raw_messages = value
    messages: list[dict[str, object]] = []
    for raw in raw_messages:
        if not isinstance(raw, dict):
            continue
        message = raw.get("message", raw)
        if not isinstance(message, dict):
            continue
        author = message.get("author", {})
        role = author.get("role", "unknown") if isinstance(author, dict) else "unknown"
        content = message.get("content", message.get("text", ""))
        attachments = message.get("attachments", message.get("metadata", {}).get("attachments", []) if isinstance(message.get("metadata"), dict) else [])
        messages.append({"date": message_date(message.get("create_time", message.get("timestamp", raw.get("create_time")))), "role": role, "text": flatten_content(content), "attachments": attachments if isinstance(attachments, list) else [attachments]})
    if not messages:
        messages.append({"date": None, "role": "unknown", "text": source_name, "attachments": []})
    return messages


def run_chat_import(root: Path, sources: list[str], dry_run: bool = False, batch_id: str | None = None) -> tuple[Path, list[ImportItem]]:
    pipeline = ImportPipeline(root)
    batch_id = batch_id or datetime.now().strftime("%Y%m%d-%H%M%S-chat")
    batch = pipeline.batch_dir(batch_id)
    batch.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[dict[str, object]]] = {}
    source_items: list[ImportItem] = []
    for source in sources:
        source_url = source.startswith(("http://", "https://"))
        try:
            payload, mime_type, final_url = fetch_url(source) if source_url else (Path(source).read_bytes(), mimetypes.guess_type(source)[0] or "application/json", source)
            messages = parse_chat_export(payload, Path(source).name or "shared-link")
            for message in messages:
                grouped.setdefault(str(message.get("date") or "DATE_UNKNOWN"), []).append(message)
            digest = hashlib.sha256(payload).hexdigest()
            item = ImportItem(Path(source), source, len(payload), digest, None, "DATE_UNKNOWN", mime_type, status="ANALYZED", original_name=Path(urllib.parse.urlsplit(source).path).name or "chat-export")
            item.error = f"source={source}; final_url={final_url}; deletion_capability={'DELETE_UNKNOWN' if source_url else 'USER_ACTION_REQUIRED'}"
            item.extraction_status = "EXTRACTED"
            source_items.append(item)
        except (OSError, urllib.error.URLError, ValueError) as exc:
            source_items.append(ImportItem(Path(source), source, 0, "", None, "DATE_UNKNOWN", "", status="ACCESS_DENIED", original_name=Path(source).name or "chat", error=f"chat import failed: {exc}"))
    items: list[ImportItem] = []
    for date_key, messages in sorted(grouped.items()):
        text_lines = [f"# Chat Import — {date_key}", "", "- Source deletion: USER_ACTION_REQUIRED", "", "## Messages", ""]
        attachment_rows: list[dict[str, object]] = []
        for message in messages:
            text_lines.extend([f"### {message.get('role', 'unknown')}", "", str(message.get("text", "")), ""])
            for attachment in message.get("attachments", []):
                attachment_rows.append({"source": attachment})
        markdown_path = batch / "chat" / f"{date_key}.md"
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        if not dry_run:
            markdown_path.write_text("\n".join(text_lines), encoding="utf-8")
            if attachment_rows:
                markdown_path.with_suffix(".attachments.json").write_text(json.dumps(attachment_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        digest = hashlib.sha256("\n".join(text_lines).encode("utf-8")).hexdigest()
        item = ImportItem(Path(str(markdown_path)), f"chat:{date_key}", len("\n".join(text_lines).encode("utf-8")), digest, None if date_key == "DATE_UNKNOWN" else date_key, "message_timestamp" if date_key != "DATE_UNKNOWN" else "DATE_UNKNOWN", "text/markdown", status="VERIFIED" if dry_run else STATUS_IMPORTED, destination=markdown_path.relative_to(root).as_posix(), original_name=markdown_path.name, analysis_path=markdown_path.relative_to(root).as_posix(), extraction_status="EXTRACTED")
        item.error = "deletion_capability=USER_ACTION_REQUIRED"
        items.append(item)
    for source_item in source_items:
        if source_item.status != "ACCESS_DENIED":
            source_item.status = "VERIFIED" if dry_run else STATUS_IMPORTED
        items.append(source_item)
    report = pipeline._write_reports(batch_id, items, dry_run)
    return report, items
