"""af_cli.py on / off lifecycle in a temp git repo."""
import json
import unittest

import afhelpers as H
from afhelpers import core, hook


class OnOff(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)

    def state(self):
        return core.read_state(self.repo)

    def test_on_creates_phase1_hard_sprint(self):
        r = H.run_cli(self.repo, "on", "--title", "My Sprint")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.state()
        self.assertEqual((st["phase"], st["mode"], st["paused"], st["title"]), (1, "hard", False, "My Sprint"))
        self.assertEqual(st["history"], [])
        self.assertIn("Framework ON", r.stdout)
        self.assertTrue(hook.context_line(self.repo))

    def test_on_default_title_and_soft_mode_on_creation(self):
        r = H.run_cli(self.repo, "on", "--mode", "soft")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.state()
        self.assertEqual((st["mode"], st["phase"], st["title"]), ("soft", 1, "Sprint"))

    def test_off_pauses_and_disables_gate_and_context_keeping_state(self):
        H.set_state(self.repo, phase=8, mode="hard", title="Keep")
        # baseline: gate is live at phase 8 without approval
        self.assertIsNotNone(hook.gate_decision(self.repo, "git push"))
        self.assertIsNotNone(hook.context_line(self.repo))
        before = self.state()
        r = H.run_cli(self.repo, "off")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Framework OFF", r.stdout)
        st = self.state()
        self.assertTrue(st["paused"])
        for k in ("title", "phase", "mode", "history"):
            self.assertEqual(st[k], before[k])
        self.assertIsNone(hook.gate_decision(self.repo, "git push"))
        self.assertIsNone(hook.gate_decision(self.repo, "gh pr create"))
        self.assertIsNone(hook.context_line(self.repo))

    def test_off_through_hook_entrypoint_allows_push(self):
        H.set_state(self.repo, phase=2, mode="hard")
        ev = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.repo),
                         "tool_input": {"command": "git push"}})
        r = H.run_cli(self.repo, "hook", stdin=ev)
        self.assertIn("deny", r.stdout)
        H.run_cli(self.repo, "off")
        r = H.run_cli(self.repo, "hook", stdin=ev)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.strip(), "")
        up = json.dumps({"hook_event_name": "UserPromptSubmit", "cwd": str(self.repo)})
        self.assertEqual(H.run_cli(self.repo, "hook", stdin=up).stdout.strip(), "")

    def test_on_again_resumes_same_phase_and_reenables_gate(self):
        H.set_state(self.repo, phase=5, mode="hard", title="Resume")
        H.run_cli(self.repo, "off")
        r = H.run_cli(self.repo, "on")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("resumed at phase 5", r.stdout)
        st = self.state()
        self.assertEqual((st["phase"], st["paused"], st["mode"], st["title"]), (5, False, "hard", "Resume"))
        self.assertIsNotNone(hook.gate_decision(self.repo, "git push"))
        self.assertIsNotNone(hook.context_line(self.repo))

    def test_on_does_not_reset_title_or_history_of_existing_sprint(self):
        core.write_state(self.repo, {"title": "Orig", "phase": 4, "mode": "hard", "paused": True,
                                     "history": [{"phase": 3}]})
        H.run_cli(self.repo, "on", "--title", "Other")
        st = self.state()
        self.assertEqual((st["title"], st["phase"], st["history"]), ("Orig", 4, [{"phase": 3}]))

    def test_on_mode_soft_changes_mode_of_existing_sprint(self):
        H.set_state(self.repo, phase=3, mode="hard", paused=True)
        r = H.run_cli(self.repo, "on", "--mode", "soft")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.state()
        self.assertEqual((st["mode"], st["paused"], st["phase"]), ("soft", False, 3))
        self.assertIsNone(hook.gate_decision(self.repo, "git push"))

    def test_on_without_mode_keeps_existing_soft_mode(self):
        H.set_state(self.repo, phase=3, mode="soft", paused=True)
        H.run_cli(self.repo, "on")
        self.assertEqual(self.state()["mode"], "soft")

    def test_on_rejects_invalid_mode(self):
        r = H.run_cli(self.repo, "on", "--mode", "turbo")
        self.assertNotEqual(r.returncode, 0)
        self.assertIsNone(self.state())

    def test_off_with_no_state_is_noop_exit0(self):
        r = H.run_cli(self.repo, "off")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("already OFF", r.stdout)
        self.assertIsNone(self.state())
        self.assertFalse((H.sdlc(self.repo) / "state.json").exists())

    def test_off_twice_is_idempotent(self):
        H.set_state(self.repo, phase=6)
        H.run_cli(self.repo, "off")
        first = self.state()
        r = H.run_cli(self.repo, "off")
        self.assertEqual(r.returncode, 0)
        strip = lambda d: {k: v for k, v in d.items() if k != "updated"}
        self.assertEqual(strip(self.state()), strip(first))

    def test_status_shows_paused(self):
        H.set_state(self.repo, phase=2)
        H.run_cli(self.repo, "off")
        self.assertIn("Paused: True", H.run_cli(self.repo, "status").stdout)


if __name__ == "__main__":
    unittest.main()
