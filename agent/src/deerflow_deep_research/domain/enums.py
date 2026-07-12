"""Stable pure-domain enums shared by graph and node contracts."""

from enum import StrEnum


class NodePhase(StrEnum):
    INFRASTRUCTURE = "infrastructure"
    ORCHESTRATION = "orchestration"
    RESEARCH = "research"
    SYNTHESIS = "synthesis"
    QUALITY = "quality"
    PUBLICATION = "publication"


class NodeFinishReason(StrEnum):
    SUCCESS = "success"
    CANCELLED = "cancelled"
    FAILED = "failed"
    POLICY_DENIED = "policy_denied"
    BUDGET_EXHAUSTED = "budget_exhausted"
    USAGE_UNAVAILABLE = "usage_unavailable"
    INVALID_OUTPUT = "invalid_output"
