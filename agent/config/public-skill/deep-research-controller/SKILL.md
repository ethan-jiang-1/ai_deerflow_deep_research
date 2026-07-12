---
name: deep-research-controller
description: Route multi-source research requests through DeerFlow's development full-fake lifecycle skeleton.
---

# Deep Research Controller

This is a development control-flow skeleton, not a research engine. Every lifecycle result must visibly retain `implementation_mode=full_fake`. Never present its terminal fixture marker as findings, evidence, a report, or completed research.

For a qualifying new request, call `deep_research` with `action="start"` as the sole tool call in that assistant turn. Do not copy the user's question or choose an id in tool arguments. Preserve the returned opaque `research_id` and, when suspended, let the Web UI or a compatible generic client collect the requested human response.

After the matching user response arrives, call `deep_research` with `action="resume"` and the preserved `research_id` as the sole tool call in that turn. The response belongs in the latest user message, never in tool arguments. Use `status` for an accurate read and `cancel` for a durable stop, each with that id.

Known IM transports and non-interactive contexts refuse start/resume; report that limitation directly. Status and cancel remain available. Report any denial or unavailable code exactly, and never invent progress, output, access, or authorization guarantees.
