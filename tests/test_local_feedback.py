"""Local filesystem and concurrent recording tests; never touches live user data."""

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "local_feedback.py"
spec = importlib.util.spec_from_file_location("local_feedback", SCRIPT)
recorder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recorder)
FINISH = {"goal_summary": "帮助新人理解方法", "method_summary": "用独立数例组织解释", "result_summary": "已给设计；学习效果未实测", "outcome": "delivered"}


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "data"

    def enable(self):
        recorder.configure(self.root, True)

    def begin(self, summary="设计论文分享", agent="codex"):
        return recorder.begin(self.root, agent, "prompt", {"task_summary": summary})["id"]

    def test_disabled_is_read_only_and_default_off(self):
        self.assertFalse(recorder.config(self.root)["enabled"])
        self.assertFalse(recorder.begin(self.root, "codex", "prompt", {"task_summary": "a"})["recorded"])
        self.assertEqual(recorder.recent(self.root), [])
        self.assertFalse(self.root.exists())

    def test_use_completion_and_feedback_keep_distinct_provenance(self):
        self.enable()
        identifier = self.begin()
        start = (self.root / "uses" / identifier / "use.json").read_bytes()
        recorder.append_event(self.root, identifier, "completion", FINISH)
        recorder.append_event(self.root, identifier, "feedback", {"text": "内容有价值，但是过长", "interpretation": "可能低估了时间约束，尚未确认"})
        actual = recorder.show(self.root, identifier)
        self.assertEqual([e["kind"] for e in actual["events"]], ["completion", "feedback"])
        self.assertEqual(actual["events"][0]["outcome"], "delivered")
        self.assertEqual(actual["events"][1]["text"], "内容有价值，但是过长")
        self.assertEqual((self.root / "uses" / identifier / "use.json").read_bytes(), start)
        self.assertEqual(len(actual["use"]["skill"]["fingerprint"]), 64)
        self.assertNotIn("satisfied", actual["use"])

    def test_parallel_events_and_independent_uses_are_not_lost(self):
        self.enable()
        with ThreadPoolExecutor(max_workers=8) as executor:
            ids = list(executor.map(lambda n: self.begin(str(n)), range(24)))
        self.assertEqual(len(set(ids)), 24)
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(lambda n: recorder.append_event(self.root, ids[0], "feedback", {"text": "反馈 " + str(n)}), range(30)))
        actual = recorder.show(self.root, ids[0])
        self.assertEqual(len(actual["events"]), 30)
        self.assertEqual(len({e["id"] for e in actual["events"]}), 30)
        self.assertEqual(len(recorder.recent(self.root, 100)), 24)

    def test_separate_cli_processes_can_record_concurrently(self):
        self.enable()
        def run(n):
            output = subprocess.run([sys.executable, str(SCRIPT), "--data-dir", str(self.root), "begin", "--agent", "opencode", "--intent", "answer", "--input", "-"],
                                    input=json.dumps({"task_summary": "任务 " + str(n)}, ensure_ascii=False), encoding="utf-8", capture_output=True, check=True)
            return json.loads(output.stdout)["id"]
        with ThreadPoolExecutor(max_workers=4) as executor:
            ids = list(executor.map(run, range(8)))
        self.assertEqual(len(set(ids)), 8)
        self.assertEqual(len(recorder.recent(self.root)), 8)

    @unittest.skipUnless(os.name == "nt", "Windows app-data redirection regression")
    def test_windows_agents_with_different_appdata_use_one_home_directory(self):
        shared_home = Path(self.temporary.name) / "user-home"
        outputs = []
        for app in ("ordinary-agent", "packaged-agent"):
            environment = {**os.environ, "USERPROFILE": str(shared_home), "LOCALAPPDATA": str(Path(self.temporary.name) / app)}
            environment.pop("AMBITIOUS_PROMPT_DATA_DIR", None)
            result = subprocess.run([sys.executable, str(SCRIPT), "status"], env=environment, capture_output=True, encoding="utf-8", check=True)
            outputs.append(json.loads(result.stdout)["data_dir"])
        self.assertEqual(outputs[0], outputs[1])
        self.assertTrue(Path(outputs[0]).is_relative_to(shared_home))
        self.assertFalse(shared_home.exists(), "Status must not write user data")

    def test_missing_completion_does_not_become_failure_or_satisfaction(self):
        self.enable()
        self.begin()
        entry = recorder.recent(self.root)[0]
        self.assertEqual(entry["completion"], "not_recorded")
        self.assertEqual(entry["feedback_count"], 0)

    def test_disabling_stops_automatic_new_usage_and_finish(self):
        self.enable()
        identifier = self.begin()
        recorder.configure(self.root, False)
        self.assertFalse(recorder.begin(self.root, "codex", "execute", {"task_summary": "b"})["recorded"])
        self.assertFalse(recorder.append_event(self.root, identifier, "completion", FINISH)["recorded"])
        self.assertEqual(len(recorder.recent(self.root)), 1)
        # Explicit feedback on a past case remains available when requested by the user.
        recorder.append_event(self.root, identifier, "feedback", {"text": "补充历史案例反馈"})
        self.assertEqual(len(recorder.show(self.root, identifier)["events"]), 1)

    def test_ids_are_explicit_and_cannot_escape_storage(self):
        self.enable()
        self.begin()
        for bad in ("../../outside", "latest", "", "a" * 32):
            with self.assertRaises(ValueError):
                recorder.append_event(self.root, bad, "feedback", {"text": "bad"})
        self.assertFalse((Path(self.temporary.name) / "outside").exists())

    def test_export_contains_only_selected_case_and_does_not_overwrite(self):
        self.enable()
        first = self.begin("可分享的摘要")
        self.begin("另一个不能误导出的任务", agent="claude")
        output = Path(self.temporary.name) / "export.json"
        result = recorder.export(self.root, [first], output)
        bundle = json.loads(output.read_text("utf-8"))
        self.assertEqual(len(bundle["records"]), 1)
        self.assertEqual(bundle["records"][0]["use"]["id"], first)
        self.assertNotIn("另一个不能误导出的任务", output.read_text("utf-8"))
        self.assertNotIn("enabled", bundle)
        self.assertFalse(result["uploaded"])
        original = output.read_bytes()
        with self.assertRaises(FileExistsError):
            recorder.export(self.root, [first], output)
        self.assertEqual(output.read_bytes(), original)

    def test_schema_refuses_transcripts_and_unsupported_outcomes(self):
        self.enable()
        with self.assertRaises(ValueError):
            recorder.begin(self.root, "codex", "prompt", {"task_summary": "x", "full_transcript": "not allowed"})
        with self.assertRaises(ValueError):
            self.begin("x" * 601)
        identifier = self.begin()
        with self.assertRaises(ValueError):
            recorder.append_event(self.root, identifier, "completion", {**FINISH, "outcome": "user-satisfied"})
        self.assertEqual(recorder.show(self.root, identifier)["events"], [])

    def test_common_credentials_are_redacted_in_record_and_export(self):
        self.enable()
        token = "ghp_" + "A" * 24
        key = "sk-proj-" + "B" * 24
        identifier = self.begin("例子 " + token + " " + key)
        recorder.append_event(self.root, identifier, "feedback", {"text": "password=example-password"})
        output = Path(self.temporary.name) / "export.json"
        recorder.export(self.root, [identifier], output)
        stored = output.read_text("utf-8")
        self.assertNotIn(token, stored)
        self.assertNotIn(key, stored)
        self.assertNotIn("example-password", stored)
        self.assertIn("[REDACTED]", stored)

    def test_fingerprint_is_copy_and_line_ending_independent_but_detects_changes(self):
        first = recorder.skill_identity()
        copy = Path(self.temporary.name) / "skill-copy"
        shutil.copytree(recorder.SKILL_ROOT, copy, ignore=shutil.ignore_patterns("__pycache__"))
        document = copy / "SKILL.md"
        document.write_bytes(document.read_bytes().replace(b"\n", b"\r\n"))
        with patch.object(recorder, "SKILL_ROOT", copy):
            self.assertEqual(recorder.skill_identity(), first)
            with document.open("ab") as handle:
                handle.write(b"\nChanged instructions\n")
            self.assertNotEqual(recorder.skill_identity()["fingerprint"], first["fingerprint"])

    def test_corrupt_configuration_does_not_silently_enable(self):
        self.root.mkdir()
        (self.root / "config.json").write_text('{"schema":1,"enabled":"yes"}', encoding="utf-8")
        with self.assertRaises(ValueError):
            recorder.config(self.root)
        with self.assertRaises(ValueError):
            recorder.data_root(recorder.SKILL_ROOT / "logs")

    def test_list_filters_and_repeated_completion_keep_history(self):
        self.enable()
        first = self.begin()
        self.begin(agent="claude")
        recorder.append_event(self.root, first, "completion", {**FINISH, "outcome": "partial"})
        recorder.append_event(self.root, first, "completion", FINISH)
        recorder.append_event(self.root, first, "feedback", {"text": "保留这次反馈"})
        self.assertEqual(len(recorder.show(self.root, first)["events"]), 3)
        self.assertEqual(len(recorder.recent(self.root, agent="codex", feedback_only=True)), 1)
        self.assertEqual(recorder.recent(self.root, agent="claude", feedback_only=True), [])

    @unittest.skipIf(os.name == "nt", "Uses Unix permission bits")
    def test_local_files_are_private_on_unix(self):
        self.enable()
        identifier = self.begin()
        self.assertEqual((self.root.stat().st_mode & 0o777), 0o700)
        self.assertEqual(((self.root / "config.json").stat().st_mode & 0o777), 0o600)
        self.assertEqual(((self.root / "uses" / identifier / "use.json").stat().st_mode & 0o777), 0o600)


if __name__ == "__main__":
    unittest.main()
