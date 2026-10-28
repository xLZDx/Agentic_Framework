"""Hardening round: push-detection bypasses, hash-manifest installer, pre-push on `on`, no tracked pyc."""
import hashlib
import json
import shutil
import subprocess
import unittest
from pathlib import Path

import afhelpers as H
from afhelpers import ROOT, hook, deploy

from test_af_install import InstallBase, af_hook_cmds, FW_POSIX, run, tree

BYPASS_POSITIVE = [
    "env git push",
    "env FOO=1 git push origin main",
    "env -i git push",
    "command git push",
    "exec git push",
    "nice git push",
    "nice -n 5 git push",
    "nohup git push",
    "time git push",
    "sudo git push",
    "sudo -n git push",
    "timeout 30 git push",
    "stdbuf -oL git push",
    "builtin command git push",
    "sh -c 'git push'",
    'sh -c "git push origin HEAD"',
    "bash -c 'cd x && git push'",
    'bash -lc "cd x && git push"',
    "zsh -c 'git push'",
    "cmd /c git push",
    "cmd.exe /c git push origin main",
    'powershell -Command "git push"',
    "pwsh -c 'git push'",
    "pwsh -Command git push",
    "(git push)",
    "(cd x && git push)",
    "$(git push)",
    "`git push`",
    "if true; then git push; fi",
    "for i in 1; do git push; done",
    "if true; then gh pr create; fi",
    "{ git push; }",
    "! git push",
    "sh -c \"sudo -n env FOO=1 git push\"",
    "bash -c \"sh -c 'git push'\"",
    "echo ok && sudo gh pr merge 3",
    r"C:\tools\git.exe push",
    '"C:\\Program Files\\Git\\cmd\\git.exe" push',
]

BYPASS_NEGATIVE = [
    "echo git push",
    "echo 'git push'",
    'git commit -m "a; git push"',
    "git commit -m 'a && git push'",
    "git log --grep='x | git push'",
    'sh -c "echo git push"',
    "env FOO=1 git status",
    "sudo -n ls",
    "timeout 30 pytest",
    "cmd /c dir",
    'powershell -Command "Get-ChildItem"',
    "git stash push",
    "gh pr view 3",
]


class PushBypass(unittest.TestCase):
    def test_positive(self):
        for c in BYPASS_POSITIVE:
            with self.subTest(cmd=c):
                self.assertTrue(hook.is_push_command(c), c)

    def test_negative(self):
        for c in BYPASS_NEGATIVE:
            with self.subTest(cmd=c):
                self.assertFalse(hook.is_push_command(c), c)

    def test_gh_pr_short_forms_do_not_raise_and_are_not_push(self):
        for c in ("gh", "gh pr", "gh pr ", "gh.exe pr", "git", "git -C", "sh -c", "env", "sudo", "cmd /c",
                  "powershell -Command", "(", ")", "'", '"', "``", "&&", ";", "env -"):
            with self.subTest(cmd=c):
                self.assertFalse(hook.is_push_command(c))

    def test_malformed_quotes_do_not_raise(self):
        for c in ('git push "', "echo 'a; git push", 'sh -c "git push'):
            with self.subTest(cmd=c):
                self.assertIsInstance(hook.is_push_command(c), bool)

    def test_deep_nesting_terminates(self):
        c = "git push"
        for _ in range(8):
            c = "sh -c " + json.dumps(c)
        self.assertIsInstance(hook.is_push_command(c), bool)  # depth-capped; must terminate, not raise

    def test_gate_decision_blocks_bypass_forms_and_allows_negatives(self):
        repo = H.make_repo(self)
        H.set_state(repo, phase=3, mode="hard")
        for c in BYPASS_POSITIVE:
            with self.subTest(cmd=c):
                self.assertIsNotNone(hook.gate_decision(repo, c))
        for c in BYPASS_NEGATIVE + ["gh pr", "gh"]:
            with self.subTest(cmd=c):
                self.assertIsNone(hook.gate_decision(repo, c))  # `gh pr` alone: fails OPEN (not a push)

    def test_pretooluse_hook_denies_wrapped_push_end_to_end(self):
        repo = H.make_repo(self)
        H.set_state(repo, phase=2, mode="hard")
        for c in ("env git push", 'bash -lc "cd x && git push"', "sudo -n git push"):
            ev = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(repo),
                             "tool_input": {"command": c}})
            r = H.run_cli(repo, "hook", stdin=ev)
            self.assertIn('"deny"', r.stdout, c)
        ev = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": str(repo),
                         "tool_input": {"command": 'git commit -m "a; git push"'}})
        self.assertEqual(H.run_cli(repo, "hook", stdin=ev).stdout.strip(), "")


class HashManifestInstaller(InstallBase):
    def manifest(self, home):
        return json.loads((home / "af-install-manifest.json").read_text(encoding="utf-8"))

    def test_manifest_is_path_to_sha256_of_installed_bytes(self):
        self.go()
        m = self.manifest(self.ch)
        self.assertIsInstance(m, dict)
        self.assertTrue(m)
        for path, h in m.items():
            self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(), h, path)

    def test_user_edit_is_kept_on_refresh_and_manifest_keeps_old_hash(self):
        self.go()
        f = self.ch / "agents" / "architect.md"
        old_hash = self.manifest(self.ch)[str(f)]
        f.write_bytes(b"my customised architect\n")
        r = self.go()
        self.assertEqual(f.read_bytes(), b"my customised architect\n")
        self.assertIn("MODIFIED", r.stdout)
        self.assertIn(str(f), r.stdout)
        self.assertEqual(self.manifest(self.ch)[str(f)], old_hash)
        # still kept on a third run
        self.go()
        self.assertEqual(f.read_bytes(), b"my customised architect\n")
        self.assertEqual(self.manifest(self.ch)[str(f)], old_hash)

    def test_unedited_file_is_refreshed_when_source_changes(self):
        self.go()
        f = self.ch / "agents" / "planner.md"
        m = self.manifest(self.ch)
        # simulate an older shipped version: file == what we wrote earlier but content differs from source now
        old = b"old shipped planner\n"
        f.write_bytes(old)
        mm = self.manifest(self.ch)
        mm[str(f)] = hashlib.sha256(old).hexdigest()
        (self.ch / "af-install-manifest.json").write_text(json.dumps(mm), encoding="utf-8")
        r = self.go()
        self.assertNotEqual(f.read_bytes(), old)
        self.assertNotIn(f"MODIFIED {f}", r.stdout)
        self.assertEqual(self.manifest(self.ch)[str(f)], hashlib.sha256(f.read_bytes()).hexdigest())

    def test_uninstall_keeps_edited_and_removes_unmodified(self):
        self.go()
        edited = self.ch / "agents" / "architect.md"
        untouched = self.ch / "agents" / "planner.md"
        edited.write_bytes(b"mine\n")
        r = self.go("--uninstall")
        self.assertTrue(edited.is_file())
        self.assertEqual(edited.read_bytes(), b"mine\n")
        self.assertIn("KEPT", r.stdout)
        self.assertIn(str(edited), r.stdout)
        self.assertFalse(untouched.exists())
        self.assertFalse((self.ch / "skills" / "af" / "SKILL.md").exists())
        self.assertEqual(af_hook_cmds(self.settings()), [])

    def test_uninstall_keeps_edited_codex_prompt(self):
        self.go()
        p = self.cx / "prompts" / "af.md"
        p.write_bytes(p.read_bytes() + b"\nmy note\n")
        self.go("--uninstall")
        self.assertTrue(p.is_file())
        self.assertIn(b"my note", p.read_bytes())
        self.assertFalse((self.cx / "agents" / "planner.toml").exists())

    def test_uninstall_keeps_manifest_entry_for_kept_file_until_reverted(self):
        self.go()
        f = self.ch / "agents" / "architect.md"
        orig = f.read_bytes()
        old_hash = self.manifest(self.ch)[str(f)]
        f.write_bytes(b"edited" + bytes([10]))
        self.go("--uninstall")
        self.assertTrue(f.is_file())
        self.assertTrue((self.ch / "af-install-manifest.json").is_file())
        m = self.manifest(self.ch)
        self.assertEqual(m, {str(f): old_hash})  # only the kept file remains tracked, old hash intact
        r = self.go("--uninstall")
        self.assertIn("KEPT", r.stdout)
        self.assertEqual(f.read_bytes(), b"edited" + bytes([10]))
        self.assertEqual(self.manifest(self.ch), {str(f): old_hash})
        f.write_bytes(orig)  # user reverts to the installed bytes
        self.go("--uninstall")
        self.assertFalse(f.exists())
        self.assertFalse((self.ch / "af-install-manifest.json").exists())

    def test_legacy_list_manifest_is_migrated_to_hashes(self):
        self.go()
        m = self.manifest(self.ch)
        (self.ch / "af-install-manifest.json").write_text(json.dumps(sorted(m)), encoding="utf-8")
        r = self.go()
        new = self.manifest(self.ch)
        self.assertIsInstance(new, dict)
        self.assertEqual(set(new), set(m))
        self.assertEqual(new, m)
        self.assertNotIn("SKIPPED", r.stdout)
        # migrated manifest still protects later user edits
        f = self.ch / "agents" / "architect.md"
        f.write_bytes(b"edit after migration\n")
        self.go()
        self.assertEqual(f.read_bytes(), b"edit after migration\n")

    def test_legacy_manifest_uninstall_works(self):
        self.go()
        m = self.manifest(self.ch)
        (self.ch / "af-install-manifest.json").write_text(json.dumps(sorted(m)), encoding="utf-8")
        self.go("--uninstall")
        self.assertFalse((self.ch / "agents" / "architect.md").exists())

    def test_foreign_differing_file_still_skipped_and_untracked(self):
        (self.ch / "agents").mkdir()
        mine = self.ch / "agents" / "planner.md"
        mine.write_bytes(b"foreign\n")
        r = self.go()
        self.assertIn("SKIPPED", r.stdout)
        self.assertEqual(mine.read_bytes(), b"foreign\n")
        self.assertNotIn(str(mine), self.manifest(self.ch))
        self.go("--uninstall")
        self.assertEqual(mine.read_bytes(), b"foreign\n")


class IdenticalForeignFile(InstallBase):
    def manifest(self, home):
        return json.loads((home / "af-install-manifest.json").read_text(encoding="utf-8"))

    def rendered(self, home_name="claude", rel="agents/architect.md"):
        src = ROOT / "deploy" / home_name / rel
        return src.read_text(encoding="utf-8").replace("{fw}", FW_POSIX).encode("utf-8")

    def test_identical_preexisting_file_not_owned_survives_uninstall(self):
        f = self.ch / "agents" / "architect.md"
        f.parent.mkdir(parents=True)
        f.write_bytes(self.rendered())
        r = self.go()
        self.assertIn("SAME", r.stdout)
        self.assertNotIn(str(f), self.manifest(self.ch))
        self.assertIn(str(self.ch / "agents" / "planner.md"), self.manifest(self.ch))
        self.go("--uninstall")
        self.assertTrue(f.is_file())
        self.assertEqual(f.read_bytes(), self.rendered())
        self.assertFalse((self.ch / "agents" / "planner.md").exists())

    def test_identical_file_stays_unowned_across_reinstalls(self):
        f = self.ch / "agents" / "architect.md"
        f.parent.mkdir(parents=True)
        f.write_bytes(self.rendered())
        self.go()
        self.go()
        self.assertNotIn(str(f), self.manifest(self.ch))
        self.go("--uninstall")
        self.assertTrue(f.is_file())

    def test_identical_codex_foreign_file_survives_uninstall(self):
        f = self.cx / "agents" / "architect.toml"
        f.parent.mkdir(parents=True)
        f.write_bytes(self.rendered("codex", "agents/architect.toml"))
        self.go()
        self.assertNotIn(str(f), self.manifest(self.cx))
        self.go("--uninstall")
        self.assertTrue(f.is_file())

    def test_identical_file_that_was_in_previous_manifest_is_still_tracked_and_removed(self):
        self.go()
        f = self.ch / "agents" / "architect.md"
        self.assertIn(str(f), self.manifest(self.ch))
        self.go()  # SAME on a file we own
        self.assertIn(str(f), self.manifest(self.ch))
        self.go("--uninstall")
        self.assertFalse(f.exists())


class StaleHooks(InstallBase):
    def stale(self, event_cmds=None):
        old = "python D:/old/checkout/tools/af_cli.py hook"
        foreign = {"hooks": [{"type": "command", "command": "python keep.py"}]}
        s = {"hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": old}]}, foreign],
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": old}]}],
            "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": old}]},
                           {"matcher": "Edit", "hooks": [{"type": "command", "command": "python guard.py"}]}],
        }}
        (self.ch / "settings.json").write_text(json.dumps(s), encoding="utf-8")
        return foreign

    def test_stale_path_replaced_single_hook_per_event_foreign_preserved(self):
        foreign = self.stale()
        self.go()
        s = self.settings()
        want = f"python {FW_POSIX}/tools/af_cli.py hook"
        for ev in ("SessionStart", "UserPromptSubmit", "PreToolUse"):
            ours = [h["command"] for e in s["hooks"][ev] for h in e["hooks"] if "af_cli.py hook" in h["command"]]
            self.assertEqual(ours, [want], ev)
        self.assertIn(foreign, s["hooks"]["SessionStart"])
        cmds = [h["command"] for e in s["hooks"]["PreToolUse"] for h in e["hooks"]]
        self.assertIn("python guard.py", cmds)
        self.assertNotIn("D:/old/checkout", json.dumps(s))
        matcher = [e for e in s["hooks"]["PreToolUse"] if any("af_cli.py" in h["command"] for h in e["hooks"])]
        self.assertEqual(matcher[0]["matcher"], "Bash")

    def test_stale_replacement_is_idempotent_and_backed_up(self):
        self.stale()
        orig = (self.ch / "settings.json").read_bytes()
        self.go()
        bak = list(self.ch.glob("settings.json.bak-af-*"))
        self.assertEqual(len(bak), 1)
        self.assertEqual(bak[0].read_bytes(), orig)
        snap = (self.ch / "settings.json").read_bytes()
        self.go()
        self.assertEqual((self.ch / "settings.json").read_bytes(), snap)
        self.assertEqual(len(list(self.ch.glob("settings.json.bak-af-*"))), 1)
        self.assertEqual(len(af_hook_cmds(self.settings())), 3)

    def test_uninstall_removes_only_ours_and_keeps_foreign(self):
        foreign = self.stale()
        self.go()
        self.go("--uninstall")
        s = self.settings()
        self.assertEqual(af_hook_cmds(s), [])
        self.assertEqual(s["hooks"]["SessionStart"], [foreign])
        self.assertEqual(len(s["hooks"]["PreToolUse"]), 1)
        self.assertNotIn("UserPromptSubmit", s["hooks"])

    def test_duplicate_stale_entries_collapse_to_one(self):
        old = {"hooks": [{"type": "command", "command": "python /a/tools/af_cli.py hook"}]}
        s = {"hooks": {"SessionStart": [old, old, old]}}
        (self.ch / "settings.json").write_text(json.dumps(s), encoding="utf-8")
        self.go()
        self.assertEqual(len(af_hook_cmds({"hooks": {"SessionStart": self.settings()["hooks"]["SessionStart"]}})), 1)


def has_sh():
    return shutil.which("sh") is not None


class OnInstallsPrePush(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)
        self.remote = H.tmpdir(self) / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(self.remote)], check=True, env=H.GIT_ENV)
        H.git(self.repo, "remote", "add", "origin", str(self.remote))
        self.hook_file = self.repo / ".git" / "hooks" / "pre-push"

    def push(self, shell_cmd):
        return subprocess.run(["sh", "-c", shell_cmd], cwd=str(self.repo), capture_output=True, text=True,
                              env=H.GIT_ENV, timeout=120)

    def remote_has_commits(self):
        r = subprocess.run(["git", "-C", str(self.remote), "rev-list", "--all", "--count"],
                           capture_output=True, text=True)
        return int(r.stdout.strip() or 0)

    def test_on_installs_prepush_on_new_and_resumed_sprint(self):
        self.assertFalse(self.hook_file.exists())
        self.assertEqual(H.run_cli(self.repo, "on").returncode, 0)
        self.assertIn("# agentic-framework pre-push", self.hook_file.read_text(encoding="utf-8"))
        self.hook_file.unlink()
        H.run_cli(self.repo, "off")
        H.run_cli(self.repo, "on")  # resume path installs too
        self.assertTrue(self.hook_file.is_file())

    @unittest.skipUnless(has_sh(), "sh not available")
    def test_real_push_blocked_before_phase_8_even_through_env_and_sh(self):
        H.run_cli(self.repo, "on")
        for cmd in ("git push origin HEAD:refs/heads/main",
                    "env git push origin HEAD:refs/heads/main",
                    "sh -c 'git push origin HEAD:refs/heads/main'"):
            with self.subTest(cmd=cmd):
                r = self.push(cmd)
                self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("push blocked", r.stderr)
                self.assertEqual(self.remote_has_commits(), 0)

    @unittest.skipUnless(has_sh(), "sh not available")
    def test_push_allowed_after_off(self):
        H.run_cli(self.repo, "on")
        H.run_cli(self.repo, "off")
        r = self.push("git push origin HEAD:refs/heads/main")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.remote_has_commits(), 1)

    @unittest.skipUnless(has_sh(), "sh not available")
    def test_soft_mode_prepush_allows_push(self):
        H.run_cli(self.repo, "on", "--mode", "soft")
        r = self.push("git push origin HEAD:refs/heads/main")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    FOREIGN = b"#!/bin/sh\necho mine\n"

    def seed_foreign(self):
        self.hook_file.parent.mkdir(parents=True, exist_ok=True)
        self.hook_file.write_bytes(self.FOREIGN)

    def state_file(self):
        return H.sdlc(self.repo) / "state.json"

    def test_hard_on_with_foreign_prepush_refused_no_state(self):
        self.seed_foreign()
        r = H.run_cli(self.repo, "on")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("NOT enabled", r.stdout)
        self.assertIn("--mode soft", r.stdout)
        self.assertFalse(self.state_file().exists())
        self.assertEqual(self.hook_file.read_bytes(), self.FOREIGN)

    def test_hard_start_with_foreign_prepush_refused_no_state(self):
        self.seed_foreign()
        r = H.run_cli(self.repo, "start", "S")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertFalse(self.state_file().exists())
        self.assertEqual(self.hook_file.read_bytes(), self.FOREIGN)

    def test_mode_hard_with_foreign_prepush_refused_state_unchanged(self):
        H.set_state(self.repo, phase=3, mode="soft")
        self.seed_foreign()
        before = self.state_file().read_bytes()
        r = H.run_cli(self.repo, "mode", "hard")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(self.state_file().read_bytes(), before)
        self.assertEqual(H.core.read_state(self.repo)["mode"], "soft")
        self.assertEqual(self.hook_file.read_bytes(), self.FOREIGN)

    def test_mode_soft_with_foreign_prepush_allowed(self):
        H.set_state(self.repo, phase=3, mode="hard")
        self.seed_foreign()
        r = H.run_cli(self.repo, "mode", "soft")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(H.core.read_state(self.repo)["mode"], "soft")
        self.assertEqual(self.hook_file.read_bytes(), self.FOREIGN)

    def test_soft_on_and_start_with_foreign_prepush_succeed_with_warning(self):
        self.seed_foreign()
        r = H.run_cli(self.repo, "on", "--mode", "soft")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("REFUSED", r.stdout)  # warning that the gate could not be installed
        st = H.core.read_state(self.repo)
        self.assertEqual((st["mode"], st["phase"], st["paused"]), ("soft", 1, False))
        self.assertEqual(self.hook_file.read_bytes(), self.FOREIGN)
        # start in soft mode in a fresh repo with a foreign hook
        repo2 = H.make_repo(self)
        h2 = repo2 / ".git" / "hooks" / "pre-push"
        h2.parent.mkdir(parents=True, exist_ok=True)
        h2.write_bytes(self.FOREIGN)
        r = H.run_cli(repo2, "start", "S", "--mode", "soft")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(H.core.read_state(repo2)["mode"], "soft")
        self.assertEqual(h2.read_bytes(), self.FOREIGN)

    def test_resume_paused_hard_sprint_with_foreign_prepush_refused_stays_paused(self):
        H.set_state(self.repo, phase=4, mode="hard", paused=True)
        self.seed_foreign()
        before = self.state_file().read_bytes()
        r = H.run_cli(self.repo, "on")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        st = H.core.read_state(self.repo)
        self.assertTrue(st["paused"])
        self.assertEqual(st["phase"], 4)
        self.assertEqual(self.state_file().read_bytes(), before)
        self.assertEqual(self.hook_file.read_bytes(), self.FOREIGN)

    def test_resume_paused_hard_sprint_with_our_own_hook_succeeds(self):
        H.run_cli(self.repo, "on")
        H.run_cli(self.repo, "off")
        self.assertTrue(H.core.read_state(self.repo)["paused"])
        r = H.run_cli(self.repo, "on")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(H.core.read_state(self.repo)["paused"])
        self.assertIn("# agentic-framework pre-push", self.hook_file.read_text(encoding="utf-8"))

    def test_resume_soft_paused_with_foreign_prepush_succeeds(self):
        H.set_state(self.repo, phase=4, mode="soft", paused=True)
        self.seed_foreign()
        r = H.run_cli(self.repo, "on")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(H.core.read_state(self.repo)["paused"])

    def test_hard_on_with_our_stale_hook_rewrites_it(self):
        self.hook_file.parent.mkdir(parents=True, exist_ok=True)
        self.hook_file.write_text("#!/bin/sh\n# agentic-framework pre-push\npython /old/af_cli.py gate-check\n",
                                  encoding="utf-8")
        r = H.run_cli(self.repo, "on")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("/old/af_cli.py", self.hook_file.read_text(encoding="utf-8"))

    def test_on_twice_keeps_single_our_hook(self):
        H.run_cli(self.repo, "on")
        first = self.hook_file.read_bytes()
        H.run_cli(self.repo, "on")
        self.assertEqual(self.hook_file.read_bytes(), first)


class NoTrackedBytecode(unittest.TestCase):
    def test_git_ls_files_has_no_pyc_or_pycache(self):
        r = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True)
        if r.returncode != 0:
            self.skipTest("not a git checkout: " + r.stderr.strip())
        bad = [f for f in r.stdout.splitlines() if f.endswith(".pyc") or "__pycache__" in f]
        self.assertEqual(bad, [])

    def test_gitignore_covers_pycache(self):
        r = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", "tools/af/__pycache__/x.pyc"],
                           capture_output=True)
        self.assertEqual(r.returncode, 0, "tools/af/__pycache__ is not git-ignored")


if __name__ == "__main__":
    unittest.main()
