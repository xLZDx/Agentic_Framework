---
name: agent-consensus
description: Multi-round peer-review consensus loop across specialist agents on architectural plans. Recon-triages roster, runs round 1 in parallel, cross-reviews in round 2, converges or hits 4-round circuit breaker. Use for any architectural / multi-phase / multi-file plan before showing operator.
---

# Agent Consensus Loop — Core Protocol

Drive the N-round consensus loop until convergence or hard 4-round circuit breaker. Full output template + Round 0 JSON schema + anti-patterns are in `REFERENCE.md` (Read on demand, do NOT auto-load).

## Inputs

| Arg | Default | Meaning |
|---|---|---|
| Plan text (required) | — | Plan under review. Pass inline or doc path. |
| `--tier T1\|T2\|T3\|T4` | auto-detect | Override tier classification. |
| `--max-rounds N` | per tier | T2=1, T3=2, T4=4. |
| `--quorum N` | 2 | Agents AGREE needed to confirm a finding. |

## Tier classification (apply FIRST)

| Tier | Trigger | Agents | Rounds | Typical calls |
|---|---|---|---|---|
| **T1** | typo / 1-line config / comment-only | 0 | 0 | 0 — skip skill |
| **T2** | single-file logic change | 3 | 1 | 3 |
| **T3** | multi-file feature, single domain | 5-7 | 1-2 | 5-14 |
| **T4** | architectural / multi-domain / ML / risk / governance | 10-15 | up to 4 | 17-60 |

Only **T4** runs the full loop. T1 skipped. T2/T3 stop after round 1 (or 2 if findings overlap).

## Protocol

### Round 0 — Structured Recon + Triage (T3/T4 only)

Spawn ONE `code-explorer` (or `Explore`) with plan + agent roster (`~/.claude/CLAUDE.md`) + findings cache (`<project>/core/KNOWN_OBJECTIONS.md`). Agent MUST return JSON per the schema in `REFERENCE.md` (no preamble): `plan_tier`, `domains_touched`, `relevant_agents[]`, `skip_agents[]`, `known_objection_matches[]`.

Spawn EXACTLY the agents in `relevant_agents` — do not subjectively second-guess. If a relevant agent is missing, fix the recon prompt and re-run round 0; do not patch the roster.

**Floor sanity check:** T2≥3, T3≥5, T4≥8 (≥12 if ml/risk/governance/data/security in domains). If JSON falls below, recon was too narrow; re-run with explicit "consider full domain map".

### Round 1 — Discovery (parallel)

One message, multiple parallel `Agent` calls. Each agent receives plan + specialist framing + matching `known_objection_matches` (respond `applies` / `does-not-apply`; do NOT re-derive). Output format: `BLOCKER | MAJOR | MINOR | NIT` with one-sentence justification.

Collect: `round_1_findings = {agent → [findings]}`.

### Skip-round-2 gate

Skip round 2 if ALL hold: 0 BLOCKER, ≤2 MAJOR, no overlapping concerns, each MAJOR bounded to one specialty. Covers ~60% of plans → straight to operator-presentation.

### Round 2 — Cross-Review (parallel, NARROWED)

Respawn only agents whose domains overlap with findings requiring debate (typical 30-50% of round 1). Domain-bounded findings (e.g. SSRF flagged by `security-reviewer` alone) auto-confirm without peer vote.

Each agent receives plan + their round-1 (brief) + ALL peer findings. Brevity: one sentence per peer finding (`AGREE` / `DISAGREE` / `REFINE` + justification); one sentence per new finding; no re-explanation.

Bucket consolidation: `confirmed` (≥quorum AGREE), `contested` (any DISAGREE), `refined` (REFINE accepted), `new`.

### Skip-round-3 gate

Skip round 3 if zero `contested` AND zero `new` BLOCKER/MAJOR.

### Round 3+ — Convergence Check

Narrow respawn on `contested` + `new`. Each declares "consensus reached" OR "remaining concerns: …" (one sentence per item).

### Stop conditions (ALL must hold)

1. Every agent in current round declares "consensus reached".
2. No NEW BLOCKER/MAJOR in this round.
3. Zero DISAGREE on prior findings.

### Circuit breaker

Hard max **4 rounds**. After 4: stop, surface unresolved items with each agent's stated position verbatim, mark report `partial_consensus`.

## When to invoke

- Operator types `/agent-consensus` explicitly.
- Implicitly for any architectural / multi-phase / multi-file plan (mandated by `~/.claude/CLAUDE.md`).
- Plans touching: new modules, risk/governance, ML pipeline, data infra, cross-project refactor, security-sensitive surfaces.

## When NOT to invoke

- Single-line tweaks, typo fixes, log rewording, comment-only changes.
- Sub-steps of already-consensused plans.
- Pure execution (tests, restart, cleanup) inside reviewed scope.

## Reference material (load on demand)

When you need the full Round 0 JSON schema, output artifact template, anti-patterns list, cost details, or cross-references: **Read `REFERENCE.md` in this skill directory**. Do NOT auto-load — it costs ~1200 tokens you usually don't need.

Memory: `feedback_agent_consensus_loop.md`.
