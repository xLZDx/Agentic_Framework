import contextlib
import copy
import hashlib
import io
import json
import os
import shutil
import unittest
from unittest import mock

import afhelpers as H
from afhelpers import APPROVE, core, pm_review

NODE = shutil.which("node")


class Verify(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)

    def test_no_approval_fails(self):
        ok, why = pm_review.verify(self.repo)
        self.assertFalse(ok)
        self.assertIn("no code approval", why)

    def test_valid_approval_ok(self):
        h = H.write_approval(self.repo)
        ok, why = pm_review.verify(self.repo)
        self.assertTrue(ok, why)
        self.assertIn(h, why)

    def test_new_commit_invalidates(self):
        H.write_approval(self.repo)
        H.commit_file(self.repo)
        ok, why = pm_review.verify(self.repo)
        self.assertFalse(ok)
        self.assertIn("invalidates", why)

    def test_gate_md_missing(self):
        H.write_approval(self.repo, md=None)
        ok, why = pm_review.verify(self.repo)
        self.assertFalse(ok)
        self.assertIn("gate-approval.md", why)

    def test_gate_md_mismatched_head(self):
        H.write_approval(self.repo, md="Head: 0000000000000000000000000000000000000000\n")
        ok, why = pm_review.verify(self.repo)
        self.assertFalse(ok)
        self.assertIn("does not match", why)

    def test_dirty_tracked_file_after_approval(self):
        H.write_approval(self.repo)
        (self.repo / "README.md").write_text("changed\n", encoding="utf-8")
        ok, why = pm_review.verify(self.repo)
        self.assertFalse(ok)
        self.assertIn("uncommitted", why)

    def test_staged_change_counts_as_dirty(self):
        H.write_approval(self.repo)
        (self.repo / "README.md").write_text("changed\n", encoding="utf-8")
        H.git(self.repo, "add", "README.md")
        self.assertFalse(pm_review.verify(self.repo)[0])

    def test_untracked_file_does_not_invalidate(self):
        H.write_approval(self.repo)
        (self.repo / "scratch.txt").write_text("u\n", encoding="utf-8")
        self.assertTrue(pm_review.verify(self.repo)[0])

    def test_non_approve_verdicts_fail(self):
        for v in ("MINOR", "MAJOR", "BLOCKER", "approve", None):
            with self.subTest(verdict=v):
                H.write_approval(self.repo, verdict=v)
                ok, why = pm_review.verify(self.repo)
                self.assertFalse(ok)
                self.assertIn("does not unlock", why)

    def test_missing_ids_fail(self):
        for kw in ({"request_id": None}, {"reply_id": None}, {"request_id": ""}):
            with self.subTest(kw=kw):
                H.write_approval(self.repo, **kw)
                ok, why = pm_review.verify(self.repo)
                self.assertFalse(ok)
                self.assertIn("ids", why)

    def test_docs_kind_is_independent_of_code_kind(self):
        H.write_approval(self.repo, kind="docs")
        self.assertTrue(pm_review.verify(self.repo, "docs")[0])
        self.assertFalse(pm_review.verify(self.repo, "code")[0])

    def test_cli_verify_exit_codes(self):
        r = H.run_cli(self.repo, "verify")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stdout.startswith("FAIL"))
        H.write_approval(self.repo)
        r = H.run_cli(self.repo, "verify")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.startswith("OK"))


GOOD_EVIDENCE = chr(10).join(["# Evidence", "", "## Test evidence", "all green", "", "## NOT_RUN", "nothing", ""])


@unittest.skipUnless(NODE, "NOT_RUN: node is not available; fake review.js cannot be executed")
class Request(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)
        H.commit_file(self.repo, "a.txt")
        H.set_state(self.repo, phase=8)
        H.write_artifact(self.repo, "verify-evidence.md", GOOD_EVIDENCE)
        self.base = H.first_commit(self.repo)
        self.tools = H.tmpdir(self)
        (self.tools / "review.js").write_text(H.FAKE_REVIEW_JS, encoding="utf-8")

    def run_request(self, result=None, kind="code", repo=None, **opts):
        repo = repo or self.repo
        base = opts.pop("base", None) or (H.first_commit(repo) if repo != self.repo else self.base)
        cfg = {"result": result if result is not None else APPROVE,
               "argv_out": str(self.tools / "argv.json"), "packet_out": str(self.tools / "packet.md")}
        cfg.update(opts)
        (self.tools / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
        env = {"AF_PM_REVIEW_JS": str(self.tools / "review.js"), "FAKE_CFG": str(self.tools / "cfg.json")}
        with mock.patch.dict(os.environ, env):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = pm_review.request(repo, kind, base)
        return rc, buf.getvalue()

    def approval_files(self, repo=None, kind="code"):
        repo = repo or self.repo
        j = H.sdlc(repo) / ".pm-review" / ("approval.json" if kind == "code" else "approval-docs.json")
        m = H.sdlc(repo) / ("gate-approval.md" if kind == "code" else "docs-approval.md")
        return j, m

    def test_full_approve_writes_bound_approval_and_verifies(self):
        rc, out = self.run_request()
        self.assertEqual(rc, 0, out)
        self.assertIn("APPROVED", out)
        j, m = self.approval_files()
        a = json.loads(j.read_text(encoding="utf-8"))
        head = core.head(self.repo)
        self.assertEqual(a["head"], head)
        self.assertEqual(a["base"], self.base)
        self.assertEqual(a["verdict"], "APPROVE")
        self.assertEqual((a["request_id"], a["reply_id"], a["input_hash"]), ("req-1", "reply-1", "hash-1"))
        self.assertEqual(a["reply_sha256"], hashlib.sha256(APPROVE["reply"].encode()).hexdigest())
        self.assertIn(head, m.read_text(encoding="utf-8"))
        ok, why = pm_review.verify(self.repo)
        self.assertTrue(ok, why)
        # and a later commit revokes it
        H.commit_file(self.repo, "b.txt")
        self.assertFalse(pm_review.verify(self.repo)[0])

    def test_request_passes_exact_range_and_packet_to_review_js(self):
        H.write_artifact(self.repo, "verify-evidence.md", GOOD_EVIDENCE + "EVIDENCE-MARKER")
        rc, out = self.run_request()
        self.assertEqual(rc, 0, out)
        argv = json.loads((self.tools / "argv.json").read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--cwd") + 1], str(self.repo))
        self.assertEqual(argv[argv.index("--base") + 1], self.base)
        self.assertIn("--final", argv)
        packet = (self.tools / "packet.md").read_text(encoding="utf-8")
        self.assertIn(f"Exact HEAD under review: {core.head(self.repo)}", packet)
        self.assertIn("EVIDENCE-MARKER", packet)

    def test_missing_verify_evidence_is_refused_for_code(self):
        (H.sdlc(self.repo) / "verify-evidence.md").unlink()
        rc, out = self.run_request()
        self.assertEqual(rc, 2)
        self.assertIn("REFUSED", out)
        self.assertFalse((self.tools / "argv.json").exists())  # review.js never invoked

    def test_project_id_forwarded(self):
        cfg = {"result": APPROVE, "argv_out": str(self.tools / "argv.json"), "packet_out": str(self.tools / "packet.md")}
        (self.tools / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
        env = {"AF_PM_REVIEW_JS": str(self.tools / "review.js"), "FAKE_CFG": str(self.tools / "cfg.json")}
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(pm_review.request(self.repo, "code", self.base, project_id="proj-9"), 0)
        argv = json.loads((self.tools / "argv.json").read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--project") + 1], "proj-9")

    def test_docs_kind_writes_docs_approval_only(self):
        rc, out = self.run_request(kind="docs")
        self.assertEqual(rc, 0, out)
        j, m = self.approval_files(kind="docs")
        self.assertTrue(j.is_file() and m.is_file())
        self.assertTrue(pm_review.verify(self.repo, "docs")[0])
        self.assertFalse(self.approval_files(kind="code")[0].exists())
        self.assertFalse(pm_review.verify(self.repo, "code")[0])

    def test_rejected_results_write_no_approval(self):
        cases = {
            "uncorrelated": {"correlated": False},
            "correlated_missing": {"correlated": None},
            "truncated": {"truncated": True},
            "final_overridden": {"final_overridden": True},
            "not_final": {"final": False},
            "verdict_minor": {"verdict": "MINOR"},
            "verdict_major": {"verdict": "MAJOR"},
            "verdict_blocker": {"verdict": "BLOCKER"},
            "verdict_none": {"verdict": None},
            "verdict_contradiction": {"verdict_contradiction": True},
            "ok_false": {"ok": False},
            "timeout": {"review_status": "NOT_RUN_TIMEOUT"},
            "no_reply_id": {"replyId": ""},
            "no_request_id": {"reviewRequestId": None},
        }
        for label, patch in cases.items():
            with self.subTest(case=label):
                repo = H.make_repo(self)
                H.commit_file(repo, "a.txt")
                H.set_state(repo, phase=8)
                H.write_artifact(repo, "verify-evidence.md", GOOD_EVIDENCE)
                result = copy.deepcopy(APPROVE)
                result.update(patch)
                rc, out = self.run_request(result, repo=repo)
                self.assertEqual(rc, 1, out)
                self.assertIn("NOT_APPROVED", out)
                j, m = self.approval_files(repo)
                self.assertFalse(j.exists(), "approval.json must not exist")
                self.assertFalse(m.exists(), "gate-approval.md must not exist")
                self.assertFalse(pm_review.verify(repo)[0])

    def test_rejection_does_not_clobber_existing_valid_approval_for_other_head(self):
        self.run_request()
        H.commit_file(self.repo, "c.txt")
        bad = dict(APPROVE, verdict="MINOR")
        rc, _ = self.run_request(bad)
        self.assertEqual(rc, 1)
        self.assertFalse(pm_review.verify(self.repo)[0])  # old approval is for a stale head

    def test_dirty_tree_refused_before_review_runs(self):
        (self.repo / "a.txt").write_text("dirty\n", encoding="utf-8")
        rc, out = self.run_request()
        self.assertEqual(rc, 2)
        self.assertIn("REFUSED", out)
        self.assertFalse((self.tools / "argv.json").exists(), "review.js must not be called")
        self.assertFalse(self.approval_files()[0].exists())

    def test_untracked_files_do_not_block_request(self):
        (self.repo / "untracked.txt").write_text("u\n", encoding="utf-8")
        rc, out = self.run_request()
        self.assertEqual(rc, 0, out)

    def test_head_moving_during_review_refused(self):
        rc, out = self.run_request(commit_in=str(self.repo))
        self.assertEqual(rc, 2)
        self.assertIn("HEAD moved", out)
        self.assertFalse(self.approval_files()[0].exists())
        self.assertFalse(self.approval_files()[1].exists())

    def test_review_js_without_json_is_not_run(self):
        rc, out = self.run_request(raw="boom, not json\n", exit=3)
        self.assertEqual(rc, 2)
        self.assertIn("NOT_RUN", out)
        self.assertFalse(self.approval_files()[0].exists())

    def test_review_js_empty_output_is_not_run(self):
        rc, out = self.run_request(raw="", exit=0)
        self.assertEqual(rc, 2)
        self.assertIn("NOT_RUN", out)

    def test_missing_review_js_exits_2(self):
        pm = copy.deepcopy(core.load_phase_map())
        pm["pm_review"]["review_js_candidates"] = []  # hide the real review.js on this machine
        env = {"AF_PM_REVIEW_JS": str(self.tools / "does-not-exist.js")}
        with mock.patch.dict(os.environ, env), mock.patch.object(core, "load_phase_map", return_value=pm):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = pm_review.request(self.repo, "code", self.base)
        self.assertEqual(rc, 2)
        self.assertIn("NOT_RUN", buf.getvalue())
        self.assertFalse(self.approval_files()[0].exists())

    def test_unknown_kind_rejected(self):
        with self.assertRaises(SystemExit):
            pm_review.request(self.repo, "bogus", self.base)

    def test_cli_pm_review_end_to_end(self):
        cfg = {"result": APPROVE, "argv_out": str(self.tools / "argv.json"), "packet_out": str(self.tools / "packet.md")}
        (self.tools / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
        env = {"AF_PM_REVIEW_JS": str(self.tools / "review.js"), "FAKE_CFG": str(self.tools / "cfg.json")}
        r = H.run_cli(self.repo, "pm-review", "--kind", "code", "--base", self.base, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(H.run_cli(self.repo, "verify").returncode, 0)
        self.assertEqual(H.run_cli(self.repo, "next").returncode, 0)  # phase 8 -> 9 requires gate-approval.md + valid approval
        # rejected review exit code is 1
        cfg["result"] = dict(APPROVE, verdict="MAJOR")
        (self.tools / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
        H.commit_file(self.repo, "z.txt")
        r = H.run_cli(self.repo, "pm-review", "--base", self.base, env=env)
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
