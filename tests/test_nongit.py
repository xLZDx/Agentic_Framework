"""af_cli run outside a git repository: friendly error, non-zero exit, no traceback, no state written."""
import unittest

import afhelpers as H


class NotAGitRepo(unittest.TestCase):
    def setUp(self):
        self.d = H.tmpdir(self)  # plain temp dir, no git

    def check(self, r):
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Not inside a git repository", r.stderr)
        self.assertIn("--project", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertNotIn("RuntimeError", r.stderr)
        self.assertFalse((self.d / "docs").exists(), "no state may be written outside a repo")

    def test_status_and_on_and_friends_from_cwd(self):
        for args in (("status",), ("on",), ("on", "--mode", "soft"), ("off",), ("start", "T"), ("next",),
                     ("migrate",), ("verify",), ("install-githook",), ("pause",), ("mode", "hard")):
            with self.subTest(cmd=args):
                self.check(H.run_cli(self.d, *args))

    def test_project_flag_pointing_to_non_git_dir(self):
        other = H.tmpdir(self)
        repo = H.make_repo(self)
        r = H.run_cli(repo, "--project", str(other), "status")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Not inside a git repository", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        self.assertFalse((other / "docs").exists())

    def test_project_flag_to_missing_path_is_friendly_or_clean(self):
        r = H.run_cli(self.d, "--project", str(self.d / "does-not-exist"), "status")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stderr)

    def test_inside_repo_still_works(self):
        repo = H.make_repo(self)
        self.assertEqual(H.run_cli(repo, "status").returncode, 0)


if __name__ == "__main__":
    unittest.main()
