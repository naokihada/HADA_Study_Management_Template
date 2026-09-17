# AI Working Area

This directory is not a user-data directory.

User-owned records must be stored only under `data/`, `plans/`, `records/`, and `artifacts/`. Do not store learner profiles, study sessions, assessments, reviews, schedules, photos, meal records, health records, or other personal content under `AI/`.

Allowed disposable areas:

- `working/` — temporary agent work
- `cache/` — rebuildable cache
- `reports/` — temporary generated reports
- `history/` — non-user operational history that must be promoted or removed deliberately
- `handoff/` — disposable request/result evidence; do not store user data

`python tools/study_cli.py ai-reset` removes only `working/`, `cache/`, and `reports/`. It never removes `data/`, `plans/`, `records/`, or `artifacts/`, and it does not erase ChatGPT or another AI provider's conversation history.
