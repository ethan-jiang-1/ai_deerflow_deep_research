## Why

The Deep Research graph is complete from bootstrap to final delivery (changes 00–16). Two runtime gaps remain: non-interactive mode currently hard-denies start/resume, and graph phase transitions are not surfaced as progress events. These are blockers for scheduled/automated runs and operator visibility.

## What Changes

- **Non-interactive policy**: Modify `tool.py` to permit non-interactive start/resume when a `non_interactive_policy` dict is provided with `auto_profile` and `auto_proceed` keys. The policy is stored in checkpoint state. HITL1 reads `auto_profile` to generate a default profile instead of calling `interrupt()`. HITL2 reads `auto_proceed` to auto-proceed with limitations. Without a policy, non-interactive is denied as before. All automated decisions are recorded in audit state.
- **Orphan attempt detection**: On crash recovery, detect work attempts left in `running` state from a prior graph incarnation and transition them to `failed` with orphan reason.

## Capabilities

### New Capabilities

- `runtime-operations`: Non-interactive policy with auto-profile/auto-proceed, and orphan attempt detection on recovery. Requirement IDs: RUO-001 through RUO-004.

### Modified Capabilities

None. Graph topology and node implementations are unchanged.

## Impact

- **Source**: modify `tool.py` (non-interactive gating), `graph/nodes/hitl1/node.py` (auto-profile), `graph/nodes/hitl2/node.py` (auto-proceed), `domain/state.py` (non_interactive_policy field), `graph/builder.py` (progress events in wrapper).
- **Typed state**: new `non_interactive_policy` field (dict, default None). `RESEARCH_STATE_SCHEMA_VERSION` not bumped.
- **Graph**: no topology changes.
- **Node-agent roles**: none added.
- **Non-goals**: no Postgres multi-worker support (deferred). No `backend`/`frontend` changes.
