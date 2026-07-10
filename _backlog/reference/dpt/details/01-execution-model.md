# Analysis: DPT Framework Agentic Execution Architecture

*Source material: `guidelines/agentic-execution-model.md`, `guidelines/agentic-workflow-mechanism.md`, `DPT_FRAMEWORK/workflows/manifest.json`, `DPT_FRAMEWORK/workflows/transitions.chain.json`*

---

## 1. Overview

The DPT Framework implements a deep-research agent as a **Markdown-controlled, Engine-validated state machine**. No JS "while(true)" loop drives the workflow — a **Phase Agent** operating in "MD controller mode" reads Markdown instructions, executes them, calls a gate CLI, and asks a static routing table for the next step. This produces a system where:

- **Judgment** (research decisions, repair strategy, synthesis) lives in the Agent.
- **Procedure** (goals, allowed actions, gate commands, pass/fail handling) lives in Markdown.
- **Determinism** (schema validation, routing lookup, audit trail) lives in a stateless JS Engine.
- **Truth** (current state) lives in JSON/JSONL files inside the active runtime bundle.

Two axes of structure compose this system:

1. **Granularity axis** (from `agentic-execution-model.md`): Chain → Queue → Work Unit — three nested tiers of execution scope.
2. **Authority axis** (from `agentic-workflow-mechanism.md`): MD phase node / `transitions.chain.json` / JS Engine — three components that divide *who decides what*, orthogonal to granularity.

---

## 2. The Three-Tier Execution Model (Chain, Queue, Work Unit)

The execution model is nested by granularity, not by time — each tier is a scope within which a different kind of decision is made.

```text
Tier 1: Chain
  phase gate passes -> transition lookup -> next phase Markdown

Tier 2: Queue
  phase-local demand -> claim/complete non-delegated work
  phase-local delegated demand -> claim work units

Delegated attempt layer: Work Unit
  Engine allocates work_id -> Sub-agent executes bounded task
  -> submit validates result/receipt/output/cache
  -> Engine appends submitted ledger row
```

### 2.1 Tier 1 — Chain (phase-to-phase)

The outermost tier. Once a phase's gate passes, the Engine looks up `{currentNodeRef, outcome}` in `transitions.chain.json` and returns the next phase's Markdown file reference (`fileRef`). This is the **only** phase-to-phase routing mechanism. Concurrency model: **single step** — one phase transition at a time, no parallel phase execution.

### 2.2 Tier 2 — Queue (phase-local demand)

Within a single phase, `rb_queue.json` (bundle-root relative, e.g., inside the active `dpt_rb_*` bundle) tracks **demand items** — units of phase-local work identified by `queue_item_id`. The Queue layer, mediated by `operate-queue` / a queue Engine/CLI, tracks:
- What work is needed
- Where each demand item "lives" (its location/state)
- Completion of **non-delegated** work directly
- **In-flight bindings** for demand that has been delegated to a work unit

Concurrency model: an **ordered demand window** plus in-flight delegated bindings — multiple demand items can be tracked simultaneously, but delegated completion is mediated through Work Unit, not through the queue directly.

Critically: **the Queue layer does not accept delegated results as coverage**. A demand item that was delegated cannot be marked "done" by queue mechanics alone — it must be proven via the Work Unit submit boundary.

### 2.3 Delegated Attempt Layer — Work Unit

This is the tier where actual bounded task execution happens via Sub-agents. The production path is a single, fixed pipeline:

```text
queue demand item -> work unit -> sub-agent -> submit -> ledger -> gate
```

Mechanics:
1. Phase Agent runs `operate-work-unit claim <bundle> --phase waveN [--count N]`.
2. The **Engine** (never the Agent, never the Sub-agent) allocates a unique `work_id`, moves the demand into `delegated_in_flight`, and materializes a **work-unit envelope** at bundle-root `_work_units/waveN/{work_id}/` — containing manifest, `task.md`, result schema, `_beacon.json`, and receipt surfaces.
3. Phase Agent spawns a bounded native Sub-agent with the `task.md` prompt.
4. The Sub-agent reads `task.md`, `_beacon.json`, `result.schema.json`; writes declared outputs/cache and lifecycle receipt events carrying `work_id`, `queue_item_id`, `kind`, `receipt_nonce`.
5. Phase Agent runs `operate-work-unit submit <bundle> --work-id <id> --result <result.json>` — **this is the only successful delegated completion transaction**.
6. The Engine validates result, receipt, output files, cache trails, queue binding, hashes, and an idempotency fingerprint, then:
   - Completes the bound queue demand
   - Updates work-unit state
   - Appends a row to `rb_output_declarations.jsonl` (the **submitted ledger row** — the sole gate-readable coverage authority for delegated work)

Concurrency model: **batched delegated fan-out** via `claim --count N`; each attempt gets a distinct `work_id`.

**Hard boundary:** Sub-agents do not allocate IDs, mutate queue state, append ledgers, or pass gates. They only execute the bounded task and write outputs/receipts. All state-mutating actions are Engine-only.

### 2.4 Layer Boundary Table (from `agentic-execution-model.md` §3.1)

| Layer | Authority | Does | Does not do |
|---|---|---|---|
| Chain | Gate verdict + transition table | Selects next phase after a pass | Does not inspect queue or allocate work |
| Queue | `rb_queue.json` via queue Engine/CLI | Tracks phase-local demand, locations, non-delegated completion, delegated in-flight bindings | Does not accept delegated results as coverage |
| Work Unit | `_work_units/_index.json` + `operate-work-unit` transactions | Allocates delegated attempts, validates submit, writes result/status, appends submitted ledger row | Does not choose phase transitions or replace gate judgment |
| Gate | Gate definition JSON + gate CLI output | Aggregates structural/provenance checks for phase completion | Does not infer delegated coverage from filesystem presence alone |

### 2.5 A Concrete Walkthrough (Wave1 example)

1. Phase Agent reads `phase-wave1.md`.
2. Queue state has a `wave1_topic_deepening` demand with a `queue_item_id`.
3. Phase Agent runs `operate-work-unit claim <bundle> --phase wave1`.
4. Engine allocates `work_id`, writes `_work_units/wave1/{work_id}/`, returns prompt refs.
5. Phase Agent spawns `dpt-evidence-extractor` Sub-agent with the work-unit task.
6. Sub-agent writes outputs/cache + receipt events with `work_id`, `queue_item_id`, `kind`, `receipt_nonce`.
7. Phase Agent runs `operate-work-unit submit ... --work-id <id> --result <result.json>`.
8. Engine validates everything and appends the submitted ledger row.
9. Phase Agent keeps claiming until phase drain, then runs the wave gate.
10. Gate checks submitted ledger coverage + cross-checks → **only then** does Chain select the next phase.

---

## 3. The Agentic Loop (Tier 1, in detail)

`agentic-workflow-mechanism.md` describes the **outer loop mechanics** that Tier 1 (Chain) implements. This is explicitly *not* a JS `while(true)` loop — it is a **dynamic-loading closed loop driven by the Phase Agent**:

> Phase Agent 读 phase MD → 执行 → gate 验证 → chain 查路由 → 通过 accepted handoff loader/check 消费 `check.next` → 读取下一 phase MD → 重复

Step by step:

```text
1. Phase Agent loads the current phase node MD (assessNode)
        │
        ▼
2. MD body tells the Phase Agent: goal, actions, gate command
        │
        ▼
3. Phase Agent executes the action(s) → runs the gate CLI
        │
        ▼
4. Gate internally queries transitions.chain.json
   → check.next = fileRef of the next node
        │
        ▼
5. Phase Agent reads check.next → via accepted handoff loader/check
   renders/loads the next phase node MD
        │
        └──────────────── loop ─────────────────→ back to 1
```

Key properties:

- **The driving force is the Phase Agent operating in MD controller mode**, not JS code. There is no `while(true) { advance() }`, no lifecycle walker, no cursor pointer.
- The Phase Agent "holds" the current node, finishes the gate check, then asks the chain "who's next," receives a `fileRef`, and loads that Markdown via the accepted loader/check into context.
- Boundary terms to distinguish: `advance-status` / `phase_transition` only sync **runtime status**; `enter-phase` / route-bound `load_complete` only prove the Phase Agent **entered** the target Markdown control surface — they do **not** prove that target phase's work is complete. Actual completion of the target phase must still be proven by that phase's own artifacts and gate/content rules.

### Dynamic Loading

Nodes load **on demand**, never preloaded:

- The Phase Agent only loads the next node after receiving `check.next`, through the accepted loader/check.
- Engine-side caching (avoiding redundant disk reads) is just a cache, not a preloading mechanism.
- **`manifest.json` is not the authority for execution order — `transitions.chain.json` is.** The manifest is inventory (a flat list of all phase nodes + their gates); the chain defines the actual transitions between them.
- Concretely: the 11 nodes listed in `transitions.chain.json` (instantiation → hitl1 → setup → seed-topics → wave0 → wave1 → wave2 → hitl2 → readiness → rerun → final) are not loaded until the Phase Agent actually reaches them. "chain 只是地图，不是行程单" — the chain is a map, not an itinerary.

This on-demand loading is called out as a **structural requirement**, not a performance optimization: if nodes were preloaded, (a) the Phase Agent could execute a phase the gate never authorized (bypassing the gate checkpoint), and (b) the Phase Agent's context would accumulate content from unreached phases, defeating the context-isolation benefit of single-phase-at-a-time execution.

---

## 4. Three-Authority Architecture

This is an **orthogonal axis** to the granularity tiers — it answers *who decides*, not *at what scope*. Three components divide authority with hard "MUST NOT" boundaries:

| Authority Component | What it is | What it does | MUST NOT |
|---|---|---|---|
| **MD phase node** | Controller surface | Tells the Phase Agent: this step's goal, inputs, allowed actions, gate command, pass/fail handling, stop behavior, anti-cheating rules | Does not make deterministic rulings; does not query the routing table; does not write trace records |
| **`transitions.chain.json`** | Passive routing table | `{currentNodeRef, outcome} → nextNodeRef`, a pure static mapping | Does not encode branch logic (fail/repair belongs to the Agent); does not hold state; does not drive the loop |
| **JS Engine** (gate CLI, loader/check, trace) | Validator + lookup | Schema validation, gate rule evaluation, chain lookup, trace/loader receipt writes | Does not drive the loop; does not autonomously choose or execute the next node; does not make semantic judgments; does not choose repair strategy |

### 4.1 MD Phase Node — Controller

Each `DPT_FRAMEWORK/workflows/nodes/phases/phase-*.md` is an independent controller surface. Frontmatter declares metadata (`phase`, `gate`, `stop`); the body contains the full execution instructions.

- **MUST**: every phase node body defines the complete control surface for that phase (goal, actions, gate command, pass/fail handling).
- **MUST**: after executing, the Phase Agent runs the gate CLI, reads `check.next`, then consumes that node via the accepted handoff loader/check.
- **MUST NOT**: an MD node cannot bypass the gate and self-declare the next node — transition routing belongs to the chain.

### 4.2 `transitions.chain.json` — Passive Routing Table

The **single source of truth** for node-to-node routing. A pure static map: given a current node `fileRef` and a gate outcome, it returns the next node `fileRef`.

- **MUST**: the chain encodes only **deterministic outcomes** — an outcome whose next-node target is fixed and context-independent. Currently only `passed` (all phases) and `rerun` (HITL2 only). Indeterminate branches (`request_view_revision`, `repair`, `stop_blocked`) are **Agent judgment calls** and never enter the chain.
- **MUST**: both keys and values in the chain are node `fileRef`s (e.g., `phases/phase-wave0.md`), never gate keys or phase keys.
- **MUST NOT**: the chain holds no state, no counters, no cursor tracking, no conditional branching. It answers queries — nothing more.

The chain is **queried**, not consulted proactively — the Phase Agent asks it (via the Engine/gate's `resolveNodeTransitionDetailed()`) and gets back a string. It has no awareness of who's asking, why, or what happens after.

### 4.3 JS Engine — Validator + Lookup

The Engine layer (gate CLI, `ask-next.mjs`, `transition-chain.mjs`, `trace.mjs`, `workflow-chain.mjs`) performs only deterministic work: validation, lookup, audit-writing.

- **MUST**: the gate CLI takes `--bundle` and `--current-node`, internally invokes the chain lookup, and outputs `check.next`.
- **MUST**: the routing-query entry point lives **inside** the Engine — the MD/Phase Agent never queries the routing table directly. (Current implementation dispatches by transition-file suffix, `.chain.json`, but exact function names/dispatch rules are implementation detail governed by accepted specs, not this document's normative contract.)
- **MUST**: trace writes to `rb_trace.jsonl`, append-only — the authoritative audit trail for pass/fail.
- **MUST NOT**: the Engine does not orchestrate multi-phase flow, does not autonomously choose/load/execute the next node, does not choose repair strategy, does not make semantic judgments.

`workflow-chain.mjs` is explicitly a **passive engine**: the Phase Agent calls `assessNode(fileRef)` to load exactly **one** node (plus its dependency closure); the Engine returns MD content. **The Phase Agent decides what happens next — the Engine never advances the loop.**

---

## 5. The Two Nested Loops

The system has an explicit **outer/inner loop relationship**, spanning both documents:

### Outer Loop — Phase-to-Phase (Tier 1 / Chain)
This is the Agentic Loop described in Section 3: `read phase MD → execute → gate → chain lookup → consume check.next → read next phase MD → repeat`. It advances once per phase, gated by a single deterministic checkpoint (the gate CLI's chain query).

### Inner Loop — Within-Phase Queue (Tier 2 / Queue)
Nested *inside* a single phase's execution, this loop drains phase-local demand: claim a queue demand item → (if delegated) claim a work unit → spawn Sub-agent → submit → repeat until the phase's queue is drained → then and only then does the phase run its gate (which triggers the outer loop's next step).

The relationship is explicit in `agentic-workflow-mechanism.md`'s "Related Guidance" section: *"agentic-queue-mechanism.md 定义 queue-driven phase execution 的架构宪法：两层嵌套 loop... 本文件描述的循环是 AGQ 所依赖的当前运行时基础"* — i.e., the outer Chain loop described in `agentic-workflow-mechanism.md` is the runtime foundation that the queue mechanism's two-nested-loop architecture depends on. The outer loop (Chain) is the **container**; the inner loop (Queue + Work Unit) is what actually happens *during* a single iteration of the outer loop, before that iteration's gate can pass.

Delegated Work Unit execution is explicitly scoped to a single phase and never crosses phase boundaries: *"Sub-agent work units 在单个 phase 内部被 claimed/submitted，不跨 phase."*

---

## 6. Layer Boundaries — What Each Tier Owns / Does Not Own

Synthesizing both the granularity table (§2.4) and the authority table (§4):

| Tier/Component | Owns | Explicitly does not own |
|---|---|---|
| **Chain** | Phase-to-phase transition selection after a gate pass; deterministic outcome mapping | Queue inspection, work allocation, branch/repair logic, state, cursors |
| **Queue** | Phase-local demand tracking, non-delegated completion, delegated in-flight bindings | Delegated result acceptance as "coverage" (must go through Work Unit submit) |
| **Work Unit** | Delegated attempt allocation (`work_id`), submit validation, result/status writes, ledger row appends | Phase transition choice, gate judgment |
| **Gate** | Structural/provenance checks for phase completion, chain query trigger | Inferring delegated coverage from filesystem presence alone (must use submitted ledger) |
| **MD phase node** | Full control surface per phase: goals, actions, gate command, pass/fail handling | Deterministic rulings, routing-table queries, trace writes |
| **`transitions.chain.json`** | Static `{node, outcome} → node` map for deterministic outcomes only | State, counters, cursors, conditional/branch logic, indeterminate outcomes |
| **JS Engine** | Schema validation, chain lookup execution, trace/receipt writing | Loop-driving, autonomous next-node selection, semantic judgment, repair-strategy choice |
| **Sub-agent** | Executing one bounded `task.md`, writing outputs/cache/receipts | ID allocation, queue mutation, ledger appends, gate passing, phase authorization |

A cross-cutting rule ties these together: **both the granularity axis and the authority axis must agree**. A Markdown instruction can *tell* the Phase Agent to claim work units, but only the Engine can allocate `work_id`, accept submit, append the ledger, and produce gate-readable provenance.

---

## 7. How the 11 Phases Connect via `transitions.chain.json`

`manifest.json` lists all 11 phases as flat inventory (key, node path, gate name):

| Key | Node | Gate |
|---|---|---|
| instantiation | `phases/phase-instantiation.md` | `instantiation-complete` |
| hitl1 | `phases/phase-hitl1.md` | `hitl1-recorded` |
| setup | `phases/phase-setup.md` | `setup-ready` |
| seed-topics | `phases/phase-seed-topics.md` | `seed-topics-ready` |
| wave0 | `phases/phase-wave0.md` | `wave0-complete` |
| wave1 | `phases/phase-wave1.md` | `wave1-complete` |
| wave2 | `phases/phase-wave2.md` | `wave2-complete` |
| hitl2 | `phases/phase-hitl2.md` | `hitl2-recorded` |
| readiness | `phases/phase-readiness.md` | `readiness-passed` |
| rerun | `phases/phase-rerun.md` | `rerun-ready` |
| final | `phases/phase-final.md` | *(null — terminal, no gate)* |

`manifest.json` also lists 7 **shared** MD includes (profile, gate-rules, schemas, repair-guidance, anti-cheating-rules, agent-ux-guidance, silent-execution) that phase nodes presumably reference, but these are not part of the transition graph.

`transitions.chain.json` supplies the **actual edges** — this is the graph the manifest inventory does not encode:

```text
instantiation --passed--> hitl1
hitl1         --passed--> setup
setup         --passed--> seed-topics
seed-topics   --passed--> wave0
wave0         --passed--> wave1
wave1         --passed--> wave2
wave2         --passed--> hitl2
hitl2         --passed--> readiness
hitl2         --rerun--> rerun
rerun         --passed--> seed-topics      <-- loop-back edge
readiness     --passed--> final
```

Observations:

1. **Linear backbone**: instantiation → hitl1 → setup → seed-topics → wave0 → wave1 → wave2 → hitl2 → readiness → final is a straight-line pipeline for the `passed` outcome at every step.
2. **One branch point**: `hitl2` is the only node with two chain entries — `passed` goes forward to `readiness`, while `rerun` diverts to the `rerun` phase. This is the one *deterministic* alternate outcome besides `passed` (per the MUST rules, `rerun` is deterministic because it's a fixed, context-independent target chosen by explicit user selection at HITL2, not by ambiguous Agent judgment).
3. **One loop-back edge**: `rerun --passed--> seed-topics` — after a rerun cycle completes, the chain routes back into the seed-topics phase, re-entering the wave0/wave1/wave2 pipeline. This is how incremental re-research cycles are structured without a separate parallel pipeline.
4. **`final` has no outgoing entry** (and its gate is `null` in the manifest) — it is the terminal node; the loop ends there.
5. **Indeterminate outcomes are absent by design**: nowhere does the chain encode `request_view_revision`, `repair`, or `stop_blocked` — these outcomes, per the MUST/MUST NOT rules, are Agent-judgment branches that intentionally return `no_transition` from a chain lookup, forcing the Phase Agent (not the chain) to decide where to go (e.g., HITL2 staying in place to fix issues under `repair`).

This is a direct illustration of the "manifest is inventory, chain is routing" principle: manifest.json alone would give you 11 unordered phase/gate pairs; only transitions.chain.json reveals the actual pipeline shape, its one branch, and its one loop-back.

---

## 8. Key Implementation Constraints (MUST / MUST NOT)

### From `agentic-execution-model.md`
- MUST describe production delegated work as: `queue demand item -> work unit -> sub-agent -> submit -> ledger -> gate`.
- MUST reserve `queue_item_id` for demand identity and `work_id` for delegated-attempt identity — never conflate them.
- MUST treat `operate-work-unit submit` as the **only** delegated success boundary.
- MUST treat submitted ledger rows (in `rb_output_declarations.jsonl`) as the delegated gate-coverage authority.
- MUST treat `_work_units/`, receipts, output files, and cache trails as cross-check/diagnostic surfaces only, unless tied to submitted ledger coverage.
- MUST use "Sub-agent" (not "worker" / "child agent") for the surviving bounded actor.
- MUST NOT describe the retired delegated transport as a production path (there was a prior mechanism now retired; only the sub-agent path is current).
- MUST NOT teach delegated queue completion, filesystem presence, or hand-written ledger rows as valid production coverage.
- MUST NOT let a Sub-agent mutate queue state, append ledgers, run gates, or authorize phase completion.

### From `agentic-workflow-mechanism.md`
- MUST treat MD phase nodes as the controller for each workflow step.
- MUST treat `transitions.chain.json` as the single source of truth for node-to-node routing.
- MUST route through the Engine's accepted transition lookup — no hardcoded "next", no manifest-based next-inference.
- MUST keep the Phase Agent as the runtime driver of the loop (read → execute → gate → chain lookup → consume `check.next` → read next MD).
- MUST keep the JS Engine stateless and passive: validate, look up, write trace — never drive the loop.
- MUST encode only deterministic outcomes in the chain (`passed` for all phases, `rerun` for HITL2 only); indeterminate branches (`request_view_revision`, `repair`, `stop_blocked`) SHALL NOT have chain entries and return `no_transition`.
- MUST load nodes on demand via `check.next` + accepted handoff loader/check — never preload the whole graph.
- MUST NOT implement a JS walker/cursor/loop that drives node-to-node progression.
- MUST NOT encode indeterminate branch logic into the chain.
- MUST NOT preload all nodes at startup.
- MUST NOT let an MD node or Phase Agent bypass the gate to self-declare the next node.
- MUST NOT let the JS Engine decide which node loads next or when to advance.
- MUST NOT reintroduce an FSM as a transition mechanism — chain is the only backend.
- MUST NOT use the manifest as transition-truth — manifest is inventory, chain is routing.

### Derived Constraints (implementation properties required for the loop to function, not independent architectural rules)
- **Chain Completeness**: every deterministic outcome the workflow needs must have a chain edge; a missing edge for a deterministic outcome produces `no_transition` and stalls the loop (the chain cannot self-heal at runtime). Every new phase added MUST ship its deterministic chain entries before it can be reached.
- **Dynamic Loading Integrity**: on-demand loading isn't a performance choice — without it, the Phase Agent could execute unauthorized phases (bypassing the gate) or accumulate unreached-phase content in context, breaking context isolation. `enter-phase`/`load_complete` prove entry, not target-phase work completion.
- **Gate as Sole Phase Boundary**: the gate CLI is the only component that queries the chain and produces `check.next`. If the Phase Agent self-declares "phase complete," the chain is never consulted and phase-routing degrades to Agent self-governance — explicitly prohibited by the project charter.
- **MD Node Availability**: every `fileRef` in the chain must resolve to a readable MD file under `DPT_FRAMEWORK/workflows/nodes/`; a broken reference stops the loop with no fallback, since MD is the Phase Agent's sole source of phase-level instruction.

---

## 9. Mapping to DeerFlow

DeerFlow (the LangGraph-based open deep-research agent framework) has structurally analogous primitives that map cleanly onto the DPT three-authority split, even though the concrete mechanisms differ:

| DPT Framework concept | DeerFlow analogue | Mapping rationale |
|---|---|---|
| **MD phase node** (controller surface: goal/actions/gate command) | **Skills** (Markdown-defined procedural instructions loaded per step) | Both are Agent-readable, natural-language control surfaces that tell the model what to do at a given step without themselves being executable code. A DeerFlow skill, like a phase-*.md node, declares goals/procedure/expected-output in prose that an LLM interprets, rather than a deterministic function that runs. |
| **Gate CLI + `transitions.chain.json` lookup** | **Custom tools** (deterministic, schema-validated function calls invoked by the graph, e.g., a `check_phase_complete` / routing tool) | The gate's role — deterministic validation plus a static routing-table query returning a fixed next-step reference — maps to a DeerFlow custom tool: a Python function with a strict input/output schema that the LLM calls but does not author the logic of. Just as the chain is "queried, not consulted proactively" and returns a plain answer with no awareness of caller intent, a DeerFlow tool executes deterministically and returns structured output for the graph/agent to act on. |
| **Sub-agent executing a bounded `task.md` work unit** | **Subagents** (DeerFlow's isolated, bounded LLM invocations for a scoped subtask, e.g., a researcher or coder subagent spawned per topic) | Both are context-isolated, single-purpose LLM actors: given a bounded task definition (task.md / subagent prompt+scope), they execute independently, return a structured result, and have no authority to mutate shared state, choose next steps, or "pass gates" — that authority stays with the parent/orchestrating layer (Phase Agent in DPT; the graph/supervisor in DeerFlow). |
| **JS Engine (stateless, passive: validate/look-up/trace)** | **LangGraph nodes / state-machine runtime** underlying DeerFlow's orchestration | The Engine's "never drive the loop, only answer queries" posture parallels how DeerFlow's underlying graph executor advances state only in response to explicit node returns — it does not autonomously decide business logic, it executes what nodes/tools return. |
| **`rb_output_declarations.jsonl` submitted ledger** | DeerFlow's shared/graph **state object** (accumulated research state passed between nodes) | Both are the durable, authoritative record of "what has actually been completed and is safe to build on," as opposed to transient filesystem artifacts or in-progress work. |
| **Phase Agent (MD controller-mode driver of the outer loop)** | DeerFlow's **coordinator/planner node** (the top-level orchestrating LLM step that reads plan state and decides the next node/skill to invoke) | Both are the single actor authorized to decide "what happens next" by reading current state and choosing among deterministic options — but only after deterministic validation (gate / tool result) has run. |

**Key structural parallel**: in both systems, the *content* of "what to do" lives in natural-language/Markdown (Skills / phase nodes) interpreted by an LLM, the *correctness checking and routing* is delegated to deterministic code (custom tools / gate+chain), and *isolated execution of bounded subtasks* is delegated to bounded agent instances (subagents / Sub-agents) that cannot themselves authorize progression — only the orchestrating layer, after consuming deterministic validation output, can advance the outer loop. This is the same three-way split of judgment vs. procedure vs. determinism, expressed through different concrete tooling.

**Where the mapping is imperfect**: DPT's chain is an explicit, statically-inspectable JSON routing table separate from the tool/gate that queries it, giving auditable completeness guarantees ("Chain Completeness" constraint in §8) that DeerFlow's graph-edge routing (typically encoded directly in LangGraph edge definitions/conditional routers rather than a standalone declarative file) does not necessarily expose as a separately auditable artifact. A DeerFlow port of this architecture would benefit from externalizing its conditional-routing table into a similarly inspectable static structure, decoupled from the tool code that queries it, to preserve the "MUST NOT hold state / MUST be a pure lookup" property DPT enforces on `transitions.chain.json`.

---

## 10. Summary

The DPT Framework's agentic execution architecture is best understood as **two orthogonal decompositions layered together**:

1. **By granularity** (Chain > Queue > Work Unit): progressively narrower scopes of execution, from phase-to-phase routing down to a single bounded Sub-agent task, each with its own concurrency model and its own "what counts as done" rule (gate pass / queue completion or delegated binding / `operate-work-unit submit`).
2. **By authority** (MD / Chain-table / Engine): a strict three-way split of who decides what at any given step — Markdown holds procedure, the chain table holds only deterministic routing facts with zero state, and the Engine holds only deterministic validation and lookup with zero autonomy.

The system's central invariant, repeated across both files, is that **judgment stays with the Agent, procedure stays in Markdown, and everything deterministic (schemas, transitions, receipts, ledgers, gates) stays in the JS Engine/CLI** — and no component is permitted to reach across that boundary, even under the pressure of convenience (e.g., an MD node self-declaring the next phase, or a Sub-agent writing its own ledger row). The chain's job is reduced to the smallest possible surface — a pure, stateless, auditable lookup table for deterministic outcomes only — precisely so that the loop's correctness can be verified by inspecting a static file rather than by tracing runtime control flow.