from typing import Literal

from deerflow_deep_research.domain.lifecycle import FrozenContract


class TargetedEvidenceRequest(FrozenContract):
    generation: int


class TargetedEvidenceResult(FrozenContract):
    route: Literal["next"] = "next"


CONTRACTS = (TargetedEvidenceRequest, TargetedEvidenceResult)
