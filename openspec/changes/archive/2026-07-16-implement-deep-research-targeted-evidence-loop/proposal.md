## Why

Wave2 synthesis (change 11) produces structured findings with `search_required` gaps. But no node can act on those gaps — performing targeted web search to fill specific evidence needs. The targeted evidence loop closes this loop: it converts synthesis gaps to bounded search tasks, executes focused web workers, runs critics on results, and feeds back into synthesis for convergence.

## What Changes

- Add deterministic gap router that reads synthesis gaps and materializes targeted WorkSpecs for `search_required` gaps only.
- Add targeted worker agent performing focused web search with gap-scoped policy.
- Post-submit critic invocation on targeted evidence.
- Convergence gate: round budget, gap closure, fatigue detection.
- Extend targeted_evidence node with work-unit controller capability.

## Capabilities

### New
- `targeted-evidence-loop`: Bounded gap-to-evidence loop with convergence gate. TEL-001 through TEL-004.

## Impact

- **Source**: extend `graph/nodes/targeted_evidence/` with gap router + targeted worker. Register TEL in validation.
- Non-goals: no user HITL2, no global report. No backend/frontend changes.
