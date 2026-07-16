## Context

Change 07 delivered a real topic planning node that records a validated topic
registry as bounded planner-owned checkpoint state (`topic_refs`,
`topic_registry`). The Wave0 node (`graph/nodes/wave0/`) is still the change-04
fixture: `node.py` is the `UNAVAILABLE_REAL_FACTORY` sentinel and `subgraph.py`
runs three fixture workers (`WAVE0_FIXTURE_INTENTS`) through the shared
`run_fixture_work_unit_component`. Wave0 declares `WORK_UNIT_CONTROLLER`, is
gated, and already has `repair`/`pass`/`exhausted` routes.

Real Wave0 is the first real *worker* node. It must turn the topic registry into
per-topic source-intake `WorkSpec`s, run a bounded web worker per work unit that
fetches and validates sources, and record accepted `SubmissionRecord`s as the
evidence baseline for later phases — all without letting untrusted web content
touch control authority.

Verified facts that shape the design:
- The shared fan-out/fan-in component `run_work_unit_component`
  (`graph/components/work_units.py:410`) already implements
  allocate/dispatch/submit/refill/drain and accepts a pluggable `worker`
  callable and real `intents`. The fixture wrapper is a thin recipe over it.
- The submit path (`submit_candidate_if_active`) already validates via a closed
  `SubmissionValidationCode` registry and atomically appends the hash-chained
  ledger. The only hard-coded seam is the result-contract check
  (`engine/work_units/validation.py:104`), which is pinned to
  `("fixture.work-unit", 1)`.
- The node-agent bridge (`runtime/node_agent_bridge.py`) resolves tools via
  `_default_tools_resolver` (loads configured DeerFlow tools, intersects with
  `policy.allowed_tool_names`). HITL1/topic_planning override it with a zero-tool
  lambda; Wave0 must NOT.
- Untrusted-data discipline already exists (NOA-004): `build_untrusted_data_block`,
  the trusted package-resource policy prompt, and deny-by-default
  `ToolPolicyMiddleware`.
- Gate rules are pure/no-I/O (`gate_kernel.py`), and `WorkUnitGateView` carries
  accepted-record hashes, not source counts.

## Goals / Non-Goals

**Goals:**
- Materialize one source-intake `WorkSpec` per topic from the planner registry via
  the existing work-unit controller.
- Run a bounded web worker per work unit through the runtime bridge with a real,
  attempt-scoped tool policy, treating fetched content as untrusted data.
- Register a real `wave0.source-intake` result contract and generalize the
  result-contract validator into a registry.
- Validate submissions deterministically (URL canonicalization, real fetch/cache
  refs, path/hash/source identity) and count only accepted records as coverage.
- Replace the fixture gate with a real source-floor gate (independent sources,
  dedup, drain) and an honest degraded-capture contract.
- Swap real Wave0 into the mixed graph while preserving the full-fake path, the
  work-unit kernel, the gate, the three-authority boundary, and the v2 checkpoint.
- Keep `backend/`, `frontend/`, extensions config, skills, Agent/SOUL, MCP/ACP,
  and lead-agent middleware unchanged.

**Non-Goals:**
- No deep claim extraction, cross-topic synthesis, or source semantic critic
  (changes 09/10/11).
- Wave0 sources do not auto-satisfy Wave1's new-source floor.
- No specific web-tool provider is hard-mandated; provider provisioning is
  operator config.
- No real Wave1, synthesis, HITL2, or final delivery.
- No reading of `request/profile.json` beyond the checkpoint short fields.

## Decisions

### Decision 1: Reuse the shared work-unit component; swap intents and worker

The real Wave0 factory keeps the exact return shape the wrapper expects
(`node_update` + parent work-block update + `WorkUnitGateView` under
`WORK_UNIT_GATE_VIEW_KEY`) and drives `run_work_unit_component` with two
replacements: (a) real per-topic `WorkIntent`s materialized from
`state["topic_registry"]` (one work unit per topic, `scope=(topic_id,)`), and (b)
a real `worker` callable that calls `capabilities.run_agent()` instead of the
fixture artifact-writer loop. The controller primitives
(`materialize_work_spec`, `allocate_attempt`, `select_batch`, `work_is_drained`,
`retry_allowed`) and the submit/ledger/drain machinery are reused unchanged.

Why: the component already solves bounded `Send` fan-out, deterministic fan-in,
terminal-monotonic reducers, retry, and crash reconciliation. Rebuilding them
would duplicate the change-04 authority the architecture forbids.

### Decision 2: One WorkSpec per topic, derived from the planner registry

The controller iterates `topic_registry` (read by `WriterRole.WORKER` per the
ownership table) and builds one `WorkIntent` per topic whose scope binds the
topic id and its must-answer questions and whose required outputs declare the
source-intake artifacts. `materialize_work_spec` mints the immutable `WorkSpec`
identity (`generation`, `phase`, `work_ordinal`) and `spec_hash`. No second
controller or work authority is introduced.

### Decision 3: Real result contract and a validation registry

Change 08 generalizes the hard-coded `("fixture.work-unit", 1)` check in
`engine/work_units/validation.py` into a registry mapping
`(result_contract, result_schema_version) -> validator`, keeps the fixture
contract registered (fake Wave0/Wave1 still use it), and registers the real
`wave0.source-intake` v1 contract with a frozen result model (canonical source
URLs, source metadata, baseline facts, fetch/cache refs, limitations). The
existing `SubmissionValidationCode` closed registry and atomic ledger append are
unchanged; only the result-contract dispatch becomes extensible.

### Decision 4: Bounded web worker with a real, attempt-scoped tool policy

The Wave0 worker bridge uses a real `ExecutionPolicy` (not the zero-tool lambda):
a non-empty `allowed_tool_names` for web search/fetch, per-tool `ToolPolicySpec`
entries declaring each tool's path fields/effect, `read_roots` covering the
worker's attempt root and shared fetch-cache region, `write_roots=(attempt_root,)`
(the policy invariant requires every write root under `attempt_root`), and a
bounded `ExecutionBudget`. The bridge uses `_default_tools_resolver` so the
worker receives the configured web tools filtered by the policy. `_project_result`
enforces the structured-output budget and redacts failures.

### Decision 5: Fetched content is untrusted data; deny-by-default tools

All external page/PDF/snippet/cache text is placed in the
`<untrusted-source-data>` block (via `build_untrusted_data_block`) or referenced
as a sandbox artifact — never spliced into the trusted package-resource system
prompt. The deny-by-default `ToolPolicyMiddleware` re-authorizes every tool call
(name in `allowed_tool_names`, eligible `ToolPolicySpec`, every path field within
roots), so a prompt-injected source cannot escalate to a forbidden tool/path or
mutate phase/gate/ledger state. Adversarial sources only yield a source
limitation or rejection. This is the NOA-004 contract; Wave0 consumes it, it does
not rebuild it.

### Decision 6: Real source-floor gate; coverage encoded at submit time

The Wave0 gate drops `FixtureSequenceRule` and keeps the shared
`WorkUnitCompletionRule` (drain + accepted-record coverage), then adds a real
source-floor rule: each accepted topic submission must carry at least N
independent, deduplicated `SourceRef`s. Because gate rules are pure/no-I/O and
`WorkUnitGateView` carries hashes (not source counts), the per-topic source floor
and independent-source/dedup checks are enforced at **submit-validation time**
(the worker builds `source_refs`; the validator canonicalizes URLs via
`canonicalize_source_url` and rejects duplicates/insufficient-independent-source
candidates). The gate's completion rule then verifies that every planned topic has
an accepted record and the work is drained. The route map stays
`{PASS: "pass", REPAIR: "repair", BLOCKED: "exhausted"}`.

### Decision 7: Honest degraded capture, no fabricated success

When a source is unreachable, the worker records a typed degraded capture in the
result document (limitation + attempted URL + reason) and submits it; the
validator accepts a degraded capture only when the independent-source floor is
otherwise met, and the gate may return a degraded `PASS`. The worker never marks
an unfetched source as authoritative, and worker final text never counts as
coverage — only accepted `SubmissionRecord`s do.

### Decision 8: Web-tool provisioning is an operator prerequisite, surfaced by doctor

Concrete web search/fetch tools are DeerFlow community tools the operator
configures; the deep-research agent template ships none today. Change 08 declares
the Wave0 worker tool-policy surface (`allowed_tool_names`) and the resolver
intersection, and adds a doctor/configure read-only indication when no web tools
are configured for the deep-research agent (Wave0 would produce no sources). It
does **not** add a specific provider, an `extensions_config.json` key, a skill,
or an Agent/SOUL change. Tests inject replay/fake tools (`ReplayChatModel` /
fake tool specs) so the change is fully deterministic without live web access.

### Decision 9: Mixed-graph integration off the real topic chain

Real Wave0 is selectable only in the mixed implementation map and requires
`bootstrap=real`, `hitl1=real`, and `topic_planning=real`, because the worker
consumes the real topic registry. Selecting `wave0=real` without the real topic
chain fails closed before graph invocation (mirroring the topic-planning
dependency guard). The topology is unchanged; full-fake Wave0 remains the fixture
path and does not construct the node-agent bridge.

## Risks / Trade-offs

- **Worker fetches poor/adversarial content:** untrusted-data discipline +
  deny-by-default tools + deterministic submit validation reject malformed or
  injecting sources; the source floor requires independent corroboration.
- **No web tools configured:** doctor surfaces it; tests use replay tools; a real
  install fetches nothing until the operator configures a provider.
- **Live web is non-deterministic:** all tests use replay/fake tools; real-LLM
  /live-web coverage is optional and `@requires_llm`-marked.
- **Gate source floor without I/O:** encoded at submit-validation time so the
  pure gate only reads the resulting accepted records; keeps the gate pure.
- **Checkpoint bloat from sources:** sources live in the sandbox as
  `SourceRef`s/`ContentRef`s; only short refs/hashes enter the ledger and the
  accepted-ref set (WOU/REG-008 boundary unchanged).
- **Cross-attempt writes:** the artifact writer and path containment enforce
  per-attempt roots; the policy invariant forbids writes outside `attempt_root`.

## Migration Plan

None. The change extends the zero-API `implementation_mode=full_fake` skeleton
and reuses the change-04 work-unit kernel. No checkpoint migration, no schema
bump, no mandated restart beyond importing new Python source on the next agent
build. Rollback is `git revert`; the full-fake Wave0 path is never altered.

## Open Questions

- Which web-tool provider(s) to recommend/default for the deep-research agent
  (tavily / jina / ddg / searxng / firecrawl). Deferred to operator config;
  change 08 only declares the policy surface.
- Whether to extend `WorkUnitGateView` with a per-work source count for richer
  gate rules in a later change. Not needed for v1 (submit-time enforcement
  suffices).
