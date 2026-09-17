import tempfile
import unittest
from pathlib import Path

from tools import study_cli
from tools import template_upgrade
from tools import validate_domain_pack


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
        self.assertEqual(manifest["template_version"], "1.1.0")
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


if __name__ == "__main__":
    unittest.main()
