"""Filesystem behavior tests; no agents, model calls, or real user settings."""

import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("install_skill", ROOT / "scripts" / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def test_python_runtime_cache_is_not_distributed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for item in ("SKILL.md", "agents", "assets", "references", "scripts"):
                source = ROOT / item
                if source.is_dir():
                    shutil.copytree(source, root / item, ignore=shutil.ignore_patterns("__pycache__"))
                else:
                    shutil.copyfile(source, root / item)
            for name in ("LICENSE", "NOTICE.md"):
                shutil.copyfile(ROOT / name, root / name)
            cache = root / "scripts" / "__pycache__"
            cache.mkdir(parents=True, exist_ok=True)
            (cache / "sentinel.pyc").write_bytes(b"not distributable")
            selected = installer.payload(root)
            self.assertFalse(any("__pycache__" in str(p) or p.suffix == ".pyc" for p in selected))
            self.assertIn(Path("scripts/local_feedback.py"), selected)
            self.assertIn(Path("SKILL.md"), selected)
            self.assertNotIn(Path("scripts/install.py"), selected)

    def test_install_all_and_repeat_preserves_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            roots = installer.target_roots(Path(temporary), {})
            targets = installer.install(ROOT, roots, installer.AGENTS)
            for _, target in targets:
                for relative, source in installer.payload(ROOT).items():
                    self.assertEqual((target / relative).read_bytes(), source.read_bytes())
            target = targets[0][1] / "SKILL.md"
            before = target.stat().st_mtime_ns
            installer.install(ROOT, roots, installer.AGENTS)
            self.assertEqual(before, target.stat().st_mtime_ns)

    def test_conflict_prevents_writes_to_other_agents(self):
        with tempfile.TemporaryDirectory() as temporary:
            roots = installer.target_roots(Path(temporary), {})
            existing = roots["zcode"] / installer.SKILL_NAME / "SKILL.md"
            existing.parent.mkdir(parents=True)
            existing.write_text("my custom skill", encoding="utf-8")
            with self.assertRaises(ValueError):
                installer.install(ROOT, roots, installer.AGENTS)
            self.assertEqual(existing.read_text(encoding="utf-8"), "my custom skill")
            self.assertFalse(roots["claude"].exists())

    def test_dry_run_does_not_create_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            installer.install(ROOT, installer.target_roots(home, {}), installer.AGENTS, True)
            self.assertEqual(list(home.iterdir()), [])

    def test_parent_file_blocks_all_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            (home / ".zcode").write_text("existing file", encoding="utf-8")
            roots = installer.target_roots(home, {})
            with self.assertRaises(ValueError):
                installer.install(ROOT, roots, installer.AGENTS)
            self.assertFalse(roots["dsh"].exists())

    def test_existing_codex_and_custom_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            legacy = home / ".codex" / "skills" / installer.SKILL_NAME
            legacy.mkdir(parents=True)
            self.assertEqual(installer.target_roots(home, {})["codex"], legacy.parent)
            custom = home / "custom"
            roots = installer.target_roots(home, {"DSH_HOME": str(custom), "CODEX_HOME": str(custom)})
            self.assertEqual(roots["dsh"], custom / "skills")
            self.assertEqual(roots["codex"], custom / "skills")

    def test_workbuddy_editions_are_independent_and_keep_settings(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            roots = installer.target_roots(home, {})
            self.assertEqual(roots["workbuddy"], home / ".workbuddy" / "skills")
            self.assertEqual(roots["workbuddy-intl"], home / ".workbuddy-ai" / "skills")
            settings = []
            for root in (".workbuddy", ".workbuddy-ai"):
                config = home / root / "app" / "app-config.json"
                config.parent.mkdir(parents=True)
                config.write_text('{"personalization":{"customPrompt":"keep me"}}', encoding="utf-8")
                settings.append((config, config.read_bytes()))
            installer.install(ROOT, roots, ["workbuddy-intl"])
            self.assertFalse(roots["workbuddy"].exists())
            self.assertTrue((roots["workbuddy-intl"] / installer.SKILL_NAME / "SKILL.md").is_file())
            for config, original in settings:
                self.assertEqual(config.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
