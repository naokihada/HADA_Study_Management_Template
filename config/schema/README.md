# Data contracts

The v1.0.0 CLI uses the CSV headers and required fields documented in
`tools/study_cli.py`. `config/template.yaml` is JSON-compatible YAML so the
template works with the Python standard library without a mandatory external
YAML dependency. It may be replaced by a full YAML parser in a future version.

All dates use `YYYY-MM-DD`. Date-times use ISO 8601 with an offset when a time
is present. The configured timezone defaults to `Asia/Tokyo`.
