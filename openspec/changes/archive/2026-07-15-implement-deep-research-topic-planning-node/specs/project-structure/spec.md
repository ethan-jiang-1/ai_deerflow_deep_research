> req: PRS-001, PRS-003, PRS-004

## MODIFIED Requirements

### Requirement: Canonical downstream package ownership

The project SHALL place all Deep Research Python source under
`agent/src/deerflow_deep_research/`, all owned tests under `agent/tests/`, and all
owned runtime templates and launch tooling under `agent/`. The documented ownership
layers SHALL be `runtime`, `domain`, `engine`, `agents`, and `graph`; no Deep Research
source SHALL be added under `backend/` or `frontend/`.

Real HITL1 SHALL add only canonical downstream production paths owned by that change:
`agent/src/deerflow_deep_research/domain/profile.py`,
`agent/src/deerflow_deep_research/graph/nodes/hitl1/prompts.py`, and
`agent/src/deerflow_deep_research/runtime/request_bundle.py`. These paths SHALL be registered in
`openspec/governance/project-structure.toml` and reflected in the generated
`agent/AGENTS.md` block.

Real topic planning SHALL add only canonical downstream production paths owned by this
change: `agent/src/deerflow_deep_research/domain/topics.py` (the frozen topic contracts)
and `agent/src/deerflow_deep_research/graph/nodes/topic_planning/prompts.py` (the
planner prompt template). These paths SHALL be registered in
`openspec/governance/project-structure.toml` and reflected in the generated
`agent/AGENTS.md` block. topic_planning is not a HITL node, so no import-policy
exception is added: its modules import only `domain`/`engine`.

#### Scenario: Canonical HITL1 paths pass
- **WHEN** the folder contract inspects this change after implementation
- **THEN** the new profile, HITL1 prompt, and `runtime/request_bundle.py` paths appear under the canonical downstream package and no Deep Research source appears under `backend/` or `frontend/`

#### Scenario: Canonical topic planning paths pass
- **WHEN** the folder contract inspects this change after implementation
- **THEN** the new `domain/topics.py` and `topic_planning/prompts.py` paths appear under the canonical downstream package, topic_planning imports only `domain`/`engine`, and no Deep Research source appears under `backend/` or `frontend/`

#### Scenario: Canonical scaffold passes
- **WHEN** the folder contract inspects a fresh change 00 checkout
- **THEN** it finds the required owned roots, package metadata, module guide, and mirrored test roots at their canonical paths

#### Scenario: Second source tree is rejected
- **WHEN** a fixture places Deep Research implementation source at repository root or under an upstream tree
- **THEN** the folder contract fails and identifies the non-canonical owner
