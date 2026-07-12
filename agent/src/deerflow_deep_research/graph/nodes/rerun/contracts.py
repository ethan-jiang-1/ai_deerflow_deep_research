from typing import Literal

from deerflow_deep_research.domain.lifecycle import FrozenContract


class RerunRequest(FrozenContract):
    generation: int


class RerunResult(FrozenContract):
    route: Literal["next", "exhausted"]


CONTRACTS = (RerunRequest, RerunResult)
