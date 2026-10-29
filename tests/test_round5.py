"""Round-5: structured evidence, sprint-id stamping, migrate, prompt pre-computation and artifact digests."""
import contextlib
import hashlib
import io
import json
import os
import shutil
import unittest
from unittest import mock

import afhelpers as H
from afhelpers import ROOT, APPROVE, core, pm_review

sys_path_done = H.TOOLS  # tools/ is already on sys.path via afhelpers
from af import evidence  # noqa: E402

NODE = shutil.which("node")
NL = chr(10)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def state(repo):
    return core.read_state(repo)


# ---------------------------------------------------------------- evidence.validate
class EvidenceValidate(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)
        H.commit_file(self.repo, "a.py", "x = 1" + NL)
        self.head = core.head(self.repo)
        H.write_evidence(self.repo)

    def problems(self):
        return evidence.validate(self.repo, core.head(self.repo))

    def assert_rejects(self, needle):
        p = self.problems()
        self.assertTrue(p, "expected a rejection")
        self.assertTrue(any(needle in x for x in p), p)

    def ev(self, **over):
        return H.write_evidence(self.repo, **over)

    def test_valid_evidence_has_no_problems(self):
        self.assertEqual(self.problems(), [])

    def test_missing_file(self):
        (H.sdlc(self.repo) / "verify-evidence.json").unlink()
        self.assert_rejects("missing")

    def test_invalid_json(self):
        (H.sdlc(self.repo) / "verify-evidence.json").write_text("{not json", encoding="utf-8")
        self.assert_rejects("not valid JSON")

    def test_json_not_an_object(self):
        (H.sdlc(self.repo) / "verify-evidence.json").write_text("[1, 2]", encoding="utf-8")
        self.assert_rejects("JSON object")

    def test_tested_head_missing_or_short(self):
        for v in (None, "", "abc", 12345):
            with self.subTest(v=v):
                self.ev(tested_head="x")  # write then overwrite below
                d = json.loads((H.sdlc(self.repo) / "verify-evidence.json").read_text(encoding="utf-8"))
                d["tested_head"] = v
                (H.sdlc(self.repo) / "verify-evidence.json").write_text(json.dumps(d), encoding="utf-8")
                self.assert_rejects("tested_head")

    def test_tested_head_unknown_commit(self):
        self.ev(tested_head="0123456789abcdef0123456789abcdef01234567")
        self.assert_rejects("not an ancestor commit")

    def test_tested_head_not_an_ancestor(self):
        H.git(self.repo, "checkout", "-q", "-b", "side", H.first_commit(self.repo))
        side = H.commit_file(self.repo, "side.txt")
        H.git(self.repo, "checkout", "-q", "-")
        self.ev(tested_head=side)
        self.assert_rejects("not an ancestor commit")

    def test_code_changed_after_tested_head_is_rejected(self):
        self.ev(tested_head=self.head)
        H.commit_file(self.repo, "b.py", "y = 2" + NL)
        self.assert_rejects("code changed after the tested head")
        self.assertIn("b.py", " ".join(self.problems()))

    def test_docs_only_change_after_tested_head_is_allowed(self):
        self.ev(tested_head=self.head)
        H.commit_file(self.repo, "docs/guide.md", "doc" + NL)
        self.assertEqual(self.problems(), [])

    def test_allowed_core_logs_after_tested_head(self):
        self.ev(tested_head=self.head)
        for name in ("core/DECISION_LOG.md", "core/LESSONS_LOG.md", "core/BACKLOG.md"):
            (self.repo / "core").mkdir(exist_ok=True)
            H.commit_file(self.repo, name, name + NL)
        self.assertEqual(self.problems(), [])

    def test_other_core_file_after_tested_head_is_code(self):
        self.ev(tested_head=self.head)
        (self.repo / "core").mkdir(exist_ok=True)
        H.commit_file(self.repo, "core/agents.md", "x" + NL)
        self.assert_rejects("code changed")

    def test_mixed_docs_and_code_change_rejected(self):
        self.ev(tested_head=self.head)
        H.commit_file(self.repo, "docs/g.md", "d" + NL)
        H.commit_file(self.repo, "c.py", "z" + NL)
        self.assert_rejects("c.py")

    def test_runs_empty_or_not_a_list(self):
        for v in ([], None, "x", {}):
            with self.subTest(v=v):
                self.ev(runs=v)
                self.assert_rejects("runs must be a non-empty list")

    def run_with(self, **kw):
        r = {"command": "pytest", "total": 4, "passed": 4, "failed": 0, "errors": 0, "skipped": 0}
        r.update(kw)
        self.ev(runs=[r])

    def test_run_command_missing_or_blank(self):
        for v in (None, "", "   ", 5):
            with self.subTest(v=v):
                self.run_with(command=v)
                self.assert_rejects("command is missing")

    def test_non_integer_or_negative_counts(self):
        for key in ("total", "passed", "failed", "errors", "skipped"):
            for bad in ("3", 3.0, True, None, -1):
                with self.subTest(key=key, bad=bad):
                    self.run_with(**{key: bad})
                    self.assert_rejects("integer")

    def test_missing_count_key(self):
        self.ev(runs=[{"command": "x", "total": 1, "passed": 1}])
        self.assert_rejects("integer")

    def test_contradictory_counts(self):
        self.run_with(total=10, passed=4)
        self.assert_rejects("contradictory")
        self.run_with(total=3, passed=4)
        self.assert_rejects("contradictory")

    def test_zero_tests(self):
        self.run_with(total=0, passed=0)
        self.assert_rejects("zero tests")

    def test_failed_or_errors_are_red(self):
        self.run_with(total=4, passed=3, failed=1)
        self.assert_rejects("is red")
        self.run_with(total=4, passed=3, errors=1)
        self.assert_rejects("is red")

    def test_skipped_alone_is_allowed(self):
        self.run_with(total=4, passed=3, skipped=1)
        self.assertEqual(self.problems(), [])

    def test_optional_log_accepted(self):
        self.run_with(log="D:/logs/run.txt")
        self.assertEqual(self.problems(), [])

    def test_one_red_run_among_green_rejects(self):
        good = {"command": "a", "total": 1, "passed": 1, "failed": 0, "errors": 0, "skipped": 0}
        bad = dict(good, command="b", passed=0, failed=1)
        self.ev(runs=[good, bad])
        self.assert_rejects("runs[1] is red")

    def test_not_run_entries_need_item_and_reason(self):
        for entry in ({"item": "x"}, {"reason": "y"}, {"item": " ", "reason": "y"}, {"item": "x", "reason": ""}, "str"):
            with self.subTest(entry=entry):
                self.ev(not_run=[entry])
                self.assert_rejects("needs item and reason")

    def test_not_run_must_be_list_but_may_be_empty(self):
        self.ev(not_run="none")
        self.assert_rejects("not_run must be a list")
        self.ev(not_run=[])
        self.assertEqual(self.problems(), [])

    def test_open_blocker_or_major_rejected(self):
        self.ev(findings={"open_blocker": 1, "open_major": 0})
        self.assert_rejects("open blocking findings")
        self.ev(findings={"open_blocker": 0, "open_major": 2})
        self.assert_rejects("open blocking findings")

    def test_findings_malformed(self):
        for v in (None, {}, {"open_blocker": 0}, {"open_blocker": "0", "open_major": 0}, {"open_blocker": 0, "open_major": -1}):
            with self.subTest(v=v):
                self.ev(findings=v)
                self.assert_rejects("findings needs integer")

    def test_reviewers_malformed(self):
        good = {"role": "r", "model": "m", "effort": "e", "verdict": "APPROVE"}
        for v in ("x", [{"role": "r"}], [dict(good, verdict="")], [5]):
            with self.subTest(v=v):
                self.ev(reviewers=v)
                self.assertTrue(self.problems())
        self.ev(reviewers=[])
        self.assert_rejects("reviewers_waived_reason")  # empty list is no longer free

    def test_reviewer_field_null_is_rejected(self):
        good = {"role": "r", "model": "m", "effort": "e", "verdict": "APPROVE"}
        for k in ("role", "model", "effort", "verdict"):
            with self.subTest(field=k):
                self.ev(reviewers=[dict(good, **{k: None})])
                self.assertTrue(self.problems(), f"reviewers[0].{k}=null must be rejected")

    def test_not_run_null_item_or_reason_is_rejected(self):
        for entry in ({"item": None, "reason": "r"}, {"item": "i", "reason": None}):
            with self.subTest(entry=entry):
                self.ev(not_run=[entry])
                self.assertTrue(self.problems(), f"{entry} must be rejected")

    def test_run_with_no_passing_test_rejected(self):
        self.run_with(total=1, passed=0, skipped=1)
        self.assert_rejects("no passing test")
        self.run_with(total=3, passed=0, skipped=3)
        self.assert_rejects("skipped tests are not evidence")

    def test_mixed_runs_one_with_zero_passed_rejected(self):
        good = {"command": "a", "total": 2, "passed": 2, "failed": 0, "errors": 0, "skipped": 0}
        skipped = {"command": "b", "total": 1, "passed": 0, "failed": 0, "errors": 0, "skipped": 1}
        self.ev(runs=[good, skipped])
        self.assert_rejects("runs[1]")
        self.ev(runs=[skipped, good])
        self.assert_rejects("runs[0]")

    def test_run_with_some_pass_and_some_skipped_still_ok(self):
        self.run_with(total=5, passed=1, skipped=4)
        self.assertEqual(self.problems(), [])

    def test_empty_reviewers_need_non_blank_string_reason(self):
        self.ev(reviewers=[])
        self.assert_rejects("reviewers_waived_reason")
        for bad in (None, "", "   ", 5, True, ["x"]):
            with self.subTest(reason=bad):
                self.ev(reviewers=[], reviewers_waived_reason=bad)
                self.assert_rejects("reviewers_waived_reason")
        self.ev(reviewers=[], reviewers_waived_reason="solo operator run; no agent roster available")
        self.assertEqual(self.problems(), [])

    def test_non_empty_reviewers_unaffected_by_waiver_field(self):
        self.ev()  # defaults: one reviewer, no waiver
        self.assertEqual(self.problems(), [])
        self.ev(reviewers_waived_reason=None)  # irrelevant when reviewers are present
        self.assertEqual(self.problems(), [])

    def test_all_problems_reported_together(self):
        self.ev(runs=[], findings={"open_blocker": 1, "open_major": 0}, not_run=[{}])
        self.assertGreaterEqual(len(self.problems()), 3)


# ---------------------------------------------------------------- sprint id / migrate / digests
class SprintId(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)

    def test_start_and_on_assign_distinct_hex_sprint_ids(self):
        ids = []
        for cmd in (("start", "S"), ("on",)):
            repo = H.make_repo(self)
            self.assertEqual(H.run_cli(repo, *cmd).returncode, 0)
            sid = state(repo)["sprint_id"]
            self.assertRegex(sid, r"^[0-9a-f]{12}$")
            ids.append(sid)
        self.assertNotEqual(*ids)

    def test_artifact_without_sprint_id_is_missing_and_stamped_accepted(self):
        H.run_cli(self.repo, "start", "S")
        H.write_artifact(self.repo, "requirements.md", "no id here" + NL, stamp=False)
        self.assertEqual(core.missing_artifacts(self.repo, 1), ["requirements.md"])
        r = H.run_cli(self.repo, "next")
        self.assertEqual(r.returncode, 1)
        self.assertIn("requirements.md", r.stdout)
        H.write_artifact(self.repo, "requirements.md", "now stamped" + NL)  # helper stamps current id
        self.assertEqual(core.missing_artifacts(self.repo, 1), [])
        self.assertEqual(H.run_cli(self.repo, "next").returncode, 0)
        self.assertEqual(state(self.repo)["phase"], 2)

    def test_stale_artifact_from_previous_sprint_rejected(self):
        H.run_cli(self.repo, "start", "S")
        H.write_artifact(self.repo, "requirements.md", "old sprint" + NL, stamp="000000000000")
        self.assertEqual(core.missing_artifacts(self.repo, 1), ["requirements.md"])
        self.assertEqual(H.run_cli(self.repo, "next").returncode, 1)

    def test_old_mtime_does_not_matter_only_the_id(self):
        H.run_cli(self.repo, "start", "S")
        H.write_artifact(self.repo, "requirements.md")
        p = H.sdlc(self.repo) / "requirements.md"
        os.utime(p, (1_000_000_000, 1_000_000_000))
        self.assertEqual(core.missing_artifacts(self.repo, 1), [])

    def test_sprint_id_embedded_in_longer_text_counts(self):
        H.set_state(self.repo, phase=1)
        H.write_artifact(self.repo, "requirements.md", "intro" + NL + "Sprint: " + H.TEST_SID + NL + "more", stamp=False)
        self.assertEqual(core.missing_artifacts(self.repo, 1), [])

    def test_glob_artifact_requires_stamp(self):
        H.set_state(self.repo, phase=6)
        H.write_artifact(self.repo, "change-records/c1.md", "x", stamp=False)
        self.assertEqual(core.missing_artifacts(self.repo, 6), ["change-records/*.md"])
        H.write_artifact(self.repo, "change-records/c2.md", "x")
        self.assertEqual(core.missing_artifacts(self.repo, 6), [])

    def test_status_and_hook_context_show_sprint_id(self):
        H.run_cli(self.repo, "start", "S")
        sid = state(self.repo)["sprint_id"]
        self.assertIn(sid, H.run_cli(self.repo, "status").stdout)
        from af import hook
        self.assertIn(sid, hook.context_line(self.repo))

    def test_resume_keeps_sprint_id(self):
        H.run_cli(self.repo, "on")
        sid = state(self.repo)["sprint_id"]
        H.run_cli(self.repo, "off")
        H.run_cli(self.repo, "on")
        self.assertEqual(state(self.repo)["sprint_id"], sid)


class Legacy(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)
        H.set_state(self.repo, phase=1, sid=None)
        H.write_artifact(self.repo, "requirements.md", "legacy artifact" + NL)

    def test_next_blocked_with_migrate_hint(self):
        self.assertNotIn("sprint_id", state(self.repo))
        r = H.run_cli(self.repo, "next")
        self.assertEqual(r.returncode, 1)
        self.assertIn("BLOCKED", r.stdout)
        self.assertIn("migrate", r.stdout)
        self.assertEqual(state(self.repo)["phase"], 1)

    def test_force_does_not_bypass_legacy_block(self):
        self.assertEqual(H.run_cli(self.repo, "next", "--force").returncode, 1)
        self.assertEqual(state(self.repo)["phase"], 1)

    def test_legacy_status_hints_migrate(self):
        self.assertIn("migrate", H.run_cli(self.repo, "status").stdout)

    def test_migrate_assigns_id_and_is_idempotent(self):
        r = H.run_cli(self.repo, "migrate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        sid = state(self.repo)["sprint_id"]
        self.assertRegex(sid, r"^[0-9a-f]{12}$")
        self.assertIn(sid, r.stdout)
        keep = {k: v for k, v in state(self.repo).items() if k != "updated"}
        r2 = H.run_cli(self.repo, "migrate")
        self.assertEqual(r2.returncode, 0)
        self.assertIn("Already migrated", r2.stdout)
        self.assertEqual({k: v for k, v in state(self.repo).items() if k != "updated"}, keep)

    def test_after_migrate_unstamped_artifact_blocks_until_stamped(self):
        H.run_cli(self.repo, "migrate")
        r = H.run_cli(self.repo, "next")
        self.assertEqual(r.returncode, 1)
        self.assertIn("requirements.md", r.stdout)
        H.write_artifact(self.repo, "requirements.md", "restamped" + NL)
        self.assertEqual(H.run_cli(self.repo, "next").returncode, 0)

    def test_migrate_preserves_phase_title_mode_and_history(self):
        core.write_state(self.repo, {"title": "Keep", "phase": 4, "mode": "soft", "paused": True,
                                     "history": [{"phase": 3}]})
        H.run_cli(self.repo, "migrate")
        st = state(self.repo)
        self.assertEqual((st["title"], st["phase"], st["mode"], st["paused"], st["history"]),
                         ("Keep", 4, "soft", True, [{"phase": 3}]))

    def test_migrate_without_sprint_fails(self):
        repo = H.make_repo(self)
        r = H.run_cli(repo, "migrate")
        self.assertEqual(r.returncode, 1)
        self.assertIn("No sprint", r.stdout)


class HistoryDigests(unittest.TestCase):
    def test_next_records_artifact_digests_in_history(self):
        repo = H.make_repo(self)
        H.run_cli(repo, "start", "S")
        H.write_artifact(repo, "requirements.md", "req text")
        self.assertEqual(H.run_cli(repo, "next").returncode, 0)
        entry = state(repo)["history"][-1]
        self.assertEqual(entry["phase"], 1)
        self.assertEqual(entry["artifacts"], {"requirements.md": sha((H.sdlc(repo) / "requirements.md").read_bytes())})

    def test_digests_accumulate_and_change_with_content(self):
        repo = H.make_repo(self)
        H.run_cli(repo, "start", "S")
        H.write_artifact(repo, "requirements.md", "one")
        H.run_cli(repo, "next")
        H.write_artifact(repo, "backlog.md", "two")
        H.run_cli(repo, "next")
        h1, h2 = state(repo)["history"]
        self.assertEqual(set(h1["artifacts"]), {"requirements.md"})
        self.assertEqual(set(h2["artifacts"]), {"requirements.md", "backlog.md"})

    def test_artifact_digests_unit_includes_glob_and_evidence_json(self):
        repo = H.make_repo(self)
        H.set_state(repo, phase=7)
        H.stamp_phases_1_7(repo)
        H.write_evidence(repo)
        d = core.artifact_digests(repo)
        self.assertIn("change-records/c1.md", d)
        self.assertIn("verify-evidence.json", d)
        self.assertIn("verify-evidence.md", d)
        self.assertNotIn("gate-approval.md", d)
        for k, v in d.items():
            self.assertEqual(v, sha((H.sdlc(repo) / k).read_bytes()))
        self.assertEqual(set(core.artifact_digests(repo, 1)), {"requirements.md", "verify-evidence.json"})


# ---------------------------------------------------------------- pm_review integration
@unittest.skipUnless(NODE, "NOT_RUN: node is not available; fake review.js cannot be executed")
class PmReviewFlow(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)
        self.first = H.first_commit(self.repo)
        H.commit_file(self.repo, "a.txt")
        H.set_state(self.repo, phase=8)
        H.stamp_phases_1_7(self.repo)
        H.write_evidence(self.repo)
        self.tools = H.tmpdir(self)
        (self.tools / "review.js").write_text(H.FAKE_REVIEW_JS, encoding="utf-8")
        self.calls = self.tools / "calls.txt"
        self.argv = self.tools / "argv.json"

    def request(self, kind="code", **opts):
        cfg = {"result": APPROVE, "argv_out": str(self.argv), "packet_out": str(self.tools / "packet.md"),
               "calls_out": str(self.calls)}
        cfg.update(opts)
        (self.tools / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
        env = {"AF_PM_REVIEW_JS": str(self.tools / "review.js"), "FAKE_CFG": str(self.tools / "cfg.json")}
        buf = io.StringIO()
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(buf):
            rc = pm_review.request(self.repo, kind, self.first)
        return rc, buf.getvalue()

    def call_log(self):
        return self.calls.read_text(encoding="utf-8").split() if self.calls.exists() else []

    def approval(self):
        return json.loads((H.sdlc(self.repo) / ".pm-review" / "approval.json").read_text(encoding="utf-8"))

    def no_approval_files(self):
        self.assertFalse((H.sdlc(self.repo) / ".pm-review" / "approval.json").exists())
        self.assertFalse((H.sdlc(self.repo) / "gate-approval.md").exists())

    def refused_before_review(self, rc, out, needle=None):
        self.assertEqual(rc, 2, out)
        self.assertIn("REFUSED", out)
        if needle:
            self.assertIn(needle, out)
        self.assertEqual(self.call_log(), [])
        self.no_approval_files()

    # --- evidence integration
    def test_baseline_approves_and_runs_dump_then_real(self):
        rc, out = self.request()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.call_log(), ["dump", "real"])

    def test_no_passing_test_run_refused_before_review(self):
        H.write_evidence(self.repo, runs=[{"command": "x", "total": 1, "passed": 0, "failed": 0, "errors": 0, "skipped": 1}])
        self.refused_before_review(*self.request(), "no passing test")

    def test_empty_reviewers_refused_before_review_unless_waived(self):
        H.write_evidence(self.repo, reviewers=[])
        self.refused_before_review(*self.request(), "reviewers_waived_reason")
        for bad in (None, "  "):
            H.write_evidence(self.repo, reviewers=[], reviewers_waived_reason=bad)
            self.refused_before_review(*self.request(), "reviewers_waived_reason")
        H.write_evidence(self.repo, reviewers=[], reviewers_waived_reason="operator waived reviewer roster")
        rc, out = self.request()
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.call_log(), ["dump", "real"])

    def test_old_markdown_headings_no_longer_satisfy_code_review(self):
        (H.sdlc(self.repo) / "verify-evidence.json").unlink()
        H.write_artifact(self.repo, "verify-evidence.md", "## Test evidence" + NL + "## NOT_RUN" + NL)
        self.refused_before_review(*self.request(), "verify-evidence.json")

    def test_invalid_evidence_variants_refused_before_review(self):
        cases = {
            "red": dict(runs=[{"command": "x", "total": 2, "passed": 1, "failed": 1, "errors": 0, "skipped": 0}]),
            "zero": dict(runs=[{"command": "x", "total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}]),
            "contradictory": dict(runs=[{"command": "x", "total": 9, "passed": 1, "failed": 0, "errors": 0, "skipped": 0}]),
            "open_major": dict(findings={"open_blocker": 0, "open_major": 1}),
            "bad_reviewer": dict(reviewers=[{"role": "x"}]),
        }
        for label, over in cases.items():
            with self.subTest(case=label):
                H.write_evidence(self.repo, **over)
                self.refused_before_review(*self.request(), "not acceptable")

    def test_code_changed_after_tested_head_refused(self):
        H.commit_file(self.repo, "later.py", "z" + NL)
        self.refused_before_review(*self.request(), "code changed after the tested head")

    def test_docs_only_change_after_tested_head_allowed(self):
        H.commit_file(self.repo, "docs/note.md", "n" + NL)
        rc, out = self.request()
        self.assertEqual(rc, 0, out)

    def test_docs_kind_does_not_need_json_evidence(self):
        (H.sdlc(self.repo) / "verify-evidence.json").unlink()
        rc, out = self.request(kind="docs")
        self.assertEqual(rc, 0, out)

    def test_packet_includes_structured_evidence(self):
        H.write_evidence(self.repo, not_run=[{"item": "JSON-MARKER-ITEM", "reason": "r"}])
        rc, out = self.request()
        self.assertEqual(rc, 0, out)
        packet = (self.tools / "packet.md").read_text(encoding="utf-8")
        self.assertIn("verify-evidence.json", packet)
        self.assertIn("JSON-MARKER-ITEM", packet)

    # --- sprint id integration
    def test_legacy_state_refused_with_migrate_hint(self):
        st = state(self.repo)
        del st["sprint_id"]
        core.write_state(self.repo, st)
        self.refused_before_review(*self.request(), "migrate")

    def test_unstamped_phase_artifact_refused(self):
        H.write_artifact(self.repo, "design.md", "no stamp", stamp=False)
        self.refused_before_review(*self.request(), "design.md")

    def test_artifact_stamped_with_other_sprint_refused(self):
        H.write_artifact(self.repo, "test-plan.md", "old", stamp="ffffffffffff")
        self.refused_before_review(*self.request(), "test-plan.md")

    def test_missing_phase_6_artifact_refused(self):
        shutil.rmtree(H.sdlc(self.repo) / "change-records")
        self.refused_before_review(*self.request(), "phase 6")

    def test_no_sprint_state_does_not_require_stamps(self):
        (H.sdlc(self.repo) / "state.json").unlink()
        rc, out = self.request()
        self.assertEqual(rc, 0, out)

    # --- prompt pre-computation
    def test_approval_records_hashes_digests_and_sprint(self):
        rc, out = self.request()
        self.assertEqual(rc, 0, out)
        a = self.approval()
        head = core.head(self.repo)
        prompt_file = H.sdlc(self.repo) / ".pm-review" / f"prompt-code-{head[:12]}.txt"
        prompt = prompt_file.read_text(encoding="utf-8")
        self.assertEqual(a["expected_input_hash"], sha(prompt.encode("utf-8")))
        self.assertEqual(a["input_hash"], a["expected_input_hash"])
        self.assertIn(head, prompt)
        diff = H.git(self.repo, "diff", f"{self.first}...{head}")
        self.assertEqual(a["diff_sha256"], sha(diff.encode("utf-8")))
        cut = prompt.index("Diff:" + NL + "```diff" + NL) + len("Diff:" + NL + "```diff" + NL)
        self.assertEqual(a["diff_in_prompt_sha256"], sha(prompt[cut:].encode("utf-8")))
        self.assertIn(diff.strip(), prompt[cut:])
        self.assertEqual(a["evidence_sha256"], sha((H.sdlc(self.repo) / "verify-evidence.json").read_bytes()))
        self.assertEqual(a["sprint_id"], H.TEST_SID)
        self.assertEqual(a["artifacts"], core.artifact_digests(self.repo))
        self.assertIn("verify-evidence.json", a["artifacts"])

    def test_dump_env_vars_reach_review_js_on_precompute_only(self):
        self.request()
        self.assertEqual(self.call_log(), ["dump", "real"])

    def test_wrong_review_input_hash_not_approved_no_files(self):
        rc, out = self.request(bad_hash="0" * 64)
        self.assertEqual(rc, 1, out)
        self.assertIn("NOT_APPROVED", out)
        self.assertIn("reviewInputHash", out)
        self.assertEqual(self.call_log(), ["dump", "real"])
        self.no_approval_files()
        self.assertFalse(pm_review.verify(self.repo)[0])

    def test_hash_from_old_style_result_not_approved(self):
        rc, out = self.request(keep_hash=True)  # APPROVE carries reviewInputHash "hash-1"
        self.assertEqual(rc, 1, out)
        self.no_approval_files()

    def test_missing_dump_refused_and_review_not_sent(self):
        rc, out = self.request(dump_mode="empty")
        self.assertEqual(rc, 2, out)
        self.assertIn("REFUSED", out)
        self.assertEqual(self.call_log(), ["dump"])  # only the dump-only call; the real review never ran
        self.no_approval_files()

    def test_prompt_lacking_packet_or_head_refused(self):
        rc, out = self.request(dump_mode="wrong")
        self.assertEqual(rc, 2, out)
        self.assertIn("does not contain", out)
        self.assertEqual(self.call_log(), ["dump"])
        self.no_approval_files()

    def test_review_js_without_dump_support_refused(self):
        rc, out = self.request(dump_mode="ignored")
        self.assertEqual(rc, 2, out)
        self.assertIn("REFUSED", out)
        self.no_approval_files()

    def test_cli_exit_codes_for_hash_mismatch_and_missing_dump(self):
        for opts, code in (({"bad_hash": "1" * 64}, 1), ({"dump_mode": "empty"}, 2)):
            with self.subTest(opts=opts):
                cfg = {"result": APPROVE, "argv_out": str(self.argv), "packet_out": str(self.tools / "packet.md"),
                       "calls_out": str(self.calls)}
                cfg.update(opts)
                (self.tools / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
                r = H.run_cli(self.repo, "pm-review", "--kind", "code", "--base", self.first,
                              env={"AF_PM_REVIEW_JS": str(self.tools / "review.js"),
                                   "FAKE_CFG": str(self.tools / "cfg.json")})
                self.assertEqual(r.returncode, code, r.stdout + r.stderr)
                self.no_approval_files()

    # --- fixes: generated approval carries the sprint line; CRLF / non-ASCII byte-exact hashing
    def test_genuine_review_then_next_advances_to_phase_9(self):
        rc, out = self.request()
        self.assertEqual(rc, 0, out)
        gate = (H.sdlc(self.repo) / "gate-approval.md").read_text(encoding="utf-8")
        self.assertIn("Sprint: " + H.TEST_SID, gate)
        self.assertIn(core.head(self.repo), gate)
        r = H.run_cli(self.repo, "next")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(state(self.repo)["phase"], 9)
        self.assertEqual(state(self.repo)["history"][-1]["phase"], 8)

    def test_genuine_review_via_cli_then_next(self):
        cfg = {"result": APPROVE, "argv_out": str(self.argv), "packet_out": str(self.tools / "packet.md")}
        (self.tools / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
        env = {"AF_PM_REVIEW_JS": str(self.tools / "review.js"), "FAKE_CFG": str(self.tools / "cfg.json")}
        r = H.run_cli(self.repo, "pm-review", "--kind", "code", "--base", self.first, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(H.run_cli(self.repo, "verify").returncode, 0)
        self.assertEqual(H.run_cli(self.repo, "next").returncode, 0)
        self.assertEqual(state(self.repo)["phase"], 9)

    def test_no_sprint_state_means_no_sprint_line(self):
        (H.sdlc(self.repo) / "state.json").unlink()
        rc, out = self.request()
        self.assertEqual(rc, 0, out)
        gate = (H.sdlc(self.repo) / "gate-approval.md").read_text(encoding="utf-8")
        self.assertNotIn("Sprint:", gate)
        self.assertIn(core.head(self.repo), gate)

    def test_docs_approval_carries_sprint_line(self):
        rc, out = self.request(kind="docs")
        self.assertEqual(rc, 0, out)
        self.assertIn("Sprint: " + H.TEST_SID, (H.sdlc(self.repo) / "docs-approval.md").read_text(encoding="utf-8"))

    def test_crlf_in_diff_and_non_ascii_packet_hash_is_byte_exact(self):
        ev = H.write_evidence(self.repo)
        ev["not_run"] = [{"item": "Pr" + chr(252) + "fung " + chr(8212) + " " + chr(1090) + chr(1077) + chr(1089) + chr(1090),
                          "reason": "caf" + chr(233) + " " + chr(26085) + chr(26412)}]
        (H.sdlc(self.repo) / "verify-evidence.json").write_text(json.dumps(ev, ensure_ascii=False), encoding="utf-8")
        H.write_artifact(self.repo, "design.md", "design " + chr(1076) + chr(1080) + chr(1079) + chr(1072) + chr(1081) + chr(1085))
        rc, out = self.request(raw_bytes=True, inject_crlf=True)
        self.assertEqual(rc, 0, out)
        packet_bytes = (H.sdlc(self.repo) / ".pm-review" / f"packet-code-{core.head(self.repo)[:12]}.md").read_bytes()
        self.assertNotIn(bytes([13]), packet_bytes)
        self.assertIn(("Pr" + chr(252) + "fung").encode("utf-8"), packet_bytes)
        prompt_bytes = (H.sdlc(self.repo) / ".pm-review" / f"prompt-code-{core.head(self.repo)[:12]}.txt").read_bytes()
        self.assertIn(bytes([13, 10]), prompt_bytes)  # CRLF really survived inside the dumped Diff block
        a = self.approval()
        self.assertEqual(a["expected_input_hash"], sha(prompt_bytes))
        self.assertEqual(a["input_hash"], a["expected_input_hash"])
        self.assertTrue(pm_review.verify(self.repo)[0])

    def test_crlf_hash_mismatch_still_rejected(self):
        rc, out = self.request(raw_bytes=True, inject_crlf=True, bad_hash="2" * 64)
        self.assertEqual(rc, 1, out)
        self.no_approval_files()

    # --- verify() detects artifact edits after approval
    def approved(self):
        rc, out = self.request()
        self.assertEqual(rc, 0, out)
        ok, why = pm_review.verify(self.repo)
        self.assertTrue(ok, why)

    def test_verify_detects_edited_phase_artifact(self):
        self.approved()
        p = H.sdlc(self.repo) / "design.md"
        original = p.read_bytes()
        p.write_bytes(original + b"tampered")
        ok, why = pm_review.verify(self.repo)
        self.assertFalse(ok)
        self.assertIn("artifacts changed after the approval", why)
        self.assertIn("design.md", why)
        p.write_bytes(original)
        self.assertTrue(pm_review.verify(self.repo)[0])

    def test_verify_detects_edited_structured_evidence(self):
        self.approved()
        p = H.sdlc(self.repo) / "verify-evidence.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["runs"][0]["passed"] = 10
        d["runs"][0]["total"] = 11
        p.write_text(json.dumps(d), encoding="utf-8")
        ok, why = pm_review.verify(self.repo)
        self.assertFalse(ok)
        self.assertIn("verify-evidence.json", why)

    def test_verify_detects_deleted_and_added_artifacts(self):
        self.approved()
        extra = H.sdlc(self.repo) / "change-records" / "c2.md"
        H.write_artifact(self.repo, "change-records/c2.md", "extra")
        ok, why = pm_review.verify(self.repo)
        self.assertFalse(ok)
        self.assertIn("c2.md", why)
        extra.unlink()
        self.assertTrue(pm_review.verify(self.repo)[0])
        (H.sdlc(self.repo) / "backlog.md").unlink()
        ok, why = pm_review.verify(self.repo)
        self.assertFalse(ok)
        self.assertIn("backlog.md", why)

    def test_untouched_artifacts_keep_approval_valid_and_gate_allows_push(self):
        self.approved()
        from af import hook
        self.assertIsNone(hook.gate_decision(self.repo, "git push"))
        p = H.sdlc(self.repo) / "requirements.md"
        p.write_bytes(p.read_bytes() + b"x")
        self.assertIsNotNone(hook.gate_decision(self.repo, "git push"))


if __name__ == "__main__":
    unittest.main()
