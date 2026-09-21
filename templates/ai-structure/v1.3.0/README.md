# AI Working Area

This directory is not a user-data directory.

User-owned records must be stored only under `data/`, `plans/`, `records/`, and `artifacts/`. Do not store learner profiles, study sessions, assessments, reviews, schedules, photos, meal records, health records, consent records, upgrade evidence, or other personal content under `AI/`.

The versioned AI structure contains only disposable working directories:

- `working/` — temporary agent work
- `cache/` — rebuildable cache
- `reports/` — temporary generated reports

AI Reset is an advanced and potentially destructive operation. It deletes all
children of `AI/` and restores the versioned README and disposable directory
structure. Review the dry-run output before using `--apply`. It never removes
`data/`, `plans/`, `records/`, or `artifacts/`, and it does not erase
ChatGPT or another AI provider's conversation history.
