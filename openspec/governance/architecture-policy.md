# Architecture Governance Policy

This directory is a project extension to OpenSpec. OpenSpec does not load it
implicitly, so `openspec/config.yaml` and the repository/module `AGENTS.md` files
must retain short bootstrap pointers to this policy and its checker.

## Authority

| Surface | Authority |
|---|---|
| Active `project-structure` main spec | Normative semantic requirements after the first archive |
| One active owning delta | Pending normative requirements before the first archive |
| `project-structure.toml` | Exact machine-readable structural enumeration |
| Generated block in `agent/AGENTS.md` | Deterministic operational projection of the registry |
| Human-authored `agent/AGENTS.md` text | Navigation, rationale, commands, and explicitly labelled future plans |
| Archived change artifacts | Historical context only |
| Contract tests and `check_project_architecture.py` | Mechanical enforcement |

The registry is subordinate to the owning spec. It contains enumerable facts,
not a second prose architecture. This policy defines ownership and update rules
only; it must not contain an independent directory tree or import matrix.

## Lifecycle

Before `openspec/specs/project-structure/spec.md` exists, exactly one active
`project-structure` delta may own the pending structural requirements and must
contain the registry reference marker. Once the main spec exists, it is the
active authority. An archived delta never substitutes for a missing or stale
main-spec reference.

## Synchronized Changes

A change that adds, removes, renames, or reassigns a structural path must:

1. update the owning delta when semantic requirements change;
2. update `project-structure.toml` with the exact current enumeration;
3. regenerate the bounded block in `agent/AGENTS.md`;
4. update deterministic contract fixtures; and
5. pass `check_project_architecture.py` before archive.

A new node that conforms to the existing node-package grammar adds its current
package path to the registry without rewriting the grammar. Changing the grammar
itself requires a `project-structure` spec change.

The generated block is bounded by the markers declared in the registry. Text
outside those markers is human-authored and may explain the structure, but it
cannot override the generated contract.
