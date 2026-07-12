from deerflow_deep_research.domain.lifecycle import FrozenContract, ReadinessVerdict


class ReadinessRequest(FrozenContract):
    generation: int


class ReadinessResult(FrozenContract):
    route: ReadinessVerdict


CONTRACTS = (ReadinessRequest, ReadinessResult)
