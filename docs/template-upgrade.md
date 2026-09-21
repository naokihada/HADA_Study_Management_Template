# Template Upgrade

The v1.3.0 upgrade process is candidate-first and preserves user data.
It compares three trees:

```text
P = Previous Template
C = Current Project
N = New Template Release
```

Run a dry run before any change:

```text
python tools/template_upgrade.py --previous P --current C --new N --manifest N/config/template-manifest.json --release-version v1.3.0
```

For a project derived from an older Template that is missing current version
carriers, prepare a Candidate without changing the project:

```text
python tools/template_upgrade.py --previous P --current C --new N --manifest N/config/template-manifest.json --release-version v1.3.0 --legacy-bootstrap --candidate-only --candidate PATH_TO_CANDIDATE
```

The process never deletes files, renames undated photos, infers dates, runs AI
Reset, or performs Git operations. It preserves user-owned records, plans,
photos, imports, `tmp/`, and custom dependency files for human review.

The public Template and Sample artifacts are validated separately. Both must
retain `AGENTS.md` and `AI/README.md`. Internal SPEC/ReSPEC documents and AI
working data are excluded. The public Template must not contain user data. The
Sample may contain fictional data only.
