from deerflow_deep_research.domain.lifecycle import FrozenContract, GateVerdict


class Wave1Request(FrozenContract):
    generation: int


class Wave1Result(FrozenContract):
    route: GateVerdict


CONTRACTS = (Wave1Request, Wave1Result)
