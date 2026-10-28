"""is_push_command tokenised detection and its effect on gate_decision."""
import unittest

import afhelpers as H
from afhelpers import hook

POSITIVE = [
    "git push",
    "git push origin main",
    "git -C x push",
    "git -C /some/path push origin HEAD",
    "git -c a=b push",
    "git -c user.name=x -C y push --force",
    "git --git-dir=.git push",
    "git --no-pager push",
    "cd a && git push",
    "cd a; git push",
    "make test || git push",
    "echo hi | git push",
    "FOO=1 git push",
    "FOO=1 BAR=2 git push",
    "git.exe push",
    '"C:\\Program Files\\Git\\bin\\git.exe" push',
    '"C:/Program Files/Git/bin/git.exe" push',
    '"C:\Program Files\Git\cmd\git.exe" push',
    r"C:\tools\git.exe push",
    "/usr/bin/git push",
    "gh pr create",
    "gh pr create --title x",
    "gh pr merge 3",
    "gh.exe pr merge 3 --squash",
    "git status\ngit push",
]

NEGATIVE = [
    'git commit -m "fix push bug"',
    "git log --grep push",
    "git stash push",
    "git status",
    "git diff",
    "git pull",
    "echo git push",
    'echo "git push"',
    "git push-helper-foo",
    "gh pr view 3",
    "gh pr list",
    "gh issue create",
    "pushd /tmp",
    "python push.py",
    "",
]


class IsPushCommand(unittest.TestCase):
    def test_positive(self):
        for c in POSITIVE:
            with self.subTest(cmd=c):
                self.assertTrue(hook.is_push_command(c), c)

    def test_negative(self):
        for c in NEGATIVE:
            with self.subTest(cmd=c):
                self.assertFalse(hook.is_push_command(c), c)

    def test_unbalanced_quote_does_not_crash(self):
        self.assertIsInstance(hook.is_push_command('git commit -m "oops'), bool)


class GateDecisionHard(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)

    def test_non_push_allowed_before_phase_8(self):
        H.set_state(self.repo, phase=3, mode="hard")
        for c in NEGATIVE + ["git commit -m x", "pytest -q", "ls"]:
            with self.subTest(cmd=c):
                self.assertIsNone(hook.gate_decision(self.repo, c))

    def test_push_denied_before_phase_8_for_every_positive_form(self):
        H.set_state(self.repo, phase=3, mode="hard")
        for c in POSITIVE:
            with self.subTest(cmd=c):
                r = hook.gate_decision(self.repo, c)
                self.assertIsNotNone(r)
                self.assertIn("phase is 3", r)

    def test_phase8_without_approval_denies_push_but_allows_non_push(self):
        H.set_state(self.repo, phase=8, mode="hard")
        self.assertIsNotNone(hook.gate_decision(self.repo, "git push"))
        self.assertIsNone(hook.gate_decision(self.repo, 'git commit -m "push fix"'))

    def test_substring_regression_not_blocked(self):
        # the original bug: substring match blocked these
        H.set_state(self.repo, phase=1, mode="hard")
        for c in ('git commit -m "fix push bug"', "git log --grep push", "git stash push"):
            self.assertIsNone(hook.gate_decision(self.repo, c), c)

    def test_soft_mode_allows_push(self):
        H.set_state(self.repo, phase=1, mode="soft")
        self.assertIsNone(hook.gate_decision(self.repo, "git push"))


if __name__ == "__main__":
    unittest.main()
