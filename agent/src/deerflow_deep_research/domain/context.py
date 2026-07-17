"""Authority-reduced values that may cross into graph and node code."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    minimum_tool_calls: int = Field(default=0, ge=0, le=32)
    tool_call_limit: int | None = Field(default=None, ge=1, le=32)
    tools_enabled: bool = True

    @model_validator(mode="after")
    def validate_tool_window(self) -> NodeExecutionRequest:
        if self.tool_call_limit is not None and self.minimum_tool_calls > self.tool_call_limit:
            raise ValueError("minimum_tool_calls_exceed_limit")
        if not self.tools_enabled and (self.minimum_tool_calls or self.tool_call_limit is not None):
            raise ValueError("disabled_tools_cannot_have_call_requirements")
        return self


class NodeExecutionResult(FrozenDomainModel):
    finish_reason: NodeFinishReason
    summary: str = Field(default="", max_length=16_384)
    artifact_refs: tuple[ArtifactRef, ...] = ()
    untrusted_tool_results: tuple[str, ...] = Field(default=(), max_length=8)
    error_code: str | None = Field(default=None, max_length=128, pattern=r"^[a-z][a-z0-9_]*$")

    @field_validator("untrusted_tool_results")
    @classmethod
    def validate_tool_results(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not isinstance(value, str) or len(value.encode("utf-8")) > 16_384 for value in values):
            raise ValueError("untrusted_tool_result_invalid")
        return values
