"""Read-only public template safety checks."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path.cwd())
    root = parser.parse_args().root.resolve()
    manifest = json.loads((root / 'config/template-manifest.json').read_text(encoding='utf-8'))
    base = (root / 'TEMPLATE_BASE.md').read_text(encoding='utf-8')
    errors = []
    if f"Template ID: `{manifest.get('template_id')}`" not in base: errors.append('TEMPLATE_BASE template id mismatch')
    if f"Version: `{manifest.get('template_version')}`" not in base: errors.append('TEMPLATE_BASE version mismatch')
    paths = [p for p in root.rglob('*') if p.is_file() and '.git' not in p.relative_to(root).parts and '__pycache__' not in p.relative_to(root).parts and p.suffix not in {'.pyc', '.pyo'}]
    errors.extend(f'lone CR: {p.relative_to(root).as_posix()}' for p in paths if b'\r' in p.read_bytes().replace(b'\r\n', b''))
    errors.extend(f'path over 260: {p.relative_to(root).as_posix()}' for p in paths if len(str(p.resolve())) > 260)
    print('FRAMEWORK_VALIDATION: ' + ('PASS' if not errors else 'FAIL'))
    crlf_files = sum(b'\r\n' in p.read_bytes() for p in paths)
    long_paths = sum(len(str(p.resolve())) > 260 for p in paths)
    print(f'CRLF_FILES: {crlf_files}')
    print(f'PATHS_OVER_260: {long_paths}')
    for error in errors: print('ERROR: ' + error)
    return 0 if not errors else 1

if __name__ == '__main__': raise SystemExit(main())
