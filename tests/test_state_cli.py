import json
import unittest

import afhelpers as H
from afhelpers import core


def state(repo):
    return json.loads((H.sdlc(repo) / "state.json").read_text(encoding="utf-8"))


class StartStatus(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)

    def test_status_without_sprint(self):
        r = H.run_cli(self.repo, "status")
        self.assertEqual(r.returncode, 0)
        self.assertIn("No sprint", r.stdout)

    def test_start_creates_state_and_state_md(self):
        r = H.run_cli(self.repo, "start", "My sprint")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = state(self.repo)
        self.assertEqual((st["title"], st["phase"], st["mode"], st["paused"]), ("My sprint", 1, "hard", False))
        md = (H.sdlc(self.repo) / "STATE.md").read_text(encoding="utf-8")
        self.assertIn("Phase: 1 Discovery", md)
        self.assertIn("requirements.md", md)

    def test_start_soft_mode_and_no_overwrite(self):
        self.assertEqual(H.run_cli(self.repo, "start", "A", "--mode", "soft").returncode, 0)
        self.assertEqual(state(self.repo)["mode"], "soft")
        r = H.run_cli(self.repo, "start", "B")
        self.assertEqual(r.returncode, 1)
        self.assertIn("refusing to overwrite", r.stdout)
        self.assertEqual(state(self.repo)["title"], "A")

    def test_status_reports_phase_roles_and_missing_artifact(self):
        H.run_cli(self.repo, "start", "S")
        r = H.run_cli(self.repo, "status")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Phase: 1 Discovery", r.stdout)
        self.assertIn("business-analyst", r.stdout)
        self.assertIn("Missing exit artifacts: requirements.md", r.stdout)
        H.write_artifact(self.repo, "requirements.md")
        self.assertIn("Missing exit artifacts: none", H.run_cli(self.repo, "status").stdout)

    def test_status_at_phase_8_shows_approval_validity(self):
        H.set_state(self.repo, phase=8)
        self.assertIn("NOT VALID", H.run_cli(self.repo, "status").stdout)
        H.write_approval(self.repo)
        self.assertIn("PM-GPT approval: OK", H.run_cli(self.repo, "status").stdout)

    def test_project_flag_from_other_cwd(self):
        other = H.tmpdir(self)
        r = H.run_cli(other, "--project", str(self.repo), "start", "X")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(state(self.repo)["title"], "X")


class NextGate(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)
        H.run_cli(self.repo, "start", "S")

    def test_next_without_sprint(self):
        repo = H.make_repo(self)
        r = H.run_cli(repo, "next")
        self.assertEqual(r.returncode, 1)
        self.assertIn("No sprint", r.stdout)

    def test_next_blocked_when_exit_artifact_missing_then_passes(self):
        r = H.run_cli(self.repo, "next")
        self.assertEqual(r.returncode, 1)
        self.assertIn("BLOCKED", r.stdout)
        self.assertIn("requirements.md", r.stdout)
        self.assertEqual(state(self.repo)["phase"], 1)
        H.write_artifact(self.repo, "requirements.md")
        r = H.run_cli(self.repo, "next")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        st = state(self.repo)
        self.assertEqual(st["phase"], 2)
        self.assertEqual(len(st["history"]), 1)
        self.assertEqual(st["history"][0]["phase"], 1)
        self.assertFalse(st["history"][0]["forced"])
        self.assertEqual(st["history"][0]["head"], core.head(self.repo))

    def test_force_skips_missing_artifact_and_records_it(self):
        r = H.run_cli(self.repo, "next", "--force")
        self.assertEqual(r.returncode, 0)
        st = state(self.repo)
        self.assertEqual(st["phase"], 2)
        self.assertTrue(st["history"][0]["forced"])

    def test_glob_artifact_phase_6(self):
        H.set_state(self.repo, phase=6)
        self.assertEqual(H.run_cli(self.repo, "next").returncode, 1)
        H.write_artifact(self.repo, "change-records/c1.md")
        self.assertEqual(H.run_cli(self.repo, "next").returncode, 0)
        self.assertEqual(state(self.repo)["phase"], 7)

    def test_phase_5_docs_review_not_required(self):
        H.set_state(self.repo, phase=5)
        H.write_artifact(self.repo, "review-record.md")
        self.assertEqual(H.run_cli(self.repo, "next").returncode, 0)
        self.assertEqual(state(self.repo)["phase"], 6)

    def test_phase_8_blocked_without_approval_even_with_gate_file(self):
        H.set_state(self.repo, phase=8)
        H.write_artifact(self.repo, "gate-approval.md", "forged by hand\n")  # artifact present, no approval.json
        r = H.run_cli(self.repo, "next")
        self.assertEqual(r.returncode, 1)
        self.assertIn("PM-GPT approval required", r.stdout)
        self.assertEqual(state(self.repo)["phase"], 8)

    def test_phase_8_blocked_when_artifact_missing(self):
        H.set_state(self.repo, phase=8)
        r = H.run_cli(self.repo, "next")
        self.assertEqual(r.returncode, 1)
        self.assertIn("gate-approval.md", r.stdout)

    def test_phase_8_blocked_with_stale_approval_after_new_commit(self):
        H.set_state(self.repo, phase=8)
        H.write_approval(self.repo)
        H.commit_file(self.repo)
        r = H.run_cli(self.repo, "next")
        self.assertEqual(r.returncode, 1)
        self.assertIn("invalidates", r.stdout)

    def test_phase_8_passes_with_valid_approval(self):
        H.set_state(self.repo, phase=8)
        H.write_approval(self.repo)
        r = H.run_cli(self.repo, "next")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(state(self.repo)["phase"], 9)

    def test_phase_8_force_does_not_bypass_approval(self):
        H.set_state(self.repo, phase=8)
        H.write_artifact(self.repo, "gate-approval.md")
        r = H.run_cli(self.repo, "next", "--force")
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("BLOCKED", r.stdout)
        self.assertIn("--force does not apply", r.stdout)
        self.assertEqual(state(self.repo)["phase"], 8)

    def test_last_phase_does_not_advance(self):
        H.set_state(self.repo, phase=10)
        H.write_artifact(self.repo, "sprint-report.md")
        r = H.run_cli(self.repo, "next")
        self.assertEqual(r.returncode, 0)
        self.assertIn("last phase", r.stdout)
        self.assertEqual(state(self.repo)["phase"], 10)

    def test_full_walk_through_all_phases(self):
        for n, p in enumerate(core.load_phase_map()["phases"], start=1):
            if n == 8:
                H.write_approval(self.repo)
            for a in p["artifacts"]:
                if n != 8:  # phase 8 artifact is produced by the approval itself
                    H.write_artifact(self.repo, a.replace("*", "x"))
            r = H.run_cli(self.repo, "next")
            self.assertEqual(r.returncode, 0, f"phase {n}: {r.stdout}")
        self.assertEqual(state(self.repo)["phase"], 10)
        self.assertEqual(len(state(self.repo)["history"]), 9)


class ModePause(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)
        H.run_cli(self.repo, "start", "S")

    def test_mode_pause_resume_persist(self):
        self.assertEqual(H.run_cli(self.repo, "mode", "soft").returncode, 0)
        self.assertEqual(state(self.repo)["mode"], "soft")
        self.assertEqual(H.run_cli(self.repo, "pause").returncode, 0)
        self.assertTrue(state(self.repo)["paused"])
        self.assertIn("Paused: True", H.run_cli(self.repo, "status").stdout)
        self.assertEqual(H.run_cli(self.repo, "resume").returncode, 0)
        self.assertFalse(state(self.repo)["paused"])
        self.assertEqual(H.run_cli(self.repo, "mode", "hard").returncode, 0)
        self.assertEqual(state(self.repo)["mode"], "hard")
        self.assertEqual(state(self.repo)["phase"], 1)

    def test_invalid_mode_rejected(self):
        r = H.run_cli(self.repo, "mode", "turbo")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(state(self.repo)["mode"], "hard")

    def test_mode_pause_without_sprint(self):
        repo = H.make_repo(self)
        self.assertEqual(H.run_cli(repo, "pause").returncode, 1)
        self.assertEqual(H.run_cli(repo, "mode", "soft").returncode, 1)
        self.assertFalse((H.sdlc(repo) / "state.json").exists())


if __name__ == "__main__":
    unittest.main()
