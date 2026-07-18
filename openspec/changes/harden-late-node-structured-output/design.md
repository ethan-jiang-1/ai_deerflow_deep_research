## Context

The credentialed six-case live lane introduced by `rebalance-deep-research-test-assets` passed four focused prefixes and exposed two late-node failures on 2026-07-18. Wave2 returned the same otherwise valid object twice, with `search_required` present on a gap. `SynthesisFinding` owns that field today, but `GapRecord` forbids it even though `targeted_evidence.subgraph.materialize_gap_intents` consumes it from gap dictionaries. Targeted evidence then used three web-tool calls and had no model turn left for a structured answer; a bounded two-tool reproduction reached a final prose answer, which `parse_targeted_worker_output` correctly rejected. The targeted worker currently has no node-owned structured repair.

The affected production code is project-owned under `agent/src/deerflow_deep_research/`. The submission ledger remains the only accepted-evidence authority, canonical synthesis and targeted result documents remain sandbox content authority, and checkpoint state remains compact control authority. Path audit also found that real Wave2 currently returns no synthesis-gap projection and `build_wave2_real_gate_def()` is a pass-through rule, while real targeted evidence reads a nonexistent `synthesis_gaps` state field. A field-only fix would therefore validate the provider response but still bypass the targeted loop in the full graph. `backend/`, `frontend/`, public entry, and the DeerFlow node-agent runtime are unchanged; topology gains only the declared Wave2 exhausted terminal edge.

The first post-remediation complete lane passed targeted evidence but found two adjacent constraints. Focused Wave1 returned three consecutive tool-only messages because `build_wave1_worker_prompt` permits three tool calls while the live bridge permits three model calls; no successful draft exists for its already-present repair path. Focused Wave2 returned a schema-valid object with one searchable gap but zero findings. `_validate_synthesis_semantics` currently rejects only when both findings and gaps are empty, so accepted evidence can produce no synthesized finding and still be persisted. These are narrow request/semantic-floor defects at existing seams, not reasons to alter the shared bridge or public pipeline.

## Goals / Non-Goals

**Goals:**

- Establish one canonical `search_required` value on each synthesis gap and preserve it from model validation through canonical artifact storage to targeted intent routing.
- Establish the missing deterministic Wave2 gate path so searchable gaps route to targeted evidence through bounded gate-owned control state.
- Give the targeted worker a bounded opportunity to produce structured output after tool use and exactly one zero-tool repair after a successful but invalid initial answer.
- Preserve fail-closed, atomic publication: no invalid attempt creates source/result artifacts or ledger authority.
- Close both findings first with deterministic tests at the responsible production seams, then confirm provider compatibility through the existing focused live lane.
- Reserve a final structured-answer turn for Wave1 and require accepted evidence to yield at least one backed Wave2 finding before persistence.

**Non-Goals:**

- No generalized automatic JSON extraction, markdown stripping, provider-specific coercion, or arbitrary prose-to-schema parser.
- No change to the shared `RuntimeNodeAgentBridge`, global Wave0/Wave1 execution policies, checkpoint schema version, or synthesis schema version. The Wave1 change is request-local only. The only topology change is the missing Wave2 `exhausted -> blocked/END` terminal edge; no node or other route changes.
- No repair behavior for source-diagnostic or claim-verifier critics; the observed finding is specific to the targeted evidence worker submit path.
- No redesign of HITL2's complete synthesis-summary input. Audit found that its brief builder also reads the nonexistent `synthesis_gaps` state field, but the gate-owned `unresolved_gaps` ids introduced here represent only searchable routing work and are not an honest substitute for all canonical findings/gaps.
- No new persisted trace replay or additional full-pipeline E2E. The existing live canary is sufficient for provider-dependent confirmation, and the existing release lane remains singular.

## Decisions

### 1. Put routing intent on canonical `GapRecord` and project only ids through the gate

Add `search_required: bool = False` to `GapRecord`. Wave2 prompts will name fields separately for findings and gaps, including the gap field explicitly. Provider normalization will preserve an explicit boolean and rely on the default only when the field is absent. The canonical `synthesis/findings.json` document stores the value unchanged.

This resolves the current split authority: the targeted router already asks the gap for `search_required`, but the canonical gap contract rejects it. Keeping the default false preserves schema-version-1 artifacts produced before this change and prevents old or merely descriptive gaps from unexpectedly scheduling network work. The alternative of deriving the flag from `description`, priority, or `SynthesisFinding.search_required` is rejected because it creates implicit routing authority and unstable semantics.

The Wave2 node will return one internal `Wave2GatePreview` value under a reserved private result key, following the existing `WorkUnitGateView`/`WORK_UNIT_GATE_VIEW_KEY` pattern rather than adding a public store or reducer interface. Its small interface contains only the bounded, unique, canonical gap ids whose validated gaps have `search_required=true`; construction rejects unknown/duplicate/non-gap ids. The graph wrapper removes that value before the normal node update, validates its type for real Wave2, and places it only in an ephemeral gate-evaluation mapping. The focused canary uses the same graph-to-engine adapter path. A pure deterministic gate rule reads only that typed current view and emits one `MISSING_EVIDENCE` failure with a representative ref; after the shared kernel derives its verdict, the existing gate adapter projects the complete bounded id tuple from that same validated preview into the gate-owned `unresolved_gaps: tuple[str, ...]` control field and validates the update through `WriterRole.GATE`. No full description, priority, affected-topic list, boolean body, or reserved preview key enters the checkpoint.

The real targeted node will consume `unresolved_gaps` rather than the nonexistent `synthesis_gaps` field and will materialize one intent per id. A later Wave2 pass with an empty preview clears `unresolved_gaps`. A repeated semantic gap continues through the existing gate kernel: the first verdict is `REPAIR/evidence_needed`; after the bounded repair budget/fatigue policy blocks it, the new explicit `exhausted -> blocked/END` edge provides the required terminal path. The alternatives of putting complete gaps in `ResearchState`, letting the Wave2 model/node write `unresolved_gaps` directly, keeping the real gate pass-through, or misclassifying `MISSING_EVIDENCE` as degradable are rejected because they violate the authority split, bypass the targeted route, or corrupt the closed failure taxonomy.

This is an internal in-process seam, not a new public protocol or store interface. The alternative of making the synchronous gate or targeted node reread the artifact through an expanded `SynthesisBundleStoreProtocol` is rejected: it would introduce I/O into pure gate evaluation and duplicate content parsing across callers. The alternative of adding the reserved key to `ResearchState` or its ownership table is also rejected; the wrapper's pop-and-overlay pattern keeps it ephemeral. Tests exercise the existing node-wrapper/gate interface and observable state/artifact results; they do not depend on helper internals beyond directly validating the frozen preview contract.

### 2. Reserve a final-answer turn with a request-level tool window

`build_targeted_worker_prompt` will set `minimum_tool_calls=1` and `tool_call_limit=2`. The production `_wave0_worker_policy` remains unchanged: request-level limits already exist specifically to narrow one invocation beneath the broader policy. With the observed behavior, two tool calls allow a third model turn to return the answer while keeping the existing focused-live ceiling of four model calls and three tool calls.

The alternative of lowering the global Wave0 policy or changing `RuntimeNodeAgentBridge` is rejected because it would affect unrelated Wave0/Wave1 workers. Allowing all three live tool calls is also rejected for this focused worker contract because it can consume the last permitted model interaction without producing a candidate result.

### 3. Repair once as a separate zero-tool agent invocation

The targeted worker will first parse, schema-validate, and bind the initial successful `NodeExecutionResult` to the assigned gap id. Only `ValueError`/Pydantic validation failures from this combined structured-output/identity boundary trigger repair. The node then calls the same resolved capabilities once more with a `NodeExecutionRequest` built by a targeted repair prompt:

- `tools_enabled=False`, with no minimum or tool-call limit;
- the assigned canonical gap id;
- a bounded copy of the initial model draft treated as untrusted data;
- stable validation failure metadata, not a raw exception traceback;
- the exact targeted output keys and closed enum values.

The repair output passes through the same `parse_targeted_worker_output` and gap-identity check as an initial valid response. Non-successful agent results, policy/budget stops, a second invalid response, or a wrong gap id fail the work attempt. There is no recursive repair and no repair-specific parser.

A separate `run_agent` invocation is intentional. Each bridge call builds a fresh bounded child agent and middleware counters, while the parent work attempt, context, deadline, and publication boundary remain the same. Reusing a tool-enabled conversation would permit new research during repair and blur resource accounting.

### 4. Keep publication after final validation

No source cache write, targeted result write, or candidate construction occurs until the selected initial-or-repaired `TargetedWorkerOutput` is fully validated and its gap id matches the assigned `WorkSpec`. Existing `run_fixture_work_unit_component` and `WorkUnitStore` submit validation remain unchanged.

Tests will inject a writer/store that records every mutation and prove zero writes and zero ledger records for initial failure, invalid repair, non-success repair, and wrong-gap repair. This is stronger than checking only the final ledger because partial sandbox files are also unauthorized evidence surfaces.

### 5. Use short scripted workflow tests plus the existing live canary

TDD starts with failing deterministic tests at two responsible seams:

- domain/provider-shape and Wave2 node/store/gate tests for explicit true, omitted false, prompt alignment, canonical persistence, typed preview, `evidence_needed` routing, gate-owned id projection/clearing, and fabricated-state rejection;
- real targeted worker resolver/bridge/store tests for valid-first-response, prose-then-valid repair, invalid repair, wrong identity, zero repair tools, exact model/tool bounds, and no partial authority.

The deterministic repair case uses scripted `NodeExecutionResult` values through the real targeted worker function and resolver/store submission path. It is not a persisted provider trace. The focused targeted seed will stop manually adding `search_required` to a detached dictionary: it will publish a canonical `GapRecord(search_required=true)`, derive the typed Wave2 preview from that validated result, evaluate the real Wave2 gate adapter, and pass only its gate-owned `unresolved_gaps` update into the targeted node. The existing credentialed `live-one-gap-targeted-evidence` case then supplies provider compatibility evidence; no raw model prose is committed. Fixtures mutate no process-global configuration beyond the already-owned sandbox provider in the live harness, which must continue to reset through its public reset API.

### 6. Hand live scheduling back to the owning test-assets change

This production change will not independently redefine live reporting or nightly policy. It will update the focused Wave2 canary's node-owned assertion from unconditional `pass` to the real deterministic relation: a non-empty current searchable-gap preview must route `evidence_needed`, and an empty preview must route `pass`. That focused case still disclaims targeted-loop, predecessor, public-entry, recipe, and full-pipeline coverage. After deterministic and repository gates pass, the change will run the complete six-case selector with fresh identities and write evidence-v1 reports under a fresh gitignored report root. The results are recorded in both changes for provenance, while `rebalance-deep-research-test-assets` remains authoritative for checking tasks 6.7, 6.8, and 7.4 and restoring the schedule.

Because production behavior changes, the existing full-real rerun policy must be assessed after the six focused cases pass. A full-real release run is not automatic: it is required only if focused evidence cannot validate the change below the public pipeline or review identifies material public-entry/release uncertainty.

The adjacent HITL2 finding is recorded for that assessment. Closing it requires a separately reviewed content-access design (for example a bounded brief projection derived from the synthesis artifact or a read capability), because mapping `unresolved_gaps` directly to HITL2 would hide non-searchable gaps and conflate routing control with decision content. It does not block the six focused cases in this change, which stop at Wave2 and targeted worker authority, but it prevents this change from claiming that the complete Wave2-to-HITL2 public pipeline has been newly proven.

### 7. Close the second-run adjacent failures at their existing seams

Wave1 will retain `minimum_tool_calls=1` but set `tool_call_limit=2`. This mirrors the targeted request-local convergence rule and leaves a third model turn for the structured response under the focused live ceiling. Its existing parse-failure repair remains separate and zero-tool; this change does not make budget/policy stops repairable, increase attempts, or change Wave0.

Wave2 semantic validation will require `output.findings` whenever `accepted_refs` is non-empty. Gaps may accompany findings and retain their routing authority, but cannot substitute for synthesis of accepted evidence. A zero-finding initial response enters the existing one-shot zero-tool repair; a zero-finding repair fails before artifact or preview publication. The narrower alternative of teaching the canary to accept gaps-only output is rejected because it would contradict the main requirement that accepted Wave1 evidence produces backed structured findings.

## Risks / Trade-offs

- **[Risk] A defaulted field changes serialized old gaps when they are read and rewritten.** -> Keep synthesis schema version 1, default only missing input to false, and test both old-input acceptance and canonical rewritten output explicitly.
- **[Risk] A reserved gate preview could leak into checkpoint state or be forged by prior state.** -> Pop and type-check the current node result in the wrapper, pass it only to the current gate evaluation, derive `unresolved_gaps` in the gate adapter, and test that prior/fabricated checkpoint values cannot route.
- **[Risk] Adding an exhausted edge changes the frozen topology snapshot.** -> Modify `research-graph-lifecycle` explicitly, add exactly one terminal edge with no node/other-edge drift, and cover the reachable blocked outcome plus topology equality except for that declared edge.
- **[Risk] Repair could launder unsupported prose into accepted evidence.** -> Treat the draft as bounded untrusted data, disable tools, require the same schema and assigned gap identity, and retain normal source/result/ledger validation.
- **[Risk] Two tool calls may be insufficient for a different provider or harder gap.** -> This focused worker intentionally favors bounded convergence. Record any provider-only insufficiency as live evidence; do not silently raise the call window or nightly deadline without review.
- **[Risk] A second bridge invocation has fresh per-run budget counters.** -> Bound repair structurally to one call, tools disabled, under the same outer work attempt/deadline, and assert aggregate observed calls in deterministic and live reports.
- **[Risk] Concurrent active changes could claim the same live/scheduling edits.** -> Limit test-asset edits here to the focused Wave2 route assertion required by changed production semantics; update scheduling and completion checkboxes only in the existing test-assets change after measured evidence.
- **[Risk] Focused late-node success could be overstated as complete synthesis-to-HITL2 correctness.** -> Preserve the focused disclaimers, record the adjacent HITL2 content-projection finding, and make it an explicit input to the final full-real trigger assessment.
- **[Risk] A two-tool Wave1 window may reduce source breadth.** -> Keep the existing minimum one call, bounded seed, source-floor validation, and zero-tool repair; provider insufficiency remains a typed live failure rather than justification to consume the final-answer turn.
- **[Risk] Gaps-only synthesis might be a legitimate insufficient-evidence statement.** -> Require at least one backed finding from the already accepted evidence and allow searchable gaps alongside it; do not fabricate a finding or suppress the gap.

## Migration Plan

1. Record the new change's apply base and protected upstream/public-entry hashes; preserve the current dirty worktree belonging to the active test-assets change.
2. Add failing tests for canonical gap routing and targeted repair/non-publication before production edits.
3. Implement the defaulted gap field, prompt/preview alignment, real gate rule, gate-owned id projection, targeted id consumption, and exact Wave2 exhausted terminal edge, then pass focused Wave2/domain/gate/topology tests.
4. Implement the targeted request window and one zero-tool repair path, then pass focused targeted worker/store tests.
5. Run Ruff, strict OpenSpec, requirement/architecture/asset governance, and the deterministic fast/integration/workflow/full suites.
6. Run all six focused live cases with fresh identities. If the first post-remediation lane exposes an adjacent request/semantic-floor defect, add its focused red tests, apply only the reviewed request-local and semantic-floor corrections, and rerun deterministic gates.
7. Run one new complete six-case lane. If green within the existing deadline margin, update the owning test-assets tasks and restore nightly scheduling there.
8. Assess the reviewed full-real rerun trigger. Do not run or modify the sole release E2E unless the trigger is met.

Rollback reverts the production and focused-test commits together. Old schema-version-1 synthesis artifacts remain readable because missing gap flags default to false; no database, checkpoint, sandbox-layout, configuration, dependency, next-agent-build, or restart migration is introduced.

## Open Questions

None. The observed responses, existing request-level tool limit, canonical authority split, and reviewed live/release policy are sufficient to implement and verify this bounded change.
