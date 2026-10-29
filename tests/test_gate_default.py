"""The push/PR block is OFF by default: default-config behaviour and explicit opt-in (AF_PUSH_GATE=on)."""
import json
import os
import shutil
import subprocess
import unittest
from unittest import mock

import afhelpers as H
from afhelpers import core, hook

OFF = H.DEFAULT_GATE_ENV
ON = {"AF_PUSH_GATE": "on"}
FOREIGN = b"#!/bin/sh\necho mine\n"
PUSHES = ["git push", "git push origin main", "env git push", "sh -c 'git push'", "gh pr create", "gh pr merge 3"]


class GateEnabledFlag(unittest.TestCase):
    def test_phase_map_default_is_disabled(self):
        self.assertIs(core.load_phase_map()["push_gate"].get("enabled"), False)

    def test_env_values(self):
        for v, expect in (("on", True), ("ON", True), ("1", True), ("true", True), ("TRUE", True),
                          ("off", False), ("0", False), ("", False), ("no", False), ("yes", False)):
            with self.subTest(v=v):
                with mock.patch.dict(os.environ, {"AF_PUSH_GATE": v}):
                    self.assertEqual(hook.gate_enabled(), expect)

    def test_default_without_env_is_disabled(self):
        with H.default_gate():
            self.assertFalse(hook.gate_enabled())

    def test_phase_map_enabled_true_enables_without_env(self):
        pm = core.load_phase_map()
        pm["push_gate"]["enabled"] = True
        with H.default_gate(), mock.patch.object(core, "load_phase_map", return_value=pm):
            self.assertTrue(hook.gate_enabled())


class DefaultGateDecision(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)

    def test_pushes_allowed_in_hard_mode_at_every_phase_without_approval(self):
        with H.default_gate():
            for phase in (1, 5, 7, 8, 9):
                H.set_state(self.repo, phase=phase, mode="hard")
                for c in PUSHES:
                    with self.subTest(phase=phase, cmd=c):
                        self.assertIsNone(hook.gate_decision(self.repo, c))

    def test_same_commands_are_denied_when_enabled(self):
        H.set_state(self.repo, phase=1, mode="hard")
        with mock.patch.dict(os.environ, ON):
            for c in PUSHES:
                with self.subTest(cmd=c):
                    self.assertIsNotNone(hook.gate_decision(self.repo, c))

    def test_pretooluse_entry_point_does_not_deny_by_default_but_denies_when_on(self):
        H.set_state(self.repo, phase=1, mode="hard")
        ev = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(self.repo),
                         "tool_input": {"command": "git push"}})
        r = H.run_cli(self.repo, "hook", stdin=ev, env=OFF)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, ""))
        r = H.run_cli(self.repo, "hook", stdin=ev, env=ON)
        self.assertIn('"deny"', r.stdout)

    def test_phase_context_injection_still_works_when_gate_is_off(self):
        H.set_state(self.repo, phase=2, mode="hard")
        ev = json.dumps({"hook_event_name": "UserPromptSubmit", "cwd": str(self.repo)})
        r = H.run_cli(self.repo, "hook", stdin=ev, env=OFF)
        self.assertIn("phase 2", json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"])


class DefaultActivation(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)
        self.hook_file = self.repo / ".git" / "hooks" / "pre-push"

    def seed_foreign(self):
        self.hook_file.parent.mkdir(parents=True, exist_ok=True)
        self.hook_file.write_bytes(FOREIGN)

    def test_on_and_start_hard_do_not_create_pre_push(self):
        for cmd in (("on",), ("start", "S")):
            repo = H.make_repo(self)
            r = H.run_cli(repo, *cmd, env=OFF)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(core.read_state(repo)["mode"], "hard")
            self.assertFalse((repo / ".git" / "hooks" / "pre-push").exists(), cmd)

    def test_foreign_pre_push_does_not_block_hard_activation(self):
        self.seed_foreign()
        for cmd in (("on",), ("mode", "hard")):
            with self.subTest(cmd=cmd):
                if cmd[0] == "mode":
                    H.set_state(self.repo, phase=3, mode="soft")
                r = H.run_cli(self.repo, *cmd, env=OFF)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertNotIn("NOT enabled", r.stdout)
                self.assertEqual(self.hook_file.read_bytes(), FOREIGN)
        self.assertEqual(core.read_state(self.repo)["mode"], "hard")

    def test_start_and_resume_with_foreign_hook_succeed(self):
        self.seed_foreign()
        r = H.run_cli(self.repo, "start", "S", env=OFF)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        H.run_cli(self.repo, "off", env=OFF)
        r = H.run_cli(self.repo, "on", env=OFF)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(core.read_state(self.repo)["paused"])
        self.assertEqual(self.hook_file.read_bytes(), FOREIGN)

    def test_when_enabled_the_foreign_hook_still_blocks_hard_activation(self):
        self.seed_foreign()
        r = H.run_cli(self.repo, "on", env=ON)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("NOT enabled", r.stdout)
        self.assertIsNone(core.read_state(self.repo))

    def test_when_enabled_on_installs_pre_push(self):
        r = H.run_cli(self.repo, "on", env=ON)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("# agentic-framework pre-push", self.hook_file.read_text(encoding="utf-8"))

    def test_phase_flow_and_state_work_normally_with_gate_off(self):
        H.run_cli(self.repo, "start", "S", env=OFF)
        H.write_artifact(self.repo, "requirements.md", "req")
        r = H.run_cli(self.repo, "next", env=OFF)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(core.read_state(self.repo)["phase"], 2)
        self.assertEqual(H.run_cli(self.repo, "status", env=OFF).returncode, 0)


class ExplicitGateTools(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)
        self.hook_file = self.repo / ".git" / "hooks" / "pre-push"

    def test_explicit_install_githook_works_while_disabled(self):
        r = H.run_cli(self.repo, "install-githook", env=OFF)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("# agentic-framework pre-push", self.hook_file.read_text(encoding="utf-8"))

    def test_explicit_install_githook_still_refuses_foreign_hook(self):
        self.hook_file.parent.mkdir(parents=True, exist_ok=True)
        self.hook_file.write_bytes(FOREIGN)
        r = H.run_cli(self.repo, "install-githook", env=OFF)
        self.assertEqual(r.returncode, 1)
        self.assertIn("REFUSED", r.stdout)
        self.assertEqual(self.hook_file.read_bytes(), FOREIGN)

    def test_gate_check_passes_while_disabled(self):
        H.set_state(self.repo, phase=1, mode="hard")
        r = H.run_cli(self.repo, "gate-check", env=OFF)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_gate_check_blocks_when_enabled(self):
        H.set_state(self.repo, phase=1, mode="hard")
        r = H.run_cli(self.repo, "gate-check", env=ON)
        self.assertEqual(r.returncode, 1)
        self.assertIn("push blocked", r.stderr)

    def test_gate_check_with_enabled_and_no_sprint_passes(self):
        self.assertEqual(H.run_cli(self.repo, "gate-check", env=ON).returncode, 0)

    @unittest.skipUnless(shutil.which("sh"), "sh not available")
    def test_real_push_through_explicitly_installed_hook_follows_the_switch(self):
        remote = H.tmpdir(self) / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True, env=H.GIT_ENV)
        H.git(self.repo, "remote", "add", "origin", str(remote))
        H.set_state(self.repo, phase=1, mode="hard")
        self.assertEqual(H.run_cli(self.repo, "install-githook", env=OFF).returncode, 0)

        def push(env_extra):
            env = dict(H.GIT_ENV, **env_extra)
            return subprocess.run(["git", "push", "origin", "HEAD:refs/heads/main"], cwd=str(self.repo),
                                  capture_output=True, text=True, env=env, timeout=120)

        blocked = push(ON)
        self.assertNotEqual(blocked.returncode, 0, blocked.stdout + blocked.stderr)
        self.assertIn("push blocked", blocked.stderr)
        allowed = push(OFF)
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)


if __name__ == "__main__":
    unittest.main()
