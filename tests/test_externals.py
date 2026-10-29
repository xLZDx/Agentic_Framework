"""af_install.missing_external_skills_note and its logging by install(); temp homes only."""
import json
import subprocess
import sys
import unittest

import afhelpers as H
from afhelpers import ROOT

sys.path.insert(0, str(ROOT / "tools"))
import af_install  # noqa: E402

CFG = json.loads((ROOT / "core" / "framework.json").read_text(encoding="utf-8"))
EXTERNAL = CFG["external_skills"]


def make_skill(home, name):
    d = home / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("---\nname: " + name + "\n---\nx\n", encoding="utf-8")


class MissingExternalNote(unittest.TestCase):
    def setUp(self):
        self.home = H.tmpdir(self)

    def test_all_missing_lists_every_external_skill(self):
        note = af_install.missing_external_skills_note(self.home)
        self.assertIn("MISSING", note)
        for s in EXTERNAL:
            self.assertIn(s, note)

    def test_partially_present_lists_only_the_missing(self):
        make_skill(self.home, EXTERNAL[0])
        note = af_install.missing_external_skills_note(self.home)
        self.assertIn("MISSING", note)
        listed = note.split(": ", 1)[1].split(", ")
        self.assertNotIn(EXTERNAL[0], listed)
        self.assertEqual(listed, EXTERNAL[1:])

    def test_all_present_reports_ok(self):
        for s in EXTERNAL:
            make_skill(self.home, s)
        note = af_install.missing_external_skills_note(self.home)
        self.assertIn("ok", note)
        self.assertNotIn("MISSING", note)

    def test_directory_without_skill_md_counts_as_missing(self):
        (self.home / "skills" / EXTERNAL[0]).mkdir(parents=True)
        self.assertIn(EXTERNAL[0], af_install.missing_external_skills_note(self.home))

    def test_does_not_write_anything(self):
        af_install.missing_external_skills_note(self.home)
        self.assertEqual(list(self.home.rglob("*")), [])


class InstallLogsNote(unittest.TestCase):
    def setUp(self):
        self.home = H.tmpdir(self)

    def test_install_logs_missing_note_for_temp_home(self):
        log = []
        af_install.install(self.home, "claude", log, False)
        notes = [x for x in log if x.startswith("EXTERNAL-SKILLS")]
        self.assertEqual(len(notes), 1, log[-3:])
        self.assertIn("MISSING", notes[0])
        for s in EXTERNAL:
            self.assertIn(s, notes[0])

    def test_install_logs_ok_when_externals_already_present(self):
        for s in EXTERNAL:
            make_skill(self.home, s)
        log = []
        af_install.install(self.home, "claude", log, False)
        notes = [x for x in log if x.startswith("EXTERNAL-SKILLS")]
        self.assertEqual(len(notes), 1)
        self.assertIn("ok", notes[0])

    def test_install_does_not_install_external_skills(self):
        af_install.install(self.home, "claude", [], False)
        for s in EXTERNAL:
            self.assertFalse((self.home / "skills" / s).exists())

    def test_dry_run_logs_note_and_writes_nothing(self):
        log = []
        af_install.install(self.home, "codex", log, True)
        self.assertTrue(any(x.startswith("EXTERNAL-SKILLS") for x in log))
        self.assertEqual(list(self.home.rglob("*")), [])

    def test_cli_install_prints_note_per_target(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "af_install.py"),
                            "--claude-home", str(self.home / "c"), "--codex-home", str(self.home / "x")],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.count("EXTERNAL-SKILLS"), 2)


if __name__ == "__main__":
    unittest.main()
