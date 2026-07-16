## Why

Wave0 now produces accepted `SubmissionRecord`s with source refs, and Wave1 (upcoming) will extract claims from those sources. But no independent semantic quality layer exists to assess source trustworthiness or verify claims against evidence — the author of evidence is currently its own critic. Without a separate critic authority, the research pipeline cannot distinguish well-supported claims from marketing material, hallucinated refs, or prompt-injected sources. This change establishes that layer now so Wave1, Wave2, and readiness can consume it.

## What Changes

- Add two new critic agent types as node-local modules under `graph/nodes/targeted_evidence/`: **SourceDiagnostic** (assesses source trust tier, materiality, marketing risk, cross-verification need) and **ClaimVerifier** (verifies claims as supported/weakened/contradicted/uncertain with support/counter refs and reasoning). Both follow the existing wave0 pattern (`prompts.py`, `materializer.py`, `subgraph.py`). A new domain module `domain/untrusted.py` provides the untrusted-data block contract importable from any layer.
- Both critics run as bounded DeerFlow agent loops with a read-only `ExecutionPolicy` (`allowed_tool_names` empty, `write_roots` empty, `read_roots` scoped to the research bundle root). They cannot write ledger, phase, gate, or another node's artifacts.
- Critic output uses versioned structured schemas with deterministic materializers that write review artifacts to the sandbox under `critic/<node_attempt_id>/<type>.json`, where `<type>` is `source-diagnostic` or `claim-verifier`.
- The gate will consume critic verdicts in later changes (12, 15); this change produces the verdict artifacts and exposes the typed contracts. No gate modification is included.
- Author and critic share no model, prompt, or session; tests must not reuse author self-assessment as critic output.
- The existing `targeted_evidence` node package is extended with a real factory that reads work items from state and dispatches to the appropriate critic via `agents/critic_dispatcher.py`; no new top-level graph node is added. The topology is unchanged.

## Capabilities

### New Capabilities
- `evidence-critic-nodes`: SourceDiagnostic and ClaimVerifier agent nodes with versioned structured output, read-only evidence access, and gate-consumable verdict contracts. Requirement IDs: EVC-001 through EVC-005.

### Modified Capabilities
None. Existing specs are unchanged. The critics are new agent types within the existing `agents/` package and are invoked from the existing `targeted_evidence` node.

## Impact

- **Source**: new modules `domain/critics.py` (result contracts), `domain/untrusted.py` (untrusted-data block), `graph/nodes/targeted_evidence/prompts.py`, `graph/nodes/targeted_evidence/materializer.py`, `graph/nodes/targeted_evidence/subgraph.py` (critic runners + dispatcher); replace `graph/nodes/targeted_evidence/node.py` real factory. New files registered via PRS-004 sync.
- **Typed state/checkpoint data**: critic verdict refs live in sandbox artifacts only; whether to add a `critic_verdicts` checkpoint field is deferred to a later change (12 or 15). `RESEARCH_STATE_SCHEMA_VERSION` is not bumped.
- **Graph nodes/components**: the existing `targeted_evidence` node real factory is replaced (currently `UNAVAILABLE_REAL_FACTORY`); no new top-level logical node, no topology change.
- **Node-agent roles**: each critic runs one bounded agent through `capabilities.run_agent()` under a read-only `ExecutionPolicy` (`allowed_tool_names=frozenset()`, `write_roots=()`, `read_roots` covering the research bundle root). No web search/fetch tools.
- **Sandbox artifacts**: each critic writes its result to `critic/<node_attempt_id>/<type>.json` under the research sandbox, where `<type>` is `source-diagnostic` or `claim-verifier`. The `node_attempt_id` is the graph-level attempt id (`make_attempt_id(state, logical_name)`) for per-invocation isolation.
- **DeerFlow extension surfaces**: none added. No new config.yaml keys, extensions_config.json keys, skills, Agent/SOUL, MCP, ACP, or lead-agent middleware.
- **Dependencies**: no new third-party runtime dependency. Tests use `ReplayChatModel`; real-LLM coverage is `@requires_llm`-marked.
- **Non-goals**: no real Wave1 extraction or targeted web search; no final phase transition decision; no gate modification. No files under `backend/` or `frontend/` are modified.
