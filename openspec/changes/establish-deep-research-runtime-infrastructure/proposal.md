## Why

The Deep Research roadmap needs a single, enforceable foundation before the fake graph or any real phase node is added. Without a frozen downstream package layout, DeerFlow loading contract, trusted runtime boundary, checkpoint lifecycle, and bounded node-agent adapter, later changes can silently create competing source trees, state authorities, and security paths.

## What Changes

- Add a standalone, locked Python 3.12+ project at `agent/` with source at `agent/src/deerflow_deep_research/`, canonical `runtime`, `domain`, `engine`, `agents`, and `graph` ownership layers, mirrored tests, stable node-package shape, and mechanical import/folder contracts.
- Add a durable architecture-governance chain for that structure: the active `project-structure` spec owns the semantic contract, `openspec/governance/project-structure.toml` owns its exact machine-readable path/layer/node-shape enumeration, `openspec/governance/architecture-policy.md` defines authority and change protocol, and a zero-dependency checker keeps the manifest, the controlled structural block in `agent/AGENTS.md`, and the repository aligned after this change is archived.
- Expose the global `deep_research` control tool through `config.yaml -> tool_groups` and `config.yaml -> tools[].use: deerflow_deep_research.tool:deep_research_tool`; its only business-free action in this change is `infra_probe`.
- Add project-owned local/production launch assembly and a Docker Compose override that make `agent/src` importable without modifying upstream source or mounting project source into the research sandbox. Local launch quiesces the old Gateway before exact sync/editable installation, validates a secret-free startup candidate before start, and injects it so live edits to startup-only provider/sandbox config fail with `restart_required` instead of splitting outer and nested runtimes.
- Add YAML-style-preserving and JSON-structural, idempotent configuration with guarded rollback for the public `deep-research-controller` skill through `extensions_config.json -> skills`; provision the dedicated Agent to `default` only in explicit no-auth setup, while authenticated users use current-user `POST /api/agents`. The Agent is a UX route to the global tool, not an authorization boundary.
- Add `RuntimeAdapter` that stops at a runtime-only `TrustedRuntimeEnvelope`, plus a separate runtime projection that requires a registered research handler's validated opaque scope before deriving pure graph/node-agent contexts. The adapter requires server-injected identity rather than DeerFlow's permissive `default` fallback, initializes the existing parent sandbox through DeerFlow's public async lazy initializer when needed, validates thread paths against trusted user/thread scope, and preserves outer asyncio cancellation without assuming a private runtime signal. `infra_probe` does not create a research projection or workspace.
- Add a `GraphHost` shell that caches graph topology/builders, derives isolated checkpoint namespaces, serializes same-namespace actions in the supported single-worker runtime, and opens the official async checkpointer context per tool action for `infra_probe` checkpoint write/read and provider-reopen verification. One effective-provider resolver pins legacy `checkpointer`-over-`database` precedence for both GraphHost and doctor. The public research `start | resume | status | cancel` protocol remains owned by change 01.
- Add a runtime-owned node-agent bridge and bounded full-takeover wrapper around `create_deerflow_agent()` for future phase nodes. Nodes see only a pure capability protocol; the bridge alone seeds ephemeral parent sandbox/thread state and raw child runtime context. The embedded agent has no independent checkpointer, explicit model/turn/token/tool-call/tool-result/wall-time budgets, structured results, cancellation/progress projection, and code-enforced tool/path/prompt-injection policies.
- Correct the project OpenSpec architecture context so later changes use Python `StateGraph` control with bounded agent loops inside nodes, rather than the superseded Phase-Agent/Markdown controller and sandbox-bundle state assumption.
- Register the new requirement IDs `PRS-001` through `PRS-004`, `DEC-001` through `DEC-005`, `RUI-001` through `RUI-005`, and `NOA-001` through `NOA-006`.

The DeerFlow extension surfaces used are `config.yaml -> tool_groups`, `config.yaml -> tools`, `extensions_config.json -> skills`, the committed public skill, per-user Agent `config.yaml`/`SOUL.md`, and the downstream package reflection path. The change reads but does not change `config.yaml -> agents_api.enabled`, `database`, `checkpointer`, or `sandbox`, and it marks every worker input not normalizing to integer one as runtime-not-ready. No phase skill, gate tool, DeerFlow subagent role, MCP server, ACP agent, or research bundle file is introduced; the smoke graph uses only its isolated infrastructure-probe checkpoint namespace.

Configuration changes to tool groups, tools, skill enablement, and no-auth/current-user Agent files take effect on the next agent build. Changes to package source loading/PYTHONPATH, launcher assembly, Docker mounts, or existing startup-only database/checkpointer/sandbox selection require a Gateway restart; fingerprint drift fails before nested resource access. This change reads but does not rewrite those selections.

This change does not require the non-additive lead-agent middleware seam. Policy middleware is supplied only to the nested phase-agent instance created by our downstream package; the DeerFlow lead-agent middleware chain and upstream harness remain unchanged.

## Capabilities

### New Capabilities

- `project-structure`: Defines and enforces the canonical downstream package, import direction, node package, test mirror, shared-code ownership, and archive-durable architecture-governance contracts (`PRS-001`..`PRS-004`).
- `deployment-configuration`: Defines source loading, idempotent config/skill/Agent materialization, user scoping, diagnostics, and reload boundaries (`DEC-001`..`DEC-005`).
- `runtime-integration`: Defines the reflected control tool, trusted runtime adapter, isolated checkpoint namespace, GraphHost lifecycle, and persistence probe (`RUI-001`..`RUI-005`).
- `node-agent-runtime`: Defines the bounded DeerFlow agent adapter and its context, budget, tool/path, prompt-injection, output, cancellation, and clarification policies (`NOA-001`..`NOA-006`).

### Modified Capabilities

None. This is the first capability-bearing OpenSpec change in the project.

## Non-Goals

- No complete research topology, `ResearchState`, gate kernel, work-unit ledger, HITL phase, rerun path, or real research node is implemented.
- No real LLM, web search, research evidence, bundle file, or final artifact publication is used.
- No files under `backend/` or `frontend/` are modified, and neither upstream tree imports the downstream package.
- No dedicated Agent, skill, tool group, prompt, or model-facing restriction is treated as a security boundary; runtime and node policies remain authoritative.

## Impact

The change adds the top-level `agent/` package, its tests/configuration/launch tooling, a materialized public skill under `skills/public/deep-research-controller/`, no-auth or current-user Agent provisioning, OpenSpec requirement records, the permanent structure manifest/policy/checker under `openspec/governance/`, and architecture documentation updates. Runtime configuration gains one tool group, one reflected tool, and one enabled public skill. Existing DeerFlow database, checkpointer, sandbox, and lead graph APIs are consumed without upstream changes; frontend, MCP, ACP, and DeerFlow task-subagent behavior remain unchanged and unused by change 00.
