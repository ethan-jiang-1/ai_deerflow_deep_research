---
name: deep-research-controller
description: Route multi-source deep research requests through the DeerFlow Deep Research control tool.
---

# Deep Research Controller

For a user request that requires multi-source deep research, call `deep_research` and treat its structured result as the authority for what is currently available.

When the tool returns `action_unavailable`, report that the requested capability is unavailable in the current runtime. Do not emulate a parallel research workflow in the lead or dedicated Agent.

Never invent workflow progress, user-review decisions, or tool-access guarantees. This skill and its recommended Agent are routing surfaces, not authorization boundaries.
