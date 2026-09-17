# Study Management CLI

The v1.1.0 foundation uses the Python standard library only.

Run commands from the repository root:

```text
python tools/study_cli.py validate
python tools/study_cli.py calendar
python tools/study_cli.py photos
python tools/study_cli.py summary
python tools/study_cli.py init
python tools/study_cli.py domain-status
python tools/study_cli.py domain-change --to tekken-8
python tools/study_cli.py ai-reset
python tools/validate_domain_pack.py examples/domain_packs/second_class_electrician/config.yaml
```

Use `--root PATH` to inspect another local project directory. `validate`,
`calendar`, `photos`, and `summary` are read-only. `init` creates missing
directories only and never overwrites existing files.

`domain-status` is read-only. `domain-change` is a dry-run unless `--confirm`
is supplied; use `--force --confirm` only after reviewing the warning for an
incompatible domain. `ai-reset` is a dry-run unless `--apply` is supplied and
targets only disposable AI working directories.

The CLI discovers every project directory under `plans/<project-id>/` and
`records/<project-id>/`; `default` is only the included sample project name,
not a hard-coded data-model limitation.

YAML configuration files shipped with the foundation use the JSON-compatible
YAML subset so no external package is required.

Template upgrades use a read-only dry run by default:

```text
python tools/template_upgrade.py --previous P --current C --new N --manifest config/template-manifest.json
```

Add `--apply` only when safe AUTO template-owned changes are intentionally
approved. The tool never deletes files or performs Git operations.
