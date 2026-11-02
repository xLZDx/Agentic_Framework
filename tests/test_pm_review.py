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


@unittest.skipUnless(NODE, "NOT_RUN: node is not available; fake review.js cannot be executed")
class Request(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)
        H.commit_file(self.repo, "a.txt")
        H.set_state(self.repo, phase=8)
        H.stamp_phases_1_7(self.repo)
        H.write_evidence(self.repo)
        self.base = H.first_commit(self.repo)
        self.tools = H.tmpdir(self)
        fake_review = H.FAKE_REVIEW_JS.replace(
            "const head = cp.execSync('git -C \"' + cwd + '\" rev-parse HEAD').toString().trim();",
            "const head = arg('--head') || cp.execSync('git -C \"' + cwd + '\" rev-parse HEAD').toString().trim();",
        )
        (self.tools / "review.js").write_text(fake_review, encoding="utf-8")

    def run_request(self, result=None, kind="code", repo=None, **opts):
        repo = repo or self.repo
        base = opts.pop("base", None) or (H.first_commit(repo) if repo != self.repo else self.base)
        review_cwd = opts.pop("review_cwd", None)
        task_base = opts.pop("task_base", None)
        task_id = opts.pop("task_id", None)
        predecessor_task = opts.pop("predecessor_task", None)
        cfg = {"result": result if result is not None else APPROVE,
               "argv_out": str(self.tools / "argv.json"), "packet_out": str(self.tools / "packet.md")}
        cfg.update(opts)
        (self.tools / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
        env = {"AF_PM_REVIEW_JS": str(self.tools / "review.js"), "FAKE_CFG": str(self.tools / "cfg.json")}
        with mock.patch.dict(os.environ, env):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = pm_review.request(repo, kind, base, review_cwd=review_cwd,
                                       task_base=task_base, task_id=task_id,
                                       predecessor_task=predecessor_task)
        return rc, buf.getvalue()

    def commit_accepted_task_base(self):
        H.git(self.repo, "add", "docs/sdlc")
        H.git(self.repo, "commit", "-q", "-m", "commit baseline SDLC evidence")
        predecessor_source = H.commit_file(self.repo, "accepted-predecessor.py", "accepted\n")
        H.write_evidence(self.repo, tested_head=predecessor_source)
        H.git(self.repo, "add", "accepted-predecessor.py", "docs/sdlc/verify-evidence.json")
        H.git(self.repo, "commit", "-q", "-m", "commit predecessor evidence baseline")
        return core.head(self.repo)

    def approve_task_base(self, accepted_head):
        self.assertEqual(core.head(self.repo), accepted_head)
        rc, out = self.run_request()
        self.assertEqual(rc, 0, out)
        approval = json.loads(self.approval_files()[0].read_text(encoding="utf-8"))
        self.assertEqual(approval["head"], accepted_head)
        return approval

    def add_predecessor_acceptance(self, accepted_head, record_head=None):
        path = H.sdlc(self.repo) / "verify-evidence.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["task_acceptance_records"] = {
            "DEC-01-T05": {
                "status": "ACCEPTED", "accepted_head": record_head or accepted_head,
                "request_id": "accepted-request", "reply_id": "accepted-reply",
                "bridge_job_id": "accepted-job", "correlated": True,
            }
        }
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        H.git(self.repo, "add", "docs/sdlc/verify-evidence.json")
        H.git(self.repo, "commit", "-q", "-m", "record accepted predecessor decision")

    def add_task_scope_evidence(self, task_head, accepted_head, task_id="DEC-01-T06", predecessor_task="DEC-01-T05"):
        path = H.sdlc(self.repo) / "verify-evidence.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["task_exact_heads"] = {task_id: {"head": task_head}}
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        H.git(self.repo, "add", "docs/sdlc/verify-evidence.json")
        H.git(self.repo, "commit", "-q", "-m", "record accepted task scope evidence")

    def test_explicit_task_scope_reviews_only_accepted_task_delta_and_binds_head(self):
        accepted_head = self.commit_accepted_task_base()
        self.approve_task_base(accepted_head)
        task_head = self.commit_code_and_evidence()
        self.add_task_scope_evidence(task_head, accepted_head)
        candidate_head = core.head(self.repo)
        rc, out = self.run_request(task_base=accepted_head, task_id="DEC-01-T06",
                                   predecessor_task="DEC-01-T05")
        self.assertEqual(rc, 0, out)

        argv = json.loads((self.tools / "argv.json").read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--base") + 1], accepted_head)
        self.assertEqual(argv[argv.index("--head") + 1], candidate_head)
        packet = (self.tools / "packet.md").read_text(encoding="utf-8")
        self.assertIn("Explicit task-scoped review", packet)
        self.assertIn("Task: DEC-01-T06", packet)
        self.assertIn("Previous task label: DEC-01-T05", packet)
        self.assertIn("task labels and task-head evidence are scope metadata, not acceptance proof", packet)
        self.assertIn(f"Exact HEAD under review: {candidate_head}", packet)

        approval = json.loads(self.approval_files()[0].read_text(encoding="utf-8"))
        self.assertEqual(approval["head"], candidate_head)
        self.assertEqual(approval["review_scope"]["id"], "DEC-01-T06")
        self.assertEqual(approval["review_scope"]["base_sha"], accepted_head)
        self.assertEqual(approval["review_scope"]["task_head"], task_head)
        self.assertTrue(pm_review.verify(self.repo)[0])

    def test_scoped_review_requires_official_pm_approval_at_exact_base(self):
        accepted_head = self.commit_accepted_task_base()
        task_head = self.commit_code_and_evidence()
        self.add_task_scope_evidence(task_head, accepted_head)
        rc, out = self.run_request(task_base=accepted_head, task_id="DEC-01-T06",
                                   predecessor_task="DEC-01-T05")
        self.assertEqual(rc, 2)
        self.assertIn("requires a valid correlated PM approval at the exact --task-base HEAD", out)
        self.assertFalse(self.approval_files()[0].exists())

    def test_task_acceptance_metadata_does_not_substitute_for_official_pm_approval(self):
        accepted_head = self.commit_accepted_task_base()
        self.add_predecessor_acceptance(accepted_head)
        task_head = self.commit_code_and_evidence()
        self.add_task_scope_evidence(task_head, accepted_head)

        rc, out = self.run_request(task_base=accepted_head, task_id="DEC-01-T06",
                                   predecessor_task="DEC-01-T05")
        self.assertEqual(rc, 2)
        self.assertIn("requires a valid correlated PM approval at the exact --task-base HEAD", out)
        self.assertFalse(self.approval_files()[0].exists())

    def test_scoped_review_ignores_untrusted_task_acceptance_metadata(self):
        accepted_head = self.commit_accepted_task_base()
        self.approve_task_base(accepted_head)
        self.add_predecessor_acceptance(accepted_head, record_head=self.base)
        task_head = self.commit_code_and_evidence()
        self.add_task_scope_evidence(task_head, accepted_head)

        rc, out = self.run_request(task_base=accepted_head, task_id="DEC-01-T06",
                                   predecessor_task="DEC-01-T05")
        self.assertEqual(rc, 0, out)

    def test_scoped_review_refuses_corrupted_prior_approval_result_receipt(self):
        accepted_head = self.commit_accepted_task_base()
        self.approve_task_base(accepted_head)
        task_head = self.commit_code_and_evidence()
        self.add_task_scope_evidence(task_head, accepted_head)
        receipt = H.sdlc(self.repo) / ".pm-review" / f"result-code-{accepted_head[:12]}.json"
        receipt.write_text("{corrupted receipt\n", encoding="utf-8")

        rc, out = self.run_request(task_base=accepted_head, task_id="DEC-01-T06",
                                   predecessor_task="DEC-01-T05")
        self.assertEqual(rc, 2)
        self.assertIn("requires a valid correlated PM approval at the exact --task-base HEAD", out)

    def test_task_scope_refuses_later_edits_to_task_files(self):
        accepted_head = self.commit_accepted_task_base()
        previous_approval = self.approve_task_base(accepted_head)
        approval_path = self.approval_files()[0]
        self.add_predecessor_acceptance(accepted_head)
        task_head = self.commit_code_and_evidence("task.py")
        self.add_task_scope_evidence(task_head, accepted_head)
        latest_source_head = H.commit_file(self.repo, "task.py", "changed after recorded task head\n")
        H.write_evidence(self.repo, tested_head=latest_source_head)
        self.add_task_scope_evidence(task_head, accepted_head)

        rc, out = self.run_request(task_base=accepted_head, task_id="DEC-01-T06",
                                   predecessor_task="DEC-01-T05")
        self.assertEqual(rc, 2)
        self.assertIn("task-scope evidence or exact path range", out)
        refused_approval = json.loads(approval_path.read_text(encoding="utf-8"))
        self.assertEqual(refused_approval["approval_id"], previous_approval["approval_id"])
        self.assertEqual(refused_approval["head"], accepted_head)

    def test_task_scoped_approval_can_anchor_next_incremental_review(self):
        accepted_head = self.commit_accepted_task_base()
        previous = self.approve_task_base(accepted_head)
        evidence_path = H.sdlc(self.repo) / "verify-evidence.json"

        task_source = H.commit_file(self.repo, "task.py", "changed\n")
        H.write_evidence(self.repo, tested_head=task_source,
                         task_exact_heads={"DEC-01-T06": {"head": task_source}})
        H.git(self.repo, "add", "docs/sdlc/verify-evidence.json")
        H.git(self.repo, "commit", "-q", "-m", "record task implementation evidence")
        task_head = core.head(self.repo)
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence["task_exact_heads"] = {"DEC-01-T06": {"head": task_head}}
        evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        H.git(self.repo, "add", "docs/sdlc/verify-evidence.json")
        H.git(self.repo, "commit", "-q", "-m", "record exact task implementation head")

        rc, out = self.run_request(task_base=accepted_head, task_id="DEC-01-T06",
                                   predecessor_task="DEC-01-T05")
        self.assertEqual(rc, 0, out)
        scoped = json.loads(self.approval_files()[0].read_text(encoding="utf-8"))
        self.assertEqual(scoped["review_scope"]["task_head"], task_head)
        self.assertEqual(scoped["previous_approval"]["head"], accepted_head)

        next_source = H.commit_file(self.repo, "next-task.py", "changed\n")
        H.write_evidence(self.repo, tested_head=next_source,
                         task_exact_heads={"DEC-01-T06": {"head": task_head}})
        H.git(self.repo, "add", "docs/sdlc/verify-evidence.json")
        H.git(self.repo, "commit", "-q", "-m", "record next task verification evidence")
        next_head = core.head(self.repo)
        rc, out = self.run_request()
        self.assertEqual(rc, 0, out)
        argv = json.loads((self.tools / "argv.json").read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--base") + 1], scoped["head"])
        self.assertEqual(argv[argv.index("--head") + 1], next_head)

    def approval_files(self, repo=None, kind="code"):
        repo = repo or self.repo
        j = H.sdlc(repo) / ".pm-review" / ("approval.json" if kind == "code" else "approval-docs.json")
        m = H.sdlc(repo) / ("gate-approval.md" if kind == "code" else "docs-approval.md")
        return j, m

    def pm_review_tree_bytes(self, repo):
        root = H.sdlc(repo) / ".pm-review"
        if not root.is_dir():
            return {}
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def approve_committed_baseline(self):
        H.git(self.repo, "add", "--all")
        H.git(self.repo, "commit", "-q", "-m", "record review baseline")
        approved_head = core.head(self.repo)
        rc, out = self.run_request()
        self.assertEqual(rc, 0, out)
        approval = json.loads(self.approval_files()[0].read_text(encoding="utf-8"))
        self.assertEqual(approval["head"], approved_head)
        return approval

    def commit_code_and_evidence(self, file_name="next.py"):
        code_head = H.commit_file(self.repo, file_name, "changed\n")
        H.write_evidence(self.repo, tested_head=code_head)
        H.git(self.repo, "add", "docs/sdlc/verify-evidence.json")
        H.git(self.repo, "commit", "-q", "-m", "record new verification evidence")
        return core.head(self.repo)

    def approve_incremental_successor(self, previous_head, file_name):
        self.commit_code_and_evidence(file_name)
        rc, out = self.run_request()
        self.assertEqual(rc, 0, out)
        approval = json.loads(self.approval_files()[0].read_text(encoding="utf-8"))
        self.assertEqual(approval["base"], previous_head)
        self.assertEqual(approval["head"], core.head(self.repo))
        return approval

    def test_incremental_review_uses_valid_prior_approval_and_binds_new_head(self):
        previous = self.approve_committed_baseline()
        self.commit_code_and_evidence()
        new_head = core.head(self.repo)

        rc, out = self.run_request()
        self.assertEqual(rc, 0, out)
        argv = json.loads((self.tools / "argv.json").read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--base") + 1], previous["head"])

        packet = (self.tools / "packet.md").read_text(encoding="utf-8")
        self.assertIn("Validated approval chain (oldest first):", packet)
        self.assertIn(
            f"- {previous['approval_id']} | HEAD {previous['head']} | request/reply "
            f"{previous['request_id']} / {previous['reply_id']}",
            packet,
        )

        approval = json.loads(self.approval_files()[0].read_text(encoding="utf-8"))
        self.assertEqual(approval["head"], new_head)
        self.assertEqual(approval["base"], previous["head"])
        self.assertEqual(approval["sprint_base"], self.base)
        self.assertEqual(approval["previous_approval"]["approval_id"], previous["approval_id"])
        self.assertEqual(approval["previous_approval"]["head"], previous["head"])
        ok, why = pm_review.verify(self.repo)
        self.assertTrue(ok, why)

    def test_linked_candidate_uses_prior_approval_from_registered_checkout(self):
        previous = self.approve_committed_baseline()
        self.commit_code_and_evidence()
        candidate_head = core.head(self.repo)
        registered_before = self.pm_review_tree_bytes(self.repo)
        linked = self.tools / "incremental-candidate-worktree"
        H.git(self.repo, "worktree", "add", "--detach", str(linked), candidate_head)
        try:
            candidate_approval = self.approval_files(repo=linked)[0]
            self.assertFalse(candidate_approval.exists())

            rc, out = self.run_request(repo=linked, review_cwd=self.repo)
            self.assertEqual(rc, 0, out)
            argv = json.loads((self.tools / "argv.json").read_text(encoding="utf-8"))
            self.assertEqual(argv[argv.index("--base") + 1], previous["head"])
            self.assertEqual(argv[argv.index("--head") + 1], candidate_head)

            approval = json.loads(candidate_approval.read_text(encoding="utf-8"))
            self.assertEqual(approval["head"], candidate_head)
            self.assertEqual(approval["base"], previous["head"])
            self.assertEqual(approval["previous_approval"]["approval_id"], previous["approval_id"])
            self.assertEqual(approval["previous_approval"]["head"], previous["head"])
            candidate_history = H.sdlc(linked) / ".pm-review" / "history"
            self.assertTrue((candidate_history / f"approval-code-{previous['head'][:12]}.md").is_file())
            self.assertTrue((candidate_history / f"approval-code-{candidate_head[:12]}.md").is_file())
            self.assertEqual(self.pm_review_tree_bytes(self.repo), registered_before)
            self.assertEqual(
                json.loads(self.approval_files(repo=self.repo)[0].read_text(encoding="utf-8")),
                previous,
            )
        finally:
            H.git(self.repo, "worktree", "remove", "--force", str(linked))

    def test_second_linked_candidate_cannot_mutate_first_candidates_history(self):
        previous = self.approve_committed_baseline()
        self.commit_code_and_evidence()
        candidate_head = core.head(self.repo)
        registered_before = self.pm_review_tree_bytes(self.repo)
        first = self.tools / "first-incremental-candidate"
        second = self.tools / "second-incremental-candidate"
        H.git(self.repo, "worktree", "add", "--detach", str(first), candidate_head)
        H.git(self.repo, "worktree", "add", "--detach", str(second), candidate_head)
        try:
            rc, out = self.run_request(repo=first, review_cwd=self.repo)
            self.assertEqual(rc, 0, out)
            first_approval = json.loads(self.approval_files(repo=first)[0].read_text(encoding="utf-8"))
            self.assertEqual(first_approval["previous_approval"]["approval_id"], previous["approval_id"])
            first_history_before = self.pm_review_tree_bytes(first)

            rc, out = self.run_request(repo=second, review_cwd=self.repo)
            self.assertEqual(rc, 0, out)
            second_approval = json.loads(self.approval_files(repo=second)[0].read_text(encoding="utf-8"))
            self.assertEqual(second_approval["previous_approval"]["approval_id"], previous["approval_id"])
            self.assertTrue((H.sdlc(second) / ".pm-review" / "history" / f"approval-code-{candidate_head[:12]}.md").is_file())

            self.assertEqual(self.pm_review_tree_bytes(first), first_history_before)
            self.assertEqual(self.pm_review_tree_bytes(self.repo), registered_before)
        finally:
            H.git(self.repo, "worktree", "remove", "--force", str(first))
            H.git(self.repo, "worktree", "remove", "--force", str(second))

    def test_conflicting_candidate_history_refuses_without_mutating_registered_checkout(self):
        previous = self.approve_committed_baseline()
        self.commit_code_and_evidence()
        candidate_head = core.head(self.repo)
        registered_before = self.pm_review_tree_bytes(self.repo)
        linked = self.tools / "conflicting-incremental-candidate"
        H.git(self.repo, "worktree", "add", "--detach", str(linked), candidate_head)
        try:
            candidate_history = H.sdlc(linked) / ".pm-review" / "history"
            candidate_history.mkdir(parents=True, exist_ok=True)
            conflicting_path = candidate_history / f"approval-code-{previous['head'][:12]}.md"
            conflicting_bytes = b"conflicting candidate approval history\n"
            conflicting_path.write_bytes(conflicting_bytes)

            rc, out = self.run_request(repo=linked, review_cwd=self.repo)
            self.assertEqual(rc, 2, out)
            self.assertIn("historical approval Markdown", out)
            self.assertFalse(self.approval_files(repo=linked)[0].exists())
            self.assertEqual(conflicting_path.read_bytes(), conflicting_bytes)
            self.assertEqual(self.pm_review_tree_bytes(self.repo), registered_before)
            self.assertEqual(
                json.loads(self.approval_files(repo=self.repo)[0].read_text(encoding="utf-8")),
                previous,
            )
        finally:
            H.git(self.repo, "worktree", "remove", "--force", str(linked))

    def test_incremental_approval_chain_progresses_a_to_b_to_c(self):
        approval_a = self.approve_committed_baseline()
        approval_b = self.approve_incremental_successor(approval_a["head"], "task-b.py")
        self.assertEqual(
            [record["approval_id"] for record in approval_b["approval_chain"]],
            [approval_a["approval_id"]],
        )

        approval_c = self.approve_incremental_successor(approval_b["head"], "task-c.py")
        argv = json.loads((self.tools / "argv.json").read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--base") + 1], approval_b["head"])
        self.assertEqual(
            [record["approval_id"] for record in approval_c["approval_chain"]],
            [approval_a["approval_id"], approval_b["approval_id"]],
        )
        self.assertEqual(approval_c["previous_approval"]["approval_id"], approval_b["approval_id"])
        self.assertEqual(approval_c["head"], core.head(self.repo))

    def test_missing_historical_a_markdown_invalidates_a_to_b_to_c_chain(self):
        approval_a = self.approve_committed_baseline()
        self.approve_incremental_successor(approval_a["head"], "task-b.py")
        historical_a = H.sdlc(self.repo) / ".pm-review" / "history" / f"approval-code-{approval_a['head'][:12]}.md"
        self.assertTrue(historical_a.is_file())
        historical_a.unlink()
        self.commit_code_and_evidence("task-c.py")

        rc, out = self.run_request()
        self.assertEqual(rc, 0, out)
        argv = json.loads((self.tools / "argv.json").read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--base") + 1], self.base)
        current = json.loads(self.approval_files()[0].read_text(encoding="utf-8"))
        self.assertEqual(current["base"], self.base)
        self.assertIsNone(current["previous_approval"])
        self.assertEqual(current["approval_chain"], [])

    def test_corrupted_historical_b_markdown_invalidates_a_to_b_to_c_chain(self):
        approval_a = self.approve_committed_baseline()
        approval_b = self.approve_incremental_successor(approval_a["head"], "task-b.py")
        historical_b = H.sdlc(self.repo) / ".pm-review" / "history" / f"approval-code-{approval_b['head'][:12]}.md"
        self.assertTrue(historical_b.is_file())
        historical_b.write_text("corrupted historical approval\n", encoding="utf-8")
        self.commit_code_and_evidence("task-c.py")

        rc, out = self.run_request()
        self.assertEqual(rc, 0, out)
        argv = json.loads((self.tools / "argv.json").read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--base") + 1], self.base)
        current = json.loads(self.approval_files()[0].read_text(encoding="utf-8"))
        self.assertEqual(current["base"], self.base)
        self.assertIsNone(current["previous_approval"])
        self.assertEqual(current["approval_chain"], [])

    def test_missing_predecessor_a_invalidates_otherwise_valid_b_chain(self):
        approval_a = self.approve_committed_baseline()
        self.approve_incremental_successor(approval_a["head"], "task-b.py")
        prior_result = (
            H.sdlc(self.repo) / ".pm-review" / f"result-code-{approval_a['head'][:12]}.json"
        )
        prior_result.unlink()
        self.commit_code_and_evidence("task-c.py")

        rc, out = self.run_request()
        self.assertEqual(rc, 0, out)
        argv = json.loads((self.tools / "argv.json").read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--base") + 1], self.base)
        current = json.loads(self.approval_files()[0].read_text(encoding="utf-8"))
        self.assertEqual(current["base"], self.base)
        self.assertIsNone(current["previous_approval"])
        self.assertEqual(current["approval_chain"], [])

    def test_mismatched_b_to_a_link_invalidates_incremental_chain(self):
        approval_a = self.approve_committed_baseline()
        approval_b = self.approve_incremental_successor(approval_a["head"], "task-b.py")
        approval_path = self.approval_files()[0]
        approval_b["previous_approval"]["approval_id"] = "mismatched-A"
        approval_path.write_text(json.dumps(approval_b), encoding="utf-8")
        self.commit_code_and_evidence("task-c.py")

        rc, out = self.run_request()
        self.assertEqual(rc, 0, out)
        argv = json.loads((self.tools / "argv.json").read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--base") + 1], self.base)
        current = json.loads(approval_path.read_text(encoding="utf-8"))
        self.assertEqual(current["base"], self.base)
        self.assertIsNone(current["previous_approval"])
        self.assertEqual(current["approval_chain"], [])

    def test_duplicate_or_cyclic_approval_chain_falls_back_without_hanging(self):
        approval_a = self.approve_committed_baseline()
        approval_b = self.approve_incremental_successor(approval_a["head"], "task-b.py")
        approval_path = self.approval_files()[0]
        approval_b_record = {key: value for key, value in approval_b.items() if key != "approval_chain"}
        approval_b["approval_chain"].append(approval_b_record)
        approval_path.write_text(json.dumps(approval_b), encoding="utf-8")
        self.commit_code_and_evidence("task-c.py")

        rc, out = self.run_request()
        self.assertEqual(rc, 0, out)
        argv = json.loads((self.tools / "argv.json").read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--base") + 1], self.base)
        current = json.loads(approval_path.read_text(encoding="utf-8"))
        self.assertEqual(current["base"], self.base)
        self.assertIsNone(current["previous_approval"])
        self.assertEqual(current["approval_chain"], [])

    def test_corrupt_prior_prompt_falls_back_to_full_sprint_range(self):
        previous = self.approve_committed_baseline()
        prior_prompt = H.sdlc(self.repo) / ".pm-review" / f"prompt-code-{previous['head'][:12]}.txt"
        prior_prompt.write_text("tampered prior review prompt\n", encoding="utf-8")
        self.commit_code_and_evidence()

        rc, out = self.run_request()
        self.assertEqual(rc, 0, out)
        argv = json.loads((self.tools / "argv.json").read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--base") + 1], self.base)
        approval = json.loads(self.approval_files()[0].read_text(encoding="utf-8"))
        self.assertEqual(approval["base"], self.base)
        self.assertIsNone(approval["previous_approval"])

    def test_malformed_prior_artifacts_fall_back_to_full_sprint_range(self):
        self.approve_committed_baseline()
        approval_path = self.approval_files()[0]
        prior = json.loads(approval_path.read_text(encoding="utf-8"))
        prior["artifacts"] = ["not", "an", "artifact-map"]
        approval_path.write_text(json.dumps(prior), encoding="utf-8")
        self.commit_code_and_evidence()

        rc, out = self.run_request()
        self.assertEqual(rc, 0, out)
        argv = json.loads((self.tools / "argv.json").read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--base") + 1], self.base)
        current = json.loads(approval_path.read_text(encoding="utf-8"))
        self.assertEqual(current["base"], self.base)
        self.assertIsNone(current["previous_approval"])

    def test_oversized_prepared_prompt_is_refused_before_review_send(self):
        calls = self.tools / "review-calls.txt"
        with mock.patch.object(pm_review, "MAX_REVIEW_PROMPT_BYTES", 64):
            rc, out = self.run_request(calls_out=str(calls))
        self.assertEqual(rc, 2)
        self.assertIn("safe limit is 64", out)
        self.assertEqual(calls.read_text(encoding="utf-8").splitlines(), ["dump"])
        self.assertFalse(self.approval_files()[0].exists())
        self.assertFalse(self.approval_files()[1].exists())

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
        self.assertEqual((a["request_id"], a["reply_id"], a["input_hash"]), ("req-1", "reply-1", a["expected_input_hash"]))
        self.assertEqual(a["reply_sha256"], hashlib.sha256(APPROVE["reply"].encode()).hexdigest())
        self.assertIn(head, m.read_text(encoding="utf-8"))
        ok, why = pm_review.verify(self.repo)
        self.assertTrue(ok, why)
        # and a later commit revokes it
        H.commit_file(self.repo, "b.txt")
        self.assertFalse(pm_review.verify(self.repo)[0])

    def test_request_passes_exact_range_and_packet_to_review_js(self):
        H.write_evidence(self.repo, not_run=[{"item": "EVIDENCE-MARKER", "reason": "r"}])
        rc, out = self.run_request()
        self.assertEqual(rc, 0, out)
        argv = json.loads((self.tools / "argv.json").read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--cwd") + 1], str(self.repo))
        self.assertEqual(argv[argv.index("--base") + 1], self.base)
        self.assertEqual(argv[argv.index("--head") + 1], core.head(self.repo))
        self.assertIn("--final", argv)
        packet = (self.tools / "packet.md").read_text(encoding="utf-8")
        self.assertIn(f"Exact HEAD under review: {core.head(self.repo)}", packet)
        self.assertIn("EVIDENCE-MARKER", packet)

    def test_linked_candidate_routes_through_primary_checkout_and_pins_exact_head(self):
        linked = self.tools / "candidate-worktree"
        H.git(self.repo, "worktree", "add", "--detach", str(linked), core.head(self.repo))
        try:
            H.set_state(linked, phase=8)
            H.stamp_phases_1_7(linked)
            H.write_evidence(linked)
            candidate_head = core.head(linked)
            rc, out = self.run_request(repo=linked, review_cwd=self.repo)
            self.assertEqual(rc, 0, out)
            argv = json.loads((self.tools / "argv.json").read_text(encoding="utf-8"))
            self.assertEqual(argv[argv.index("--cwd") + 1], str(self.repo.resolve()))
            self.assertEqual(argv[argv.index("--head") + 1], candidate_head)
            self.assertEqual(argv[argv.index("--base") + 1], self.base)
            approval = json.loads((H.sdlc(linked) / ".pm-review" / "approval.json").read_text(encoding="utf-8"))
            self.assertEqual(approval["head"], candidate_head)
        finally:
            H.git(self.repo, "worktree", "remove", "--force", str(linked))

    def test_unrelated_review_checkout_is_refused_before_review_or_approval(self):
        unrelated = H.make_repo(self)
        rc, out = self.run_request(review_cwd=unrelated)
        self.assertEqual(rc, 2)
        self.assertIn("same Git repository", out)
        self.assertFalse((self.tools / "argv.json").exists(), "review.js must not be invoked")
        self.assertFalse(self.approval_files()[0].exists(), "refused routing must not create approval")

    def test_missing_verify_evidence_is_refused_for_code(self):
        (H.sdlc(self.repo) / "verify-evidence.json").unlink()
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
                H.stamp_phases_1_7(repo)
                H.write_evidence(repo)
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
        H.write_evidence(self.repo)
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
        r = H.run_cli(self.repo, "pm-review", "--kind", "code", "--base", self.base,
                      "--review-cwd", str(self.repo), env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = json.loads((self.tools / "argv.json").read_text(encoding="utf-8"))
        self.assertEqual(argv[argv.index("--cwd") + 1], str(self.repo.resolve()))
        self.assertEqual(argv[argv.index("--head") + 1], core.head(self.repo))
        self.assertEqual(H.run_cli(self.repo, "verify").returncode, 0)
        self.assertEqual(H.run_cli(self.repo, "next").returncode, 0)  # phase 8 -> 9 requires gate-approval.md + valid approval
        # rejected review exit code is 1
        cfg["result"] = dict(APPROVE, verdict="MAJOR")
        (self.tools / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
        H.commit_file(self.repo, "z.txt")
        H.write_evidence(self.repo)
        r = H.run_cli(self.repo, "pm-review", "--base", self.base, env=env)
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
