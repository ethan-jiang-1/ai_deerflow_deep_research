## Context
Change 11 produces synthesis gaps. Change 09 provides critic dispatch. The loop: synthesis → targeted evidence → synthesis.

## Decisions
1. Gap router is deterministic: only search_required gaps become WorkSpecs.
2. Targeted worker uses web tools with gap-scoped policy.
3. Convergence gate enforces round budget and fatigue detection.
4. Node declares WORK_UNIT_CONTROLLER for fan-out.
