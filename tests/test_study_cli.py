import hashlib
import json
import tempfile
import urllib.parse
import unittest
from pathlib import Path

from tools import study_cli
from tools import template_upgrade
from tools import validate_domain_pack
from tools.import_pipeline import ImportPipeline, run_chat_import, run_url_import


class StudyCliTests(unittest.TestCase):
    def test_sample_validates(self):
        root = Path(__file__).resolve().parents[1]
        errors, warnings, counts = study_cli.validate(root)
        self.assertEqual(errors, [], "\n".join(errors))
        self.assertGreaterEqual(counts["photos"], 0)

    def test_calendar_is_date_ordered(self):
        root = Path(__file__).resolve().parents[1]
        output = study_cli.calendar(root)
        if (root / "records" / "default" / "events.csv").exists():
            self.assertIn("第二種電気工事士 筆記試験", output)
            self.assertLess(output.index("筆記試験"), output.index("技能試験"))
        else:
            self.assertEqual(output, "(events: none)")

    def test_photos_are_independent_date_groups(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config" / "template.yaml").write_text('{"photo_root":"artifacts","allowed_photo_extensions":[".jpg"]}', encoding="utf-8")
            (root / "artifacts" / "2026").mkdir(parents=True)
            (root / "artifacts" / "2026" / "20260911_test01.jpg").write_bytes(b"fake")
            output = study_cli.photo_groups(root)
            self.assertIn("2026-09-11", output)
            self.assertIn("20260911_test01.jpg", output)

    def test_multiple_projects_are_discovered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config" / "template.yaml").write_text('{"allowed_photo_extensions":[]}', encoding="utf-8")
            for project, title in (("alpha", "Alpha event"), ("beta", "Beta event")):
                path = root / "records" / project
                path.mkdir(parents=True)
                (path / "events.csv").write_text(
                    "event_id,event_type,title,start_at,all_day,timezone,importance,status\n"
                    f"event-{project},OTHER,{title},2026-01-01T09:00:00+09:00,false,Asia/Tokyo,LOW,PLANNED\n",
                    encoding="utf-8",
                )
            output = study_cli.calendar(root)
            self.assertIn("Alpha event", output)
            self.assertIn("Beta event", output)

    def test_calendar_normalizes_timezone_for_ordering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "records" / "one"
            path.mkdir(parents=True)
            (root / "config").mkdir()
            (root / "config" / "template.yaml").write_text('{"timezone":"Asia/Tokyo"}', encoding="utf-8")
            (path / "events.csv").write_text(
                "event_id,event_type,title,start_at,end_at,all_day,timezone,importance,status\n"
                "late,OTHER,Local late,2026-01-01T09:00:00+09:00,,false,Asia/Tokyo,LOW,PLANNED\n"
                "early,OTHER,UTC earlier,2026-01-01T00:30:00+00:00,,false,UTC,LOW,PLANNED\n",
                encoding="utf-8",
            )
            output = study_cli.calendar(root)
            self.assertLess(output.index("Local late"), output.index("UTC earlier"))

    def test_upgrade_planner_preserves_user_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous, current, new = (root / name for name in ("previous", "current", "new"))
            for path in (previous, current, new):
                path.mkdir()
            (previous / "data.csv").write_text("old", encoding="utf-8")
            (current / "data.csv").write_text("user", encoding="utf-8")
            (new / "data.csv").write_text("new", encoding="utf-8")
            manifest = {"ownership": {"template_owned": ["tools/**"], "user_owned": ["data.csv"]}}
            output = template_upgrade.plan(previous, current, new, manifest)
            self.assertIn("REVIEW_REQUIRED\tdata.csv\tUSER_OWNED", output)

    def test_upgrade_apply_only_copies_safe_template_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous, current, new = (root / name for name in ("previous", "current", "new"))
            for path in (previous, current, new):
                path.mkdir()
            (previous / "tools").mkdir()
            (current / "tools").mkdir()
            (new / "tools").mkdir()
            (previous / "tools" / "check.py").write_text("old", encoding="utf-8")
            (current / "tools" / "check.py").write_text("old", encoding="utf-8")
            (new / "tools" / "check.py").write_text("new", encoding="utf-8")
            manifest = {"ownership": {"template_owned": ["tools/**"]}}
            applied = template_upgrade.apply_safe(previous, current, new, manifest)
            self.assertEqual(applied, ["tools/check.py"])
            self.assertEqual((current / "tools" / "check.py").read_text(encoding="utf-8"), "new")

    def test_v1_upgrade_manifest_is_stable_and_three_way(self):
        root = Path(__file__).resolve().parents[1]
        manifest = study_cli.load_json_file(root / "config" / "template-manifest.json")
        self.assertEqual(manifest["template_version"], "1.2.0")
        self.assertEqual(manifest["schema_version"], "1.0.0")
        self.assertEqual(manifest["data_format_version"], "1.0.0")
        self.assertEqual(manifest["upgrade_contract"]["user_data_policy"], "preserve")
        self.assertEqual(manifest["upgrade_contract"]["comparison"], ["previous_template", "current_project", "new_template"])
        self.assertFalse(manifest["upgrade_contract"]["automatic_deletion"])
        self.assertEqual(template_upgrade.validate_manifest(manifest), [])

    def test_domain_pack_schema(self):
        root = Path(__file__).resolve().parents[1]
        pack_paths = sorted((root / "examples/domain_packs").glob("*/config.yaml"))
        self.assertGreaterEqual(len(pack_paths), 10)
        for pack_path in pack_paths:
            self.assertEqual(validate_domain_pack.validate(pack_path), [], str(pack_path))

    def test_domain_change_requires_confirmation_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config" / "project-state.yaml").write_text(
                '{"initialization_status":"initialized","domain_lock_status":"locked","domain_family":"competitive-gaming","domain_variant":"soulcalibur-6","domain_history":[]}',
                encoding="utf-8",
            )
            (root / "config" / "domain-compatibility.yaml").write_text(
                '{"families":{"competitive-gaming":["soulcalibur-6","tekken-8"],"activity":["swimming"]},"related_upgrades":{"soulcalibur-6":["tekken-8"]}}',
                encoding="utf-8",
            )
            self.assertIn("DRY-RUN", study_cli.change_domain(root, "tekken-8", False, False))
            self.assertEqual(study_cli.load_project_state(root)["domain_variant"], "soulcalibur-6")
            self.assertIn("WARNING", study_cli.change_domain(root, "swimming", False, False))
            result = study_cli.change_domain(root, "swimming", True, True)
            self.assertIn("APPLIED", result)
            state = study_cli.load_project_state(root)
            self.assertEqual(state["domain_variant"], "swimming")
            self.assertEqual(state["domain_history"][-1]["change_type"], "forced")

    def test_ai_reset_dry_run_and_apply_do_not_touch_user_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AI" / "working").mkdir(parents=True)
            (root / "AI" / "cache").mkdir(parents=True)
            (root / "AI" / "reports").mkdir(parents=True)
            (root / "data").mkdir()
            (root / "data" / "user.txt").write_text("keep", encoding="utf-8")
            self.assertIn("DRY-RUN", study_cli.ai_reset(root, False))
            self.assertTrue((root / "AI" / "working").exists())
            self.assertIn("APPLIED", study_cli.ai_reset(root, True))
            self.assertFalse((root / "AI" / "working").exists())
            self.assertEqual((root / "data" / "user.txt").read_text(encoding="utf-8"), "keep")

    def test_ai_boundary_rejects_user_data_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AI" / "data").mkdir(parents=True)
            errors, warnings, counts = study_cli.validate(root)
            self.assertTrue(any("AI boundary violation" in error for error in errors))

    def test_core_stage_metric_and_visibility_contracts(self):
        root = Path(__file__).resolve().parents[1]
        errors, warnings, counts = study_cli.validate(root)
        self.assertEqual(errors, [], "\n".join(errors))
        if (root / "data" / "master" / "stages.csv").exists():
            self.assertGreaterEqual(counts["stages"], 2)
        if (root / "data" / "master" / "metrics.csv").exists():
            self.assertGreaterEqual(counts["metrics"], 2)
        if (root / "records" / "default" / "metric_observations.csv").exists():
            self.assertGreaterEqual(counts["metric_observations"], 2)

    def test_invalid_visibility_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config" / "template.yaml").write_text('{"default_visibility":"private","visibility_values":["private","summary","public"]}', encoding="utf-8")
            (root / "data" / "master").mkdir(parents=True)
            (root / "data" / "master" / "goals.csv").write_text(
                "goal_id,title,goal_type,status,priority,start_date,target_date,visibility\n"
                "goal-1,Test,study,PLANNED,LOW,2026-01-01,2026-12-31,secret\n", encoding="utf-8")
            errors, warnings, counts = study_cli.validate(root)
            self.assertTrue(any("visibility must be private" in error for error in errors))

    def test_local_import_recurses_moves_and_writes_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "inbox" / "nested" / "20260917_notes.txt"
            source.parent.mkdir(parents=True)
            source.write_text("study notes", encoding="utf-8")
            report, items = ImportPipeline(root).run_local()
            self.assertEqual(items[0].status, "IMPORTED")
            self.assertFalse(source.exists())
            self.assertTrue(report.joinpath("import-report.md").exists())
            self.assertTrue(report.joinpath("import-manifest.json").exists())
            self.assertTrue(list((root / "artifacts" / "2026").glob("*.txt")))

    def test_local_import_keeps_hash_duplicates_and_renames_name_collisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inbox = root / "inbox"
            inbox.mkdir(parents=True)
            first = inbox / "20260917_notes.txt"
            first.write_text("one", encoding="utf-8")
            ImportPipeline(root).run_local(batch_id="first")
            duplicate = inbox / "20260917_other.txt"
            duplicate.write_text("one", encoding="utf-8")
            duplicate_report, duplicate_items = ImportPipeline(root).run_local(batch_id="duplicate")
            self.assertEqual(duplicate_items[0].status, "DUPLICATE")
            self.assertTrue(duplicate.exists())
            collision = inbox / "20260917_notes.txt"
            collision.write_text("two", encoding="utf-8")
            digest = hashlib.sha256(b"two").hexdigest()[:8]
            existing = root / "artifacts" / "2026" / f"20260917_20260917_notes_{digest}.txt"
            existing.parent.mkdir(parents=True, exist_ok=True)
            existing.write_text("different existing content", encoding="utf-8")
            report, items = ImportPipeline(root).run_local(batch_id="collision")
            self.assertEqual(items[0].status, "IMPORTED")
            self.assertIn("_000", items[0].destination)
            self.assertTrue("_000" in report.joinpath("import-report.md").read_text(encoding="utf-8"))

    def test_local_import_dry_run_does_not_move_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "inbox" / "20260917_dry.txt"
            source.parent.mkdir(parents=True)
            source.write_text("dry", encoding="utf-8")
            _, items = ImportPipeline(root).run_local(dry_run=True, batch_id="dry")
            self.assertEqual(items[0].status, "VERIFIED")
            self.assertTrue(source.exists())

    def test_local_import_separates_extraction_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "inbox" / "20260917_facts.txt"
            source.parent.mkdir(parents=True)
            source.write_text("A fact.\n2026-09-17 is mentioned here.", encoding="utf-8")
            report, items = ImportPipeline(root).run_local(batch_id="extract")
            self.assertEqual(items[0].extraction_status, "EXTRACTED")
            analysis = root / items[0].analysis_path
            self.assertTrue(analysis.exists())
            self.assertIn("## Facts", analysis.read_text(encoding="utf-8"))
            self.assertIn("## Inferences and limitations", analysis.read_text(encoding="utf-8"))

    def test_local_import_reports_unsupported_files_without_moving(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "inbox" / "20260917_archive.zip"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"not imported")
            _, items = ImportPipeline(root).run_local(batch_id="unsupported")
            self.assertEqual(items[0].status, "UNSUPPORTED")
            self.assertTrue(source.exists())

    def test_url_import_extracts_canonical_and_published_date(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.html"
            source.write_text(
                '<html><head><link rel="canonical" href="https://example.test/post" />'
                '<meta property="article:published_time" content="2026-09-17T10:00:00+09:00" />'
                '<title>Example Post</title></head><body>Hello study</body></html>',
                encoding="utf-8",
            )
            report, items = run_url_import(root, [source.as_uri()], batch_id="url")
            self.assertEqual(items[0].status, "IMPORTED")
            self.assertEqual(items[0].detected_date, "2026-09-17")
            source_report = root / items[0].analysis_path
            self.assertTrue(source_report.exists())
            self.assertIn("https://example.test/post", source_report.read_text(encoding="utf-8"))
            self.assertTrue((report / "import-manifest.json").exists())

    def test_chat_import_splits_messages_by_date_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "chat.json"
            source.write_text(
                json.dumps({"messages": [
                    {"timestamp": "2026-09-17T09:00:00+09:00", "author": {"role": "user"}, "content": {"parts": ["Day one"]}},
                    {"timestamp": "2026-09-18T09:00:00+09:00", "author": {"role": "assistant"}, "content": {"parts": ["Day two"]}, "attachments": [{"name": "photo.jpg"}]},
                ]}),
                encoding="utf-8",
            )
            report, items = run_chat_import(root, [str(source)], batch_id="chat")
            self.assertTrue(source.exists())
            self.assertIn("2026-09-17", (root / "records" / "imports" / "chat" / "chat" / "2026-09-17.md").read_text(encoding="utf-8"))
            self.assertIn("2026-09-18", (root / "records" / "imports" / "chat" / "chat" / "2026-09-18.md").read_text(encoding="utf-8"))
            self.assertTrue(any("USER_ACTION_REQUIRED" in item.error for item in items))
            self.assertTrue((report / "import-manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
