## Why

Wave0 is still the change-04 fixture: `wave0/node.py` is the
`UNAVAILABLE_REAL_FACTORY` sentinel and its fake runs three fixture workers that
write canned `fixture.json` artifacts through the shared work-unit component.
Every later research phase depends on Wave0 having *actually* performed
breadth-first source intake — fetching real sources per topic, validating them,
and recording accepted `SubmissionRecord`s that Wave1, synthesis, and the
critics use as the evidence baseline. Without a real Wave0, there is no real
evidence authority and the research waves have nothing to deepen. This change
upgrades Wave0 to the first real worker node while preserving the full-fake
path, the work-unit kernel, the gate, and the three-authority boundary.

## What Changes

- Replace the fake/sentinel Wave0 node with a real controller that reads the
  planner-owned `topic_registry`/`topic_refs` and materializes one immutable
  source-intake `WorkSpec` per topic through the existing work-unit controller
  (reusing `materialize_work_spec` and the shared fan-out/fan-in component). The
  real node keeps the exact `node_update` + parent work-block update +
  `WorkUnitGateView` return shape the wrapper already pops.
- Run a bounded web source-intake worker per `WorkSpec` through
  `capabilities.run_agent()` on the runtime node-agent bridge, with a real
  non-zero `ExecutionPolicy` (allowed web search/fetch tool names, per-tool
  `ToolPolicySpec`, attempt-scoped read/write roots). The worker produces a
  `wave0.source-intake` result document with canonical source URLs, source
  metadata, baseline facts, fetch/cache refs, and limitations.
- Generalize the deterministic submit validator's hard-coded
  `("fixture.work-unit", 1)` result-contract check into a registry and register
  the real `wave0.source-intake` v1 contract with a frozen result model. Submit
  validation canonicalizes URLs, verifies real fetched/cached content refs,
  checks path/hash/source identity, and rejects snippet-as-cache,
  cross-attempt, and out-of-containment writes. Only accepted
  `SubmissionRecord`s count as coverage.
- Treat all external page/PDF/snippet/cache content as untrusted data (NOA-004):
  it is placed in the `<untrusted-source-data>` block or referenced as a sandbox
  artifact, never spliced into the trusted system prompt, and the deny-by-default
  `ToolPolicyMiddleware` blocks any tool/path the worker is not allow-listed for.
  Adversarial sources ("ignore rules", "call a forbidden tool", "mark me
  authoritative") only produce a source limitation or rejection.
- Replace the Wave0 fixture gate with a real gate: drop `FixtureSequenceRule`,
  keep the shared `WorkUnitCompletionRule`, and add a real source-floor rule
  (per-topic minimum independent sources, dedup, drain). Source-floor coverage is
  encoded at submit-validation time because gate rules are pure and the
  `WorkUnitGateView` carries accepted-record hashes, not source counts.
- Add an honest degraded-capture contract: when a source is unreachable, the
  worker records a typed degraded capture rather than fabricating a success, and
  the gate may pass with a degraded verdict when the floor is met by independent
  sources.
- Swap real Wave0 into the mixed implementation map. The topology is unchanged
  (Wave0 already has `repair`/`pass`/`exhausted` edges); only the node internals
  and the gate definition change. The lifecycle result remains
  `implementation_mode=full_fake` because Wave1, synthesis, HITL2, and final
  delivery remain fake.
- `backend/` and `frontend/` are not modified.

## Capabilities

### New Capabilities

- `wave0-node`: Real Wave0 source-intake node behavior — per-topic
  `WorkSpec` materialization from the planner registry via the work-unit
  controller, a bounded web worker agent with an untrusted-data discipline, a
  real `wave0.source-intake` result contract with canonicalized/verified sources,
  deterministic submit validation, a real source-floor gate with degraded
  capture, and mixed-graph integration preserving full-fake behavior. Requirement
  IDs: WAN-001 through WAN-005.

### Modified Capabilities

- `work-unit-kernel`: generalize the submit validator's hard-coded fixture
  result-contract check into a registry of `(result_contract,
  result_schema_version)` validators and register `wave0.source-intake` v1,
  while preserving every existing kernel contract and fixture scenario.
- `research-graph-lifecycle`: add real-Wave0 scenarios to the routing/fan-in,
  three-authority, and bundle-layout requirements (real workers write only their
  attempt artifacts and the validated ledger; worker text never counts as
  coverage) while preserving every existing full-fake Wave0 scenario and the
  repair/pass/exhausted routes.
- `project-structure`: register the new production paths
  `graph/nodes/wave0/prompts.py` and `graph/nodes/wave0/gate.py` (and any new
  domain result-contract module) through the PRS-004 mechanical sync.

The `deep_research_tool` reflection path, identity derivation, the request-bundle
profile writer, and the work-unit store/ledger are unchanged. The Wave0 gate
still writes the route via the gate kernel (GAK-003).

## Impact

- **Source:** add a frozen `wave0.source-intake` result-contract model (under
  `domain/` or `graph/nodes/wave0/`); add a worker prompt helper under
  `graph/nodes/wave0/prompts.py`; add the real Wave0 gate rules under
  `graph/nodes/wave0/gate.py`; replace the `UNAVAILABLE_REAL_FACTORY` sentinel
  in `graph/nodes/wave0/node.py` with a real factory that reads the topic
  registry and drives the shared component with real per-topic intents + a real
  worker; extend `wave0/subgraph.py` to supply real intents/worker; generalize
  `engine/work_units/validation.py` result-contract dispatch into a registry.
  New files are registered via the PRS-004 sync.
- **Typed state/checkpoint data affected:** none new. Wave0 writes the existing
  controller/submit-owned work block (`work_specs_by_id`, `attempts_by_id`,
  `work_status_by_id`, `active_attempt_by_work_id`,
  `terminal_failures_by_attempt_id`, `accepted_submission_refs`) and reads the
  planner-owned `topic_registry`/`topic_refs`. `RESEARCH_STATE_SCHEMA_VERSION`
  is not bumped.
- **Graph nodes/components affected:** only `wave0` swaps from fake/sentinel to
  real in the mixed graph; every other phase remains fake. Wave0 stays gated and
  keeps its `repair`/`pass`/`exhausted` routes; the gate definition is replaced
  (fixture rule removed, completion rule kept, source-floor rule added). The
  shared `run_work_unit_component` is reused unchanged.
- **Node-agent roles used:** Wave0 runs one bounded worker agent per in-flight
  attempt through `capabilities.run_agent()`, under a real `ExecutionPolicy`
  with web search/fetch tools, attempt-scoped roots, and a bounded budget. The
  worker cannot write phase/gate/ledger state, cannot write another attempt's
  directory, and sees only its own `WorkSpec`. Fetched content is untrusted data.
- **Sandbox artifacts read/written:** the controller writes `work-spec.json`;
  each worker writes its `result.json` + declared `outputs/` and fetched/cache
  content only under its own `work/<work_id>/<attempt_id>/` root; submit writes
  the hash-chained `evidence/submissions.jsonl`. Out-of-containment,
  cross-attempt, and snippet-as-cache writes are rejected.
- **DeerFlow extension surfaces:** the existing reflection path
  `deerflow_deep_research.tool:deep_research_tool` and lifecycle handlers are
  unchanged. Wave0's worker consumes DeerFlow web search/fetch tools through the
  bridge's `_default_tools_resolver` filtered by the worker policy's
  `allowed_tool_names`. Concrete web-tool **provisioning is an operator
  configuration prerequisite**: the deep-research agent must have web tools
  configured for Wave0 to fetch real sources. This change declares the worker
  tool-policy surface and surfaces the prerequisite via doctor/configure; it does
  not add a specific provider, no `extensions_config.json` key, no public/custom
  skill, no per-user Agent/SOUL, no MCP/ACP, and no lead-agent middleware change.
- **Diagnostics:** doctor gains a read-only indication when no web tools are
  configured for the deep-research agent (Wave0 would produce no sources). Real
  Wave0 is available only in the mixed recipe with `bootstrap=real`,
  `hitl1=real`, and `topic_planning=real`, because the worker consumes the real
  topic registry.
- **Reload boundary:** adding web tools to the effective deep-research agent
  config is a next-agent-build change (tool/config changes take effect on the
  next agent build); no `reload_boundary.STARTUP_ONLY_FIELDS` value changes
  unless an operator mounts a new tool provider.
- **Dependencies:** no new third-party runtime dependency. Web tools are
  DeerFlow community tools the operator configures; tests use replay/fake tools.
- **Non-goals:** no deep claim extraction, cross-topic synthesis, or source
  semantic critic (changes 09/10/11); Wave0 sources do not auto-satisfy Wave1's
  new-source floor; no specific web-tool provider is hard-mandated; no real
  Wave1, synthesis, HITL2, or final delivery. No files under `backend/` or
  `frontend/` are modified.

New requirement IDs are WAN-001 through WAN-005 (`wave0-node`). Existing WOU, GAK,
NOA, and REG requirements are referenced (work-unit kernel, gate, node-agent
runtime, lifecycle) and modified narrowly to register the real result contract,
the real Wave0 gate, and the new paths; supporting files are registered through
the existing PRS-004 registry sync.
