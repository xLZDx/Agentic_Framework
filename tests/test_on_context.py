"""Regression coverage for phase context printed by the `on` command."""
import unittest

import afhelpers as H
from afhelpers import core, hook


class OnContext(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)

    def state(self):
        return core.read_state(self.repo)

    def assert_context_output(self, result):
        expected = hook.context_line(self.repo)
        self.assertIsNotNone(expected)
        self.assertIn(expected, result.stdout.splitlines())

    def test_fresh_on_prints_canonical_phase_context(self):
        result = H.run_cli(self.repo, "on", "--title", "Context Sprint")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Framework ON", result.stdout)
        self.assert_context_output(result)
        state = self.state()
        self.assertEqual((state["title"], state["phase"], state["mode"], state["paused"]),
                         ("Context Sprint", 1, "hard", False))
        self.assertEqual(state["history"], [])

    def test_resume_prints_context_for_retained_phase_and_mode(self):
        H.set_state(self.repo, phase=4, mode="soft", paused=True, title="Retain")

        result = H.run_cli(self.repo, "on")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("resumed at phase 4 (soft)", result.stdout)
        self.assert_context_output(result)
        state = self.state()
        self.assertEqual((state["title"], state["phase"], state["mode"], state["paused"]),
                         ("Retain", 4, "soft", False))

    def test_explicit_mode_prints_context_after_applying_mode(self):
        H.set_state(self.repo, phase=3, mode="hard", paused=True)

        result = H.run_cli(self.repo, "on", "--mode", "soft")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("resumed at phase 3 (soft)", result.stdout)
        self.assert_context_output(result)
        self.assertEqual((self.state()["phase"], self.state()["mode"]), (3, "soft"))

    def test_refused_fresh_activation_prints_no_context_and_creates_no_state(self):
        hooks = self.repo / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        foreign_hook = hooks / "pre-push"
        foreign_hook.write_text("#!/bin/sh\necho foreign\n", encoding="utf-8")

        result = H.run_cli(self.repo, "on")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Framework NOT enabled", result.stdout)
        self.assertNotIn("[Agentic_Framework SDLC]", result.stdout)
        self.assertIsNone(self.state())

    def test_refused_resume_prints_no_context_and_preserves_paused_state(self):
        H.set_state(self.repo, phase=5, mode="hard", paused=True, title="Paused")
        before = self.state()
        hooks = self.repo / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        (hooks / "pre-push").write_text("#!/bin/sh\necho foreign\n", encoding="utf-8")

        result = H.run_cli(self.repo, "on")

        self.assertEqual(result.returncode, 1)
        self.assertIn("Framework NOT enabled", result.stdout)
        self.assertNotIn("[Agentic_Framework SDLC]", result.stdout)
        self.assertEqual(self.state(), before)

    def test_on_does_not_advance_phase_or_request_pm_approval(self):
        H.set_state(self.repo, phase=8, mode="soft", paused=True, title="Approval boundary")
        before = self.state()

        result = H.run_cli(self.repo, "on")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_context_output(result)
        after = self.state()
        self.assertEqual((after["phase"], after["mode"], after["paused"]), (8, "soft", False))
        self.assertEqual(after["history"], before["history"])
        self.assertFalse((H.sdlc(self.repo) / ".pm-review" / "request.json").exists())
        self.assertFalse((H.sdlc(self.repo) / ".pm-review" / "approval.json").exists())


if __name__ == "__main__":
    unittest.main()
