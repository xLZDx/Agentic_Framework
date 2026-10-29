import json
import subprocess
import unittest

import afhelpers as H
from afhelpers import hook

MATCHED = [
    "git push", "git push origin main", "git push --force-with-lease", "git -C x push", "git -C /a/b push origin HEAD",
    "git -c a=b push", "cd x && git push", "echo hi; git push", "gh pr create --title t", "gh pr merge 5 --squash",
    "gh  pr   create",
]
NOT_MATCHED = ["git status", "git log --oneline", "git pull", "git commit -m ok", "gh pr list", "gh pr view 3",
               "ls -la", "python push.py", "echo pushing", "gh issue create"]


class GateDecision(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)

    def test_no_state_allowed(self):
        self.assertIsNone(hook.gate_decision(self.repo, "git push"))

    def test_soft_mode_allowed(self):
        H.set_state(self.repo, phase=1, mode="soft")
        self.assertIsNone(hook.gate_decision(self.repo, "git push"))

    def test_paused_allowed(self):
        H.set_state(self.repo, phase=1, paused=True)
        self.assertIsNone(hook.gate_decision(self.repo, "git push"))

    def test_hard_mode_before_phase_8_denies_push_and_pr(self):
        for phase in (1, 4, 7):
            H.set_state(self.repo, phase=phase)
            for cmd in MATCHED:
                with self.subTest(phase=phase, cmd=cmd):
                    reason = hook.gate_decision(self.repo, cmd)
                    self.assertIsNotNone(reason)
                    self.assertIn(f"phase is {phase}", reason)

    def test_non_push_commands_allowed_even_when_hard(self):
        H.set_state(self.repo, phase=1)
        for cmd in NOT_MATCHED:
            with self.subTest(cmd=cmd):
                self.assertIsNone(hook.gate_decision(self.repo, cmd))

    def test_empty_command_allowed(self):
        H.set_state(self.repo, phase=1)
        self.assertIsNone(hook.gate_decision(self.repo, ""))

    def test_phase_8_without_approval_denied(self):
        H.set_state(self.repo, phase=8)
        reason = hook.gate_decision(self.repo, "git push")
        self.assertIn("approval gate", reason)

    def test_phase_8_valid_approval_allowed_then_new_commit_denied(self):
        H.set_state(self.repo, phase=8)
        H.write_approval(self.repo)
        self.assertIsNone(hook.gate_decision(self.repo, "git push"))
        self.assertIsNone(hook.gate_decision(self.repo, "gh pr create"))
        H.commit_file(self.repo)
        reason = hook.gate_decision(self.repo, "git push")
        self.assertIsNotNone(reason)
        self.assertIn("invalidates", reason)

    def test_phase_9_still_requires_valid_approval(self):
        H.set_state(self.repo, phase=9)
        self.assertIsNotNone(hook.gate_decision(self.repo, "git push"))
        H.write_approval(self.repo)
        self.assertIsNone(hook.gate_decision(self.repo, "git push"))

    def test_phase_8_wrong_verdict_denied(self):
        H.set_state(self.repo, phase=8)
        H.write_approval(self.repo, verdict="MINOR")
        self.assertIsNotNone(hook.gate_decision(self.repo, "git push"))

    def test_push_word_inside_other_git_command_not_blocked(self):
        """Regression guard: a commit message / grep mentioning push must not be treated as a push."""
        H.set_state(self.repo, phase=1)
        for cmd in ('git commit -m "fix push bug"', "git log --grep push", "git stash push -m wip"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(hook.gate_decision(self.repo, cmd))


class HookMain(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)

    def call(self, event, cwd=None):
        raw = event if isinstance(event, str) else json.dumps(event)
        return H.run_cli(cwd or self.repo, "hook", stdin=raw)

    def pre(self, command, cwd=None):
        return self.call({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.repo),
                          "tool_input": {"command": command}}, cwd)

    def test_push_denied_with_claude_schema(self):
        H.set_state(self.repo, phase=3)
        r = self.pre("git push origin main")
        self.assertEqual(r.returncode, 0)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("phase is 3", out["permissionDecisionReason"])

    def test_allowed_commands_print_nothing(self):
        H.set_state(self.repo, phase=3)
        r = self.pre("git status")
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_non_bash_tool_not_gated(self):
        H.set_state(self.repo, phase=3)
        r = self.call({"hook_event_name": "PreToolUse", "tool_name": "Edit", "cwd": str(self.repo),
                       "tool_input": {"command": "git push"}})
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_soft_paused_and_no_state_are_inert(self):
        self.assertEqual(self.pre("git push").stdout, "")  # no state
        H.set_state(self.repo, phase=1, mode="soft")
        self.assertEqual(self.pre("git push").stdout, "")
        H.set_state(self.repo, phase=1, paused=True)
        self.assertEqual(self.pre("git push").stdout, "")

    def test_phase_8_valid_allowed_then_denied_after_commit(self):
        H.set_state(self.repo, phase=8)
        H.write_approval(self.repo)
        self.assertEqual(self.pre("git push").stdout, "")
        H.commit_file(self.repo)
        self.assertEqual(json.loads(self.pre("git push").stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_cwd_in_subdirectory_resolves_project(self):
        H.set_state(self.repo, phase=2)
        sub = self.repo / "sub" / "deeper"
        sub.mkdir(parents=True)
        r = self.call({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(sub),
                       "tool_input": {"command": "git push"}})
        self.assertIn("deny", r.stdout)

    def test_fail_open_on_garbage_and_edge_input(self):
        H.set_state(self.repo, phase=3)
        for raw in ("not json at all {{{", "[1,2,3]", '"str"', "null", "", "{}"):
            with self.subTest(stdin=raw):
                r = self.call(raw)
                self.assertEqual(r.returncode, 0)
                self.assertNotIn("deny", r.stdout)

    def test_fail_open_on_corrupt_state_file(self):
        H.set_state(self.repo, phase=3)
        (H.sdlc(self.repo) / "state.json").write_text("{corrupt", encoding="utf-8")
        r = self.pre("git push")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("deny", r.stdout)
        self.assertIn("af hook error", r.stderr)

    def test_fail_open_outside_git_repo(self):
        other = H.tmpdir(self)
        r = self.call({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(other),
                       "tool_input": {"command": "git push"}}, cwd=other)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_missing_tool_input_does_not_crash_or_deny(self):
        H.set_state(self.repo, phase=3)
        r = self.call({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.repo)})
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_user_prompt_submit_emits_context(self):
        H.set_state(self.repo, phase=1, title="Alpha")
        for name in ("UserPromptSubmit", "SessionStart"):
            with self.subTest(event=name):
                r = self.call({"hook_event_name": name, "cwd": str(self.repo)})
                self.assertEqual(r.returncode, 0)
                out = json.loads(r.stdout)["hookSpecificOutput"]
                self.assertEqual(out["hookEventName"], name)
                ctx = out["additionalContext"]
                self.assertIn("sprint 'Alpha'", ctx)
                self.assertIn("phase 1 Discovery", ctx)
                self.assertIn("id " + H.TEST_SID, ctx)
                self.assertIn("Missing exit artifacts: requirements.md", ctx)
                self.assertIn("business-analyst", ctx)

    def test_context_tracks_phase_and_artifacts(self):
        H.set_state(self.repo, phase=8)
        ctx = json.loads(self.call({"hook_event_name": "UserPromptSubmit", "cwd": str(self.repo)}).stdout)[
            "hookSpecificOutput"]["additionalContext"]
        self.assertIn("phase 8 PM-GPT review and approve", ctx)
        self.assertIn("pm-gpt-review", ctx)
        self.assertIn("gate-approval.md", ctx)

    def test_context_silent_when_no_state_or_paused(self):
        self.assertEqual(self.call({"hook_event_name": "UserPromptSubmit", "cwd": str(self.repo)}).stdout, "")
        H.set_state(self.repo, phase=1, paused=True)
        self.assertEqual(self.call({"hook_event_name": "UserPromptSubmit", "cwd": str(self.repo)}).stdout, "")

    def test_unknown_event_is_silent(self):
        H.set_state(self.repo, phase=1)
        self.assertEqual(self.call({"hook_event_name": "Stop", "cwd": str(self.repo)}).stdout, "")


class GitHook(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)
        self.hook_file = self.repo / ".git" / "hooks" / "pre-push"

    def test_install_writes_marker_hook_and_is_idempotent(self):
        r = H.run_cli(self.repo, "install-githook")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = self.hook_file.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/bin/sh\n# agentic-framework pre-push"))
        self.assertIn("gate-check", text)
        self.assertIn(H.CLI.as_posix(), text)
        self.assertEqual(H.run_cli(self.repo, "install-githook").returncode, 0)
        self.assertEqual(self.hook_file.read_text(encoding="utf-8"), text)

    def test_refuses_to_overwrite_foreign_hook(self):
        self.hook_file.parent.mkdir(parents=True, exist_ok=True)
        self.hook_file.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
        r = H.run_cli(self.repo, "install-githook")
        self.assertEqual(r.returncode, 1)
        self.assertIn("REFUSED", r.stdout)
        self.assertEqual(self.hook_file.read_text(encoding="utf-8"), "#!/bin/sh\necho mine\n")

    def test_gate_check_exit_codes(self):
        self.assertEqual(H.run_cli(self.repo, "gate-check").returncode, 0)  # no state
        H.set_state(self.repo, phase=3)
        r = H.run_cli(self.repo, "gate-check")
        self.assertEqual(r.returncode, 1)
        self.assertIn("push blocked", r.stderr)
        H.set_state(self.repo, phase=3, mode="soft")
        self.assertEqual(H.run_cli(self.repo, "gate-check").returncode, 0)
        H.set_state(self.repo, phase=3, paused=True)
        self.assertEqual(H.run_cli(self.repo, "gate-check").returncode, 0)
        H.set_state(self.repo, phase=8)
        self.assertEqual(H.run_cli(self.repo, "gate-check").returncode, 1)
        H.write_approval(self.repo)
        self.assertEqual(H.run_cli(self.repo, "gate-check").returncode, 0)
        H.commit_file(self.repo)
        self.assertEqual(H.run_cli(self.repo, "gate-check").returncode, 1)

    def test_installed_hook_blocks_and_allows_real_git_push(self):
        remote = H.tmpdir(self)
        H.git(remote, "init", "-q", "--bare")
        H.git(self.repo, "remote", "add", "origin", str(remote))
        self.assertEqual(H.run_cli(self.repo, "install-githook").returncode, 0)
        H.set_state(self.repo, phase=3)
        branch = H.git(self.repo, "rev-parse", "--abbrev-ref", "HEAD").strip()

        def push():
            return subprocess.run(["git", "-C", str(self.repo), "push", "origin", branch],
                                  capture_output=True, text=True, env=H.GIT_ENV, timeout=60)
        r = push()
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(H.git(remote, "branch", "--list").strip(), "")  # nothing reached the remote
        H.set_state(self.repo, phase=8)
        H.write_approval(self.repo)
        r = push()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(branch, H.git(remote, "branch", "--list"))


if __name__ == "__main__":
    unittest.main()
