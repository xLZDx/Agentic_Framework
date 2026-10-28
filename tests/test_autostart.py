"""tools/af_autostart.py with VSCODE_TASKS/LOG redirected to temp paths and subprocess.run patched."""
import json
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

import afhelpers as H
from afhelpers import ROOT

import af_autostart as A  # noqa: E402  (tools/ is on sys.path via afhelpers)

LABEL = "Agentic_Framework autostart"
OTHER = {"label": "build", "type": "shell", "command": "make"}


class Base(unittest.TestCase):
    def setUp(self):
        d = H.tmpdir(self)
        self.tasks = d / "vs" / "tasks.json"
        self.log = d / "logs" / "af.log"
        for attr, val in (("VSCODE_TASKS", self.tasks), ("LOG", self.log)):
            p = mock.patch.object(A, attr, val)
            p.start()
            self.addCleanup(p.stop)
        # safety net: any unpatched subprocess call in these tests fails loudly
        p = mock.patch.object(A.subprocess, "run", side_effect=AssertionError("unexpected real subprocess"))
        self.run_mock = p.start()
        self.addCleanup(p.stop)

    def data(self):
        return json.loads(self.tasks.read_text(encoding="utf-8"))

    def ours(self):
        return [t for t in self.data()["tasks"] if t.get("label") == LABEL]


class VsCode(Base):
    def test_register_creates_file_with_single_folderopen_task(self):
        self.assertEqual(A.cmd_register_vscode(None), 0)
        d = self.data()
        self.assertEqual(d["version"], "2.0.0")
        self.assertEqual(len(d["tasks"]), 1)
        t = d["tasks"][0]
        self.assertEqual(t["label"], LABEL)
        self.assertEqual(t["runOptions"], {"runOn": "folderOpen"})
        self.assertEqual(t["command"], sys.executable)
        self.assertEqual(t["args"][1], "run")
        self.assertTrue(t["args"][0].endswith("af_autostart.py"))

    def test_preserves_other_tasks_and_top_level_keys(self):
        self.tasks.parent.mkdir(parents=True)
        self.tasks.write_text(json.dumps({"version": "2.0.0", "tasks": [OTHER], "inputs": [1]}), encoding="utf-8")
        A.cmd_register_vscode(None)
        d = self.data()
        self.assertIn(OTHER, d["tasks"])
        self.assertEqual(len(d["tasks"]), 2)
        self.assertEqual(d["inputs"], [1])

    def test_idempotent_no_duplicates(self):
        for _ in range(3):
            A.cmd_register_vscode(None)
        self.assertEqual(len(self.ours()), 1)
        self.assertEqual(len(self.data()["tasks"]), 1)

    def test_rerun_refreshes_stale_definition(self):
        self.tasks.parent.mkdir(parents=True)
        stale = {"label": LABEL, "command": "old", "runOptions": {"runOn": "default"}}
        self.tasks.write_text(json.dumps({"version": "2.0.0", "tasks": [OTHER, stale]}), encoding="utf-8")
        A.cmd_register_vscode(None)
        o = self.ours()
        self.assertEqual(len(o), 1)
        self.assertEqual(o[0]["runOptions"]["runOn"], "folderOpen")
        self.assertIn(OTHER, self.data()["tasks"])

    def test_unregister_removes_only_ours(self):
        self.tasks.parent.mkdir(parents=True)
        self.tasks.write_text(json.dumps({"version": "2.0.0", "tasks": [OTHER]}), encoding="utf-8")
        A.cmd_register_vscode(None)
        self.run_mock.side_effect = None
        self.run_mock.return_value = SimpleNamespace(returncode=0, stdout="ok", stderr="")
        self.assertEqual(A.cmd_unregister(None), 0)
        self.assertEqual(self.data()["tasks"], [OTHER])
        argv = self.run_mock.call_args[0][0]
        self.assertEqual(argv[:2], ["schtasks", "/Delete"])
        self.assertIn(A.TASK, argv)

    def test_unregister_without_file_does_not_create_it(self):
        self.run_mock.side_effect = None
        self.run_mock.return_value = SimpleNamespace(returncode=1, stdout="", stderr="not found")
        self.assertEqual(A.cmd_unregister(None), 0)
        self.assertFalse(self.tasks.exists())

    def test_unregister_when_our_task_absent_leaves_file_bytes(self):
        self.tasks.parent.mkdir(parents=True)
        self.tasks.write_bytes(b'{"version": "2.0.0", "tasks": []}')
        self.run_mock.side_effect = None
        self.run_mock.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        A.cmd_unregister(None)
        self.assertEqual(self.tasks.read_bytes(), b'{"version": "2.0.0", "tasks": []}')


class Run(Base):
    def test_run_logs_deploy_and_install_and_returns_0(self):
        self.run_mock.side_effect = None
        self.run_mock.return_value = SimpleNamespace(returncode=0, stdout="a\nlast line\n", stderr="")
        self.assertEqual(A.cmd_run(None), 0)
        text = self.log.read_text(encoding="utf-8")
        lines = text.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("deploy exit=0", lines[0])
        self.assertIn("install exit=0", lines[1])
        self.assertIn("last line", lines[0])
        calls = [c[0][0] for c in self.run_mock.call_args_list]
        self.assertTrue(calls[0][1].endswith("af_cli.py") and calls[0][2] == "deploy")
        self.assertTrue(calls[1][1].endswith("af_install.py"))
        self.assertEqual(len(calls), 2)

    def test_run_returns_0_when_a_step_raises_and_continues(self):
        def fake(args, **kw):
            if args[1].endswith("af_cli.py"):
                raise OSError("boom")
            return SimpleNamespace(returncode=0, stdout="done", stderr="")
        self.run_mock.side_effect = fake
        self.assertEqual(A.cmd_run(None), 0)
        lines = self.log.read_text(encoding="utf-8").splitlines()
        self.assertIn("deploy error=boom", lines[0])
        self.assertIn("install exit=0", lines[1])

    def test_run_logs_nonzero_exit_but_returns_0(self):
        self.run_mock.side_effect = None
        self.run_mock.return_value = SimpleNamespace(returncode=3, stdout="", stderr="bad")
        self.assertEqual(A.cmd_run(None), 0)
        self.assertIn("deploy exit=3", self.log.read_text(encoding="utf-8"))

    def test_run_appends_across_invocations(self):
        self.run_mock.side_effect = None
        self.run_mock.return_value = SimpleNamespace(returncode=0, stdout="x", stderr="")
        A.cmd_run(None)
        A.cmd_run(None)
        self.assertEqual(len(self.log.read_text(encoding="utf-8").splitlines()), 4)

    def test_run_paths_point_into_framework_checkout(self):
        self.run_mock.side_effect = None
        self.run_mock.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")
        A.cmd_run(None)
        for c in self.run_mock.call_args_list:
            self.assertTrue(c[0][0][1].startswith(str(ROOT)))


class Register(Base):
    def test_register_builds_schtasks_create_argv(self):
        self.run_mock.side_effect = None
        self.run_mock.return_value = SimpleNamespace(returncode=0, stdout="SUCCESS", stderr="")
        self.assertEqual(A.cmd_register(None), 0)
        argv = self.run_mock.call_args[0][0]
        self.assertEqual(argv[0], "schtasks")
        self.assertEqual(argv[1], "/Create")
        self.assertIn("/F", argv)
        self.assertEqual(argv[argv.index("/SC") + 1], "ONLOGON")
        self.assertEqual(argv[argv.index("/TN") + 1], A.TASK)
        self.assertEqual(argv[argv.index("/RL") + 1], "LIMITED")
        tr = argv[argv.index("/TR") + 1]
        self.assertIn(A._pythonw(), tr)
        self.assertIn("af_autostart.py", tr)
        self.assertTrue(tr.endswith(" run"))
        self.assertIn("python", A._pythonw().lower())
        self.assertEqual(self.run_mock.call_count, 1)

    def test_register_propagates_failure_code(self):
        self.run_mock.side_effect = None
        self.run_mock.return_value = SimpleNamespace(returncode=5, stdout="", stderr="denied")
        self.assertEqual(A.cmd_register(None), 5)

    def test_pythonw_prefers_sibling_when_exists_else_python(self):
        d = H.tmpdir(self)
        fake_py = d / "python.exe"
        fake_py.write_bytes(b"")
        with mock.patch.object(A, "PY", str(fake_py)):
            self.assertEqual(A._pythonw(), str(fake_py))
            (d / "pythonw.exe").write_bytes(b"")
            self.assertEqual(A._pythonw(), str(d / "pythonw.exe"))


if __name__ == "__main__":
    unittest.main()
