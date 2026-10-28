"""Round-4 hardening: sprint-start staleness, PM review preflight + digests, next --force, effort mapping, core hygiene."""
import contextlib
import hashlib
import io
import json
import os
import shutil
import tomllib
import unittest
from unittest import mock

import afhelpers as H
from afhelpers import ROOT, core, deploy, pm_review, APPROVE

NODE = shutil.which("node")
GOOD = chr(10).join(["# Evidence", "", "## Test evidence", "all green", "", "## NOT_RUN", "nothing", ""])
PAST = 1_000_000_000  # 2001: well before any sprint start


def state(repo):
    return core.read_state(repo)


def age(path, ts=PAST):
    os.utime(path, (ts, ts))


class StaleArtifacts(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)

    def test_artifact_from_before_start_is_rejected_then_after_start_accepted(self):
        H.write_artifact(self.repo, "requirements.md")
        age(H.sdlc(self.repo) / "requirements.md")
        r = H.run_cli(self.repo, "start", "S")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(core.missing_artifacts(self.repo, 1), ["requirements.md"])
        blocked = H.run_cli(self.repo, "next")
        self.assertEqual(blocked.returncode, 1)
        self.assertIn("requirements.md", blocked.stdout)
        # rewriting it after the start makes it count
        H.write_artifact(self.repo, "requirements.md", "fresh\n")
        self.assertEqual(core.missing_artifacts(self.repo, 1), [])
        ok = H.run_cli(self.repo, "next")
        self.assertEqual(ok.returncode, 0, ok.stdout)
        self.assertEqual(state(self.repo)["phase"], 2)

    def test_artifact_created_after_start_accepted(self):
        H.run_cli(self.repo, "start", "S")
        H.write_artifact(self.repo, "requirements.md")
        self.assertEqual(core.missing_artifacts(self.repo, 1), [])

    def test_stale_artifact_does_not_count_via_on_either(self):
        H.write_artifact(self.repo, "requirements.md")
        age(H.sdlc(self.repo) / "requirements.md")
        H.run_cli(self.repo, "on")
        self.assertEqual(core.missing_artifacts(self.repo, 1), ["requirements.md"])

    def test_force_still_skips_missing_artifacts(self):
        H.run_cli(self.repo, "start", "S")
        r = H.run_cli(self.repo, "next", "--force")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(state(self.repo)["phase"], 2)
        self.assertTrue(state(self.repo)["history"][-1]["forced"])

    def test_glob_artifact_staleness_phase_6(self):
        H.set_state(self.repo, phase=6)
        st = state(self.repo)
        st["started_epoch"] = 2_000_000_000.0  # far future start: anything on disk is older
        core.write_state(self.repo, st)
        H.write_artifact(self.repo, "change-records/c1.md")
        self.assertEqual(core.missing_artifacts(self.repo, 6), ["change-records/*.md"])
        st["started_epoch"] = PAST
        core.write_state(self.repo, st)
        self.assertEqual(core.missing_artifacts(self.repo, 6), [])

    def test_legacy_state_without_started_epoch_keeps_old_behaviour(self):
        H.write_artifact(self.repo, "requirements.md")
        age(H.sdlc(self.repo) / "requirements.md")
        H.set_state(self.repo, phase=1)  # helper writes a state without started_epoch
        self.assertNotIn("started_epoch", state(self.repo))
        self.assertEqual(core.missing_artifacts(self.repo, 1), [])

    def test_no_state_means_no_staleness_filter(self):
        H.write_artifact(self.repo, "requirements.md")
        age(H.sdlc(self.repo) / "requirements.md")
        self.assertEqual(core.missing_artifacts(self.repo, 1), [])

    def test_start_and_on_record_epoch_and_start_head(self):
        for cmd in (("start", "S"), ("on",)):
            repo = H.make_repo(self)
            r = H.run_cli(repo, *cmd)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            st = state(repo)
            self.assertEqual(st["start_head"], core.head(repo))
            self.assertIsInstance(st["started_epoch"], float)
            self.assertLessEqual(abs(st["started_epoch"] - __import__("time").time()), 120)

    def test_resume_keeps_original_epoch_and_start_head(self):
        H.run_cli(self.repo, "on")
        before = state(self.repo)
        H.run_cli(self.repo, "off")
        H.commit_file(self.repo, "later.txt")
        H.run_cli(self.repo, "on")
        after = state(self.repo)
        self.assertEqual((after["started_epoch"], after["start_head"]), (before["started_epoch"], before["start_head"]))


class NextForce(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)
        H.commit_file(self.repo, "a.txt")

    def test_force_at_phase8_without_approval_stays_blocked(self):
        H.set_state(self.repo, phase=8)
        H.write_artifact(self.repo, "gate-approval.md")  # a hand-written file is not an approval
        r = H.run_cli(self.repo, "next", "--force")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--force does not apply", r.stdout)
        self.assertEqual(state(self.repo)["phase"], 8)
        self.assertEqual(state(self.repo)["history"], [])

    def test_force_with_missing_artifact_and_no_approval_stays_blocked(self):
        H.set_state(self.repo, phase=8)
        r = H.run_cli(self.repo, "next", "--force")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(state(self.repo)["phase"], 8)

    def test_phase8_with_valid_approval_passes_without_force(self):
        H.set_state(self.repo, phase=8)
        H.write_approval(self.repo)
        r = H.run_cli(self.repo, "next")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(state(self.repo)["phase"], 9)

    def test_force_with_valid_approval_advances(self):
        H.set_state(self.repo, phase=8)
        H.write_approval(self.repo)
        r = H.run_cli(self.repo, "next", "--force")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(state(self.repo)["phase"], 9)
        self.assertTrue(state(self.repo)["history"][-1]["forced"])

    def test_force_skips_missing_artifact_only_when_approval_valid(self):
        H.set_state(self.repo, phase=8)
        H.write_approval(self.repo, md=None)  # approval.json valid, but no gate-approval.md artifact on disk
        r = H.run_cli(self.repo, "next", "--force")
        # verify() itself requires gate-approval.md to match, so this must stay blocked
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(state(self.repo)["phase"], 8)

    def test_stale_approval_after_new_commit_blocks_even_with_force(self):
        H.set_state(self.repo, phase=8)
        H.write_approval(self.repo)
        H.commit_file(self.repo, "b.txt")
        r = H.run_cli(self.repo, "next", "--force")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(state(self.repo)["phase"], 8)


@unittest.skipUnless(NODE, "NOT_RUN: node is not available; fake review.js cannot be executed")
class Preflight(unittest.TestCase):
    def setUp(self):
        self.repo = H.make_repo(self)
        self.first = H.first_commit(self.repo)
        H.commit_file(self.repo, "a.txt")
        H.set_state(self.repo, phase=8)
        H.write_artifact(self.repo, "verify-evidence.md", GOOD)
        self.tools = H.tmpdir(self)
        (self.tools / "review.js").write_text(H.FAKE_REVIEW_JS, encoding="utf-8")
        self.argv = self.tools / "argv.json"

    def request(self, base=None, kind="code", repo=None):
        repo = repo or self.repo
        cfg = {"result": APPROVE, "argv_out": str(self.argv), "packet_out": str(self.tools / "packet.md")}
        (self.tools / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
        env = {"AF_PM_REVIEW_JS": str(self.tools / "review.js"), "FAKE_CFG": str(self.tools / "cfg.json")}
        buf = io.StringIO()
        with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(buf):
            rc = pm_review.request(repo, kind, base or self.first)
        return rc, buf.getvalue()

    def assert_refused(self, rc, out, needle=None):
        self.assertEqual(rc, 2, out)
        self.assertIn("REFUSED", out)
        if needle:
            self.assertIn(needle, out)
        self.assertFalse(self.argv.exists(), "review.js must not be invoked")
        self.assertFalse((H.sdlc(self.repo) / ".pm-review" / "approval.json").exists())

    def test_baseline_compliant_request_approves(self):
        rc, out = self.request()
        self.assertEqual(rc, 0, out)

    def test_evidence_file_missing(self):
        (H.sdlc(self.repo) / "verify-evidence.md").unlink()
        self.assert_refused(*self.request(), "verify-evidence.md")

    def test_evidence_lacks_each_required_heading(self):
        for drop in ("## Test evidence", "## NOT_RUN"):
            with self.subTest(missing=drop):
                H.write_artifact(self.repo, "verify-evidence.md", GOOD.replace(drop, "## Other"))
                self.assert_refused(*self.request(), drop)

    def test_evidence_empty(self):
        H.write_artifact(self.repo, "verify-evidence.md", "")
        self.assert_refused(*self.request())

    def test_docs_kind_does_not_need_evidence(self):
        (H.sdlc(self.repo) / "verify-evidence.md").unlink()
        rc, out = self.request(kind="docs")
        self.assertEqual(rc, 0, out)

    def test_base_does_not_resolve(self):
        self.assert_refused(*self.request(base="no-such-ref"), "does not resolve")

    def test_base_not_an_ancestor_of_head(self):
        H.git(self.repo, "checkout", "-q", "-b", "side", self.first)
        side = H.commit_file(self.repo, "side.txt")
        H.git(self.repo, "checkout", "-q", "-")
        self.assert_refused(*self.request(base=side), "not an ancestor")

    def test_base_after_sprint_start_head_is_refused(self):
        start = core.head(self.repo)
        mid = H.commit_file(self.repo, "mid.txt")
        H.commit_file(self.repo, "late.txt")
        st = state(self.repo)
        st["start_head"] = start
        core.write_state(self.repo, st)
        self.assert_refused(*self.request(base=mid), "sprint baseline")

    def test_base_at_or_before_start_head_is_accepted(self):
        start = core.head(self.repo)
        H.commit_file(self.repo, "work.txt")
        st = state(self.repo)
        st["start_head"] = start
        core.write_state(self.repo, st)
        for base in (self.first, start):
            with self.subTest(base=base):
                rc, out = self.request(base=base)
                self.assertEqual(rc, 0, out)

    def test_docs_kind_ignores_start_head_coverage(self):
        start = core.head(self.repo)
        mid = H.commit_file(self.repo, "mid.txt")
        H.commit_file(self.repo, "late.txt")
        st = state(self.repo)
        st["start_head"] = start
        core.write_state(self.repo, st)
        rc, out = self.request(base=mid, kind="docs")
        self.assertEqual(rc, 0, out)

    def test_empty_range_refused(self):
        self.assert_refused(*self.request(base=core.head(self.repo)), "empty")

    def test_digests_recorded_and_correct(self):
        rc, out = self.request()
        self.assertEqual(rc, 0, out)
        a = json.loads((H.sdlc(self.repo) / ".pm-review" / "approval.json").read_text(encoding="utf-8"))
        head = core.head(self.repo)
        self.assertEqual(a["base_sha"], self.first)
        diff = H.git(self.repo, "diff", f"{self.first}...{head}")
        self.assertEqual(a["diff_sha256"], hashlib.sha256(diff.encode("utf-8")).hexdigest())
        ev = (H.sdlc(self.repo) / "verify-evidence.md").read_bytes()
        self.assertEqual(a["evidence_sha256"], hashlib.sha256(ev).hexdigest())
        self.assertTrue(pm_review.verify(self.repo)[0])

    def test_digest_changes_with_range_and_evidence(self):
        self.request()
        p = H.sdlc(self.repo) / ".pm-review" / "approval.json"
        a1 = json.loads(p.read_text(encoding="utf-8"))
        H.commit_file(self.repo, "more.txt")
        H.write_artifact(self.repo, "verify-evidence.md", GOOD + "extra line" + chr(10))
        self.request()
        a2 = json.loads(p.read_text(encoding="utf-8"))
        self.assertNotEqual(a1["diff_sha256"], a2["diff_sha256"])
        self.assertNotEqual(a1["evidence_sha256"], a2["evidence_sha256"])
        self.assertEqual(a1["base_sha"], a2["base_sha"])

    def test_cli_refuses_with_exit_2_without_evidence(self):
        (H.sdlc(self.repo) / "verify-evidence.md").unlink()
        cfg = {"result": APPROVE, "argv_out": str(self.argv), "packet_out": str(self.tools / "packet.md")}
        (self.tools / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
        r = H.run_cli(self.repo, "pm-review", "--kind", "code", "--base", self.first,
                      env={"AF_PM_REVIEW_JS": str(self.tools / "review.js"), "FAKE_CFG": str(self.tools / "cfg.json")})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("REFUSED", r.stdout)
        self.assertFalse(self.argv.exists())


class EffortMapping(unittest.TestCase):
    CLAUDE = {"model": "sonnet", "effort": "medium"}
    CODEX = {"model": "gpt-6-luna", "effort": "medium"}

    def meta(self, effort=None):
        m = {"name": "x", "description": "d"}
        if effort is not None:
            m["effort"] = effort
        return m

    def claude_effort(self, effort):
        text = deploy.render_claude_agent(self.meta(effort), "body", self.CLAUDE)
        return [l for l in text.splitlines() if l.startswith("effort:")][0].split(": ")[1]

    def codex_effort(self, effort):
        return tomllib.loads(deploy.render_codex_agent(self.meta(effort), "body", self.CODEX))["model_reasoning_effort"]

    def test_claude_allowed_values_preserved(self):
        for e in ("low", "medium", "high", "HIGH", " high "):
            with self.subTest(e=e):
                self.assertEqual(self.claude_effort(e), e.strip().lower())

    def test_claude_unsupported_or_missing_falls_back_to_default(self):
        for e in ("xhigh", "max", "", "turbo", None):
            with self.subTest(e=e):
                self.assertEqual(self.claude_effort(e), "medium")

    def test_codex_allowed_values_preserved(self):
        for e in ("low", "medium"):
            self.assertEqual(self.codex_effort(e), e)

    def test_codex_high_and_xhigh_fall_back_to_default(self):
        for e in ("high", "xhigh", "", None):
            with self.subTest(e=e):
                self.assertEqual(self.codex_effort(e), "medium")

    def test_default_follows_target_not_hardcoded(self):
        low = {"model": "m", "effort": "low"}
        text = deploy.render_claude_agent(self.meta("xhigh"), "b", low)
        self.assertIn("effort: low", text)

    def test_ui_designer_deployed_values(self):
        deploy.build()
        src, _ = deploy.parse_agent(ROOT / "core" / "agents" / "ui-designer.md")
        self.assertEqual(src["effort"], "high")
        cl = (ROOT / "deploy" / "claude" / "agents" / "ui-designer.md").read_text(encoding="utf-8")
        self.assertIn("effort: high", cl)
        cx = tomllib.loads((ROOT / "deploy" / "codex" / "agents" / "ui-designer.toml").read_text(encoding="utf-8"))
        self.assertEqual(cx["model_reasoning_effort"], "medium")

    def test_every_deployed_agent_effort_is_policy_allowed_and_matches_source(self):
        deploy.build()
        cfg = json.loads((ROOT / "core" / "framework.json").read_text(encoding="utf-8"))
        for name in cfg["bundled_agents"]:
            src, _ = deploy.parse_agent(ROOT / "core" / "agents" / f"{name}.md")
            e = str(src.get("effort", "")).strip().lower()
            cl = deploy.parse_agent(ROOT / "deploy" / "claude" / "agents" / f"{name}.md")[0]["effort"]
            cx = tomllib.loads((ROOT / "deploy" / "codex" / "agents" / f"{name}.toml").read_text(encoding="utf-8"))
            with self.subTest(agent=name):
                self.assertIn(cl, ("low", "medium", "high"))
                self.assertIn(cx["model_reasoning_effort"], ("low", "medium"))
                self.assertEqual(cl, e if e in ("low", "medium", "high") else "medium")
                self.assertEqual(cx["model_reasoning_effort"], e if e in ("low", "medium") else "medium")


class CoreHygiene(unittest.TestCase):
    def test_core_has_no_tools_vst_or_s1_store_mentions(self):
        hits = []
        for f in (ROOT / "core").rglob("*"):
            if f.is_file():
                try:
                    t = f.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for needle in ("tools/vst", "tools" + chr(92) + "vst", "S1 store"):
                    if needle in t:
                        hits.append((str(f.relative_to(ROOT)), needle))
        self.assertEqual(hits, [])

    def test_deployed_output_has_no_tools_vst(self):
        deploy.build()
        hits = [str(f) for f in (ROOT / "deploy").rglob("*") if f.is_file()
                and "tools/vst" in f.read_text(encoding="utf-8", errors="ignore")]
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
