# DPT Engine 系统 — 详细分析

> 从 `ai_tool_deepresearch` 分析，用于在 DeerFlow 上重实现。
> 主控文档: [../dpt-to-deerflow-mapping.md](../dpt-to-deerflow-mapping.md)

## 概述

DPT Engine 是 JS 确定性层，包含四个核心子系统：Gate（门禁检点）、Queue（任务队列）、Work Unit（委托执行）、Trace（审计追踪）。

---

# DPT Framework Gate System — Detailed Analysis

## 1. `engine/gate-loop.mjs` — `checkGate` (pure checkpoint primitive)

`checkGate(state, rules, next?)` is a small, pure function (29–91 lines) with **zero domain knowledge**. It validates its own inputs (`validateState`, `validateRules` from `gate-helpers.mjs`) and throws on malformed calls — that's the only "impure" thing it does (throwing, not side-effecting).

**Rule evaluation semantics — first-match-wins:**
```js
for (const rule of rules) {
  if (rule.schema) {
    const parsed = rule.schema.safeParse(state);
    if (!parsed.success) return { passed: false, say: rule.say, errors: zodErrors(parsed.error) };
  }
  if (rule.check && rule.check(state)) {
    return { passed: false, say: rule.say };
  }
}
return { passed: true, say: '门禁通过。', ...(next ? { next } : {}) };
```
Rules are ordered; the engine iterates and returns on the **first** rule that fires. A rule can carry `schema` (Zod), `check` (predicate), or both — when both are present, schema runs first and short-circuits before `check` is ever evaluated. This gives a clean separation: **schema rules catch shape/type problems** (missing field, wrong type — "field-level"), **check rules catch domain/business logic** ("business-level", e.g. a count below a threshold). If no rule fires, the state is considered clean and the function returns `passed: true` plus an optional caller-supplied `next` label — note `next` here is just an opaque string the caller wants echoed back, not something `checkGate` computes itself (that's `transition-chain`'s job, layered on top).

The return contract is uniform JSON regardless of outcome: `{ passed, say, next?, errors? }`. `say` is **always** a natural-language string — this is the crux of the whole design (see §4 below).

## 2. `engine/gate-fork.mjs` — `forkGate` (branching checkpoint)

`forkGate(state, rules, branches)` reuses the exact same rule-evaluation kernel as `checkGate` (same schema/check semantics, same first-match-wins ordering) but changes what happens when a rule fires. Instead of just failing, it consults a `branches` map keyed by `rule.key`:

```js
if (rule.check && rule.check(state)) {
  const branch = branches[rule.key];
  if (branch) {
    if (branch.when && !branch.when(state)) return { rule: rule.key, say: rule.say };
    return { branch: rule.key, say: branch.say };
  }
  return { rule: rule.key, say: rule.say };
}
```

Three distinct outcomes:
- **Branch matched** (`{ branch, say }`) — MD should execute the branch's natural-language action.
- **Rule fired, no branch** (`{ rule, say }`) — either no branch was registered for that key, or the branch had a `when` guard that returned false; MD interprets this as "repair the state", not "take an action".
- **Nothing fired** (`{ say: '门禁通过，但没有分叉。' }`) — all rules passed, there's no fork to take.

Critically, `forkGate` does not execute the branch — it only *decides which branch and returns a description of the action*. The actual doing (writing a file, calling another tool, transitioning phase) is left entirely to the calling Markdown-driven agent. This is deliberate: the engine is a decision oracle, not an executor, keeping it side-effect-free and testable.

## 3. `engine/transition-chain.mjs` — `resolveTransition` (chain lookup)

This module is completely orthogonal to the gate rule engines — it has no concept of `state`, `rules`, or `say`. It's a **stateless dictionary lookup** over a validated chain table:

```js
export const ChainDefinition = z.record(
  z.string().min(1),
  z.record(z.string().min(1), z.string().nullable())
);
```
i.e. `{ [currentNodeRef]: { [outcome]: nextNodeRefOrNull } }`.

`loadChain(path)` reads and Zod-validates a `.chain.json` file. `resolveTransition(chain, currentNodeRef, outcome)` does a two-level lookup: first find the node's entry, then find the outcome's target inside it. If either lookup misses, it returns `{ next: null, found: false }` rather than throwing — a missing entry is a legitimate "no transition defined" signal, not an error.

Note it explicitly disclaims ownership of "current node progression" — the caller (the CLI wrapper, ultimately the MD agent) is responsible for knowing what node it's currently on and feeding that in; the module itself carries no cursor/session state between calls. This is layered above `checkGate`/`forkGate`'s pass/fail decision: `gate-loop.mjs` decides *whether* the state passes; `transition-chain.mjs` (via `ask-next.mjs`'s `resolveNodeTransitionDetailed`, which dispatches to it) decides *where to go next* given the node + outcome. `ask-next.mjs` wraps this into a richer discriminated result (`kind: next | terminal | no_transition | invalid_input | config_error`), which is what the CLI layer actually consumes as `routing`.

## 4. `engine/helpers/gate-helpers.mjs` — barrel module

This file is a pure re-export barrel with no logic of its own, aggregating six sub-modules:
- **`gate-helpers-core.mjs`** (~995 lines) — the real workhorse: `parseGateCliArgs` (argv → `{bundle, currentNode, transitions, attempt}`), `loadGateDefinition`/`tryLoadGateDefinition` (JSON gate-definition loader), `loadManifest`, `validateNodeGateBinding` (cross-checks `--current-node` against `workflows/manifest.json`'s node↔gate binding), `resolveRouting` (thin wrapper over `ask-next.mjs`'s `resolveNodeTransitionDetailed`), `buildGateResult`/`emitGateResult` (assemble and print the final JSON + set process exit code), plus trace/checkpoint writers (`writeGateAttempt`, `writeCheckpointManifest`, diagnostics writers, `writePlanProgress`, `readTraceEvents`).
- **`gate-helpers-readers.mjs`** — bundle file readers (plan, profile, frontmatter, declared outputs) plus `validateState`/`validateRules`/`zodErrors`, the exact helpers `gate-loop.mjs`/`gate-fork.mjs` import for their own argument validation.
- **`gate-helpers-checks.mjs`** — reusable rule-check implementations (reference format/URL/coverage checks, `checkCacheCoverage`).
- **`gate-helpers-provenance.mjs`** — work-unit ledger/output/submission provenance checks and "delegated bypass" suspicion detection.
- **`gate-helpers-serial.mjs`** — resilient YAML/JSON readers with repair, plus template-not-expanded scanning.
- **`handoff-helpers.mjs`** — trace-backed lifecycle handoff validation (`checkPhaseHandoffPreflight`, enter-phase target validation).

This barrel is the seam between the generic gate primitives (`gate-loop`/`gate-fork`) and the concrete per-gate CLI scripts — every `check-gate-*.mjs` script imports from here rather than from the individual sub-modules directly.

## 5–6. How the CLI gate modules actually compose things

**Important finding:** neither `check-gate-wave0-complete.mjs` nor `check-gate-instantiation-complete.mjs` imports `checkGate` or `forkGate` at all. A repo-wide grep shows only `cli/validate-work-unit-hygiene.mjs` (a linter over gate *definitions*, not a live gate) references `checkGate`/`forkGate` by name, and even that's a false-positive match (`checkGateDefinitions`, a local function). So in practice, the two "canonical" pure engine primitives documented in `gate-loop.mjs`/`gate-fork.mjs` are **not** the mechanism driving the real, deployed gate CLIs — those CLIs have grown their own hand-rolled, isomorphic rule loop built directly on `gate-helpers-core.mjs` primitives. The `gate-loop.mjs`/`gate-fork.mjs` module docstrings describe the *intended* generic pattern; the actual gates implement the same `{key/id, check, say/failure_message}` first/all-fail idea by hand, with extra machinery (topic expansion, masking, degradation, fatigue) that the generic primitives don't support.

Concretely, each `check-gate-*.mjs` script follows this pipeline:
1. `parseGateCliArgs()` → `{ bundle, currentNode, transitions, attempt }` (never calls `process.exit` itself — returns a structured `error` for the caller to emit).
2. `tryLoadGateDefinition(gateKey, currentNode)` → loads `schema/gate_definitions/gate-<key>.definition.json` (rules with `id`, `check` type, `target`, `failure_message`).
3. `validateNodeGateBinding(currentNode, definition.gate)` → cross-checks against `workflows/manifest.json`.
4. `checkPhaseHandoffPreflight(bundle, currentNode)` → lifecycle sanity check before evaluating any rule.
5. A `for (const rule of definition.rules)` loop that dispatches on `rule.check` (`file_exists`, `dir_exists`, `pattern_match`, `status_value`, `cache_coverage`, `work_unit_ledger_exists`, `delegated_bypass_suspected`, `trace_event_present`, …), each delegating to a specific helper from `gate-helpers-checks.mjs`/`gate-helpers-provenance.mjs`. Unlike `checkGate`'s first-match-wins, **this loop evaluates every rule** and accumulates all failures into `inspect`/`advice`/`failedRuleIds` — closer to "collect all schema errors" than "stop at first".
6. `resolveRouting(transitions, currentNode, outcome)` → delegates to `ask-next.mjs` → `resolveTransition` in `transition-chain.mjs`, turning `passed`/`failed` into a routing `{kind, next}`.
7. `buildGateResult({passed, gate, currentNodeRef, routing, inspect, advice, extraCheck, attemptNumber})` → assembles the final envelope, injecting fatigue diagnostics if `attemptNumber >= fatigueThreshold`.
8. `writeGateAttempt(bundle, result, {...})` durably appends a `gate_attempt` trace event to the bundle's `rb_trace.jsonl` (this is the "bundle state" side-effect layer — gate evaluation is otherwise read-only over the bundle).
9. `emitGateResult(result, {bundlePath})` → `console.log(JSON.stringify(result))`, then `process.exit(0|1|2)` based on `check.passed` and `routing.kind`.

So the composition is: **rule dispatch (bespoke, per-gate) → routing (transition-chain via ask-next) → result envelope (gate-helpers-core) → trace persistence (bundle state) → stdout JSON + exit code**. The `say`-centric `{passed, say, next, errors}` shape from `gate-loop.mjs` is echoed at a higher fidelity here as `{check: {passed, gate, currentNodeRef, next}, routing, inspect: string[], advice: string[]}` — `inspect` plays the role of `say`/`errors` (what's wrong, itemized and priority-sorted via `gateMessagePriority`), and `advice` plays the role of "what to do about it" (repair guidance), which `gate-loop.mjs`'s single `say` string doesn't distinguish.

## 7. The natural-language feedback loop

The defining trait of this entire subsystem — and the reason it's called a "Markdown control surface" in every file's header comment — is that **gate output is never consumed by another program via a typed/structured branch decision**. It's consumed by an LLM agent reading raw text (`say`, or `inspect`+`advice`) and deciding in natural language what to do next. Concretely:
- `checkGate`/`forkGate` return `say` (Chinese in the pure primitives — `'门禁通过。'`/`'门禁通过，但没有分叉。'`) as the primary payload; `errors` from Zod are structured but exist only to be *quoted* by the agent, not branched on programmatically.
- The real CLIs' `inspect`/`advice` arrays are literally sentences (`Missing file: ...`, `Verify --current-node matches the phase for this gate...`, the entire fatigue-warning block is prose instructing the agent on what to consider doing).
- This output is piped to stdout as JSON and the calling Markdown-driven agent (Claude, running the DPT phase file) reads it back into its own context window as the *result of running a tool*, then decides — in its own reasoning — whether to retry, repair state, or advance. The exit code (0/1/2) is a coarse signal for shell-level control flow (did the process succeed), but the actual decision of *what to do about a failure* is entirely delegated to the LLM interpreting `say`/`inspect`/`advice`.
- This is explicit even in comments: `forkGate`'s docstring says the engine "returns which branch MD should take" and MD must "execute that action" — the engine never calls the action itself.

## 8. Mapping to DeerFlow

DeerFlow's LangGraph-based agent runs nodes with **Python tool functions** the LLM can call, and those tools can return structured dicts. The direct analogy:
- `checkGate`/`forkGate` ↔ a Python custom tool (e.g. `check_gate(state: dict, rule_key: str) -> dict`) that returns `{"passed": bool, "say": str, "next": Optional[str], "errors": Optional[list]}`.
- `transition-chain.mjs`'s chain table ↔ a Python dict/YAML lookup table consulted by that same tool (or a sibling tool) to compute `next`.
- The gate CLI's `inspect`/`advice` arrays ↔ the tool's returned "observation" text that gets appended to the ReAct/tool-loop message history, i.e., what the LLM sees in its next turn.
- Zod schema validation ↔ Pydantic model `.model_validate()` / `try/except ValidationError`, with the same "safeParse and return structured errors as data, don't raise" pattern.

The key transplant is: **the tool returns natural language + structured hints, and the LLM (inside a `ReAct`/tool-calling node) reads that return value and decides what to do next** — exactly like today's DPT loop, just swapping the calling substrate (Markdown-driven Claude Code agent) for a LangGraph tool-calling node populated by an LLM.

## 9. Why this must remain MD-facing feedback, not a LangGraph conditional edge

A LangGraph **conditional edge** is a deterministic Python function `(state) -> str` that routes the graph without any LLM involvement — the graph's control flow is decided by code, and the LLM never sees the routing decision or reasons about it. Collapsing `checkGate`/`forkGate` into a conditional edge would be a category error, for several reasons visible directly in this code:

1. **The `say`/`inspect`/`advice` fields are the entire point.** They exist to be *read by the LLM*, not by a router. If gate evaluation becomes a conditional edge, that text is thrown away — nothing consumes it — and you silently delete the mechanism by which the agent learns *why* it failed and *how* to repair it (the fatigue-warning prose, the "verify --current-node matches manifest" hints, the `failure_message` templates with `{topic}` substitution). A conditional edge can only return a discrete label, not a repair narrative.
2. **Repair is agentic, not enumerable.** When a gate fails (e.g. `cache_coverage`, `work_unit_output_coverage`, schema errors on reference metadata), the *fix* is open-ended: edit a markdown file, add a missing reference key-facts section, regenerate a JSON declaration, etc. A conditional edge presupposes a finite, pre-known set of successor nodes for each outcome; it cannot express "go do arbitrary corrective work and re-invoke this same check." The MD loop handles this naturally: the agent reads `say`, performs free-form repair actions, and calls the gate CLI again — that's an LLM tool-use loop, not a graph edge.
3. **The rule loop is designed for retries with escalating guidance, not for one-shot routing.** The `attempt`/`fatigueThreshold`/degraded-handoff logic in `gate-helpers-core.mjs` exists specifically to change the *advice text* on repeated failures ("step back", "you may be misreading inspect/advice") — this is a conversation with the agent across turns, which only makes sense if an LLM is in the loop reading and acting on that advice. A conditional edge has no notion of "this is the 3rd time we've hit this edge, escalate the message."
4. **`forkGate`'s branches are natural-language actions to *execute*, not graph nodes to jump to.** `branch.say` is literally "the action for MD to execute" (per the docstring) — it may correspond to writing a file, calling a different tool, or performing a multi-step remediation, not simply "go to node X". Only an LLM agent can interpret and carry out an arbitrary natural-language action; a LangGraph edge can only select among pre-wired graph nodes.
5. **Decoupling decision from execution is intentional and load-bearing.** Both engine files stress "Engine knows NOTHING about your domain" and never executes branches itself — this separation (pure decision oracle vs. LLM-driven executor) is what keeps the engine testable/pure while still allowing domain-specific, judgment-requiring remediation. Baking the decision into a conditional edge would force all remediation logic into Python code ahead of time, defeating the purpose of having an LLM agent in the loop at all — at which point you no longer need the LLM for this step, but the DPT framework's entire premise is that gates are checkpoints *within* an LLM-driven, Markdown-authored workflow, not a hard-coded DAG.

In short: `checkGate`/`forkGate`/the gate CLIs are a **result-as-natural-language contract** deliberately aimed at an LLM reader that will reason and act; a LangGraph conditional edge is a **result-as-discrete-label contract** aimed at deterministic code that routes without reasoning. Porting the *rule evaluation logic* (schema/check rules, first-fail-wins or collect-all) to Python tools is safe and valuable; porting the *routing decision* out of the LLM's hands and into a conditional edge would strip out the repair narrative, the retry/fatigue escalation, and the open-ended remediation capability that the whole system is built around.

---

**Files read for this analysis** (all under `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/`):
- `engine/gate-loop.mjs`, `engine/gate-fork.mjs`, `engine/transition-chain.mjs`, `engine/ask-next.mjs`
- `engine/helpers/gate-helpers.mjs`, `engine/helpers/gate-helpers-core.mjs`
- `cli/gates/check-gate-wave0-complete.mjs` (full read, 577 lines), `cli/gates/check-gate-instantiation-complete.mjs` (first 134 lines)
# DPT Queue Manager — Detailed Analysis

## 0. Module layout

`DPT_FRAMEWORK/engine/queue-manager.mjs` is a pure barrel: it has no logic of its own, it just re-exports from four sibling modules plus a ledger-compat shim. External consumers (CLI, other engine modules) are required to import only the barrel, never the internals directly.

| Module | Responsibility |
|---|---|
| `queue-manager-core.mjs` | trace/logger singleton, `QUEUE` path constants, `QueueStateSchema`/`QueueResultSchema`/`QueueFailureSchema`, `validateQueue`, `syncQueueHealth`, canonical snapshot/hash helpers |
| `queue-manager-window.mjs` | active-window mechanics: `rank`, `sortPool`, `firstOpenPosition`, `promote`, `refill`, `preempt` |
| `queue-manager-lifecycle.mjs` | public API: `createQueue`, `loadQueue`, `saveQueue`, `enqueue`, `claim`, `complete`, `fail`, `inspect`, `pendingCount`, `makeItem`, `checkReceipts` |
| `queue-manager-render.mjs` | writes the read-only Markdown projection consumed by the Phase Agent |
| `queue-manager-ledger.mjs` | back-compat re-export of `WorkUnitLedgerRecordSchema` under the old name `OutputDeclarationLedgerRecord` — a pure alias, no logic |

The wire schema itself (`QueueDemandItemSchema`, `QueueSchema`, `DelegatedInFlightSchema`, `QueueTerminalHistoryRecordSchema`, `QUEUE_ACTIVE_WINDOW_LIMIT = 20`, `QUEUE_SCHEMA_VERSION = 'queue.v2'`) lives one layer down in `DPT_FRAMEWORK/schema/contracts/queue.mjs`, imported into `queue-manager-core.mjs`.

Every mutation is: `clone → validateQueue → mutate → touchQueue(syncQueueHealth(...)) → validateQueue` — a functional, immutable-in/immutable-out style with no hidden shared mutable state (state lives only in the file and in whatever object the caller passes in/out).

## 1. Queue data structure (`rb_queue.json`)

`QueueStateSchema` (runtime) / `QueueSchema` (on-disk projection via `canonicalQueueFileShape`) defines the persisted shape:

```
schema_version: 'queue.v2'
bundle_name: string|null
queue_health: 'ready'|'thin'|'blocked'|'closed'
stop_authorization_state: 'unauthorized_continue_required'|'final_delivery'|'decision_blocker'|'empty_queue_after_refill'
active_window: QueueDemandItem[]      // bounded, <= 20
refill_pool: QueueDemandItem[]        // unbounded, priority-sorted
delegated_in_flight: { [queue_item_id]: DelegatedInFlight }
terminal_history: QueueTerminalHistoryRecord[]
projection_path / trace_path          // in-memory only, not persisted to disk (canonicalQueueFileShape strips them)
created_at / updated_at
```

Four demand/record locations, and `validateQueue` (both the zod `superRefine` in the contract and the redundant hand-rolled check in `queue-manager-core.mjs`) enforces that a given `queue_item_id` can appear in **exactly one** of: `active_window`, `refill_pool`, `delegated_in_flight` (as key, which must equal the value's `queue_item_id`), `terminal_history`. This is the queue's core invariant — no double-booking, no orphaned duplicate IDs across state.

- **`active_window`** — the "now serving" slice. Capped at `QUEUE_ACTIVE_WINDOW_LIMIT = 20`. Position `[0]` is always the current/front item; `claim`/`complete`/`fail` all operate exclusively on `active_window[0]`.
- **`refill_pool`** — everything else that's queued but not yet in the window. Kept sorted (`sortPool`) by a rank tuple so the pool is always ready to feed the window in priority order.
- **`delegated_in_flight`** — a map, not an array, keyed by `queue_item_id`, pointing at Engine-allocated `work_id` attempts (see `DelegatedInFlightSchema`: `work_id`, `wave`, `kind`, `batch_id`, `attempt_index`, `queue_item_snapshot_hash`, `claimed_at`, `timeout_ms`, `deadline_at`, `last_observed_at`). This is populated by `operate-work-unit claim`, not by `queue-manager.mjs` itself — the queue manager only *reads* it (to reject non-delegated claim/complete on those IDs) and it counts toward "queue not empty" in `syncQueueHealth`.
- **`terminal_history`** — append-only record of `done`/`failed` (also allows `blocked`/`cancelled` in the schema) items, each carrying the full `item` snapshot, a `reason`, and `completed_at`. This is the queue's audit trail; items never come back out of it.

## 2. Queue operations

- **`enqueue(queue, item, { mode })`** — `withTimestamps` stamps `status: 'queued'`, `created_at`/`updated_at`. `mode: 'auto'` (default) calls `firstOpenPosition` — if `active_window.length < 20`, push straight into the window at the tail; otherwise fall through to `refill_pool` (re-sorted via `sortPool`). `mode: 'pool'` forces refill-pool placement regardless of window space. Ends with `syncQueueHealth` + `touchQueue`.
- **`claim(queue, { actor })`** — reads `active_window[0]` only (never touches the pool or in-flight map).
  - Empty window → returns `item: null` and sets health to `thin` (pool non-empty) or `blocked` (pool empty) with correspondingly `unauthorized_continue_required` or `empty_queue_after_refill`.
  - Front item has `targets.delegates.to === 'sub-agent'` → **hard reject**: returns `item: null` with `feedback.advice` pointing at `operate-work-unit claim`. Non-delegated `claim` cannot claim delegated demand.
  - Otherwise: mutate `item.status = 'running'`, stamp `updated_at`, write back to `active_window[0]`.
- **`complete(queue, result, bundleDir)`** — the most involved op:
  1. Parse `result` against `QueueResultSchema` (`queue_item_id`, `status: 'done'`, optional `receipt`, `summary`, `writes`).
  2. If `queue_item_id` is a key in `delegated_in_flight` → reject, must use `operate-work-unit submit`.
  3. If `active_window[0].queue_item_id` doesn't match the requested ID → **throw** (hard programming-error case, not a soft feedback path — the caller is out of sync with queue-front).
  4. If the front item itself is delegated (`targets.delegates.to === 'sub-agent'`) → reject the same way.
  5. Resolve the receipt to check: `result.receipt` if given, else `item.completion_receipt`. If not `null`, run `checkReceipts` against it; a failing receipt returns `feedback.passed = false` with `inspect`/`advice`, **without mutating the queue** (item stays `running` at the front — nothing was popped).
  6. On receipt pass: mark `status = 'done'`, `promote(q)` (shift the window), push a `terminal_history` record, `refill(q)` (pull from pool into the now-open window slot), `render(q, bundleDir)` (write the projection), return `feedback.passed = true`.
- **`fail(queue, failure, bundleDir)`** — mirrors the shape of `complete` but for the failure path: validates front-item match, marks `status = 'failed'`, `promote`, pushes a `terminal_history` record with `terminal_status: 'failed'`, then synthesizes (or accepts a caller-supplied) **repair item** via `makeRepairItem`/`QueueFailureSchema.repair`, and inserts it either via `preempt` (if the window still has content after the promote) or `enqueue` (if the window emptied out). Always ends with `refill` + `render`.
- **`refill`** (window module) — sorts the pool, then repeatedly shifts the pool head into the window tail while `active_window.length < 20 && refill_pool.length > 0`. This is the mechanism that keeps the window full as items complete/fail.
- **`promote`** (window module) — `active_window.shift()` — drops the (already-terminalized) front item off the window. Always followed by `refill` in the callers.
- **`preempt(queue, item, { reason, unsafeCurrent, replaceCurrent })`** — urgent insertion. Inserts at index `1` if the current front is `running` and `unsafeCurrent` is false (protects in-progress work from being yanked); inserts at index `0` otherwise. If this pushes the window over the 20-item cap, the displaced tail item is converted back to `queued` with `restore_priority: 'next_tail_opening'` and pushed to the front of the (re-sorted) pool — so it's first in line to come back. `replaceCurrent` (only valid with `unsafeCurrent: true`) forcibly evicts the running front item itself into the pool with the same restore mechanism.
- **Drain** is not a single named function — it's the *emergent state* when `active_window` and `refill_pool` are both empty and `delegated_in_flight` is empty: `syncQueueHealth` sets `queue_health = 'blocked'` and `stop_authorization_state = 'empty_queue_after_refill'`. This is the signal the guideline (§7.2) says the phase gate is supposed to read as "queue is drained, safe to check gate readiness" — but per the guideline's implementation-status table, nothing currently *enforces* reading it before stopping.

## 3. Two nested loops — outer vs inner

Per `guidelines/agentic-queue-mechanism.md` §3, this is a two-loop model nested inside a documented three-tier execution model (Tier 1 = Chain, Tier 2 = Queue):

- **Outer loop (phase-to-phase, "Chain")**: `read MD node → execute → run gate CLI → chain looks up next → consume next MD node → loop`. Authority = gate + `transitions.chain.json`. Deterministic, single-step, statically routed. **Never enters Q** — queue-manager code is not consulted for phase routing at all.
- **Inner loop (within-phase, "Queue")**: `claim queue demand → execute non-delegated task OR claim work-unit for delegated demand → non-delegated complete OR work-unit submit → promote/refill/drain → gate`. Authority = queue-manager validated state (+ work-unit submit state for delegated demand). **Never touches chain** — nothing in `queue-manager-*.mjs` reads or writes `transitions.chain.json`.

**Boundary and interaction (§5, Structural Rules):**
- Rule 1 — the two loops don't mix; no exceptions.
- Rule 2 — queue lifecycle is bounded within a single phase: filled at phase entry, drained before gate. A task's downstream effect crosses phases only via artifacts (files), never via the queue object itself.
- Rule 3 — two separate repair paths, one per layer: **Q-repair** (task-level receipt/submit failure → `fail()` inserts a repair item, stays inside the phase) vs **Gate-repair** (phase-level gate failure → MD "On Gate Fail" + shared-repair-guidance, Phase Agent judgment, max 3 retries). The **single contact point** between the two layers is "Q empty + gate fail" — when the queue has drained but the gate still fails, authority passes to the gate layer (the Phase Agent may optionally re-enqueue to attack specific gaps, but the gate remains the authority, not the queue).
- Rule 4 — no phase rollback: `transitions.chain.json` has only forward `passed` edges; nothing lets a later phase push work back into an earlier phase's queue.

In code terms: `queue-manager.mjs` exports zero symbols related to gates/chain/phases. The coupling to the outer loop is entirely by convention — the *gate CLI* (not shown in the files reviewed) is expected to call `pendingCount`/`inspect`-style checks and read `queue_health`/`stop_authorization_state` as one input among several before declaring the phase gate passed.

## 4. Non-delegated vs delegated queue demand

Every `QueueDemandItem.targets` is a `TargetSpecSchema`: `{ controller: 'main-agent'|'engine', delegates?: { to: 'sub-agent', role_key, timeout_ms } }`. The presence of `targets.delegates` (with `to: 'sub-agent'`) is the single discriminator between the two demand classes, and `queue-manager-lifecycle.mjs` enforces the split defensively at every entry point rather than trusting callers:

- `claim()` — if `active_window[0].targets?.delegates?.to === 'sub-agent'`, refuses and returns `item: null` with advice to use `operate-work-unit claim`.
- `complete()` — checks twice: (a) is this `queue_item_id` currently a key in `delegated_in_flight` (i.e., already claimed as a work unit), and (b) is the front item itself flagged delegated. Either condition rejects with advice to use `operate-work-unit submit`.
- Non-delegated items are claimed/completed entirely through `queue-manager.mjs`'s own state machine (`running` → receipt check → `done`).
- Delegated items are lifted out of `active_window`/`refill_pool` into `delegated_in_flight` by a *different* subsystem (`operate-work-unit claim --count N`, per the guideline §6.2) — that transition isn't in any of the 6 queue-manager files reviewed; the queue manager only reads the resulting map to gate its own claim/complete paths and to feed `syncQueueHealth` (in-flight count counts as "demand exists" so the queue doesn't falsely report `blocked` while sub-agent work is outstanding).

The guideline (§6.2) frames the choice of `main-agent` vs `sub-agent` as a context-management decision along five axes (I/O density, context dependency, output type, determinism, context release) — not a capability distinction. It also states as a hard rule: "Queue active window is not a Sub-agent work pool" — fan-out is created only by `operate-work-unit claim --count N` allocating Engine-owned work-unit IDs, sub-agents never allocate their own IDs, and sub-agents can never pass gates, mutate queues, count evidence, or authorize output (§8 MUST NOTs).

## 5. Task card JSON format

`QueueDemandItemSchema` (schema/contracts/queue.mjs) is the wire contract; `makeItem()` in `queue-manager-lifecycle.mjs` is the factory with sensible defaults. Fields:

| Field | Purpose |
|---|---|
| `queue_item_id` | unique identity; enforced unique across all four queue locations |
| `title` | human label |
| `targets` | `{ controller, delegates? }` — routing/delegation (see §4) |
| `kind` | optional free-text task category |
| `action` | what to do — the instruction surfaced to the Phase Agent via the projection |
| `producer_rule` | which rule/mechanism generated this card (e.g. `manual_enqueue`, `urgent_preemption`, `failed_receipt_repair`) |
| `lineage` | free-form JSON object tracking provenance (topic_slug, trigger, preempted_from, etc.) — CLI's `resolveTopicSlug` reads `lineage.topic_slug` as fallback source |
| `priority_class` | one of 7 ordered classes, `P0_preempted_restore` (highest) through `P6_topology_triage` (lowest) — drives `rank()`/`sortPool()` |
| `action` / `done_condition` | what "done" means in agent-judgeable terms |
| `verification` | `{ engine: string[], agent: string[] }` — explicit split of deterministic engine checks vs agent judgment checks (mirrors the charter's verification-authority split) |
| `writes_to` | declared output file paths this task is expected to produce |
| `status_sync` | ancillary state files to update on completion |
| `completion_receipt` | the receipt string checked at `complete()` time; **nullable only if `required_receipts` is empty** (schema `superRefine` enforces this pairing) |
| `required_receipts` | array of receipt strings checked by `checkReceipts`; supports prefixes `file:`, `json:`, `queue:field=value`, `trace:eventName`, `work_unit:` (always fails — must go through work-unit submit), or literal `none`/`not_applicable` |
| `failure_route` | narrative note on what happens on failure (used for `fail()`'s repair path) |
| `status` | `queued`\|`running`\|`done`\|`failed`\|`blocked` |
| `restore_priority` | `normal`\|`next_tail_opening` — the latter jumps to `rank` position `-1`, ahead of even `P0`, used for preempt-displaced items |
| `created_at`/`updated_at` | timestamps |
| `payload` | free-form JSON, e.g. carries `{ failure }` for auto-generated repair items |

Schema is `.passthrough()`, so extra fields survive round-trips, but a `superRefine` explicitly **forbids** a `work_id` field on demand items — `work_id` is reserved for Engine-allocated delegated work-unit attempts (`makeItem` throws synchronously if a caller passes `work_id` in overrides, redundant with the schema-level check).

`canonicalQueueItemSnapshot`/`queueItemSnapshotHash` (core module) compute a stable SHA-256 over the item with a fixed exclusion set (`status`, `restore_priority`, timestamps, `runtime_refs`, `attempt_index`, `claimed_at`, `deadline_at`, `timeout_ms`, `last_observed_at`, `queue_item_snapshot_hash`, `work_id`) — this is the hash stored in `DelegatedInFlight.queue_item_snapshot_hash`, presumably to detect drift between the queue-demand card and what a work-unit attempt actually claimed.

## 6. Stop authorization states

Four states (`StopAuthorizationState` enum in `schema/enums.mjs`):

- `unauthorized_continue_required` — the **default**. Set whenever `queue_health` is `ready` or `thin`. Means: the Phase Agent is not authorized to stop; there is more demand (window and/or pool) or delegated work outstanding.
- `empty_queue_after_refill` — set when `demandCount === 0 && inFlightCount === 0` (i.e., window empty, pool empty, no delegated attempts outstanding) — the queue itself has nothing left to give.
- `final_delivery` / `decision_blocker` — declared in the enum and in the schema, but **`syncQueueHealth` never assigns either of these** in any of the six files reviewed. They exist as valid target states presumably meant to be set by phase-level/gate logic outside the queue manager (e.g., when the phase reaches an actual terminal deliverable or hits a genuine human-decision blocker), not by queue mechanics itself.

Per the guideline (§7.2, explicitly flagged in the "Implementation Status" table as **❌ 未实现**): the engine computes `stop_authorization_state`, but nothing currently *reads* it to actually prevent the Phase Agent from stopping. It's a pure data field today — advisory, not enforced. The guideline's stated intended enforcement point is phase-drain/gate-readiness checking (queue demand + delegated in-flight + expired attempts + repair/refill demand must all be accounted for before the gate can advance), but that wiring doesn't exist in the reviewed engine code.

## 7. Queue health: ready / thin / blocked / closed

`syncQueueHealth` (core module) is the sole place `queue_health` is computed, called at the end of every mutating operation:

```js
demandCount = active_window.length + refill_pool.length
inFlightCount = keys(delegated_in_flight).length

if demandCount === 0 && inFlightCount === 0:
    health = 'blocked'; stop = 'empty_queue_after_refill'
elif active_window.length < LIMIT(20) && refill_pool.length === 0:
    health = 'thin'; stop = 'unauthorized_continue_required'
else:
    health = 'ready'; stop = 'unauthorized_continue_required'
```

- **`ready`** — window has room to grow via refill or is at/above capacity in a healthy way; pool has stock.
- **`thin`** — window below the 20-item cap *and* pool is empty — there is nothing left to backfill with, even though current window items may still be pending/running. This is a warning state: the window will shrink toward empty as items complete, with nothing behind it.
- **`blocked`** — everything is exhausted: no window demand, no pool demand, no delegated attempts in flight. Distinct from `claim()`'s own inline health-setting when the window is momentarily empty but the pool still has stock (`claim` sets `thin` in that specific case directly, matching what `syncQueueHealth` would compute).
- **`closed`** — present in the `QueueHealth` zod enum (`schema/enums.mjs`) as a valid schema value, but `syncQueueHealth` never produces it. It's a schema-level placeholder for a health state (queue permanently closed / phase fully drained and gated?) that no reviewed engine code currently assigns — consistent with the guideline's framing that some architectural surface exists ahead of behavior implementation.

Note `claim()`'s empty-window branch computes health locally rather than calling `syncQueueHealth` (it distinguishes `thin` vs `blocked` using the same `refill_pool.length > 0` test, but doesn't factor in `delegated_in_flight` the way `syncQueueHealth` does) — a minor asymmetry: if the window is empty, the pool is empty, but there *are* delegated attempts in flight, `syncQueueHealth` would say `blocked`/`empty_queue_after_refill` is wrong (it wouldn't, since `inFlightCount` isn't 0, it'd fall into the `thin` branch's `else` → `ready`), whereas `claim()`'s inline logic would say `blocked`/`empty_queue_after_refill` purely based on pool emptiness, ignoring in-flight work. This is a subtle divergence between the two code paths worth flagging if consistency matters.

## 8. Mapping to DeerFlow (this repo, `ai_deerflow_deep_research`)

This section is **inferential/porting analysis**, not a description of existing code: I searched this repository (`ai_deerflow_deep_research`) for `queue_manager`/`rb_queue` and found no matches — there is currently no Python queue-manager tool or `rb_queue.json` file here. DeerFlow's existing tool convention lives at `backend/packages/harness/deerflow/tools/` and `backend/packages/harness/deerflow/sandbox/tools.py` (e.g. `skill_manage_tool.py` as a precedent for a tool that manages JSON-backed state), and there's an established `backend/sandbox` + sandbox-tools pattern (`test_sandbox_tools_security.py`, `test_local_sandbox_provider_mounts.py`, etc.) for tools that read/write files inside a sandboxed working directory. Porting the DPT queue-manager design onto that substrate would look like:

- **State file**: `rb_queue.json` written under the sandbox's per-run bundle directory (analogous to DPT's `bundleDir`), e.g. `_bundle/rb_queue.json`, subject to the same sandbox path-containment guarantees DeerFlow already enforces for other sandbox tools (`test_local_sandbox_virtual_path_contract.py`, `test_sandbox_windows_path_normalization.py`).
- **Tool surface**: a single Python `queue_manager` tool (mirroring `operate-queue.mjs`'s subcommands) exposing `check`/`enqueue`/`claim`/`complete`/`fail`/`preempt`/`count`/`render` as either one multi-op tool with an `action` argument or several thin tool functions, each reading `rb_queue.json`, validating (pydantic model mirroring `QueueStateSchema`/`QueueDemandItemSchema`), mutating, and rewriting — the same load→validate→mutate→save discipline as `loadQueue`/`saveQueue` in `queue-manager-lifecycle.mjs`.
- **Schema translation**: zod → pydantic models for `QueueDemandItemSchema`, `DelegatedInFlightSchema`, `QueueTerminalHistoryRecordSchema`, `QueueSchema`, preserving the uniqueness invariant (a `queue_item_id` may appear in exactly one of active_window/refill_pool/delegated_in_flight/terminal_history) and the `completion_receipt`-null-iff-`required_receipts`-empty pairing rule.
- **Active window / refill pool / delegated in-flight** map directly: DeerFlow's own agent/sub-agent delegation model (it already has sub-agent/task-tool concepts per `test_task_tool_core_logic.py`, `test_invoke_acp_agent_tool.py`) would fill the same non-delegated-vs-delegated split — non-delegated demand claimed directly by the calling agent turn, delegated demand claimed as a bounded task/tool invocation whose result is submitted back rather than completed through the queue tool directly.
- **Render projection**: DPT's `queue-manager-render.mjs` writing a Markdown snapshot to `_cache/agentic-queue/current-task.md` maps to a DeerFlow tool returning a compact JSON/text result payload to the calling agent turn — same purpose (agent reads a bounded projection/result rather than the raw queue file or raw sub-task output) instead of a file, since DeerFlow tools return content directly to the LLM context rather than through a rendered file the agent re-reads.
- **Outer/inner loop boundary**: DeerFlow doesn't have a DPT-style `transitions.chain.json` gate/chain outer loop in the files inspected here, so the *inner*-loop-only scope (§3.2/§5.1 of the guideline) is the directly portable piece; the outer-loop concept (phase-to-phase routing) would need a DeerFlow-native analogue (e.g., its own workflow/graph node sequencing) if that separation is to be preserved — this repository's own orchestration model, not something present in the DPT files reviewed, would need to be examined separately to complete that half of the mapping.

**Caveat**: everything in this subsection is a design analogy derived from the DPT mechanism plus this repo's directory conventions — it is not describing an implemented DeerFlow queue_manager tool, since none exists in this repository as of this analysis.

---

**Files read for this analysis** (all absolute paths):
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/engine/queue-manager.mjs`
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/engine/queue-manager-core.mjs`
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/engine/queue-manager-lifecycle.mjs`
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/engine/queue-manager-window.mjs`
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/engine/queue-manager-render.mjs`
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/engine/queue-manager-ledger.mjs`
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/cli/operate-queue.mjs` (lines 1–150)
- `/Users/bowhead/ai_tool_deepresearch/guidelines/agentic-queue-mechanism.md` (§3–7, full file read)
- Additionally consulted for grounding: `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/schema/contracts/queue.mjs` and `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/schema/enums.mjs` (to resolve the full wire schema and confirm the `closed`/`final_delivery`/`decision_blocker` unused-state observations in §6–7 above).
## DPT Work Unit System — Detailed Analysis

### 1. Module map (barrel structure)

`work-unit-core.mjs` is a pure re-export barrel with no logic of its own — it exposes the public API assembled from seven submodules:

| Module | Responsibility |
|---|---|
| `work-unit-constants.mjs` | Static config: root paths, ledger filename, kind registry, required receipt fields, per-kind default task/output/cache contracts |
| `work-unit-index.mjs` | `_work_units/_index.json` CRUD, `work_id` parsing/allocation/validation, batch/wave bookkeeping, file-lock transactions |
| `work-unit-envelope.mjs` | Builds and writes the on-disk task envelope (`manifest.json`, `task.md`, `result.schema.json`, `_beacon.json`, receipt/status/agent files), and the sub-agent spawn prompt |
| `work-unit-lifecycle.mjs` | `createWorkUnit`, `claimWorkUnits`, `openWorkUnitBatch`, `closeWorkUnitAttempt` (terminal transitions) |
| `work-unit-submit.mjs` | `drySubmitWorkUnit`, `submitWorkUnit`, `lateSubmitWorkUnit` — the only paths that append to the ledger |
| `work-unit-validation.mjs` | Manifest/beacon/result/receipt/output-file/cache-trail/source-claim/queue-binding validators |
| `work-unit-timeout-preflight.mjs` | Read-only progress inspection gating whether a `timeout` close is allowed |
| `work-unit-utils.mjs` / `work-unit-index.mjs` | Ledger I/O, hashing, path-safety helpers |
| `work-unit-inspect.mjs` | Cross-cuts index/receipts/beacons/ledger for a full-bundle health report |

`cli/operate-work-unit.mjs` is the thin CLI surface (`claim`, `inspect`, `submit`, `dry-submit`, `late-submit`, `fail`, `timeout`, `abandon`, `open-batch`) that the Phase Agent (main agent) invokes; it never talks to files directly.

---

### 2. Lifecycle: claimed → running → submitted | failed | timed_out | abandoned

**State machine** (encoded in `_index.json` per-record `status` field):

1. **claimed** — created by `createWorkUnitInIndex` (in `work-unit-lifecycle.mjs`) either via direct `createWorkUnit` or, more commonly, via `claimWorkUnits`. Claiming:
   - Pops the front item off `queue.active_window` (queue must be eligible: `targets.delegates.to === 'sub-agent'` and wave-matched — `isEligibleDelegatedItem`).
   - Calls `allocateWorkId` (in `work-unit-index.mjs`) to mint a `work_id` of the form `wu-w{wave}-b{batch}-{kind_code}-i{claim_index}`, bump the batch's `next_claim_index`, and compute `attempt_index` as `max(existing attempts for this queue_item_id) + 1` (this is how retries get incrementing attempt numbers under one `queue_item_id`).
   - Computes `deadline_at = claimed_at + timeout_ms` (default 600000 ms unless `queueItem.targets.delegates.timeout_ms` overrides).
   - Builds the `manifest.json` via `WorkUnitManifestSchema.parse`, writes the full envelope (`writeWorkUnitEnvelope`), and records `queue.delegated_in_flight[queue_item_id] = {work_id, wave, batch_id, kind, attempt_index, queue_item_snapshot_hash, claimed_at, timeout_ms, deadline_at}`.
   - All of this runs inside `withWorkUnitTransaction` (directory-lock + committed/failed transaction journal in `_work_units/_transactions/`), so index + queue + envelope writes are atomic relative to crash recovery bookkeeping (though see §8 on durability verification, which is separate/stronger).
   - Emits `work_unit_claimed` (or `work_unit_retry_claimed` if `attempt_index > 1`) trace + run-log events.

2. **running** — implicit, not a distinct stored status; a `claimed` record with an active sub-agent working against it is "running." The engine has no explicit signal for "in progress" beyond the runtime-receipt JSONL lifecycle events the sub-agent appends (diagnostic only, never authority — see §7 timeout preflight).

3. **submitted** — terminal-success status, set only by `submitWorkUnit` (or `lateSubmitWorkUnit` for the timed-out-recovery path). This is the *only* status transition that also writes a row to `rb_output_declarations.jsonl` and marks the queue item `done` in `terminal_history`.

4. **failed / timed_out / abandoned** — terminal-non-success statuses, set only by `closeWorkUnitAttempt(bundleDir, {work_id, status, reason, force})`:
   - Guards: status must be one of the three; `reason` required; idempotent no-op if `record.status === status && record.terminal_reason === reason`; refuses (`ok:false`) if the record is already `submitted` ("Submitted attempts cannot be terminalized") or already terminal with a *different* reason ("A terminal attempt can only be repeated idempotently with the same status and reason").
   - **timed_out is special**: before allowing the transition, it runs `timeoutPreflightWorkUnit` (read-only progress check). If `!force && !timeoutPreflight.timeout_eligible`, the close is refused and the caller gets back `recommended_action`/`progress`/`advice` instead. `--force` can override, but the resulting event carries a `forced_timeout` audit block (`preflight_timeout_eligible`, `default_timeout_would_refuse`, etc.) and an extra `work_unit_forced_timeout` trace event, so forced overrides are permanently auditable.
   - On successful close: removes `queue.delegated_in_flight[queue_item_id]`; writes `_status.json` for the work unit; records `terminal_reason`/`terminal_at` in the index record.
     - **timed_out** → re-queues a *new* queue item (`preempt(queue, retryItem, {reason:'work_unit_timeout_retry'})`) carrying `lineage.retry_of_work_id`, `retry_reason`, `attempt_index: record.attempt_index + 1`. This is how retries get a *new* `work_id` on next claim while staying bound to the same `queue_item_id`.
     - **failed / abandoned** → pushes a `terminal_history` entry (`terminal_status: 'failed'|'cancelled'`) and calls `refill(queue)`; no automatic retry.
   - Emits `work_unit_failed` / `work_unit_timed_out` / `work_unit_abandoned` trace+log events (info level, except `timed_out` logs at `warn`).

Key invariant enforced throughout: **only a `claimed` record can be terminalized**, and **only a `claimed` (non-terminal, non-submitted) record can be submitted**. This makes the state machine effectively: `claimed → {submitted} | {failed, timed_out, abandoned}`, with `timed_out` uniquely able to spawn a fresh `claimed` attempt via queue re-injection (a new `work_id`, not a resurrection of the old one). `late-submit` is the one exception allowing a `timed_out` record to still become `submitted` post-hoc under strict guardrails (§6).

---

### 3. Envelope structure

`refsForWorkUnit(bundleDir, {wave, work_id})` defines the canonical directory: `_work_units/wave{N}/{work_id}/`, containing (all paths bundle-relative):

| File | Written by | Purpose |
|---|---|---|
| `manifest.json` | `writeWorkUnitEnvelope` | Full `WorkUnitManifestSchema`-parsed record: identity (`work_id`, `queue_item_id`, wave/batch/claim indices), `producer_rule`, `creation_reason`, `queue_item_snapshot_hash`, `receipt_nonce`, `claimed_at`/`timeout_ms`/`deadline_at`, `output_contract`, `cache_policy`, `runtime_refs`, `paths`, and a full clone of the originating `queue_item`. This is the source of truth the validators re-derive everything else from. |
| `task.md` | `taskMarkdown()` | Human/agent-readable brief: binding identity fields, absolute runtime paths (`bundle_dir` + every ref), a "Write-Before-Return Checklist," the output contract and cache policy as embedded JSON, example lifecycle-receipt JSONL lines, example diagnostic-log CLI invocations, and an explicit statement that "Completion is accepted only when the main Agent submits this work unit through `operate-work-unit submit`." Kind-specific addenda are appended for `wave1_topic_deepening` and `wave2_targeted_evidence`. |
| `result.schema.json` | `resultSchemaDocument()` | A JSON Schema built dynamically from the manifest's `output_contract`: pins `work_id`/`queue_item_id`/`kind`/`receipt_nonce` as `const`, requires `requiredResultFields(outputContract)` (defaults to `work_id, queue_item_id, kind, receipt_nonce, output_files, cache_trails`), defines `output_files[]` item shape (with role enum restricted to `output_contract.output_files.allowed_roles`), and conditionally adds `source_claims[]`/`accepted_source_urls[]` when `output_contract.source_claims.allowed === true`. `additionalProperties: false` throughout — strict schema. |
| `_beacon.json` | `writeWorkUnitEnvelope` via `WorkUnitBeaconSchema` | The bootstrap file a sub-agent reads *first*: absolute `bundle_dir`, `bundle` name, identity fields, `deadline_at`, all path refs, `log_cli` path, `output_contract`, `cache_policy`, `required_receipt_fields`, and `runtime_refs` explicitly tagged `runtime_refs_authority: 'diagnostic_only'`. This is the mechanism by which a sub-agent resolves "where am I / what bundle am I in" without inheriting orchestrator state. |
| `runtime-receipt.jsonl` | initialized empty by `writeWorkUnitEnvelope`; appended by the sub-agent | Append-only lifecycle log; each line should validate against `WorkUnitRuntimeReceiptEventSchema` and carry `work_id`, `queue_item_id`, `kind`, `receipt_nonce` (the `WORK_UNIT_REQUIRED_RECEIPT_FIELDS` constant). Task guidance recommends paired batch events (`search_batch_started/done`, `fetch_batch_started/done`, `cache_write_started/cache_written`, `result_draft_started/written`) — explicitly framed as "timeout-preflight diagnostics only." |
| `_status.json` | initialized `claimed`; updated by lifecycle/submit ops | `WorkUnitStatusFileSchema`: `work_id`, `status`, `updated_at`, and post-submit also `result_hash`/`ledger_record_hash`. |
| `_agent.json` | `writeWorkUnitEnvelope` via `WorkUnitAgentFileSchema` | Holds `runtime_refs` (coding-agent thread/session/spawn IDs) — explicitly diagnostic, not authority. |
| `result.json` | written by the sub-agent (or normalized copy written by `submitWorkUnit`) | The actual deliverable the sub-agent produces, validated against `result.schema.json`/`WorkUnitResultSchema` at submit time. |

`spawnPromptForWorkUnit(manifest, bundleDir)` generates the literal text handed to the sub-agent invocation (e.g., a Task-tool prompt): it tells the sub-agent to open `task.md`/`_beacon.json`/schema first, use the exact identity fields (never mint a new nonce), write lifecycle events and the final result under the given absolute paths, verify all declared files exist before returning, and explicitly: "Do not mutate queue, work-unit index, output ledger, or gate state. Return the result path to the main Agent for `operate-work-unit submit`." This is the textual enforcement of the noise-isolation/authority boundary.

---

### 4. Claim mechanics in detail

`claimWorkUnits(bundleDir, {phase, count, batchReason})`:
- Parses `phase` (`waveN`) → integer wave via `parsePhase`.
- Does a **preview** read of the queue first (no lock) to fail fast with a structured "blocked" response if the front item isn't eligible — avoids opening a transaction for a no-op.
- Inside `withWorkUnitTransaction('claim_work_units', ...)`, loops up to `count` times, each iteration:
  - Takes `queue.active_window[0]`; if ineligible for this wave, records `blockedBy` and stops (does not skip past it — the queue is strictly FIFO/gated by wave eligibility).
  - Determines `kind` from the item or `defaultKindForWave(wave)` (wave0→`wave0_source_intake`, wave1→`wave1_topic_deepening`, wave2→`wave2_targeted_evidence`).
  - Throws hard if `queue.delegated_in_flight[queue_item_id]` already exists (duplicate-claim guard — a queue item cannot be claimed twice concurrently).
  - Shifts the item off `active_window`, allocates the work unit, records the in-flight binding.
  - After the loop, calls `refill(queue)` to backfill `active_window` from `refill_pool`.
- Returns `claimed_count`, `claimed_work_ids`, `in_flight_count`, `unclaimed_delegated_count`, `phase_drained` (true when both are zero — this is the phase-completion signal consumers poll), `blocked_by_queue_item_id`, and `prompt_refs[]` (per claimed unit: `work_id`, `queue_item_id`, all path refs, and the full `spawn_prompt` text ready to hand to a sub-agent invocation).

This confirms the description: claim allocates `work_id`, binds `queue_item_id` (via `delegated_in_flight`), and creates `_work_units/wave{N}/{work_id}/` with the full envelope — all before any sub-agent is spawned.

---

### 5. Submit mechanics and ledger

`submitWorkUnit(bundleDir, {work_id, resultPath})`:
1. `prepareWorkUnitSubmit` (validation planning phase, read side-effect-free except for computing hashes) runs all validators (§6) and, if the result content hash matches a prior submitted row for this `work_id` exactly, short-circuits as `duplicate: true` (idempotent re-submit).
2. Inside `withWorkUnitTransaction('submit_work_unit', ...)`:
   - Captures a full file snapshot (`captureSubmitSnapshot`: index, queue, ledger, result/receipt/status files) *before* mutating — this is the rollback point.
   - Writes normalized `result.json`, receipt content, and `_status.json` (`status:'submitted'`, plus `result_hash`, `ledger_record_hash`).
   - Flips `record.status = 'submitted'`, removes the queue's `delegated_in_flight` entry, pushes a `terminal_history` entry with `terminal_status:'done'`, calls `refill(queue)`.
   - `appendLedgerRow(bundleDir, prepared.ledger_row)` → appends one JSON line to `rb_output_declarations.jsonl`.
   - Saves index + queue.
   - Runs `verifySubmitDurablePostcondition` — **re-reads from disk** and asserts: queue no longer shows the item in-flight, queue `terminal_history` has a `done` row for this `(queue_item_id, work_id)`, index shows `status==='submitted'`, and the ledger actually contains a matching submitted row (`findSubmittedLedgerRow`). If any postcondition is missing, it throws, and the transaction's catch path is expected to trigger a rollback via `restoreSubmitSnapshot` (attempting to restore captured file bytes) — building a `buildSubmitDurabilityFailure` response that marks the work unit `suspect` if rollback itself failed. This is a belt-and-suspenders durability check on top of the file-lock transaction, specifically guarding against partial multi-file writes (index/queue/ledger are three separate files, not one atomic DB).
3. Emits `work_unit_ledger_appended` and `work_unit_submitted` trace/log events, plus `work_unit_submit_normalized` if any normalizations occurred (see §6 for what counts as a safe normalization).

**Ledger row shape** (`buildLedgerRow` → `WorkUnitLedgerRecordSchema`): `declared_at`, `work_id`, `queue_item_id`, `wave`, `kind`, `producer_rule`, `creation_reason`, `work_unit_ref`, `result_ref`, `runtime_receipt_ref`, `receipt_nonce`, `output_files`, `source_claims`, `accepted_source_urls`, `cache_trails`, `result_hash`, and a `ledger_record_hash` computed over the rest via `computeWorkUnitLedgerRecordHash` (stable-stringify + SHA-256) — giving each ledger row content-addressable integrity. This ledger file is what gates read as the sole "delegated coverage" authority.

---

### 6. Validation pipeline (`work-unit-validation.mjs`)

Executed (via `work-unit-submit.mjs`'s `prepareWorkUnitSubmit`, not shown in the read range but referenced) roughly in this order, each throwing a descriptive `Error` on failure that `reasonCodeForSubmit(message)` maps to a stable `reason_code` (`missing_receipt`, `nonce_mismatch`, `wrong_work_id`, `missing_output`, `missing_cache`, `stale_snapshot`, `duplicate_content_mismatch`, `invalid_result`):

1. **`readAndValidateManifest`** — manifest file must exist; parse against `WorkUnitManifestSchema`; re-derive `work_id` binding via `validateWorkIdBinding` (checks the `work_id` string's embedded wave/batch/claim/kind-code against the record's registry-resolved kind — catches ID/kind-registry drift); cross-checks every identity field between the manifest and the in-memory index record.
2. **`readAndValidateBeacon`** — beacon must exist; parse; cross-check identity fields against both the index record *and* the manifest (three-way consistency — beacon can't drift from either).
3. **`readAndValidateResult`** — result file must exist; handles an optional `{result: {...}}` wrapper (only if it's the *sole* key, else "unsafe result wrapper" error — recorded as a normalization if unwrapped); enforces required fields from the output contract (`validateRequiredResultFields`); cross-checks `work_id`/`queue_item_id`/`kind` exactly; for `receipt_nonce` specifically allows a controlled normalization *only* if the rest of the identity binding is complete AND the result file physically lives inside the assigned work-unit directory (`isPathInsideDir`) — otherwise a nonce mismatch is a hard failure. Every allowed normalization is recorded via `recordSubmitNormalization` for audit trail (`normalizations[]` returned in the response).
4. **`validateSubmitRuntimeReceipt`** — receipt file must exist and be non-empty; every line must be valid JSONL and a plain object; each event is coerced to include `schema_version` if absent, then presumably validated against `WorkUnitRuntimeReceiptEventSchema` and checked for the four required identity fields matching the record (continuing past the 150-line read window, but the pattern from `runtimeReceiptIssues` in `work-unit-inspect.mjs` confirms per-line field-match checking).
5. **`validateOutputFiles`** — (not in the read window, but referenced/imported) validates declared `output_files[]` entries actually exist under the bundle, path-safety (`isSafeBundleRelative`/`isPathInsideDir` — no `..`, no absolute paths), role is within `allowed_roles`, and `reference_requires_source_url` when applicable.
6. **`validateCacheTrails`** — validates each declared cache-trail leaf directory exists and (per `hasExplicitDegradedCapture`/`validateCacheTrailContent` in utils) contains real fetched content (`websearch.json`, `page.md`, `meta.json`) or an explicit degraded/fetch-failure record — guards against placeholder/empty cache leaves being declared as evidence.
7. **`validateSourceClaims`** — when the kind's contract allows `source_claims`, validates that any `acceptance_status` of "accepted" is backed by a cache trail ref or an explicit `degraded_capture_ref` (`accepted_requires_cache_or_degraded` in the wave1 contract).
8. **`validateQueueBindingForSubmit`** — cross-checks the live `rb_queue.json` state: the queue item must still be recorded `delegated_in_flight` under this exact `work_id`, and the `queue_item_snapshot_hash` recorded at claim time must still match the live queue item (`queueItemSnapshotHash`) — this is the **stale-snapshot** guard: if the queue item was mutated between claim and submit, submit is rejected as stale rather than silently accepting outdated context.

Failure at any validation step leaves the work unit `claimed` (non-terminal) — per the guideline: "Invalid submit is non-terminal. It leaves the attempt claimed, records rejection diagnostics, and allows corrected submit when the attempt is still valid." `recordSubmitRejection` builds a structured rejection with `reason`, `reason_code`, and traces `work_unit_submit_rejected` (or `work_unit_late_submit_rejected` if the record is already terminal) without mutating queue/index/ledger state.

---

### 7. Timeout preflight (progress-aware, read-only)

`timeoutPreflightWorkUnit` decides whether a `timeout` close is *eligible* without forcing it, by inspecting (read-only, no writes):
- Runtime receipt JSONL for events in `PROGRESS_TRACE_EVENTS`-adjacent categories (`work_unit_progress`, `work_unit_result_draft_written`, `work_unit_cache_written`) via file stat + trace scan.
- Whether a candidate result already exists (`resultPayload` unwraps the same `{result:...}` convention as submit).
- Whether the receipt file is non-empty.
- Whether output/cache artifacts show any progress.
- It optionally runs `drySubmitWorkUnit` internally to see if the current state would already validate cleanly (`dry_submit_expected`).
- Produces `progress.latest_engine_observed_progress_at`, `effective_timeout_at` (= `claimed_at + timeout_ms`, i.e., idle-timeout anchored on the claim/lease, not on last progress — meaning progress doesn't extend the deadline, it only affects *eligibility judgment* for whether a forced-vs-natural timeout close is warranted), and a `recommended_action` (`block` by default in `basePreflight`).
- Non-repairable dry-submit failure codes/phases (`wrong_work_id`, `stale_snapshot`, `duplicate_content_mismatch`; phases `work_unit_status`, `queue_binding`, `work_unit_record`, `work_unit_index`) are distinguished from repairable ones — presumably feeding into whether `timeout_eligible` should be `true` even absent explicit progress (i.e., if the unit is unsalvageable regardless of more time, timeout is "eligible" immediately).

This read-only preflight is what `closeWorkUnitAttempt` consults before allowing a non-forced `timeout` transition, and what makes forced timeouts fully auditable (comparing the forced outcome against what the preflight would have recommended).

---

### 8. Late-submit (recovery path for timed-out units)

`lateSubmitWorkUnit(bundleDir, {work_id, resultPath, reason})` is the deliberate, narrow exception to "submitted attempts and non-claimed attempts can't change state." It exists because a sub-agent may finish *after* the engine already closed the unit as `timed_out` and re-queued a retry. Guardrails visible in the read code:
- Only applies to a record whose current status is `timed_out` (asserted via `lateSubmitRejection` messaging: "late-submit is only for audited timed_out recovery").
- `planLateSubmitRetryCleanup` inspects the queue for the *retry* item spawned by the original timeout: it must find at most one queued location for the `queue_item_id`, it must not already have a second `terminal_history` row (can't double-terminalize the same queue item), and if a retry work unit was separately claimed, that retry must not itself be `submitted` (a submitted replacement always wins/blocks late-submit) and must be strictly a later `attempt_index`.
- If a valid retry-in-flight exists, late-submit will supersede it: `supersededRetryWorkIds` tracks which retry work unit gets marked `abandoned` as a side effect of accepting the late submit for the original.
- `applyLateSubmitQueueCleanup` removes the queue item from `active_window`/`refill_pool` and clears `delegated_in_flight`.
- `verifyLateSubmitDurablePostcondition` mirrors the normal submit's postcondition check but with late-submit-specific invariants: exactly one `terminal_history` row for the queue item (targeting the late-submitted `work_id` with `terminal_status:'done'`), no queued retry demand remains, any superseded retry is `abandoned` (not left claimed or submitted), and the ledger has exactly one submitted row for this `queue_item_id` (no duplicate/competing ledger rows).
- Rollback semantics mirror normal submit (`captureLateSubmitSnapshot`/`buildLateSubmitDurabilityFailure`), with the resulting `status` on failure reverting to `'timed_out'` (not `'claimed'`, since that was its state before the late-submit attempt) or `'suspect'` if rollback itself couldn't be proven.
- Guideline confirms the design intent: "Retry allocates a new `work_id`. Late submit against a terminal attempt fails closed" — i.e., late-submit is a controlled, audited exception for the *specific* timed-out predecessor, not a general reopen mechanism; any other terminal status (`failed`, `abandoned`) or an already-`submitted` competing unit fails closed.

---

### 9. Noise-isolation principle (why sub-agents at all)

Per `guidelines/agentic-subagent-mechanism.md` §1/§3: Phase Agent (main orchestrator) context is scarce and expensive. Web search, page fetching, source diagnostics, claim verification, and evidence extraction generate high I/O density and low information density — dumping raw search/fetch traffic into the main context would drown out the judgment-level reasoning the Phase Agent needs to do. Sub-agents are "bounded Agent actors" that absorb that I/O noise and return only a compact, schema-valid `result.json`.

The dividing line (explicit in the guideline) is *judgment scope*, not just I/O volume: delegate work with bounded judgment (source intake, topic deepening, source diagnostics, claim verification, targeted evidence search — mapped to named sub-agent roles like `dpt-source-intake`, `dpt-evidence-extractor`, `dpt-claim-verifier`, `dpt-topic-scout`). Never delegate cross-topic synthesis, phase routing, gate interpretation, final-report judgment, or HITL decisions — those require the Phase Agent's full context and authority and must stay in the main loop.

Structurally, the envelope design enforces this isolation: the sub-agent's world is limited to `task.md` + `_beacon.json` + `result.schema.json` + declared output/cache paths. It cannot see or touch the queue, the work-unit index, the ledger, or gate state — enforced by convention (the spawn prompt explicitly forbids it) and by the fact that the sub-agent has no tool/API surface for those files; only the Engine CLI (`operate-work-unit`) can mutate them, and that CLI is invoked by the Phase Agent, not the sub-agent.

---

### 10. The single delegated path

```
queue demand item -> work unit -> sub-agent -> submit -> ledger -> gate
```

Concretely, from the code:
1. **Queue demand** — an item sits in `rb_queue.json`'s `active_window` with `targets.delegates.to === 'sub-agent'`.
2. **Work unit** — `claimWorkUnits` converts it into a `work_id`-identified, filesystem-materialized task (`_work_units/waveN/{work_id}/`), moving the demand into `delegated_in_flight`.
3. **Sub-agent** — the Phase Agent spawns a native sub-agent using `spawn_prompt` from the claim response; the sub-agent reads the envelope, does the bounded work, writes declared outputs/cache, appends lifecycle receipts, and writes `result.json`. It never touches queue/index/ledger/gate.
4. **Submit** — the Phase Agent calls `operate-work-unit submit --work-id ... --result ...`, which runs the full validation pipeline and, only on success, performs the durable multi-file transition.
5. **Ledger** — `submitWorkUnit` appends exactly one content-hashed row to `rb_output_declarations.jsonl`; this is declared the sole "delegated coverage authority" (guideline §8, Engine/Gate section).
6. **Gate** — downstream wave-gate logic (not in the read files) reads `rb_output_declarations.jsonl` submitted rows as ground truth; it treats `_work_units/` directories and runtime receipts as cross-check/diagnostic surfaces only, and explicitly must "reject or diagnose direct/orphan delegated artifacts that lack submitted coverage" — i.e., a sub-agent writing files to disk without a corresponding submitted ledger row counts for nothing at gate time.

This single path is stated to be the *only* production mechanism: "The old delegated transport is retired as production guidance. Do not use this guideline to revive any alternate delegated completion path" (top of the guideline doc).

---

### 11. Timeout, late-submit, and terminal attempts — summary of guarantees

- **Non-terminal rejection**: a failed validation at submit time never closes the attempt; the work unit stays `claimed`, diagnostics are recorded, and a corrected submit can be retried against the same `work_id`.
- **Terminal closure is explicit and one-way per attempt**: `fail`/`timeout`/`abandon` are deliberate CLI-level operator actions with mandatory `--reason`; idempotent replay with the same status+reason is a safe no-op; replay with a different status/reason on an already-terminal (or submitted) record is rejected.
- **Timeout is progress-gated by default**: natural `timeout` requires `timeoutPreflightWorkUnit(...).timeout_eligible`; `--force` can override but is permanently audit-tagged (`work_unit_forced_timeout` trace event distinct from the normal `work_unit_timed_out` event).
- **Only `timed_out` supports recovery** via `late-submit`, and only if no competing submitted/claimed-later replacement already exists; any successful late-submit supersedes (abandons) a claimed retry rather than leaving two live attempts.
- **Retries always get new `work_id`s** — `attempt_index` increments per `queue_item_id`, and `allocateWorkId`/`nextAttemptIndex` guarantee monotonic, unique IDs; there is no in-place "retry this work unit" operation.
- **Durability is externally re-verified, not just assumed from the transaction lock**: both `submitWorkUnit` and `lateSubmitWorkUnit` re-read the queue/index/ledger from disk after writing and fail (with rollback attempt) if the expected end-state isn't actually observable — protecting against partial writes across the three separate JSON/JSONL files that together represent "submitted."

---

### 12. Mapping to DeerFlow (Claude Code / this environment)

The DPT work-unit system generalizes to the DeerFlow-style agent runtime as follows:

| DPT concept | DeerFlow / Claude Code analogue |
|---|---|
| Queue demand item (`rb_queue.json`) | A planned research/report sub-task the orchestrator (main agent) has queued for delegation |
| `claimWorkUnits` / work-unit envelope | The main agent preparing a bounded task brief (equivalent to `task.md` + beacon) before invoking the **Task tool** for a subagent call — i.e., the act of claiming and writing the envelope corresponds to constructing the subagent's prompt/context package |
| Sub-agent (native actor reading task-unit files) | The **subagent spawned via the Task tool** — a bounded, isolated context that receives only the delegated brief, not the full orchestrator transcript |
| `_beacon.json` (bundle_dir, identity, paths) | Equivalent of giving the subagent the absolute working directory / sandbox root and identifying metadata so it can resolve file paths independent of the parent's cwd — analogous to this environment's rule that "Agent threads always have their cwd reset between bash calls" and must use absolute paths |
| Work-unit state (`_work_units/{work_id}/`, `_index.json`) | The **work-unit/session state kept in the sandbox filesystem** — i.e., a durable, inspectable record of what was delegated, its deadline, and its status, independent of the subagent's own transient reasoning |
| `result.json` + `result.schema.json` validated at submit | **Submit = subagent result + file validation**: the subagent's returned text/output is not itself authoritative; the parent (Claude Code / orchestrator) must validate that declared output files actually exist on disk, match a schema, and are internally consistent (identity fields) before treating the delegation as complete — directly mirroring this Claude Code instance's own operating rule: "Do not Write report/summary/findings/analysis .md files... Return findings directly as your final assistant message" combined with "never re-read a file you just edited to verify — Edit/Write would have errored" (i.e., trust verified tool-level postconditions, not restated claims) |
| `rb_output_declarations.jsonl` ledger row | The durable record the orchestrator keeps of "this delegated unit was completed and here is its verified output" — the equivalent of a parent agent logging a completed subagent task with its verified file paths, analogous to how this subagent's own final answer must supply concrete absolute file paths as its return payload rather than a bare "Done" |
| Gate reading only ledger rows, not raw sub-agent output | The orchestrator should only treat a delegated task as "counted" if its output was explicitly validated/logged, not merely because a subagent *said* it wrote something — i.e., noise isolation and provenance discipline apply the same way: a subagent's chat-level claims are not evidence; file existence + schema validation (or equivalent explicit verification) is |
| Timeout preflight / forced timeout audit trail | The general principle of not silently abandoning a long-running subagent call without checking for partial progress, and of auditing any forced cutoff — relevant to background/async subagent tasks in this environment (`TaskStop`, background run notifications) where a forced stop should be distinguishable from a natural completion |
| "MUST NOT use filesystem presence as delegated coverage" / "MUST NOT use queue completion as delegated success" | Directly parallels this environment's guidance to trust tool-reported success/failure rather than re-deriving success from side-channel evidence — a subagent having *written* a file is not the same as the orchestrator having *validated* it |

The core transferable lesson: DPT's work-unit system is essentially a formalization of "delegate high-I/O bounded work to an isolated subagent, then require an explicit, schema-checked submit step (validated against the filesystem) before crediting the delegation as done" — the same discipline this Claude Code environment expects of any main agent that fans work out to Task-tool subagents: give the subagent a bounded, self-contained brief with absolute paths, let it do noisy I/O in isolation, and never accept "I did it" as ground truth without checking the actual artifacts it was supposed to produce.

---

**Source files referenced** (absolute paths):
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/engine/work-unit-core.mjs`
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/engine/work-unit-lifecycle.mjs`
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/engine/work-unit-envelope.mjs`
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/engine/work-unit-submit.mjs`
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/engine/work-unit-validation.mjs`
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/engine/work-unit-constants.mjs`
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/engine/work-unit-index.mjs`
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/engine/work-unit-inspect.mjs`
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/engine/work-unit-utils.mjs`
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/engine/work-unit-timeout-preflight.mjs`
- `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/cli/operate-work-unit.mjs`
- `/Users/bowhead/ai_tool_deepresearch/guidelines/agentic-subagent-mechanism.md`
I now have everything needed for a complete, evidence-grounded analysis.

---

# DPT Trace and Consistency Systems — Detailed Analysis

## 1. Trace: `engine/trace.mjs` — append-only JSONL audit log

**Design.** `createTrace(filePath, options)` is a **stateless factory** — no module-level globals, no `setTraceFile`. Each instance is bound to exactly one file (`rb_trace.jsonl` inside a run bundle), so multiple bundles never share trace state and there is no cross-run leakage. This matters because DPT runs multiple concurrent research bundles (e.g. `dpt_rb_martin-fowler-ai-sdlc-retreats/`, `dpt_rb_ai-engineer-worlds-fair-2026/`), each needing an independently-owned, tamper-evident log.

**API surface:**
- `traceInit(label, detail)` — deletes any existing trace file (`unlinkSync`) and writes a fresh `run_start` event. This is the *only* destructive operation; every other call is append-only.
- `traceEntry(event, detail)` — the core primitive. Builds `{ ts: ISO8601, event, ...detail }`, `JSON.stringify`s it, and `appendFileSync`s a single line. Optional colorized console echo (`consoleEcho`).
- `traceSummary()` — reads the whole file back, replays it into a human-readable colorized report (pass/fail counts derived from `event === 'check'` entries), and returns `{ events, passed, failed }`.
- `traceCleanup()` — deletes the file entirely (used for test teardown, not production runs).

**Event schema.** There is no rigid schema beyond the two required fields validated by `schema/contracts/trace.mjs`:
```js
TraceEntrySchema = z.object({ ts: z.string(), event: z.string() }).passthrough();
```
Every entry is `{ ts, event, ...arbitraryDetail }` — `.passthrough()` means any additional keys are legal, which is how the same file accumulates structurally different event kinds: `run_start`, `file_read`, `cache_hit`, `file_loaded`, `load_start`/`dependency_resolved`/`load_complete`/`load_error` (from `workflow-chain.mjs`), `gate_attempt` (from the gate CLI layer), `phase_transition` (from `advance-status.mjs`), `diagnostic`/`surfacing_intent` (from `log-event.mjs`), etc. This "one file, many shapes, two guaranteed fields" approach is what lets downstream readers (`handoff-helpers.mjs`, `phase-status-audit.mjs`) do targeted `event.event === 'gate_attempt'` filtering without a rigid union schema.

**Real example** (from `dpt_rb_martin-fowler-ai-sdlc-retreats/rb_trace.jsonl`):
```json
{"ts":"2026-07-08T11:52:04.073Z","bundle":"...","event":"gate_attempt","kind":"gate_attempt","gate":"instantiation-complete","phase":"instantiation","passed":true,"currentNodeRef":"phases/phase-instantiation.md","next":"phases/phase-hitl1.md","inspect_count":0,"advice_count":0,"diagnostic_path":"_diagnostics/gates/2026-07-08T11-52-04.071Z-instantiation-complete.json"}
```
and later:
```json
{"...","event":"load_complete","entry":"phases/phase-final.md","plan":[...],"handoff_source_gate":"readiness-passed","handoff_source_node":"phases/phase-readiness.md","handoff_target_node":"phases/phase-final.md","handoff_source_attempt_index":339,...}
{"...","event":"phase_transition","from":"hitl2_recorded","to":"readiness_passed","next":"none",...}
```

**How trace enables reentry.** The trace is the *sole source of truth for "what legally happened"* — richer and more trustworthy than `rb_status.json` (which is just a cached pointer). Reentry logic (`handoff-helpers.mjs`, `phase-status-audit.mjs`, `check-reentry.mjs`) reconstructs "where is this run allowed to resume" by scanning the trace for the **last legal handoff chain**: a `gate_attempt` with `passed:true` and non-null `next`, that is not later superseded by another attempt on the same gate/node, followed by a route-bound `load_complete` whose `handoff_source_*` fields cross-reference back to that exact attempt by trace index. This index-linked cross-referencing (`handoff_source_attempt_index`) is what makes the trace a verifiable chain rather than just a log — each handoff event embeds a pointer to its authorizing predecessor, so any reader can walk backward and verify the entire lineage without executing anything, purely from the JSONL file. Because the trace is append-only and never edited, it functions like a ledger: "status" can drift or be hand-edited, but the trace's witness of what actually passed cannot be spoofed without literally appending fabricated events (a difference `audit-phase-status.mjs` is built to catch).

---

## 2. Logger: `engine/logger.mjs` — diagnostic detail to `_logs/run.log`

**Explicit separation from trace.** The header states this directly: "trace = audit trail, logger = diagnostic detail. Logger does NOT write to rb_trace.jsonl." Trace records *what happened and what was authorized*; the logger records *free-form diagnostic narrative* for humans debugging a run — cache hits, load-plan lengths, warnings — without polluting the append-only ledger with noise.

**Three layered APIs, one envelope format:**
1. `createLogger({level, file, bundle, consoleEcho})` — generic factory with `debug < info < warn < error` threshold filtering. Produces lines like:
   `[2026-07-08T...] INFO gate_attempt bundle=martin-fowler-ai-sdlc-retreats {"gate":"wave0","passed":true}`
   File writes are best-effort: on `appendFileSync` failure it retries once after `mkdirSync`, then silently swallows — **diagnostics must never block the agent's control flow**, a recurring design invariant across this whole subsystem.
2. `logToRun(bundlePath, level, msg, detail)` — one-shot, file-only convenience wrapper. It re-derives `bundle` via `readBundleName()` (reading `rb_status.json.bundle`, defaulting to `'<unknown>'` on any failure) so callers only need the bundle path, nothing else. This is what `cli/log-event.mjs` calls for its `--level/--msg` mode.
3. `createRunLogger(bundlePath)` — a bound, run-scoped logger for engine hot paths (queue manager, work-unit lifecycle) that auto-emits a `logger_ready` line with `{node, platform, framework_root}` on creation — useful for correlating log file boundaries with process restarts during reentry debugging.

**`readBundleName()`** is documented as "the SINGLE read point for bundle across all 5 callers" — a deliberate DRY choke point so that bundle-name resolution logic (and its failure mode) lives in exactly one place.

**`DIAGNOSTIC_KINDS`** is a frozen, documentation-only registry of 12 canonical `kind` values (`phase_start`, `queue_enqueue`, `receipt_check`, `gate_failure_detail`, etc.) that both `_logs/run.log` and `rb_trace.jsonl` diagnostic entries are supposed to draw from — not enforced by code, but a contract for consistency across writers.

---

## 3. Consistency validator: `engine/consistency-validator.mjs` — static workflow package linter

This is **not** a runtime/trace validator — it validates the *workflow definition package itself* (the Markdown node graph, manifest, gates, transitions) for internal consistency, independent of any specific bundle run. `validateWorkflowPackage(opts)` returns `{ passed: boolean, issues: [{ class, detail, file }] }` — a flat list of typed drift findings, never throws, never repairs.

**What it checks**, layered:
1. **Manifest → node file existence** — every `manifest.phases[].node` and `manifest.shared[]` entry must resolve to a real file (`manifest_missing_node`, `manifest_missing_shared`).
2. **Gate binding consistency** — a node's frontmatter `gate` field must match the manifest's declared gate for that phase (`gate_binding_mismatch`); the referenced gate definition file must exist (`gate_definition_missing`) and its internal `gate` field must match its filename-derived key (`gate_definition_name_mismatch`).
3. **Transition table completeness** — every entry in `transitions.chain.json` must reference existing current/next nodes (`transition_missing_current_node/next_node`); every manifest phase with a non-null gate must have a chain entry (`transition_missing_entry`).
4. **Dependency resolvability** — every `requires` and `suggested_context` ref in node frontmatter must resolve under `nodes/phases/`, `nodes/shared/`, or `nodes/` directly (`unresolvable_dependency`, `unresolvable_context`).
5. **Execution-contract conformance (WNC-001/002/008)** — the largest chunk. Cross-checks a hardcoded `LIFECYCLE_INVENTORY` (11 phase nodes) and `ROLE_SPEC_INVENTORY` (5 work-unit subagent roles) against required `execution_contract` frontmatter fields: `surface` and `search_policy` must be from closed enums and match expected values per node; work-unit-capable phases must `requires` (not just `suggested_context`) both `shared-subagent-protocol` and `shared-anti-cheating-rules`; phases with `search_policy: work_unit_required*` must declare `delegated_role_keys`. It also enforces **structural document shape** — H1 placement relative to `## 0. Execution Brief`/`## 0. Role Brief`, field ordering within those briefs (`findOrderedFields`/`findOrderedExecutionBriefFields` walk `indexOf` positions and flag out-of-order fields), and presence of required numbered body sections (`## 1. Stage Goal` … `## 9. Anti-Cheating Rules`).
6. **Role-spec isolation invariants** — role specs must declare `node_type: shared`, `authority: guidance-only`, must NOT declare lifecycle fields (`phase`/`gate`/`stop`) or appear in `manifest.phases[]`/`manifest.shared[]` (they're phase-agent-loaded guidance, not globally-loaded lifecycle nodes) — `role_spec_in_manifest_phases`, `role_spec_lifecycle_frontmatter`.
7. **Serialization contract (WNC-009)** — a regex heuristic: if a role spec's `## 3. Artifacts` section mentions YAML/JSON output but never mentions `yaml.stringify`/`JSON.stringify`, it's flagged (`serialization_contract_violation`) — catching prose that would encourage hand-concatenated (and thus injection-prone/malformed) structured output.

**How it reports drift.** Every check pushes a `{ class, detail, file }` object onto a flat `issues` array — no severity levels, no early exit (except unreadable manifest, which is fatal since nothing else can be checked). `passed = issues.length === 0`. This is a pure lint pass: it never writes anything, never mutates the workflow package, and is meant to run offline/in CI against the framework's own Markdown+JSON source tree, catching drift between the four parallel truth sources (manifest.json, node frontmatter, gate definition files, transitions.chain.json) before a run ever starts.

---

## 4. Workflow-chain: `engine/workflow-chain.mjs` — dependency-DAG loader

This is the **passive runtime engine** that resolves and loads Markdown "nodes" (phase files, shared guidance, role specs) via their frontmatter `requires` field — a DAG dependency loader, not a driver of agent behavior ("the engine never drives the loop").

**Pipeline for `assessNode(fileRef, state, runtime, trace, logger)`:**
1. `resolveDependencyClosure(fileRef, runtime, trace)` → `_resolveDeps` recursively walks `requires`, using a `visiting` array (cycle detection: if a ref reappears while still on the visiting stack, throws `Dependency cycle detected: A -> B -> C`) and a `visited` set (memoization — already-resolved nodes return `[]`). Produces a **topologically-ordered plan** (dependencies before dependents, entry file last).
2. Each node is read via `readMarkdownFile` — cache-aware (`runtime.contentCache` Map keyed by resolved `.md` ref): cache hit emits `cache_hit`, first read emits `file_read`. Frontmatter is parsed by `parseFrontmatter()`, which tries JSON first (frontmatter block delimited by `---`), falls back to the `yaml` package (YAML 1.2 is a JSON superset), and preserves **all** frontmatter keys (not just `requires`) so downstream consumers (the consistency validator, the audit tooling) see the full node metadata.
3. `executeLoadPlan(plan, state, runtime, trace)` loads each fileRef from cache via `loadMarkdownFile` (emits `file_loaded`), and mutates `state.executionOrder` (push) and `state.counters[fileRef]` (increment) — the engine's own bookkeeping of what was actually loaded and how many times.
4. **WNC-008 contract-header injection**: after loading, `assessNode` checks if the *entry* fileRef is a `manifest.phases[].node`. If so, and its frontmatter says `stop:'no'` (autonomous, non-interactive) with a non-null `gate`, it injects an `AUTONOMOUS MODE` banner directly into the cached Markdown (idempotently — checks for the header's first line before re-injecting) instructing the agent it must not surface to the user, must self-repair on gate failure, etc. If it's the terminal `phase:'final'` + `stop:'no'` + `gate:null` node, it injects a `TERMINAL DELIVERY MODE` banner instead. This is a runtime content-mutation layer bolted onto the pure DAG loader — a behavioral guardrail rendered directly into the text the agent will read.

**Path safety.** `nodePath(fileRef, nodesDir)` rejects `..` and leading `/` — the only path-traversal guard in the loader; `fileRef` may include one subdirectory segment (`phases/...`, `shared/...`).

**Trace threading.** Every stage takes an optional trailing `trace` parameter; `emit()` is the single point where an in-memory `runtime.receipts` push is paired with a durable `trace.traceEntry()` call. If `trace` is omitted, `emit` no-ops on the trace side but still records the in-memory receipt — meaning the engine can run "receipts-only" (e.g. tests) without touching disk.

**How resolves phase node fileRefs (task-specific ask):** Given e.g. `phases/phase-wave1.md`, the loader reads that file's frontmatter `requires: [...]` (e.g. `shared/shared-subagent-protocol`, `shared/shared-anti-cheating-rules`), recursively resolves each dependency's own `requires`, and returns a flat ordered list of every `.md` fileRef that must be concatenated and handed to the agent — shared guidance first, phase body last. `enter-phase.mjs` is the CLI that drives this and prints the concatenated content wrapped in `<!-- DPT_LOADED_FILE_START/END -->` markers per file.

---

## 5. `ask-next.mjs` — outcome → next-node router

A pure, side-effect-free router: `resolveNodeTransitionDetailed(transitionsPath, currentNodeRef, outcome, context)`. It validates `currentNodeRef` is a safe relative `.md` path with a directory segment (`validateNodeRef` — rejects absolute paths, `..`/`.` segments, non-`.md`, bare filenames) and that `outcome ∈ {passed, failed, rerun}`, then dispatches by transitions-file suffix (only `.chain.json` is currently supported — delegates to `transition-chain.mjs`'s `loadChain`/`resolveTransition`). Returns a **discriminated union** result: `{kind: 'next', next}` | `terminal` | `no_transition` | `invalid_input` | `config_error`. This is the deterministic single source of truth for "given this node passed/failed/needs rerun, what node comes next" that both `enter-phase.mjs`'s authorization layer and `advance-status.mjs`'s gate-to-next-gate resolution ultimately depend on (via the shared `manifest.json` + `transitions.chain.json` pair).

---

## 6. `rb_status.json` schema and status management

Schema (`schema/contracts/status.mjs`, Zod, `.passthrough()`):
```js
{
  bundle?: string,
  current_mode: 'execution',              // literal
  state: 'not_started'|'in_progress'|'blocked'|'completed',
  current_gate: CurrentGate,               // enum, see below
  next_gate: CurrentGate,
  current_node?: string | null,            // e.g. "phases/phase-final.md"
}
```
`CurrentGate` enum: `instantiation_complete, hitl1_recorded, setup_ready, seed_topics_ready, wave0_complete, wave1_complete, wave2_complete, hitl2_recorded, rerun_ready, readiness_passed, none`.

Real example from a completed run (`dpt_rb_martin-fowler-ai-sdlc-retreats/rb_status.json`):
```json
{
  "bundle": "martin-fowler-ai-sdlc-retreats",
  "current_mode": "execution",
  "state": "not_started",
  "current_gate": "readiness_passed",
  "next_gate": "none",
  "current_node": "phases/phase-final.md"
}
```
(`current_node` is the loader-level pointer written by `enter-phase.mjs`; `current_gate`/`next_gate` are the higher-level gate-state pointers written by `advance-status.mjs`. `state` here stays `not_started` — a field seemingly not updated by these two CLIs, suggesting it's owned elsewhere, likely written once at instantiation or by a separate lifecycle CLI.)

`rb_status.json` is explicitly treated as a **cache, not authority** — the actual authority is the trace. Both CLI writers (`enter-phase.mjs`, `advance-status.mjs`) only mutate it *after* validating against the trace-derived handoff topology, and `phase-status-audit.mjs`/`check-reentry.mjs` treat any status content that disagrees with the trace as "drift" to be diagnosed, never silently trusted or auto-corrected.

---

## 7. Reentry: how the Agent resumes from `rb_status.json` + `rb_trace.jsonl`

Reentry is not a single function but a layered cross-check between the two files, mediated by `handoff-helpers.mjs`:

1. **`loadHandoffTopology()`** loads `manifest.json` + `transitions.chain.json` once and builds `nodeToPhase`, `gateToNode`, `nodeToGate` maps — the static "legal graph."
2. **`readTraceEventsWithIndex(bundlePath)`** parses `rb_trace.jsonl` line-by-line into `{index, lineNumber, event}` triples (index = position in the *valid* JSON lines, so downstream comparisons like `handoff_source_attempt_index` are stable references into this array).
3. **`latestLegalPassedHandoff`** walks the trace **backward** looking for the most recent `gate_attempt` with `passed:true`, non-null `next`, whose `gate`+`currentNodeRef` match the topology's edge for that gate, that is not later superseded (`supersededBy` — a later attempt on the same gate/node with different outcome/next invalidates an earlier "pass"), and (when `requireLoad`) has a matching `load_complete` event whose `handoff_source_*` fields point back exactly to that attempt's index.
4. This resolves to a `handoff` object: `{sourceGate, sourceNode, targetNode, targetGate, outcome, degraded, sourceAttemptTs, loadComplete}` — the single legally-authorized "next step."
5. **On reentry**, an agent (or `check-reentry.mjs`) compares this trace-derived `handoff.targetNode`/gate window against what `rb_status.json` currently claims. If they match and a `phase_transition` witness event exists for that exact window, status is trustworthy and the agent resumes at `current_node`. If they diverge, that's diagnosed as one of: `status_drift` (status doesn't match latest legal window), `manual_bypass_suspected` (status claims a window with **no** witnessed trace evidence at all — i.e., someone hand-edited the JSON), `missing_witness` (a legal window exists but the `phase_transition` trace record for it is absent), or `failed_gate_downstream_status` (the latest gate attempt actually *failed* but status claims to be past it).
6. Because trace is append-only and cross-referenced by index, no amount of editing `rb_status.json` alone can fabricate a legal resume point — the agent (or a human) would need to also fabricate matching, index-consistent trace entries, which is a much higher bar and is itself checkable (`supersededBy`, exact index matching in `findBoundLoad`).

`check-reentry.mjs` (first 150 lines reviewed) layers a **target-normalization** step on top: `--at wave1_complete`, `--at wave1-complete`, `--at phase-wave1`, `--at phases/phase-wave1.md` all normalize to the same closed vocabulary derived live from `manifest.json` phases (`normalizeTarget`), so a human or agent can ask "am I clean to resume at wave1?" using any natural spelling and get one canonical `{kind, status_gate, gate_key, node_ref, phase_key}` record to check against.

---

## 8. Phase transitions: `enter-phase.mjs` and `advance-status.mjs`

These are the two **write-capable** CLIs in this subsystem; everything else is read-only/diagnostic.

**`enter-phase.mjs`** (writes the handoff witness):
1. Validates `--bundle`/`--node`, confirms `rb_trace.jsonl`/`rb_status.json` exist.
2. Calls `validateEnterPhaseTarget(bundlePath, targetNode)` — this is the gate: it computes `latestLegalPassedHandoff` from the trace and refuses to proceed (`fail(...)`, exit 1) unless the requested `--node` **exactly** equals the trace-authorized `handoff.targetNode`. This is what prevents an agent from jumping to an arbitrary phase — it can only enter the node that the last passed gate's `check.next` legally points to.
3. Wraps `createTrace` in a thin proxy that, specifically on the `load_complete` event for the authorized target node, **injects the handoff witness fields** into the trace record: `handoff_source_gate`, `handoff_source_node`, `handoff_target_node`, `handoff_source_attempt_index`, `handoff_source_attempt_ts`, `handoff_source_degraded(_reason/_rules)`. This is the concrete mechanism referenced in the task — the witness is literally extra keys stapled onto the `load_complete` trace entry, back-linking it to the exact `gate_attempt` trace index that authorized it (seen live in the example trace above).
4. Calls `assessNode` (the workflow-chain loader) to actually resolve+load the DAG for that node.
5. On success, patches `rb_status.json.current_node = targetNode` (a plain read-modify-write, no handoff validation needed here since step 2 already gated it).
6. Prints the concatenated loaded Markdown (wrapped in `DPT_LOADED_FILE_START/END` HTML comments) to stdout for the agent to read — nothing else.

**`advance-status.mjs`** (syncs `current_gate`/`next_gate`):
1. Resolves `--to <gate>` through `manifest.json` (gate↔node maps) and `transitions.chain.json` (node→outcome→nextNode) to compute the candidate `nextGate`.
2. Calls `validateSourceGateStatusSync(bundlePath, targetGateEnum)` — checks whether the target gate is in `COVERED_SOURCE_NODES` (most phases are); if covered, it independently re-derives the latest legal handoff from the trace and requires it to match the requested source gate (`latest.sourceGate !== sourceGate` → error advising to `enter-phase` first). It also builds the handoff again with `requireLoad` set based on whether the target node is in `COVERED_ENTRY_TARGET_NODES` — i.e., for most gates you must have already run `enter-phase` (producing the witnessed `load_complete`) *before* `advance-status` will accept the sync. There's a legacy carve-out (`bootstrapCompatibility: 'hitl1_to_setup'`) for one specific bootstrap edge.
3. Writes the new `rb_status.json` and appends a `phase_transition` trace event (`{from, to, next, source_handoff_degraded...}`) — with a **rollback path**: if the trace append fails after the status file was already written, it attempts to restore the previous status bytes (`previousStatusRaw`) and reports either a clean rollback message or, if rollback *also* fails, an explicit "treat rb_status.json as suspect" warning. This is the one place in the reviewed code with an explicit two-phase-write consistency guard.
4. Only on both writes succeeding does it print `{"status":"ok","current_gate","next_gate","source_handoff_degraded"}`.

Together, the enforced order is: **gate passes → `enter-phase` (witnessed load, `current_node` updated) → `advance-status` (gate/next_gate synced, re-validated against the same trace witness)**. Skipping straight to `advance-status` without the prior `enter-phase` is exactly what `validateSourceGateStatusSync`'s `requireLoad` check is designed to block.

---

## 9. Audit: `audit-phase-status.mjs` / `phase-status-audit.mjs` — diagnostic-only, no repair

The CLI (`audit-phase-status.mjs`) is a 34-line wrapper: parse `--bundle`, call `auditPhaseStatus(bundlePath)`, print JSON, `exit(0)` if `result.ok` else `exit(1)` (or `exit(2)` for a missing `--bundle` argument — the classic invocation-error-vs-domain-failure exit code split used throughout these CLIs).

All real logic is in `phase-status-audit.mjs`, and it is **read-only by construction** — every branch returns an object; nothing calls `writeFileSync` anywhere in this file. `diagnostic_only: true` is stamped on literally every return value, including the passing case, making the "no repair" posture explicit in the output contract itself, not just in comments.

Outcome enum (`PHASE_STATUS_AUDIT_OUTCOMES`): `passed, status_drift, manual_bypass_suspected, missing_witness, failed_gate_downstream_status, bootstrap_exception`.

**Logic flow:**
1. Load trace + topology; any load failure → `missing_witness`.
2. Load `rb_status.json`; parse failure → `status_drift`.
3. Compute `candidateLegalWindows` — every `{currentGate, nextGate}` pair the trace can witness (mirrors `handoff-helpers`' edge logic but collects *all* windows, not just the latest).
4. **Failed-gate check first**: if the latest `gate_attempt` in the whole trace failed (`passed:false, next:null`) and status nonetheless claims to be at-or-past that gate → `failed_gate_downstream_status` (catches "gate failed but status says we moved on anyway").
5. **Premature-final check**: if `final/` contains real files but there's no legally witnessed readiness→final handoff window matching the exact current status → `status_drift` with the note "premature final output is diagnostic only, not delivery evidence" — i.e., the presence of a final report file is never itself treated as proof of completion.
6. **Exact-window match**: if status's `{current_gate, next_gate}` exactly matches a witnessed window, it further requires a `phase_transition` trace event whose `to`/`next` match — if that witness is missing, `missing_witness`; otherwise `passed`.
7. **Bootstrap exceptions**: two hardcoded legacy status windows (`setup_ready|seed_topics_ready`, `hitl1_recorded|setup_ready`) are allowed even with no witnessed window, returned as `bootstrap_exception` (still `ok:true`, but explicitly labeled as an exception rather than a clean pass).
8. **No window at all**: `manual_bypass_suspected` — status claims a state with zero trace evidence, i.e., someone likely hand-edited `rb_status.json`.
9. **Window exists but `next_gate` disagrees with where the trace says the run should point**: `manual_bypass_suspected` again.
10. **Fallback**: status doesn't match the *latest* witnessed window even though earlier windows exist → `status_drift` (stale/regressed status).

Every failing outcome comes with `advice` (`adviceForOutcome`) that is uniformly non-destructive: "Treat phase status drift as diagnostic-only; do not hand-edit rb_status.json," "Return to the latest legal phase target or rerun the predecessor gate, then consume check.next through enter-phase before advance-status." The audit never offers or performs an automatic fix — repair is explicitly routed back through the same `enter-phase`/`advance-status` CLIs that produce trustworthy trace-witnessed writes, never through direct JSON editing.

---

## 10. Mapping to DeerFlow

DPT's trace/consistency architecture maps cleanly onto the concepts you'd want in a DeerFlow-style research orchestrator:

| DPT concept | DeerFlow equivalent |
|---|---|
| `rb_trace.jsonl` (append-only JSONL, one instance per bundle dir, no shared state) | DeerFlow's `run_events` table/stream, or — if sandboxed like DPT — a per-sandbox `rb_trace.jsonl` file. The key transferable property is **append-only + index-linkable**: each event should carry enough back-reference (source gate, source attempt index/id, timestamp) that a later reader can reconstruct legality without re-executing anything. If DeerFlow uses a DB table instead of a file, the equivalent invariant is "never UPDATE/DELETE run_events rows, only INSERT," and design any "handoff" row to embed a foreign key back to its authorizing predecessor row (the DPT analogue of `handoff_source_attempt_index`). |
| `rb_status.json` as a cache, not authority | DeerFlow's cached/materialized "current state" (e.g. a `sandbox.current_phase`/`current_node` column) should likewise be treated as a **derived projection** of the event log, not ground truth — recomputable and auditable, never the sole basis for resuming. |
| `enter-phase.mjs` writing a handoff witness into the `load_complete` trace event | Whatever DeerFlow does when a thread/agent restarts and re-enters a phase should similarly stamp the resulting "I resumed here" event with a back-pointer to the specific prior event (gate/tool-call/checkpoint id) that authorized the resume — not just "we think we're at phase X." |
| `validateEnterPhaseTarget` / `validateSourceGateStatusSync` gating writes on trace-derived authorization | DeerFlow's reentry/resume logic on **thread restart** should read the bundle/sandbox's full event history first, compute the single legally-next step, and refuse to resume anywhere else — this is the direct analogue of "Agent reads bundle state on thread restart": don't trust a cached `current_node`/`current_phase` field blindly, recompute it from the event log the same way `latestLegalPassedHandoff` does, and only accept the cached pointer if it agrees. |
| `audit-phase-status.mjs` / `check-reentry.mjs` as diagnostic-only, no-repair tools | DeerFlow should have an equivalent "explain drift, never auto-fix" utility — surfacing `status_drift`/`manual_bypass_suspected`/`missing_witness`-style outcomes so operators (or the agent itself) can decide how to repair (typically: replay/rerun the last verified step) rather than having the system silently "fix" a JSON/DB field and potentially paper over a real correctness bug. |
| `logger.mjs`'s trace/log separation | DeerFlow should likewise keep a clear line between the durable, verifiable event ledger (used for reentry/authorization decisions) and free-form diagnostic logging (used for human debugging) — mixing the two makes it much harder to write reliable resume logic, since you can no longer trust "no entries of type X" as meaning "X never happened." |
| `consistency-validator.mjs` as a static package linter | DeerFlow's equivalent would be a startup/CI check that its own workflow/graph definitions (node graph, tool registrations, gate/checkpoint definitions) are internally consistent before any run starts — catching drift between the graph definition and its metadata *before* it manifests as a runtime reentry bug. |

The throughline in DPT worth carrying over explicitly: **trace is the single source of truth; every other stateful file (status, logs) is a cache that must be validated against the trace, never trusted in isolation, and repaired only by replaying the legitimate write path (enter-phase → advance-status), never by hand-editing state.**

---

**Files reviewed** (all absolute paths under `/Users/bowhead/ai_tool_deepresearch/DPT_FRAMEWORK/`):
`engine/trace.mjs`, `engine/logger.mjs`, `engine/consistency-validator.mjs`, `engine/workflow-chain.mjs`, `engine/ask-next.mjs`, `cli/log-event.mjs`, `cli/advance-status.mjs`, `cli/enter-phase.mjs`, `cli/check-reentry.mjs` (lines 1–150), `cli/audit-phase-status.mjs`, plus supporting context read for accuracy: `schema/contracts/status.mjs`, `schema/contracts/trace.mjs`, `schema/enums.mjs`, `engine/helpers/handoff-helpers.mjs`, `engine/helpers/phase-status-audit.mjs`, and live example bundle files `/Users/bowhead/ai_tool_deepresearch/dpt_rb_martin-fowler-ai-sdlc-retreats/{rb_status.json,rb_trace.jsonl}`.