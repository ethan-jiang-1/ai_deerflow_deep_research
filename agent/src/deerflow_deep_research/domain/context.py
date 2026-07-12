"""Authority-reduced values that may cross into graph and node code."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from deerflow_deep_research.domain.enums import NodeFinishReason


class FrozenDomainModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ArtifactRef(FrozenDomainModel):
    artifact_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    virtual_path: str = Field(min_length=1, max_length=1024)
    media_type: str | None = Field(default=None, max_length=128)


class GraphContextView(FrozenDomainModel):
    research_scope_id: str = Field(min_length=1, max_length=128)
    workspace_root: str = Field(min_length=1, max_length=1024)
    uploads_root: str = Field(min_length=1, max_length=1024)
    outputs_root: str = Field(min_length=1, max_length=1024)


class NodeAgentContext(FrozenDomainModel):
    research_scope_id: str = Field(min_length=1, max_length=128)
    node_name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    attempt_id: str = Field(min_length=1, max_length=128)
    workspace_root: str = Field(min_length=1, max_length=1024)
    attempt_root: str = Field(min_length=1, max_length=1024)
    policy_name: str = Field(min_length=1, max_length=64)


class NodeExecutionRequest(FrozenDomainModel):
    objective: str = Field(min_length=1, max_length=16_384)
    source_artifact_refs: tuple[ArtifactRef, ...] = ()
    expected_output: str = Field(min_length=1, max_length=2048)


class NodeExecutionResult(FrozenDomainModel):
    finish_reason: NodeFinishReason
    summary: str = Field(default="", max_length=16_384)
    artifact_refs: tuple[ArtifactRef, ...] = ()
    error_code: str | None = Field(default=None, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
