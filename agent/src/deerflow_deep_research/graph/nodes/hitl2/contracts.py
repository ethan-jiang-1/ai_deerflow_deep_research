from deerflow_deep_research.domain.lifecycle import FrozenContract, Hitl2Decision


class Hitl2Request(FrozenContract):
    generation: int


class Hitl2Result(FrozenContract):
    route: Hitl2Decision


CONTRACTS = (Hitl2Request, Hitl2Result)
