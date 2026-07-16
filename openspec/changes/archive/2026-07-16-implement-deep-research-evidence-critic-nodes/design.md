## Context

Change 08 completed real Wave0 source intake, producing accepted `SubmissionRecord`s
with validated `SourceRef`s. Wave1 (change 10) will later extract claims from those
sources. But right now there is no independent semantic quality layer — the author of
evidence is its own critic. This change inserts two critic agent types before Wave1
consumes them, establishing a separate critic authority.

The existing `targeted_evidence` node package (`graph/nodes/targeted_evidence/`)
already has the topology position between `wave2_synthesis` and `wave2_synthesis`
(loopback). Its real factory is still the `UNAVAILABLE_REAL_FACTORY` sentinel.
Critics are invoked from this node: the caller (wave2_synthesis) passes evidence refs
from checkpoint state as work items, and the node dispatches the appropriate critic
type.

The node-agent bridge (`runtime/node_agent_bridge.py`) supports per-node
`ExecutionPolicy` with fine-grained read/write roots. The deny-by-default
`ToolPolicyMiddleware` already blocks unauthorized tool calls. These mechanisms
are reused for critic read-only enforcement.

The `agents/` package uses flat modules (`agents/prompts.py`, `agents/policies.py`,
etc.), not subdirectories. New critic code follows this convention as
`agents/critic_prompts.py`, `agents/critic_materializer.py`,
`agents/critic_factory.py`, and `agents/critic_dispatcher.py`.

## Goals / Non-Goals

**Goals:**
- Define two critic agent types with versioned structured output: `SourceDiagnostic`
  (trust tier, materiality, marketing risk, cross-verification need) and
  `ClaimVerifier` (supported/weakened/contradicted/uncertain, support refs, counter
  refs, reason).
- Run each critic as a bounded DeerFlow agent loop through the runtime node-agent
  bridge under a read-only `ExecutionPolicy` (`allowed_tool_names=frozenset()`,
  `write_roots=()`, `read_roots` covering the research bundle root).
- Implement deterministic materializers that write critic review artifacts to the
  sandbox under `critic/<node_attempt_id>/<type>.json`, where `<type>` is
  `source-diagnostic` or `claim-verifier` and `node_attempt_id` is the graph-level
  attempt id.
- Expose critic verdicts through typed Pydantic contracts that the gate and
  downstream nodes (changes 10, 12, 15) can consume without coupling to the agent
  implementation.
- Keep the existing `targeted_evidence` topology unchanged; the node remains the
  single loopback from `wave2_synthesis`.
- Tests use fixture evidence and `ReplayChatModel`; no live web access.

**Non-Goals:**
- No real Wave1 extraction or targeted web search (changes 10/12).
- No final phase transition decision — critics provide input to gate, not authority.
  Gate consumption of critic verdicts is deferred to changes 12 and 15.
- No modification to `backend/` or `frontend/`.
- No new top-level graph node or topology edge.
- Critics do not auto-satisfy any gate requirement; they are advisory.

## Decisions

### Decision 1: Two critic types under one node package

Rather than adding two new top-level graph nodes, both critic types live under the
existing `targeted_evidence` node as callable subroutines. The node receives typed
work items from checkpoint state (e.g., `{"type": "source_diagnostic", "source_refs": [...]}`
or `{"type": "claim_verifier", "claims": [...], "evidence_refs": [...]}`) and
dispatches each to the appropriate critic type via `agents/critic_dispatcher.py`.

Why: the topology already has `targeted_evidence` positioned as a loopback from
`wave2_synthesis`. Adding new top-level nodes would require topology changes and
new gate definitions. The critics are single-invocation agents — each call is
independent; they hold no conversational state across invocations.

### Decision 2: Critics use structured output, not free-text

Each critic produces a versioned Pydantic model (`SourceDiagnosticResult`,
`ClaimVerifierResult`) validated at the agent boundary. A deterministic materializer
writes the canonical JSON to the sandbox.

Why: downstream consumers (Wave1, Wave2, readiness gate) need machine-readable
verdicts. Free-text would require parsing and introduces ambiguity. Structured
output with `schema_version` enables future evolution without breaking consumers.

### Decision 3: Read-only policy, no tool escalation

The critic `ExecutionPolicy` sets `allowed_tool_names = frozenset()` (no tools) and
`write_roots = ()` (no writes). `read_roots` is set to the research bundle root so
the critic can read accepted evidence artifacts. The `ExecutionPolicy` requires
non-empty `read_roots` (enforced by `__post_init__`), so the bundle root is the
minimal viable scope.

Why: critics must not fetch new sources, write phase/ledger/gate state, or mutate
another node's artifacts. The deny-by-default `ToolPolicyMiddleware` blocks any
attempted tool call — the agent receives a tool-rejection response from the
middleware, not a "structured error" from the critic itself.

### Decision 4: Critics are advisory, not authority

The gate will consume critic verdicts in later changes (12, 15) according to
configurable policy and threshold. Conflicting critic results form a gap recorded
as such; the gate does not auto-resolve via majority vote. This change only
produces the verdict artifacts and typed contracts.

Why: DPT's critic model treats disagreement as signal, not noise. Making critics
hard authority would let a misconfigured prompt override evidence. The gate remains
the sole transition authority.

### Decision 5: Versioned schema with schema_version field

Both result types carry `schema_version: 1` and reject unknown fields. Future
changes can add fields by bumping the version.

Why: same pattern as `Wave0SourceIntakeResult` (change 08). Consumers branch on
`schema_version`.

### Decision 6: Deterministic test fixtures, not real LLM

All tests use `ReplayChatModel` with canned critic outputs covering the verdict
taxonomy (supported, weakened, contradicted, uncertain) plus edge cases (empty
evidence, prompt-injected source, conflicting refs).

Why: live LLM is non-deterministic and expensive. The critic's contract is the
structured output schema, not the model's reasoning. Real-LLM coverage is
`@requires_llm`-marked.

### Decision 7: Flat module structure under agents/

Critic code lives as flat modules (`agents/critic_prompts.py`,
`agents/critic_materializer.py`, `agents/critic_factory.py`,
`agents/critic_dispatcher.py`), consistent with the existing `agents/` package
convention (`agents/prompts.py`, `agents/policies.py`, `agents/factory.py`, etc.).

Why: the existing package uses flat modules grouped by concern, not subdirectories
per agent type. Adding a `critics/` subdirectory would break the convention and
require an `__init__.py` with re-exports. The `critic_` prefix distinguishes critic
modules from existing agent infrastructure modules.

### Decision 8: Sandbox paths use node attempt id, not work-unit semantics

Critic artifacts are written to `critic/<node_attempt_id>/<type>.json` under the
research sandbox. The `node_attempt_id` comes from the graph-level attempt
(`make_attempt_id(state, logical_name)`), not from the work-unit controller.

Why: targeted_evidence does not declare `WORK_UNIT_CONTROLLER` capability — it is
not a work-unit node. Using the graph-level attempt id provides per-invocation
isolation without coupling to the work-unit infrastructure.

## Risks / Trade-offs

- **Critic hallucinates refs**: structured output validation rejects refs not in the
  assigned evidence set → candidate fails validation, no artifact written.
- **Critic misses subtle quality issues**: the structured output captures explicit
  dimensions (trust tier, materiality, etc.) but cannot catch everything. The gate
  treats critics as advisory, so a missed issue does not block the pipeline.
- **Model quality variance**: different models may produce different verdicts. This
  is a feature (independent perspectives), not a bug. Tests cover the contract, not
  model-specific behavior.
- **No tool access means no web verification**: critics cannot independently verify
  claims against live sources. That capability belongs to targeted-evidence retrieval
  (change 12), not the critic layer.
- **`read_roots` is bundle-wide**: the critic can technically read any artifact in
  the research bundle, not just its assigned evidence. This is acceptable because
  the critic has no write access and no tools; it can only return structured output.
  A future change may tighten this with evidence-specific read roots.

## Open Questions

- Whether to add a `critic_verdicts` checkpoint field or derive verdict refs from the
  sandbox artifact paths. Deferred to change 12 or 15; this change writes only
  sandbox artifacts.
- The exact threshold/policy for gate consumption of critic verdicts. Deferred to
  change 12 (targeted evidence loop) and change 15 (readiness).
